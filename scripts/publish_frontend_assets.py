"""Upload the built website and fallback page without CDK's Lambda custom resource."""

import argparse
import json
import mimetypes
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.shared.tool_registry import registry
SITES = {
    "primary": ("ap-southeast-1", "SatiBotWebPrimary", "Primary"),
    "error": ("us-east-1", "SatiBotWebErrorPage", "ErrorPage"),
}


def stack_outputs(session, region, stack_name):
    response = session.client("cloudformation", region_name=region).describe_stacks(
        StackName=stack_name
    )
    stack = response["Stacks"][0]
    if stack["StackStatus"] not in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
        raise RuntimeError(f"Stack {stack_name} is not ready: {stack['StackStatus']}")
    return {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}


def site_files(site):
    if site == "primary":
        source = ROOT / "dist" / "frontend"
        if not (source / "index.html").is_file():
            raise FileNotFoundError("Build dist/frontend before publishing the primary site")
        return [(path, path.relative_to(source).as_posix()) for path in source.rglob("*") if path.is_file()]

    source = ROOT / "frontend" / "error.html"
    if not source.is_file():
        raise FileNotFoundError(f"Missing fallback page: {source}")
    return [(source, "index.html")]


def preview_auth_config(session, frontend_origin, auth_stack="AuthStack"):
    outputs = stack_outputs(session, "ap-southeast-1", auth_stack)
    if not all(outputs.get(key) for key in ("HostedDomain", "UserPoolId", "UserPoolClientId")):
        raise RuntimeError("Cognito stack is missing browser client outputs")
    callback = frontend_origin + "/"
    client = session.client("cognito-idp", region_name="ap-southeast-1").describe_user_pool_client(
        UserPoolId=outputs["UserPoolId"], ClientId=outputs["UserPoolClientId"]
    )["UserPoolClient"]
    if callback not in client.get("CallbackURLs", []) or callback not in client.get("LogoutURLs", []):
        raise RuntimeError("Frontend URL must be registered in Cognito callback and logout URLs")
    if (not client.get("AllowedOAuthFlowsUserPoolClient") or
            "code" not in client.get("AllowedOAuthFlows", []) or
            "openid" not in client.get("AllowedOAuthScopes", []) or client.get("ClientSecret")):
        raise RuntimeError("Cognito browser client requires code flow, openid and no client secret")
    return {
        "domain": outputs["HostedDomain"],
        "client_id": outputs["UserPoolClientId"],
        "redirect_uri": callback,
    }


def publish_site(session, site, appsync_graphql_url="", *, frontend_origin="", auth_stack="AuthStack"):
    region, stack_name, output_prefix = SITES[site]
    files = site_files(site)
    outputs = stack_outputs(session, region, stack_name)
    bucket = outputs[f"{output_prefix}BucketName"]
    primary = outputs if site == "primary" else stack_outputs(session, "ap-southeast-1", "SatiBotWebPrimary")
    distribution_id = primary["PrimaryDistributionId"]
    s3_client = session.client("s3", region_name=region)

    if site == "primary":
        distribution = session.client("cloudfront", region_name="us-east-1").get_distribution_config(
            Id=distribution_id
        )["DistributionConfig"]
        behaviors = distribution.get("CacheBehaviors", {}).get("Items", [])
        api_enabled = any(item.get("PathPattern") == "api/*" for item in behaviors)
        if not api_enabled:
            raise RuntimeError("CloudFront api/* routing is required before publishing the demo")
        if not appsync_graphql_url:
            sync = stack_outputs(session, "ap-southeast-1", "SatiBotAppSync")
            appsync_graphql_url = sync["AppSyncGraphqlUrl"]
        if appsync_graphql_url:
            endpoint = urlsplit(appsync_graphql_url)
            if (endpoint.scheme != "https" or endpoint.path != "/graphql" or
                    endpoint.query or endpoint.fragment or not re.fullmatch(
                        r"[a-z0-9-]+\.appsync-api\.ap-southeast-1\.amazonaws\.com", endpoint.hostname or "")):
                raise ValueError("AppSync URL must be the primary-region AWS GraphQL endpoint")
        config = {"api_enabled": api_enabled, "tools_loaded": len(registry())}
        if appsync_graphql_url:
            config["appsync"] = {"graphql_url": appsync_graphql_url}
        origin = frontend_origin or f"https://{outputs['PrimaryDistributionDomain']}"
        if not re.fullmatch(r"https://[a-z0-9.-]+", origin):
            raise ValueError("Frontend origin must be an HTTPS hostname without a path")
        hostname = urlsplit(origin).hostname
        allowed_hosts = [outputs["PrimaryDistributionDomain"], *distribution.get("Aliases", {}).get("Items", [])]
        if hostname not in allowed_hosts:
            raise RuntimeError("Frontend hostname must belong to the primary CloudFront distribution")
        auth = preview_auth_config(session, origin, auth_stack)
        if not auth:
            raise RuntimeError("Cognito configuration is required before publishing the demo")
        config["auth"] = auth

    for source, key in files:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=source.read_bytes(),
            ContentType=content_type,
            CacheControl=(
                "public, max-age=31536000, immutable"
                if key.startswith("assets/")
                else "no-store"
            ),
        )

    if site == "primary":
        s3_client.put_object(
            Bucket=bucket,
            Key="site-config.json",
            Body=json.dumps(config).encode("utf-8"),
            ContentType="application/json",
            CacheControl="no-cache",
        )
        print(f"primary API routing enabled: {api_enabled}")

    invalidation = session.client("cloudfront", region_name="us-east-1").create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": f"satibot-{site}-{uuid.uuid4().hex}",
        },
    )
    print(
        f"{site}: uploaded {len(files)} files to {bucket}; "
        f"CloudFront invalidation {invalidation['Invalidation']['Id']}"
    )
    print(f"{site} uses shared URL: https://{primary['PrimaryDistributionDomain']}/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="AWS CLI profile")
    parser.add_argument("--expected-account", required=True, help="12-digit AWS account ID")
    parser.add_argument("--site", choices=(*SITES, "both"), default="both")
    parser.add_argument("--frontend-origin", default="", help="HTTPS frontend origin, for example https://satibot.id.vn")
    parser.add_argument("--auth-stack", default="AuthStack", help="Cognito stack supplying the browser pool and client")
    parser.add_argument("--appsync-graphql-url", default="", help="AppSync GraphQL HTTPS endpoint, after the API is deployed")
    args = parser.parse_args()

    if len(args.expected_account) != 12 or not args.expected_account.isascii() or not args.expected_account.isdigit():
        parser.error("--expected-account must be a 12-digit AWS account ID")
    session = boto3.Session(profile_name=args.profile, region_name="ap-southeast-1")
    actual_account = session.client("sts").get_caller_identity()["Account"]
    if actual_account != args.expected_account:
        raise RuntimeError(
            f"AWS account mismatch: expected {args.expected_account}, got {actual_account}. "
            "No files were published."
        )

    for site in ("error", "primary") if args.site == "both" else (args.site,):
        publish_site(session, site, args.appsync_graphql_url,
                     frontend_origin=args.frontend_origin, auth_stack=args.auth_stack)


if __name__ == "__main__":
    main()
