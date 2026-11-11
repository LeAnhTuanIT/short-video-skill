#!/usr/bin/env python3
"""Kịch bản .txt -> video dọc 1080x1920 có giọng đọc + phụ đề cứng.

Định dạng kịch bản: dòng đầu "# Tiêu đề", mỗi dòng sau là 1 câu đọc.
Câu có thể mở đầu bằng [icon] (vd "[heart] Câu...") để đổi icon ở --style night.
Dùng: make_video.py script.txt out.mp4 [--voice vi-VN-HoaiMyNeural] [--music bg.mp3] [--bg bg.mp4|jpg]
      [--style default|night]
"""
import argparse, asyncio, json, math, os, random, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request

try:
    import edge_tts as ET
except ImportError:
    # edge-tts cài bằng pipx -> chạy lại script bằng python của venv đó để dùng API (có mốc thời gian từng chữ)
    # pipx cũ: ~/.local/pipx, pipx >= 1.3: ~/.local/share/pipx
    _venv = next((p for p in map(os.path.expanduser, ["~/.local/pipx/venvs/edge-tts",
                                                       "~/.local/share/pipx/venvs/edge-tts"])
                  if os.path.exists(p)), "")
    _py = os.path.join(_venv, "bin", "python")
    # so sánh sys.prefix, không dùng realpath: python của venv là symlink tới chính python hệ thống
    if os.path.exists(_py) and os.path.realpath(sys.prefix) != os.path.realpath(_venv):
        os.execv(_py, [_py, *sys.argv])
    ET = None

W, H, FPS = 1080, 1920, 30
VIENEU_PY = os.path.expanduser("~/.local/share/vieneu/bin/python")


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path])
    return float(out)


def edge_tts(text, out, voice, rate, pitch="+0Hz"):
    """Đọc 1 câu ra mp3, trả về [giây bắt đầu của từng chữ] hoặc None nếu lỗi."""
    if ET is None:
        return None

    async def go():
        c = ET.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
        starts = []
        with open(out, "wb") as f:
            async for ch in c.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    starts.append(ch["offset"] / 1e7)
        return starts

    # ponytail: server edge-tts chập chờn (có lúc chỉ ~15% thành công), retry dày; vẫn lỗi thì cân nhắc TTS khác
    for _ in range(60):
        try:
            starts = asyncio.run(go())
            if os.path.getsize(out):
                return starts
        except Exception:
            pass
        time.sleep(1)
    return None


FPT_VOICE_FROM_EDGE = {"vi-VN-NamMinhNeural": "leminh", "vi-VN-HoaiMyNeural": "banmai"}


def fpt_tts(lines, outs, voice, key):
    """FPT.AI TTS v5: gửi hết các câu trước, rồi chờ từng link async có file (FPT sinh file sau 5 giây–2 phút)."""
    links = []
    for n, text in enumerate(lines):
        req = urllib.request.Request("https://api.fpt.ai/hmi/tts/v5", data=text.encode("utf-8"), method="POST",
                                     headers={"api_key": key, "voice": voice, "Cache-Control": "no-cache"})
        # Free Tier giới hạn lượt gọi -> 429: chờ lâu dần rồi gửi lại (tối đa ~4 phút mỗi câu)
        for wait in (5, 10, 20, 30, 45, 60, 60, 0):
            try:
                r = json.load(urllib.request.urlopen(req, timeout=30))
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or not wait:
                    sys.exit(f"FPT.AI lỗi HTTP {e.code} ở câu {n + 1}: {e.read()[:200]!r}")
                print(f"FPT.AI giới hạn lượt gọi (429), chờ {wait}s rồi gửi lại câu {n + 1}...", flush=True)
                time.sleep(wait)
        if r.get("error") != 0:
            sys.exit(f"FPT.AI lỗi: {r.get('message')}")
        links.append(r["async"])
        time.sleep(1.5)  # gửi thưa cho khỏi chạm giới hạn
    deadline = time.time() + 300
    for link, out in zip(links, outs):
        while True:
            try:
                data = urllib.request.urlopen(link, timeout=30).read()
                if data:
                    open(out, "wb").write(data)
                    break
            except urllib.error.HTTPError:
                pass  # file chưa sẵn sàng
            if time.time() > deadline:
                sys.exit(f"FPT.AI: quá 5 phút vẫn chưa có file âm thanh ({link})")
            time.sleep(2)


def say_tts(text, out):
    aiff = out + ".aiff"
    run("say", "-v", "Linh", "-o", aiff, text)
    run("ffmpeg", "-y", "-i", aiff, out)


def chunks(text, max_words=7):
    """Cắt câu dài thành các đoạn phụ đề ngắn, ưu tiên cắt ở dấu phẩy."""
    out = []
    for part in re.split(r"(?<=[,;:])\s+", text):
        words = part.split()
        n = max(1, -(-len(words) // max_words))
        size = -(-len(words) // n)
        out += [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    return out


def ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def human_prosody(lines, rate, pitch, gap):
    """Nhịp đọc như người thật: mỗi câu lệch nhẹ tốc độ/cao độ, câu mở và câu kết chậm hơn,
    nghỉ lâu hơn sau câu hỏi/câu cảm. Seed cố định -> render lại ra cùng kết quả."""
    rng = random.Random(42)
    r0, p0 = int(rate.rstrip("%")), int(pitch.rstrip("Hz"))
    out = []
    for i, line in enumerate(lines):
        r = r0 + rng.choice([-4, -2, 0, 2, 3]) - (4 if i in (0, len(lines) - 1) else 0)
        p = p0 + rng.choice([-2, -1, 0, 1, 2])
        end = line.rstrip()
        g = gap + (0.45 if end.endswith("?") else 0.25 if end.endswith(("!", "...", "…")) else 0)
        g += rng.uniform(-0.05, 0.12)
        out.append((f"{r:+d}%", f"{p:+d}Hz", round(g, 2)))
    return out


# Giọng TTS khô và "phẳng": ấm phần trầm, bớt chói, nén nhẹ, chút vang phòng, chuẩn âm lượng
VOICE_FX = ("highpass=f=70,equalizer=f=180:t=q:w=1:g=2.5,equalizer=f=3500:t=q:w=1.5:g=-1.5,"
            "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150,"
            "aecho=0.85:0.5:35|60:0.12|0.07,loudnorm=I=-16:TP=-1.5")


def build_ass(lines, durs, title, gaps):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial,78,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,520,1
Style: Title,Arial,72,&H0080E6FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,8,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev, t = [], 0.0
    total = sum(durs) + sum(gaps)
    if title:
        ev.append(f"Dialogue: 0,{ts(0)},{ts(total)},Title,,0,0,0,,{title}")
    for line, d, gap in zip(lines, durs, gaps):
        parts = chunks(line)
        weights = [len(p) for p in parts]
        for p, w in zip(parts, weights):
            seg = d * w / sum(weights)
            ev.append(f"Dialogue: 0,{ts(t)},{ts(t + seg)},Sub,,0,0,0,,{{\\fad(120,120)}}{p}")
            t += seg
        t += gap
    return head + "\n".join(ev) + "\n", total


# ---- style night: phố đêm tối, tên kênh giãn chữ, icon neon, karaoke từng chữ, sóng âm ----

TEAL, TEAL_LIGHT, RED = "&HD2C85A&", "&HF0F0B4&", "&H4646E6&"  # màu ASS là BGR


def circle(cx, cy, r):
    k = r * 0.5523
    return (f"m {cx} {cy - r} b {cx + k} {cy - r} {cx + r} {cy - k} {cx + r} {cy} "
            f"b {cx + r} {cy + k} {cx + k} {cy + r} {cx} {cy + r} b {cx - k} {cy + r} {cx - r} {cy + k} {cx - r} {cy} "
            f"b {cx - r} {cy - k} {cx - k} {cy - r} {cx} {cy - r}")


def star(cx, cy, R, r):
    pts = [(cx + (R if i % 2 == 0 else r) * math.sin(i * math.pi / 5),
            cy - (R if i % 2 == 0 else r) * math.cos(i * math.pi / 5)) for i in range(10)]
    return "m " + " l ".join(f"{x:.0f} {y:.0f}" for x, y in pts) + f" l {pts[0][0]:.0f} {pts[0][1]:.0f}"


HEART = ("m 80 140 b 20 100 10 60 40 40 b 60 28 76 40 80 55 "
         "b 84 40 100 28 120 40 b 150 60 140 100 80 140")
# Mỗi icon trong khung 160x160: (nét xanh, nét nhấn đỏ)
ICONS = {
    "sun": ("m 15 120 l 145 120 m 80 35 l 80 52 m 35 55 l 47 67 m 125 55 l 113 67 m 20 95 l 38 95 m 140 95 l 122 95",
            circle(80, 110, 28)),
    "hourglass": ("m 45 20 l 115 20 l 80 80 l 115 140 l 45 140 l 80 80 l 45 20", "m 80 112 l 98 134 l 62 134 l 80 112"),
    "gift": ("m 35 75 l 125 75 l 125 140 l 35 140 l 35 75 m 28 55 l 132 55 l 132 75 l 28 75 l 28 55",
             "m 80 55 l 80 140 m 80 55 b 55 20 35 45 80 55 m 80 55 b 105 20 125 45 80 55"),
    "heart": (HEART, "m 80 100 b 66 90 62 78 70 73 b 75 70 79 73 80 78 b 81 73 85 70 90 73 b 98 78 94 90 80 100"),
    "leaf": ("m 30 135 b 25 70 70 30 140 22 b 138 90 100 135 30 135", "m 30 135 l 105 58"),
    "book": ("m 80 50 b 60 35 30 35 18 42 l 18 132 b 30 126 60 126 80 140 b 100 126 130 126 142 132 l 142 42 "
             "b 130 35 100 35 80 50 m 80 50 l 80 140", "m 112 20 l 112 62 l 120 54 l 128 62 l 128 20"),
    "star": (star(80, 82, 62, 26), circle(80, 82, 7)),
    "eye": ("m 15 80 b 50 30 110 30 145 80 b 110 130 50 130 15 80", circle(80, 80, 18)),
}


def icon_events(name, start, end):
    teal, red = ICONS[name]
    base = f"\\an7\\pos({W // 2 - 120},400)\\fscx150\\fscy150\\fad(400,250)\\1a&HFF&\\p1"
    out = []
    for path, col in ((teal, TEAL), (red, RED)):
        out.append(f"Dialogue: 0,{ts(start)},{ts(end)},Icon,,0,0,0,,{{{base}\\3c{col}\\bord7\\blur12\\3a&H70&}}{path}")
        out.append(f"Dialogue: 1,{ts(start)},{ts(end)},Icon,,0,0,0,,{{{base}\\3c{col}\\bord2.5\\blur0.8}}{path}")
    return out


def build_ass_night(lines, icons, durs, starts, title, gaps):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kara,Avenir Next,72,&H00FFFFFF,&HB4FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,5,0,1,0,3,5,150,150,0,1
Style: Brand,Avenir Next,34,&H00D2C85A,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,14,0,1,0,0,8,0,0,0,1
Style: Icon,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    total = sum(durs) + sum(gaps)
    ev = []
    if title:
        ev.append(f"Dialogue: 0,{ts(0)},{ts(total)},Brand,,0,0,0,,{{\\pos({W // 2},230)}}{title.upper()}")
        ev.append(f"Dialogue: 0,{ts(0)},{ts(total)},Brand,,0,0,0,,{{\\an8\\pos({W // 2},292)\\p1}}m 0 0 l 100 0 l 100 5 l 0 5")

    t, icon_t, icon = 0.0, 0.0, None
    for line, ic, d, st, gap in zip(lines, icons, durs, starts, gaps):
        if ic:
            if icon:
                ev += icon_events(icon, icon_t, t)
            icon, icon_t = ic, t
        words = line.split()
        if not st or len(st) != len(words):
            # không có mốc thời gian khớp -> chia theo độ dài chữ
            lens = [len(w) + 1 for w in words]
            st = [d * sum(lens[:i]) / sum(lens) for i in range(len(words))]
        n = max(1, -(-len(words) // 11))
        size = -(-len(words) // n)
        for i in range(0, len(words), size):
            j = min(i + size, len(words))
            s = t if i == 0 else t + st[i]
            e = t + d + gap if j == len(words) else t + st[j]
            kara = f"{{\\k{round((t + st[i] - s) * 100)}}}"
            for k in range(i, j):
                nxt = st[k + 1] if k + 1 < j else e - t
                kara += f"{{\\k{max(1, round((nxt - st[k]) * 100))}}}{words[k].upper()} "
            ev.append(f"Dialogue: 2,{ts(s)},{ts(e)},Kara,,0,0,0,,{{\\pos({W // 2},930)\\fad(150,100)}}{kara.strip()}")
        t += d + gap
    if icon:
        ev += icon_events(icon, icon_t, total)
    return head + "\n".join(ev) + "\n", total


# ---- style ui: video hướng dẫn công nghệ: thanh series + ô bước, cửa sổ app mô phỏng, terminal gõ phím,
# khung phụ đề tô cam từ khóa. Tag đầu câu: [step:Tên bước] [card:Tiêu đề|mục 1|mục 2] [term:lệnh]; *từ khóa* ----

ORANGE, UI_BG, UI_ROW, UI_LINE, UI_GREY, UI_GREEN = \
    "&H1E64F0&", "&H1E1A17&", "&H2A2420&", "&H3A3430&", "&H9A8F88&", "&H6CD94A&"


def rrect(w, h, r):
    k = r * 0.45
    return (f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} l {w} {h - r} b {w} {h - k} {w - k} {h} {w - r} {h} "
            f"l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} l 0 {r} b 0 {k} {k} 0 {r} 0")


def ui_box(layer, s, e, x, y, w, h, r, fill, line=UI_LINE, extra=""):
    return (f"Dialogue: {layer},{ts(s)},{ts(e)},UI,,0,0,0,,"
            f"{{\\an7\\pos({x},{y})\\1c{fill}\\3c{line}\\bord1.5{extra}\\p1}}{rrect(w, h, r)}")


def ui_text(layer, s, e, x, y, txt, size, col="&HFFFFFF&", an=7, extra=""):
    return f"Dialogue: {layer},{ts(s)},{ts(e)},UI,,0,0,0,,{{\\an{an}\\pos({x},{y})\\fs{size}\\1c{col}{extra}}}{txt}"


def highlight(words):
    """*từ khóa* -> tô cam (có thể trải nhiều chữ: *App Center*)."""
    out, on = [], False
    for w in words:
        on = on or w.startswith("*")
        clean = w.replace("*", "")
        out.append(f"{{\\1c{ORANGE}}}{clean}{{\\1c&HFFFFFF&}}" if on else clean)
        if w.rstrip(".,!?:;…").endswith("*"):
            on = False
    return out


def build_ass_ui(lines, tags, durs, starts, title, gaps):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: UI,Avenir Next,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Term,Menlo,30,&H00E6E6E6,&HFF000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Sub,Avenir Next,50,&H00FFFFFF,&H000000FF,&H00191C1E,&H00000000,-1,0,0,0,100,100,0,0,3,24,0,5,150,150,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    total = sum(durs) + sum(gaps)
    t_line = [sum(durs[:i]) + sum(gaps[:i]) for i in range(len(lines))]
    steps = [(i, t[5:]) for i, tg in enumerate(tags) for t in tg if t.startswith("step:")]
    scenes = [(i, t) for i, tg in enumerate(tags) for t in tg if t.startswith(("card:", "term:"))]
    ev = []

    # thanh series trên cùng + ô bước
    ev.append(ui_box(0, 0, total, 60, 180, 960, 84, 22, UI_BG))
    label = f"● {title.upper()}"
    bw = 44 + 17 * len(label)
    ev.append(ui_box(1, 0, total, 84, 202, bw, 40, 12, "&H1A140F&", ORANGE))
    ev.append(ui_text(2, 0, total, 84 + bw // 2, 222, label, 22, ORANGE, an=5, extra="\\fsp2"))
    n = len(steps)
    bounds = [0.0] + [t_line[i] for i, _ in steps] + [total]
    for k in range(n + 1):  # k = số bước đã bắt đầu
        s, e = bounds[k], bounds[k + 1]
        if e <= s:
            continue
        if k:
            ev.append(ui_text(2, s, e, 84 + bw + 22, 222, steps[k - 1][1], 30, an=4, extra="\\fad(200,0)"))
        for j in range(n):
            x = 1020 - 24 - (n - j) * 52 - (n - 1 - j) * 12
            cur, done = j == k - 1, j < k - 1
            fill, line, num = (ORANGE, ORANGE, "&HFFFFFF&") if cur else \
                (UI_ROW, ORANGE, ORANGE) if done else (UI_ROW, UI_LINE, UI_GREY)
            if cur:
                ev.append(ui_box(1, s, e, x, 196, 52, 52, 14, ORANGE, ORANGE, "\\bord5\\blur9\\1a&H80&\\3a&H90&"))
            ev.append(ui_box(2, s, e, x, 196, 52, 52, 14, fill, line))
            ev.append(ui_text(3, s, e, x + 26, 222, str(j + 1), 26, num, an=5))

    # cửa sổ app / terminal mô phỏng, giữ đến cảnh kế tiếp
    for k, (i, tag) in enumerate(scenes):
        s = t_line[i]
        e = t_line[scenes[k + 1][0]] if k + 1 < len(scenes) else total
        kind, body = tag.split(":", 1)
        parts = body.split("|")
        fad = "\\fad(250,150)"
        if kind == "card":
            items = parts[1:]
            h = 96 + len(items) * 78
            ev.append(ui_box(4, s, e, 90, 330, 900, h, 24, UI_BG, "&H2A3A64&", fad + "\\shad6\\4c&H000000&\\4a&H60&"))
            ev.append(ui_text(5, s, e, 126, 366, parts[0], 30, an=4, extra=fad))
            for c, cx in enumerate((878, 912, 946)):
                ev.append(ui_box(5, s, e, cx - 11, 355, 22, 22, 11, "&H3A4AD8&" if c == 2 else UI_LINE,
                                 UI_LINE, fad))
            for r, item in enumerate(items):
                si, y = s + 0.35 + 0.3 * r, 410 + r * 78
                ev.append(ui_box(5, si, e, 120, y, 840, 62, 16, UI_ROW, UI_LINE, "\\fad(200,150)"))
                ev.append(ui_text(6, si, e, 150, y + 31, " ".join(highlight(item.split())), 30, an=4, extra="\\fad(200,150)"))
        else:  # term
            cmd = parts[0]
            ev.append(ui_box(4, s, e, 90, 330, 900, 250, 24, "&H120F0D&", "&H2A3A64&", fad))
            ev.append(ui_text(5, s, e, 126, 366, "Terminal", 28, UI_GREY, an=4, extra=fad))
            ev.append(ui_box(5, s, e, 935, 355, 22, 22, 11, UI_GREEN, UI_GREEN, fad))
            typing = min(2.0, 0.05 * len(cmd))
            per = max(1, round(typing * 100 / max(1, len(cmd))))
            typed = "".join(f"{{\\k{per}}}{ch}" for ch in cmd)
            ev.append(f"Dialogue: 6,{ts(s)},{ts(e)},Term,,0,0,0,,{{\\an7\\pos(126,420)\\1c{UI_GREEN}}}$ "
                      f"{{\\1c&HE6E6E6&\\k40}}{typed}")
            ev.append(ui_text(6, s + 0.4 + typing + 0.6, e, 126, 490, "✓ Xong!", 30, UI_GREEN,
                              extra="\\fad(200,0)"))

    # khung phụ đề, cắt ≤ 8 chữ, bám mốc thời gian thật nếu có
    for line, d, st, gap, t in zip(lines, durs, starts, gaps, t_line):
        words = line.split()
        colored = highlight(words)  # tô cả câu trước rồi mới cắt đoạn, để từ khóa nhiều chữ không bị mất màu
        if not st or len(st) != len(words):
            lens = [len(w) + 1 for w in words]
            st = [d * sum(lens[:i]) / sum(lens) for i in range(len(words))]
        m = max(1, -(-len(words) // 8))
        size = -(-len(words) // m)
        for i in range(0, len(words), size):
            j = min(i + size, len(words))
            s = t if i == 0 else t + st[i]
            e = t + d + gap if j == len(words) else t + st[j]
            ev.append(f"Dialogue: 7,{ts(s)},{ts(e)},Sub,,0,0,0,,{{\\pos({W // 2},1180)\\fad(120,80)}}"
                      f"{' '.join(colored[i:j])}")
    return head + "\n".join(ev) + "\n", total



def align_lines(lines, audio):
    """Mốc câu cho giọng có sẵn: ước theo tỉ lệ số ký tự, rồi bắt vào khoảng lặng gần nhất (±1.5s).
    Trả về (durs, gaps) với gap=0, mỗi câu kéo dài tới mốc câu sau."""
    log = subprocess.run(["ffmpeg", "-i", audio, "-af", "silencedetect=noise=-35dB:d=0.2", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    sil = list(zip(map(float, re.findall(r"silence_start: ([\d.]+)", log)),
                   map(float, re.findall(r"silence_end: ([\d.]+)", log))))
    total = duration(audio)
    t0 = sil[0][1] if sil and sil[0][0] < 0.05 else 0.0  # bỏ lặng đầu file
    t1 = sil[-1][0] if sil and sil[-1][1] > total - 0.05 else total
    mids = [(s + e) / 2 for s, e in sil if t0 < s and e < t1]
    lens = [len(l) for l in lines]
    bounds, prev = [0.0], t0
    # ponytail: ước tỉ lệ + bắt khoảng lặng; lệch nhiều thì dùng whisper word timestamps
    for k in range(1, len(lines)):
        guess = t0 + (t1 - t0) * sum(lens[:k]) / sum(lens)
        cand = [m for m in mids if m > prev + 0.3 and abs(m - guess) < 1.5]
        prev = min(cand, key=lambda m: abs(m - guess)) if cand else max(guess, prev + 0.3)
        bounds.append(prev)
    bounds.append(total)
    return [b - a for a, b in zip(bounds, bounds[1:])], [0.0] * len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--voice", default="vi-VN-HoaiMyNeural")
    ap.add_argument("--audio", help="file giọng đọc có sẵn (bỏ qua TTS); kịch bản phải khớp lời đọc, "
                                    "mỗi dòng 1 cụm ngắn để phụ đề bắt đúng chỗ ngắt hơi")
    ap.add_argument("--rate", default="-5%", help="tốc độ đọc edge-tts, vd -10%%, +0%%")
    ap.add_argument("--pitch", default="+0Hz", help="cao độ edge-tts, vd -8Hz cho giọng trầm hơn")
    ap.add_argument("--music", help="nhạc nền (tự lặp, nhỏ tiếng)")
    ap.add_argument("--bg", help="ảnh hoặc video nền; bỏ trống = gradient đêm chuyển động")
    ap.add_argument("--gap", type=float, default=0.35, help="khoảng lặng giữa các câu (giây)")
    ap.add_argument("--target", default="45-60", help="khoảng thời lượng mong muốn (giây), vd 15-30")
    ap.add_argument("--style", default="default", choices=["default", "night", "ui"],
                    help="night: tên kênh + icon neon + karaoke + sóng âm; ui: video hướng dẫn công nghệ "
                         "(ô bước, cửa sổ app, terminal, tô màu *từ khóa*)")
    ap.add_argument("--engine", default="edge", choices=["edge", "fpt"],
                    help="vieneu: giọng người thật hơn, chạy cục bộ; --voice là tên giọng VieNeu (vd \"Minh Đức\"). "
                         "fpt: FPT.AI (cần biến môi trường FPT_API_KEY); --voice leminh|banmai|thuminh|lannhi|...")
    ap.add_argument("--no-wave", action="store_true", help="night: bỏ sóng âm, chỉ giữ nền + phụ đề")
    ap.add_argument("--print-timing", action="store_true",
                    help="cùng --audio: in mốc từng dòng (bắt đầu, độ dài, ký tự/giây) rồi thoát, không render")
    a = ap.parse_args()
    if a.engine == "fpt" and not os.environ.get("FPT_API_KEY"):
        sys.exit("Thiếu FPT_API_KEY: lấy key ở console.fpt.ai (bật Text to Speech), rồi "
                 "`export FPT_API_KEY=...` (vd thêm vào ~/.zshrc)")
    if a.engine == "vieneu" and not os.path.exists(VIENEU_PY):
        sys.exit(f"Chưa cài VieNeu: uv venv {os.path.dirname(os.path.dirname(VIENEU_PY))} --python 3.12 "
                 "&& VIRTUAL_ENV=... uv pip install vieneu")

    raw = [l.strip() for l in open(a.script, encoding="utf-8") if l.strip()]
    title = raw[0][1:].strip() if raw and raw[0].startswith("#") else ""
    lines = raw[1:] if title else raw
    if not lines:
        sys.exit("Kịch bản rỗng")
    # Tag đầu câu: [icon] (night) hoặc [step:..] [card:..] [term:..] (ui); *từ khóa* chỉ để tô màu, bỏ khi đọc
    tags, ui_lines = [], []
    for l in lines:
        m = re.match(r"((?:\[[^\]]+\]\s*)*)(.*)", l)
        tags.append(re.findall(r"\[([^\]]+)\]", m.group(1)))
        ui_lines.append(m.group(2))
    lines = [l.replace("*", "") for l in ui_lines]
    icons = [next((t for t in tg if t in ICONS), None) for tg in tags]
    bad = {t for tg in tags for t in tg if ":" not in t and t not in ICONS}
    if bad:
        sys.exit(f"Icon không có: {bad}. Có sẵn: {sorted(ICONS)}")

    tmp = tempfile.mkdtemp(prefix="shortvid_")
    if a.audio:
        # Giọng có sẵn: không TTS, chia mốc từng câu theo chỗ ngắt hơi trong file
        voice = a.audio
        durs, gaps = align_lines(lines, voice)
        if a.print_timing:
            t = 0.0
            for l, d in zip(lines, durs):
                print(f"{t:5.1f}s {d:4.1f}s {len(l) / d:5.1f}c/s  {l}")
                t += d
            return
        starts = [None] * len(lines)
    else:
        durs, concat = [], []
        prosody = human_prosody(lines, a.rate, a.pitch, a.gap)
        gaps = [g for _, _, g in prosody]
        tempo = [1.0] * len(lines)
        if a.engine == "vieneu":
            # VieNeu chạy cục bộ trong venv riêng; không có mốc từng chữ -> karaoke chia theo độ dài chữ.
            # Tốc độ (--rate + dao động từng câu) áp bằng atempo; --pitch bỏ qua vì đổi cao độ làm méo giọng thật.
            vdir = os.path.join(tmp, "vieneu")
            os.makedirs(vdir)
            subprocess.run([VIENEU_PY, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vieneu_tts.py"),
                            vdir, a.voice], input=json.dumps(lines), text=True, check=True)
            mp3s = [os.path.join(vdir, f"{i}.wav") for i in range(len(lines))]
            starts = [None] * len(lines)
            tempo = [1 + int(r.rstrip("%")) / 100 for r, _, _ in prosody]
        elif a.engine == "fpt":
            # FPT.AI không có mốc từng chữ; tốc độ áp bằng atempo như VieNeu. Giọng edge tự đổi sang giọng FPT tương ứng.
            voice = FPT_VOICE_FROM_EDGE.get(a.voice, a.voice)
            mp3s = [os.path.join(tmp, f"{i}.mp3") for i in range(len(lines))]
            fpt_tts(lines, mp3s, voice, os.environ["FPT_API_KEY"])
            starts = [None] * len(lines)
            tempo = [1 + int(r.rstrip("%")) / 100 for r, _, _ in prosody]
        else:
            mp3s = [os.path.join(tmp, f"{i}.mp3") for i in range(len(lines))]
            # Một giọng cho cả video: câu nào edge-tts lỗi thì đọc lại TẤT CẢ bằng say, không trộn giọng
            starts = [edge_tts(l, m, a.voice, r, p) for l, m, (r, p, _) in zip(lines, mp3s, prosody)]
            if any(s is None for s in starts):
                print("CẢNH BÁO: edge-tts lỗi, cả video dùng giọng macOS Linh")
                starts = [None] * len(lines)
                for l, m in zip(lines, mp3s):
                    say_tts(l, m)
        for i, (mp3, gap) in enumerate(zip(mp3s, gaps)):
            wav, silence = os.path.join(tmp, f"{i}.wav"), os.path.join(tmp, f"gap{i}.wav")
            run("ffmpeg", "-y", "-i", mp3, "-af", f"atempo={tempo[i]:.3f}", "-ar", "24000", "-ac", "1", wav)
            run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(gap), silence)
            durs.append(duration(wav))
            concat += [f"file '{wav}'", f"file '{silence}'"]
        lst = os.path.join(tmp, "list.txt")
        open(lst, "w").write("\n".join(concat))
        raw_voice, voice = os.path.join(tmp, "raw.wav"), os.path.join(tmp, "voice.wav")
        run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, raw_voice)
        run("ffmpeg", "-y", "-i", raw_voice, "-af", VOICE_FX, "-ar", "48000", voice)

    night = a.style == "night"
    if night:
        ass_text, total = build_ass_night(lines, icons, durs, starts, title, gaps)
    elif a.style == "ui":
        ass_text, total = build_ass_ui(ui_lines, tags, durs, starts, title, gaps)
    else:
        ass_text, total = build_ass(lines, durs, title, gaps)
    ass = os.path.join(tmp, "subs.ass")
    open(ass, "w", encoding="utf-8").write(ass_text)
    total += 0.8  # đuôi lặng cho kết thúc êm

    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    dark = "eq=brightness=-0.14:saturation=0.75,vignette=PI/4" if night else "eq=brightness=-0.08"
    if not a.bg and a.style == "ui":
        # tối ấm nâu -> xanh đen + lưới mờ
        bg_in = ["-f", "lavfi", "-i",
                 f"gradients=s={W}x{H}:r={FPS}:speed=0.003:c0=0x2a1712:c1=0x1c1420:c2=0x101a22:nb_colors=3"]
        vf = "drawgrid=w=60:h=60:t=1:c=white@0.035,vignette"
    elif not a.bg:
        bg_in = ["-f", "lavfi", "-i",
                 f"gradients=s={W}x{H}:r={FPS}:speed=0.004:c0=0x0b1026:c1=0x1b1f4a:c2=0x2a1a4a:c3=0x0a2a43:nb_colors=4"]
        vf = "noise=alls=6:allf=t,vignette"
    elif a.bg.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        bg_in = ["-loop", "1", "-i", a.bg]
        # Ken Burns zoom chậm
        vf = f"{fit},zoompan=z='min(zoom+0.0004,1.15)':d=1:s={W}x{H}:fps={FPS},{dark}"
    else:
        bg_in = ["-stream_loop", "-1", "-i", a.bg]
        vf = f"{fit},fps={FPS},{dark}"
    post = f"subtitles='{ass}',fade=in:d=0.6,fade=out:st={total - 0.8}:d=0.8,format=yuv420p"

    graph = f"[0:v]{vf}[bg];"
    if night and not a.no_wave:
        graph += (f"[1:a]showwaves=s=48x100:mode=cline:rate={FPS}:colors=0xE6E6E6:scale=sqrt:draw=full,"
                  f"scale=480x100:flags=neighbor,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(mod(X,10),5),alpha(X,Y),0)'[w];[bg][w]overlay=(W-w)/2:1330[bgw];[bgw]{post}[v]")
    else:
        graph += f"[bg]{post}[v]"
    cmd = ["ffmpeg", "-y", *bg_in, "-i", voice]
    if a.music:
        cmd += ["-stream_loop", "-1", "-i", a.music]
        graph += ";[1:a]pan=stereo|c0=c0|c1=c0[vo]"
        graph += (f";[2:a]volume=0.12,afade=out:st={total - 1.5}:d=1.5[m];"
                  "[vo][m]amix=inputs=2:duration=first:normalize=0,apad[a]")
    else:
        graph += ";[1:a]pan=stereo|c0=c0|c1=c0,apad[a]"  # mono -> stereo không hạ 3dB
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
    cmd += ["-t", f"{total:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", a.out]
    run(*cmd)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"OK {a.out} — {total:.1f}s")
    lo, hi = map(float, a.target.split("-"))
    if not lo <= total <= hi + 2:
        print(f"CẢNH BÁO: thời lượng {total:.1f}s ngoài khoảng {a.target}s, hãy thêm/bớt câu.")


if __name__ == "__main__":
    main()
