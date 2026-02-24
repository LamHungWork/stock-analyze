Technical Requirements: VN30 Technical Analysis Tool (Python)
1. Tổng quan hệ thống
Xây dựng công cụ Python chạy cục bộ (Local) để phân tích kỹ thuật rổ chỉ số VN30 vào cuối mỗi phiên giao dịch. Hệ thống sử dụng Fibonacci và SMA để dự đoán xu hướng ngắn hạn (T+5 đến T+10).

2. Thông số kỹ thuật & Thư viện sử dụng
Ngôn ngữ: Python 3.9+

Dữ liệu: Sử dụng thư viện vnstock hoặc yfinance để lấy dữ liệu chứng khoán Việt Nam.

Thư viện phân tích: pandas, pandas_ta (hoặc talib), numpy.

Lưu trữ: Hệ thống file (Folders/Markdown/CSV).

3. Quy trình xử lý dữ liệu (Logic Phân tích)
Với mỗi mã trong VN30, Agent cần thực hiện:

A. Chỉ báo kỹ thuật (Technical Indicators)
SMA 20: Tính đường trung bình động 20 phiên.

Price vs SMA: Xác định vị thế giá so với đường SMA20 (Nằm trên hay dưới).

Volume vs SMA20_Volume: So sánh khối lượng phiên hiện tại với trung bình 20 phiên.

Fibonacci Retreatment: * Tự động xác định Đỉnh (Swing High) và Đáy (Swing Low) gần nhất trong 3-6 tháng.

Tính toán các ngưỡng: 0.236, 0.382, 0.5, 0.618, 0.786.

B. Logic dự đoán (Algorithm)
Xu hướng Tăng (Bullish): Giá nằm trên SMA20 + Volume đột biến (>1.2 lần trung bình) + Giá vừa bật lại từ hỗ trợ Fibonacci (thường là 0.5 hoặc 0.618).

Xu hướng Giảm (Bearish): Giá thủng SMA20 + Giá chạm kháng cự Fibonacci và quay đầu.

Tỷ lệ thành công: Tính toán dựa trên khoảng cách từ giá hiện tại đến mục tiêu (Target) và cắt lỗ (Stoploss).

4. Cấu trúc lưu trữ (File System)
Hệ thống phải tự động tạo cấu trúc thư mục như sau:

reports/

SUMMARY_REPORT.csv (File tổng hợp)

VIC/

2023-10-25.md

2023-10-26.md

VNM/

2023-10-25.md

... (các mã khác trong VN30)

5. Chi tiết đầu ra (Output Requirements)
A. File Report chi tiết mã ([Tên_Mã]/[Ngày].md)
Nội dung file phải bao gồm:

Thông tin chung: Mã CP, Giá đóng cửa, % Thay đổi.

Phân tích SMA: Trạng thái giá so với SMA20, tín hiệu Volume.

Phân tích Fibonacci: Ngưỡng hỗ trợ/kháng cự gần nhất.

Dự đoán:

Xu hướng: (Tăng/Giảm/Đi ngang)

Giá dự báo (Target): [Giá]

Cắt lỗ (Stoploss): [Giá]

Tỷ lệ thành công: [%]

Lý do: Giải thích ngắn gọn bằng text dựa trên logic SMA và Fibo.

B. File Report tổng hợp (SUMMARY_REPORT.csv)
Cập nhật mỗi khi chạy tool:
| Ngày | Mã | Giá Hiện Tại | Dự đoán | Target | Tỷ lệ thành công | Kết quả thực tế |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2023-10-25 | ACB | 22.5 | Tăng | 24.0 | 75% | (Để trống để cập nhật sau) |

6. Tính năng kiểm chứng (Backtest/Tracking)
Công cụ cần có hàm kiểm tra: Khi chạy tool vào ngày hôm sau, nó sẽ mở file SUMMARY_REPORT.csv, kiểm tra các dự đoán cũ. Nếu giá chạm Target hoặc Stoploss thì ghi nhận vào cột "Kết quả thực tế" là Đúng hoặc Sai.