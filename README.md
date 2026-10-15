# THIẾT KẾ VÀ CHẾ TẠO THIẾT BỊ IOT TRẢ LỜI CÂU HỎI TRẮC NGHIỆM DÀNH CHO HỌC SINH, SINH VIÊN

Hệ thống thiết bị trả lời trắc nghiệm sử dụng ESP32, bàn phím ma trận và màn hình OLED. Học sinh, sinh viên nhập mã số, chọn đáp án A–D và gửi kết quả qua Wi-Fi đến máy chủ. Giáo viên quản lý lớp học, bộ câu hỏi và theo dõi kết quả trên giao diện web tiếng Việt.

## Chức năng

- Nhập mã số học sinh, sinh viên trên thiết bị.
- Hiển thị trạng thái, số câu hỏi và đáp án trên OLED.
- Gửi đáp án qua HTTP, đồng bộ phiên kiểm tra và trạng thái mở/khóa trả lời.
- Quản lý lớp, danh sách sinh viên, bộ câu hỏi và phiên kiểm tra.
- Trình chiếu câu hỏi, công bố đáp án và thống kê lựa chọn.
- Xem điểm, tỷ lệ trả lời đúng; xuất báo cáo CSV và Excel.

## Công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Vi điều khiển | ESP32, ESP-IDF, C |
| Nhập liệu | Bàn phím ma trận 4×4 |
| Hiển thị | OLED I²C 128×32 |
| Máy chủ | Python, Flask |
| Cơ sở dữ liệu | MySQL/MariaDB |
| Giao diện | HTML, CSS, JavaScript |

## Cấu trúc mã nguồn

- `main/`: firmware ESP32, Wi-Fi, HTTP, bàn phím và OLED.
- `server/`: máy chủ Flask, giao diện, báo cáo và kiểm thử.
- `server/database/`: các tập lệnh nâng cấp cơ sở dữ liệu.
- `tools/`: công cụ hỗ trợ build, nạp firmware, cấu hình IP và chạy máy chủ.
- `sdkconfig`, `CMakeLists.txt`, `dependencies.lock`: cấu hình dự án ESP-IDF.
- `IOT.zip`: bản mã nguồn gọn để tải xuống.

## Kết nối phần cứng theo mã nguồn

| Thiết bị | Chân ESP32 |
| --- | --- |
| Hàng bàn phím R1, R2, R3, R4 | GPIO14, GPIO27, GPIO26, GPIO25 |
| Cột bàn phím C1, C2, C3, C4 | GPIO33, GPIO32, GPIO21, GPIO22 |
| OLED SDA | GPIO18 |
| OLED SCL | GPIO19 |

OLED dùng địa chỉ I²C `0x3C`. Kiểm tra nguồn cấp, GND và sơ đồ thiết bị thực tế trước khi đấu nối.

## Chạy máy chủ

```bash
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
export DB_HOST=localhost
export DB_USER=esp32app
export DB_PASSWORD='MAT_KHAU_CUA_BAN'
export DB_NAME=esp32_db
python server/server.py
```

Mở `http://localhost:5000`. Máy chủ cần cơ sở dữ liệu phù hợp trước khi sử dụng. Xem [hướng dẫn máy chủ](server/README.md) về các phiên bản và migration. `migration_v2.sql` chỉ chạy một lần trên cấu trúc cũ; `migration_v3.sql` bổ sung chức năng trình chiếu. Sao lưu cơ sở dữ liệu trước khi nâng cấp.

Các bản sao lưu cơ sở dữ liệu chứa mã sinh viên và lịch sử trả lời đã được loại khỏi bản công khai. Kho chỉ giữ các tập lệnh migration; cần chuẩn bị cơ sở dữ liệu riêng theo hướng dẫn máy chủ.

## Cấu hình và nạp ESP32

1. Cài đặt và kích hoạt môi trường ESP-IDF tương thích với dự án.
2. Sửa `YOUR_WIFI_SSID`, `YOUR_WIFI_PASSWORD` trong `main/main.c`.
3. Cập nhật địa chỉ IP máy chủ trong `main/http_client.c` để ESP32 truy cập được qua mạng nội bộ.
4. Tại thư mục gốc dự án, chạy:

```bash
idf.py set-target esp32
idf.py build
idf.py -p PORT flash monitor
```

Thay `PORT` bằng cổng nối tiếp thực tế. ESP32 và máy chủ phải truy cập được nhau; mở cổng 5000 trên máy chủ nếu cần.

## Cách sử dụng

1. Chạy máy chủ và mở trang quản lý.
2. Tạo lớp, thêm sinh viên, tạo bộ câu hỏi và bắt đầu phiên kiểm tra.
3. Nhập mã số trên thiết bị, nhấn `#` để xác nhận.
4. Chọn đáp án A–D và thao tác xác nhận theo thông báo OLED.
5. Giáo viên chuyển câu, công bố đáp án, kết thúc phiên và xuất kết quả.

## Nội dung bản công khai

Mã nguồn được lấy từ `IOT(1).zip`. Đã bỏ thư mục build, các môi trường Python và thư viện có thể cài lại; mật khẩu Wi-Fi/cơ sở dữ liệu được thay bằng cấu hình mẫu. Các thay đổi này cũng áp dụng cho `IOT.zip`.

Kho này chứa mã nguồn; chưa xác minh build ESP-IDF, kết nối MariaDB hay hoạt động trên phần cứng trong môi trường đăng tải.
