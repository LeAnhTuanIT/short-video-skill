# short-video — skill Claude Code làm video dọc có giọng đọc + phụ đề

Kịch bản `.txt` (hoặc file voice `.mp3` có sẵn) → video MP4 1080x1920 cho TikTok/Reels/Shorts: nền ảnh/video, phụ đề karaoke tiếng Việt burn cứng.

## Cài đặt

Hỗ trợ macOS và Ubuntu/Debian. Windows: dùng trong WSL.

### 1. Lấy skill về đúng thư mục

Skill phải nằm ở `~/.claude/skills/short-video/` để Claude Code nhận ra:

```bash
git clone https://github.com/LeAnhTuanIT/short-video-skill.git ~/.claude/skills/short-video
```

### 2. Cài phụ thuộc

```bash
bash ~/.claude/skills/short-video/setup.sh
```

Script cài:

| Gói | Dùng để |
|---|---|
| `ffmpeg-full` (macOS, qua Homebrew) / `ffmpeg` (apt) | Ghép nền, audio, burn phụ đề (cần filter `subtitles`/libass) |
| `pipx` + `edge-tts` | Giọng đọc TTS miễn phí của Microsoft (chỉ cần khi không có voice mp3) |
| `fonts-noto-core` (Linux) | Font đủ dấu tiếng Việt |

macOS cần [Homebrew](https://brew.sh) trước. Cuối script phải in `OK: ffmpeg có subtitles`.

### 3. Chạy thử

```bash
cd ~/.claude/skills/short-video
python3 make_video.py example-sleep.txt /tmp/thu.mp4
```

Ra file `/tmp/thu.mp4` là cài xong.

## Dùng

**Với Claude Code:** gõ `/short-video` kèm chủ đề, hoặc gửi đường dẫn file mp3 + lời thoại. Claude tự viết/tách kịch bản, render và kiểm tra phụ đề.

**Tự chạy với voice có sẵn** (ví dụ mp3 từ EverAI):

```bash
cd ~/.claude/skills/short-video
# 1. Kiểm tra mốc từng dòng (không render)
python3 make_video.py kichban.txt ~/Downloads/video.mp4 --audio voice.mp3 --print-timing
# 2. Render
python3 make_video.py kichban.txt ~/Downloads/video.mp4 --audio voice.mp3 \
  --style night --no-wave --bg assets/pho-dem.mp4
```

`--print-timing` in mỗi dòng kèm giây bắt đầu, độ dài, ký tự/giây. Bình thường ~12–16 ký tự/giây; dòng lệch xa thì gộp/tách dòng rồi chạy lại.

Chi tiết kịch bản, tham số và lỗi hay gặp: [HUONG-DAN.md](HUONG-DAN.md). Toàn bộ tuỳ chọn: `python3 make_video.py -h`.

## Tuỳ chọn thêm

- **FPT.AI TTS:** `--engine fpt --voice leminh`, cần `export FPT_API_KEY=...` (lấy ở console.fpt.ai). Không ghi key vào file trong repo.
- **Nền:** `assets/pho-dem.mp4` là video phố đêm stock Mixkit, dùng thương mại được.

## Lỗi hay gặp

| Hiện tượng | Xử lý |
|---|---|
| `No such filter: 'subtitles'` | ffmpeg thiếu libass → macOS: `brew install ffmpeg-full && brew link --overwrite ffmpeg-full` |
| `edge-tts` lỗi mạng | Tự chuyển sang giọng `say -v Linh` (macOS); hoặc dùng `--audio` |
| Video không có tiếng | Mac đang xuất âm ra AirPods |
| Chữ mất dấu (Linux) | Chưa có font: `sudo apt-get install fonts-noto-core` |
