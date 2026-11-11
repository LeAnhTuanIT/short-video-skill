---
name: short-video
description: Tạo video ngắn dọc 9:16 (TikTok/Reels/Shorts) cho mọi chủ đề, có giọng đọc tiếng Việt (hoặc ngôn ngữ khác) và phụ đề cứng, từ một kịch bản Claude tự viết hoặc người dùng đưa. Dùng khi người dùng muốn làm video ngắn, video TikTok/Reels/Shorts, video có sub/giọng đọc, ghép phụ đề cho file voice mp3 có sẵn (vd từ EverAI), hoặc gõ /short-video.
---

# Video ngắn có giọng đọc + phụ đề

Pipeline: kịch bản `.txt` → `make_video.py` (edge-tts đọc từng câu → ghép audio → phụ đề ASS theo thời lượng thật → nền + burn sub bằng ffmpeg) → MP4 1080x1920.

## Chế độ đã chốt: voice có sẵn → video (dùng mặc định khi người dùng gửi mp3)
Người dùng tạo giọng trên EverAI (web, tốc độ 0.85), gửi `mp3 + lời thoại`. Không gọi API, không clone giọng, không chạy model giọng (VieNeu) trên máy.
1. Tách lời thoại thành file `.txt` mỗi dòng 1 cụm ngắn (ở dấu phẩy/chấm/"..."), không dòng `#`, không `[icon]`.
2. `python3 make_video.py kichban.txt ~/Downloads/<ten>.mp4 --audio voice.mp3 --style night --no-wave --bg assets/pho-dem.mp4 --target <dài±5>`
3. In mốc từng dòng: chạy lại lệnh trên thêm `--print-timing` (không render). Kiểm tra: dòng nào dài/ngắn bất thường so với số chữ → gộp/tách rồi render lại.
4. Trích 1–2 khung hình kiểm tra phụ đề, báo đường dẫn + thời lượng. Không nghe thấy tiếng → thường do Mac xuất ra AirPods.
Hướng dẫn cho người: `HUONG-DAN.md`.

## Cài trên máy khác
Chép cả thư mục `~/.claude/skills/short-video/` sang máy mới (cùng đường dẫn), rồi chạy `bash ~/.claude/skills/short-video/setup.sh`. Hỗ trợ macOS và Ubuntu/Debian; Windows dùng qua WSL. Nền phố đêm có sẵn: `assets/pho-dem.mp4` (stock Mixkit, dùng thương mại được).

## Yêu cầu (đã cài trên máy này)
- `ffmpeg-full` (cần filter `subtitles`/libass): `brew install ffmpeg-full`
- `edge-tts`: `pipx install edge-tts` (lỗi mạng thì tự fallback giọng `say -v Linh`)

## Bước 1 — Chốt brief
Lấy từ yêu cầu; thiếu thì dùng mặc định, chỉ hỏi khi chủ đề hoàn toàn không rõ:
- **Chủ đề / góc nhìn** — chưa có góc cụ thể thì tự chọn một góc hấp dẫn, cụ thể.
- **Thời lượng** — mặc định 45–60s.
- **Giọng** — mặc định nữ `vi-VN-HoaiMyNeural`; nam `vi-VN-NamMinhNeural`. Ngôn ngữ khác: `edge-tts --list-voices | grep <mã>` (vd `en-US-AriaNeural`).
- **Nền / nhạc** — ảnh/video người dùng đưa, nếu không có thì nền gradient mặc định.

## Bước 2 — Viết kịch bản
Lưu file `.txt`, dòng đầu là tiêu đề, mỗi dòng sau là 1 câu đọc:

```
# Tiêu đề ngắn hiện ở đầu màn hình (≤ 6 từ)
Câu hook gây tò mò, ≤ 12 từ.
Câu nội dung...
Câu kết + kêu gọi hành động.
```

Quy tắc:
- Độ dài tiếng Việt: **~2.3 từ/giây** (đo thực tế: 155 từ ≈ 65s). 45–60s → 110–140 từ; 30s → ~65 từ; 15s → ~30 từ.
- Mỗi dòng 1 câu, 8–20 từ. 3 giây đầu là hook (câu hỏi / sự thật bất ngờ). Giữa: 3–5 ý cụ thể, dễ nhớ. Cuối: CTA (lưu lại, theo dõi, bình luận).
- Sự thật phải chính xác; chủ đề sức khỏe/tài chính/pháp lý: không chẩn đoán, không khuyên cụ thể kiểu chuyên gia, gợi ý hỏi chuyên gia khi cần.
- Viết số/ký hiệu bằng chữ khi đọc dễ sai ("bốn - bảy - tám" thay "4-7-8", "phần trăm" thay "%"). Tránh emoji, ký tự `{}` `\`.

Cho người dùng duyệt kịch bản trước khi render, trừ khi họ đã đưa sẵn nội dung hoặc bảo cứ làm luôn.

## Bước 3 — Render
```bash
python3 ~/.claude/skills/short-video/make_video.py kichban.txt out.mp4 \
  [--voice vi-VN-HoaiMyNeural] [--rate -5%] [--target 45-60] \
  [--bg anh_hoac_video_nen] [--music nhac_nen.mp3] [--gap 0.35] \
  [--pitch -8Hz] [--style default|night]
```
- **Giọng có sẵn:** `--audio voice.mp3` bỏ qua TTS. Kịch bản phải khớp lời đọc, mỗi dòng 1 cụm ngắn (tách ở dấu phẩy/chấm); mốc câu bắt vào chỗ ngắt hơi. In mốc bằng `--print-timing` (bình thường ~12–16 ký tự/giây), câu nào dài/ngắn bất thường thì gộp/tách dòng rồi render lại.
- **FPT.AI:** `--engine fpt --voice leminh` (nam Bắc; còn `banmai`, `thuminh` nữ Bắc, `lannhi`, `linhsan` nữ Nam, `myan` nữ Trung, `giahuy` nam Trung). Cần `export FPT_API_KEY=...` (key ở console.fpt.ai, gói Free Tier 100.000 ký tự/tháng). Không có mốc từng chữ nên karaoke chia theo độ dài chữ; `--rate` áp bằng atempo. Không bao giờ ghi key vào file skill.
- Mọi engine đều có nhịp đọc như người (lệch nhẹ tốc độ/cao độ từng câu, nghỉ lâu sau câu hỏi) + xử lý giọng ấm, nén, vang nhẹ. Viết kịch bản theo văn nói, dùng "..." và dấu chấm giữa câu để tạo chỗ ngắt hơi.
- Giọng nam Bắc trầm, trưởng thành (edge): `--voice vi-VN-NamMinhNeural --pitch=-8Hz --rate=-10%` (NamMinh là giọng nam vi duy nhất).
- `--style night --no-wave` + kịch bản không có dòng `#`, không tag `[icon]` → chỉ còn nền + phụ đề.
- `--style night` (kiểu reel "phố đêm"): tiêu đề in hoa giãn chữ màu teal + gạch chân, icon neon nét mảnh, phụ đề in hoa karaoke từng chữ (mốc thời gian thật từ edge-tts), sóng âm dạng vạch. Đặt `[icon]` đầu câu để đổi icon từ câu đó: `sun hourglass gift heart leaf book star eye`. Nền nên là video phố đêm thật: stock miễn phí ở Mixkit (`https://mixkit.co/free-stock-video/night-city-street/`, link `assets.mixkit.co/videos/<id>/<id>-1080.mp4`), ghép vài clip, crop dọc, `setpts=1.4*PTS` cho chậm.
- `--style ui` (video hướng dẫn công nghệ): nền tối có lưới, thanh series (tiêu đề `#`) + ô bước 1..n, cửa sổ app mô phỏng, terminal gõ phím, khung phụ đề tô cam `*từ khóa*`. Tag đầu câu: `[step:Tên bước]` (sang bước mới), `[card:Tiêu đề|mục 1|mục 2]` (cửa sổ, giữ đến cảnh sau), `[term:lệnh]`. Câu đọc phím tắt viết bằng chữ ("Command, Shift, ba"), còn trong card ghi "Command + Shift + 3". Mẫu: giọng `vi-VN-NamMinhNeural --pitch=-4Hz --rate=+15% --gap 0.25`.
- Không có `--bg` → nền gradient xanh tím tối chuyển động chậm (hợp chủ đề nhẹ nhàng; chủ đề sôi động nên xin ảnh/video nền). Ảnh → hiệu ứng zoom chậm. Video → tự lặp.
- `--music` được hạ còn 12% âm lượng, fade cuối.
- Script in thời lượng và cảnh báo nếu ngoài `--target` → thêm/bớt câu hoặc chỉnh `--rate` rồi render lại.

## Bước 4 — Kiểm tra
Trích 1 khung hình xem sub có vỡ dấu/tràn lề không:
`ffmpeg -v error -y -ss 5 -i out.mp4 -frames:v 1 frame.jpg` rồi Read `frame.jpg`. Báo người dùng đường dẫn tuyệt đối của video và thời lượng.

Mẫu kịch bản: `example-sleep.txt` trong thư mục skill.
