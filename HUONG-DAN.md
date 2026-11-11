# Làm video dọc: Voice EverAI + Phụ đề + Nền

Quy trình đã chốt (video mẫu: `la-ban-giay-thue-si-dien-v3.mp4`, 86,8s, 1080x1920).

**EverAI (web) → tải mp3 → gửi Claude kèm lời thoại → video.** Không dùng API, không dùng giọng clone.

Kết quả: chỉ có **nền phố đêm + phụ đề karaoke chữ in hoa** chạy theo giọng. Không tiêu đề, không icon, không sóng âm.

## 1. Tạo giọng trên EverAI

1. Vào everai.vn, dán lời thoại, chọn giọng.
2. Chỉnh tốc độ **0.85**.
3. Tải file `.mp3` về (ví dụ vào `~/Downloads`).

| Gói Basic | Theo tháng | Theo năm |
|---|---|---|
| Giá | 99.000đ/tháng | 83.000đ/tháng |
| Credits | 200.000/tháng | 2.400.000/năm |

- Giọng tiếng Việt ~**1 credit/ký tự**; mô hình turbo rẻ 50%.
- Một bài ~1.200 ký tự ≈ 1.200 credits (turbo ~600) → gói năm đủ ~2.000 video (turbo ~4.000).
- Tối đa 25.000 ký tự mỗi lần chuyển đổi, nên cả bài chỉ cần 1 lần.

## 2. Gửi cho Claude

Trong Claude Code, gửi theo mẫu:

```
'/đường/dẫn/voice.mp3'
<lời thoại>
```

Claude tự tách lời thoại thành từng cụm ngắn, ghép phụ đề theo chỗ ngắt hơi lên nền phố đêm và xuất video vào `~/Downloads`.

## 3. Tự render (không cần Claude)

Kịch bản `.txt` khớp đúng lời đọc, **mỗi dòng 1 cụm ngắn** (tách ở dấu phẩy / chấm / chỗ ngắt hơi). Không có dòng `#`, không tag `[icon]`:

```
Năm hai mươi hai tuổi,
lương bảy triệu, đặt lưng xuống giường là ngủ một mạch tới sáng...
Vậy mà ngoài ba mươi tuổi,
thu nhập đã gấp đôi, gấp ba,
```

```bash
cd ~/.claude/skills/short-video
python3 make_video.py kichban.txt ~/Downloads/video.mp4 \
  --audio "/đường/dẫn/voice.mp3" \
  --style night --no-wave --bg assets/pho-dem.mp4 --target 80-90
```

| Tham số | Ý nghĩa |
|---|---|
| `--audio` | Dùng giọng có sẵn, giữ nguyên âm lượng gốc |
| `--style night` | Phụ đề in hoa, chữ sáng dần theo giọng |
| `--no-wave` | Bỏ thanh sóng âm |
| `--bg` | Ảnh/video nền (video tự lặp, ảnh tự zoom chậm) |
| `--target` | Khoảng thời lượng mong muốn (giây), chỉ để cảnh báo |
| `--music` | (tuỳ chọn) nhạc nền, tự hạ còn 12% |

## 4. Kiểm tra

```bash
ffmpeg -v error -y -ss 30 -i ~/Downloads/video.mp4 -frames:v 1 frame.jpg
```

Mở `frame.jpg` xem phụ đề ở giây 30 có đúng câu đang đọc, chữ có dấu không lỗi.

## 5. Cách phụ đề khớp giọng

- Tìm các khoảng lặng (chỗ ngắt hơi) trong file voice.
- Ước mốc mỗi dòng theo tỉ lệ số ký tự, rồi bắt vào khoảng lặng gần nhất (±1,5s).
- Trong một dòng, chữ sáng dần theo độ dài từng chữ (ước lượng, không phải mốc thật).

**Lệch câu?** Dòng nào hiện quá lâu / quá ngắn → gộp với dòng bên cạnh hoặc tách nhỏ hơn rồi render lại.

## 6. Lỗi hay gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| Video không có tiếng | Mac đang xuất âm thanh ra **AirPods** → đeo tai nghe hoặc Control Center → Output → MacBook Speakers |
| Giọng nhỏ hơn file gốc | Đã sửa: chuyển mono → stereo không hạ âm lượng |
| Phụ đề lệch dần về cuối | Lời thoại không khớp file voice (thiếu/thừa câu) → sửa lời thoại cho đúng voice |

## 7. Làm giọng trầm hơn (tuỳ chọn)

Hạ cao độ 2 nửa cung, giữ tốc độ và chất giọng:

```bash
ffmpeg -i voice.mp3 -af "rubberband=pitch=0.8909:formant=preserved,equalizer=f=150:t=q:w=1:g=2" voice-tram.mp3
```

(1 nửa cung: `0.9439`, 3 nửa cung: `0.8409`; trầm hơn nữa dễ bị giả.)
