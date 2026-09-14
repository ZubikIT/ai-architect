#!/usr/bin/env python3
"""Рендер записи asciinema (.cast v2) в mp4 — без внешних бинарников.

    python cast2mp4.py demo.cast demo.mp4 [--fps 10] [--idle 1.0] [--scale 1]

Зачем свой рендерер: agg и ffmpeg ставятся системно, а тулчейн проекта — pip-only
(pyte + Pillow + imageio-ffmpeg, бинарь ffmpeg приезжает колесом). Длинные паузы
(загрузка весов модели) обрезаются до --idle секунд: демонстрация, а не хронометр.
"""
import argparse, json, sys
import pyte
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
PALETTE = {
    "black": (40, 42, 54), "red": (255, 85, 85), "green": (80, 250, 123),
    "brown": (241, 250, 140), "yellow": (241, 250, 140), "blue": (98, 114, 164),
    "magenta": (255, 121, 198), "cyan": (139, 233, 253), "white": (248, 248, 242),
    "brightblack": (98, 114, 164), "brightred": (255, 110, 110),
    "brightgreen": (120, 255, 150), "brightyellow": (255, 255, 170),
    "brightblue": (130, 150, 200), "brightmagenta": (255, 150, 220),
    "brightcyan": (160, 245, 255), "brightwhite": (255, 255, 255),
}
BG = (30, 31, 40)
FG = (230, 230, 238)


# pyte теряет остаток строки после emoji с вариационным селектором (U+FE0F):
# строка «⚠️ … отменён документом …» — ключевая в демонстрации, поэтому emoji
# заменяются на моноширинные эквиваленты до подачи в терминал.
EMOJI = {"\u26a0\ufe0f": "[!]", "\u26a0": "[!]", "\u2705": "[ok]", "\u274c": "[x]"}


def sanitize(data):
    for k, v in EMOJI.items():
        data = data.replace(k, v)
    return data.replace("\ufe0f", "")


def colour(name, default):
    if name in ("default", None):
        return default
    if name in PALETTE:
        return PALETTE[name]
    try:                                   # pyte отдаёт hex без решётки
        return tuple(int(name[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cast"); ap.add_argument("out")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--idle", type=float, default=1.0, help="потолок паузы, с")
    ap.add_argument("--size", type=int, default=16, help="кегль шрифта")
    ap.add_argument("--tail", type=float, default=2.0, help="стоп-кадр в конце, с")
    a = ap.parse_args()

    with open(a.cast, encoding="utf-8") as f:
        header = json.loads(f.readline())
        events = [json.loads(l) for l in f if l.strip()]
    events = [[t, k, sanitize(d)] if k == "o" else [t, k, d] for t, k, d in events]
    cols, rows = header.get("width", 80), header.get("height", 24)

    # время с обрезанными паузами
    timeline, prev, shift = [], 0.0, 0.0
    for t, kind, data in events:
        gap = t - prev
        if gap > a.idle:
            shift += gap - a.idle
        timeline.append((t - shift, kind, data))
        prev = t
    total = (timeline[-1][0] if timeline else 0.0) + a.tail

    font = ImageFont.truetype(FONT, a.size)
    font_b = ImageFont.truetype(FONT_BOLD, a.size)
    cw = round(font.getlength("M"))
    asc, desc = font.getmetrics()
    ch = asc + desc + 2
    pad = cw
    W = (cols * cw + 2 * pad + 1) // 2 * 2
    H = (rows * ch + 2 * pad + 1) // 2 * 2

    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)

    def render():
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        for y in range(rows):
            line = screen.buffer[y]
            x = 0
            while x < cols:
                c = line[x]
                run, style = [], (c.fg, c.bg, c.bold, c.reverse)
                while x < cols:
                    c2 = line[x]
                    if (c2.fg, c2.bg, c2.bold, c2.reverse) != style:
                        break
                    run.append(c2.data or " ")
                    x += 1
                text = "".join(run)
                fg = colour(style[0], FG); bg = colour(style[1], BG)
                if style[3]:
                    fg, bg = bg, fg
                x0 = pad + (x - len(run)) * cw
                y0 = pad + y * ch
                if bg != BG:
                    d.rectangle([x0, y0, x0 + len(run) * cw, y0 + ch], fill=bg)
                if text.strip():
                    d.text((x0, y0), text, font=font_b if style[2] else font, fill=fg)
        return img

    writer = imageio_ffmpeg.write_frames(a.out, (W, H), fps=a.fps, quality=8,
                                         macro_block_size=1, ffmpeg_log_level="error")
    writer.send(None)
    idx, frame_no, dirty, cache = 0, 0, True, None
    while frame_no / a.fps <= total:
        now = frame_no / a.fps
        while idx < len(timeline) and timeline[idx][0] <= now:
            _, kind, data = timeline[idx]
            if kind == "o":
                stream.feed(data)
                dirty = True
            idx += 1
        if dirty or cache is None:
            cache = render().tobytes()
            dirty = False
        writer.send(cache)
        frame_no += 1
    writer.close()
    print(f"{a.out}: {W}×{H}, {frame_no} кадров, {frame_no / a.fps:.1f} с")


if __name__ == "__main__":
    sys.exit(main())
