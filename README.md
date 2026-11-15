# SatiBot — AWS Serverless ChatOps Agent

[![Live Demo](https://img.shields.io/badge/Live_Demo-satibot.id.vn-10B981?style=for-the-badge)](https://satibot.id.vn/)
[![Backend CI](https://img.shields.io/github/actions/workflow/status/TrinhThienQuang/SitaBot/backend-ci.yml?branch=main&label=Backend%20CI&style=for-the-badge&logo=github)](https://github.com/TrinhThienQuang/SitaBot/actions/workflows/backend-ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![AWS](https://img.shields.io/badge/AWS-Serverless_%26_CDK_v2-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)](https://aws.amazon.com/cdk/)
[![React](https://img.shields.io/badge/React-19_%2B_Vite-0EA5E9?style=for-the-badge&logo=react&logoColor=white)](https://react.dev/)

**SatiBot** ([satibot.id.vn](https://satibot.id.vn/)) là nền tảng **Serverless ChatOps** tích hợp AI Agent cho phép quản trị tài nguyên **AWS** (**S3**, **EC2**, **Lambda**, **IAM**) trực tiếp bằng ngôn ngữ tự nhiên tiếng Việt.

![Giao diện web SatiBot](Report/Report%20progress%202/satibot-web.png)

## Tính năng chính

- **Liên kết liên tài khoản qua `STS AssumeRole + ExternalId`**: Kết nối tài khoản AWS đích bằng IAM Role (`/satibot/SatiBotAccessRole`) và phiên chứng thực tạm thời, không lưu AWS password hay Access Key.
- **Xác nhận an toàn 2 bước (Human-in-the-Loop)**: Các thao tác tạo, thay đổi hoặc xóa tài nguyên đều yêu cầu xem trước và bấm **Xác nhận** trước khi thực thi.
- **Quản trị S3, EC2, Lambda & IAM**: Hỗ trợ kiểm toán bảo mật, cấu hình Lifecycle/Presigned URL (S3), bật/tắt instance (EC2), kiểm tra AST code/nâng RAM/tạo Function URL/Kill-Switch (Lambda), và kiểm tra Trust Policy/Role/Policy (IAM).
- **Bảo mật & Triển khai tự động**: Bảo vệ biên bằng CloudFront + AWS WAF + Cognito JWT, dự phòng Route 53 Origin Failover và triển khai tự động qua GitHub Actions + AWS CodePipeline + CodeDeploy Canary.

---

## Kiến trúc và cấu trúc dự án

![Sơ đồ Kiến trúc Hệ thống SatiBot](Report/Report%20progress%202/so_do_kien_truc.jpg)

### Cấu trúc thư mục

| Thư mục | Nội dung |
| --- | --- |
| [`backend/`](backend/) | Lambda handlers, dịch vụ S3/EC2/Lambda/IAM, GraphQL và mã dùng chung |
| [`frontend/`](frontend/) | Giao diện web, xác thực, hội thoại và kết nối AWS |
| [`infrastructure/`](infrastructure/) | Các AWS CDK stack |
| [`ci/`](ci/) và [`.github/workflows/`](.github/workflows/) | Cấu hình build, kiểm thử và phát hành |
| [`scripts/`](scripts/) | Đóng gói, kiểm tra và hỗ trợ triển khai |
| [`tests/`](tests/) | Kiểm thử backend, frontend và hạ tầng |
| [`Report/`](Report/) | Báo cáo và sơ đồ của nhóm |

---

## Hướng dẫn liên kết tài khoản AWS với SatiBot

Tài khoản SatiBot và tài khoản AWS được quản lý tách biệt; SatiBot sử dụng IAM Role kèm `ExternalId` để xin quyền tạm thời thay vì lưu password hay Access Key.

> [!IMPORTANT]
> IAM Role trên tài khoản AWS của bạn bắt buộc phải có path **`/satibot/`** và tên **`SatiBotAccessRole`** (`arn:aws:iam::<AWS_ACCOUNT_ID>:role/satibot/SatiBotAccessRole`) thì SatiBot mới chấp nhận xác minh.

1. **Lấy `ExternalId` và `Trust policy` trên SatiBot:**
   Đăng nhập [satibot.id.vn](https://satibot.id.vn/), bấm **Kết nối tài khoản AWS** ở thanh menu trái → bấm **Lấy ExternalId** rồi bấm **Sao chép JSON** tại khung **Trust policy**.

2. **Tạo IAM Role trên tài khoản AWS cần liên kết:**
   Tạo IAM Role với path **`/satibot/`** và tên **`SatiBotAccessRole`**, dán đoạn `Trust policy` vừa sao chép và gắn các quyền S3 / EC2 / Lambda / IAM bạn cho phép.
   *(Nếu tạo qua AWS CloudShell / AWS CLI với file `trust-policy.json`: `aws iam create-role --path /satibot/ --role-name SatiBotAccessRole --assume-role-policy-document file://trust-policy.json` và gắn policy quyền tương ứng.)*

3. **Dán Role ARN và xác minh:**
   Sao chép ARN của Role vừa tạo, dán vào mục **3. Dán Role ARN vừa tạo** trên SatiBot rồi bấm **Kiểm tra và liên kết**. Khi thành công, trạng thái góc trên phải chuyển sang **AWS: Đã kết nối**.

---

## Cài đặt và kiểm thử cục bộ

Yêu cầu: **Python 3.12**, **Node.js 22**, **AWS CDK v2**.
```bash
# Cài đặt thư viện, đóng gói artifact Lambda và chạy kiểm thử backend
python -m pip install -r requirements-dev.txt
python scripts/package_backend.py --with-dependencies
python -m pytest -q

# Cài đặt, kiểm thử và build frontend
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

## Chức năng hiện có
> [!WARNING]
> SatiBot hiện chỉ hỗ trợ **một tác vụ trong mỗi lượt yêu cầu**, chưa tự động thực hiện chuỗi nhiều thao tác có quan hệ phụ thuộc. Ví dụ, yêu cầu “tạo role, cấp quyền S3 rồi gắn vào EC2” cần được tách thành các tác vụ riêng; từng tác vụ phải nằm trong phạm vi công cụ được hỗ trợ. Các thao tác thay đổi tài nguyên cần người dùng xác nhận trước khi thực thi.
SatiBot hỗ trợ quản trị bốn nhóm tài nguyên AWS bằng ngôn ngữ tự nhiên tiếng Việt:

| Module | Chức năng hỗ trợ |
|---|---|
| **Amazon EC2** | Tạo, liệt kê và xem chi tiết instance; bật, tắt, khởi động lại và xóa instance; truy vấn CPU qua CloudWatch; kiểm tra rủi ro cấu hình Security Group. |
| **Amazon S3** | Tạo bucket private; quét và chặn public access; kiểm tra dữ liệu trước khi xóa bucket có xác nhận; cấu hình lifecycle; tạo URL tải tạm thời; thống kê dung lượng và ước tính chi phí lưu trữ. |
| **AWS IAM** | Tra cứu, tạo, cập nhật và xóa Role/Policy; quản lý trust policy, managed policy và inline policy; gắn/tháo managed policy khỏi Role; kiểm tra cấu trúc policy; preview và đối soát liên kết trước khi xóa. |
| **AWS Lambda** | Tạo, liệt kê, xem cấu hình và xóa function; đọc/cập nhật mã nguồn; invoke với payload JSON; điều chỉnh memory/timeout; tạo Function URL; cấu hình version, alias và retry; chẩn đoán cấu hình và bật/tắt giới hạn thực thi khẩn cấp. |

Ngoài ra, hệ thống cung cấp đăng nhập qua Amazon Cognito, kết nối tài khoản AWS bằng STS AssumeRole, cập nhật kết quả bất đồng bộ và tra cứu lịch sử tác vụ.

**Giới hạn phạm vi:** Module IAM chỉ quản lý Role và Policy, chưa hỗ trợ quản lý User/Group hoặc gắn Role vào EC2. Khả năng thực thi thực tế phụ thuộc vào quyền của IAM Role trong tài khoản AWS đã kết nối.



