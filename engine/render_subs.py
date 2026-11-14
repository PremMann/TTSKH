#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_subs.py - cross-platform (Windows/Linux) replacement for render_subs_universal.swift.

Same command line and same outputs (empty.png, cue_XXXX.png, subs_sample.txt):
    python render_subs.py <cuesJsonPath> <outPngDir> <yMin> [height] [totalDuration] [width] [height]

Khmer needs complex-script shaping. Text is drawn by FFmpeg's libass (HarfBuzz
shaping, included in standard FFmpeg builds), all cues in one FFmpeg run; Pillow
only measures/wraps lines and draws the dark backing pill.
Set TTSKH_SUB_FONT to a .ttf/.otf path to force a font.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

FILL_ASS = '&H0026EEFF'          # Cinema Yellow #FFEE26 (ASS is &HAABBGGRR)
PILL = (0, 0, 0, int(255 * 0.72))

FONT_CANDIDATES = [
    # Preferred: Khmer OS Battambang, then Kantumruy Pro, then other Khmer fonts.
    'KhmerOSbattambang.ttf', 'Khmer OS Battambang.ttf', 'KhmerOS_battambang.ttf', 'Battambang-Bold.ttf',
    'Battambang-Regular.ttf', 'KantumruyPro-Bold.ttf', 'KantumruyPro-Regular.ttf', 'KantumruyPro[wght].ttf',
    'Kantumruy-Bold.ttf', 'Kantumruy-Regular.ttf', 'KhmerUIb.ttf', 'KhmerUI.ttf', 'daunpenh.ttf',
]


def font_dirs():
    dirs = []
    if os.name == 'nt':
        dirs += [os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
                 os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')]
    else:
        home = os.path.expanduser('~')
        dirs += [os.path.join(home, 'Library', 'Fonts'), '/Library/Fonts', '/System/Library/Fonts',
                 os.path.join(home, '.fonts'), os.path.join(home, '.local', 'share', 'fonts'),
                 '/usr/share/fonts', '/usr/local/share/fonts']
    return [d for d in dirs if d and os.path.isdir(d)]


def find_font():
    forced = os.environ.get('TTSKH_SUB_FONT')
    if forced and os.path.isfile(forced):
        return forced
    index = {}
    for d in font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                index.setdefault(f.lower(), os.path.join(root, f))
    for name in FONT_CANDIDATES:
        if name.lower() in index:
            return index[name.lower()]
    return None


# Khmer characters that attach to the previous character (vowel signs, diacritics, coeng).
def _attaches(ch):
    o = ord(ch)
    return 0x17B4 <= o <= 0x17D3 or o == 0x17DD or o in (0x200C, 0x200D)


def clusters(text):
    """Split text into units that may be broken between (keeps Khmer syllables whole)."""
    out = []
    for i, ch in enumerate(text):
        if out and (_attaches(ch) or (i > 0 and text[i - 1] == '\u17D2')):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def wrap(text, font, max_w):
    """Word-wrap at spaces; break long space-less Khmer runs between syllable clusters.
    Widths are measured unshaped, which slightly overestimates Khmer (safe for wrapping)."""
    def width(s):
        return font.getlength(s) if s else 0
    lines, cur = [], ''
    for word in text.split():
        cand = (cur + ' ' + word) if cur else word
        if width(cand) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
            cur = ''
        if width(word) <= max_w:
            cur = word
            continue
        for unit in clusters(word):
            if width(cur + unit) <= max_w or not cur:
                cur += unit
            else:
                lines.append(cur)
                cur = unit
    if cur:
        lines.append(cur)
    return lines


def cue_text(cue):
    for key in ('khmer_sub', 'khmer_spoken', 'khmer'):
        s = cue.get(key)
        if isinstance(s, str):
            s = s.strip()
            if s and s not in ('-', '—', '…', '.'):
                return s
    return ''


def layout_cue(text, font_path, y_min, sub_h, width, scale):
    """Pick font size and line breaks like the Swift renderer. Returns (px_size, lines, top_y)."""
    margin = 30.0 * scale
    box_w = width - 2 * margin
    n = len(text)
    base = 24.0 if n > 75 else 28.0 if n > 50 else 32.0 if n > 35 else 36.0
    while True:
        size = max(8, int(round(base * scale)))
        font = ImageFont.truetype(font_path, size)
        lines = wrap(text, font, box_w)
        asc, desc = font.getmetrics()
        block_h = (asc + desc) * len(lines)
        if block_h <= sub_h - 16 * scale or base <= 18.0:
            break
        base -= 2.0
    top = y_min + max(0.0, (sub_h - block_h) / 2.0)
    return size, asc + desc, lines, top


def ass_escape(s):
    return s.replace('\\', '\u29f5').replace('{', '(').replace('}', ')')


def ffmpeg_path_arg(path):
    # Escape a path for use inside an FFmpeg filter argument (Windows drive colon, quotes).
    p = path.replace('\\', '/')
    return p.replace(':', '\\:').replace("'", "\\'")


def render_all(jobs, out_dir, font_path, width, height, scale):
    """jobs: [(cue_id, ass_size, lines, top)]. Writes cue_XXXX.png for each job."""
    family = ImageFont.truetype(font_path, 20).getname()[0]
    outline = max(1.0, 3.0 * scale)
    tmp = tempfile.mkdtemp(prefix='ttskh-subs-')
    try:
        def ass_file(name, primary, outline_colour):
            head = [
                '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
                'ScaledBorderAndShadow: yes', 'WrapStyle: 2', '',
                '[V4+ Styles]',
                'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, '
                'Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, '
                'MarginR, MarginV, Encoding',
                f'Style: S,{family},40,{primary},{primary},{outline_colour},&H00000000,0,0,0,0,100,100,0,0,1,{outline:.1f},0,8,0,0,0,1',
                '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
            for i, (_cid, ass_size, lines, top) in enumerate(jobs):
                text = '\\N'.join(ass_escape(l) for l in lines)
                head.append(f'Dialogue: 0,{ts(i)},{ts(i + 0.99)},S,,0,0,0,,{{\\fs{ass_size}\\pos({width // 2},{int(top)})}}{text}')
            path = os.path.join(tmp, name)
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(head) + '\n')
            return path

        ass_file('color.ass', FILL_ASS, '&H00000000')
        ass_file('mask.ass', '&H00FFFFFF', '&H00FFFFFF')
        fonts = ffmpeg_path_arg(os.path.dirname(os.path.abspath(font_path)))
        graph = (f'color=c=black:s={width}x{height}:r=1:d={len(jobs)},format=rgb24,split[a][b];'
                 f"[a]subtitles=color.ass:fontsdir='{fonts}'[c];"
                 f"[b]subtitles=mask.ass:fontsdir='{fonts}',format=gray[m];"
                 '[c][m]alphamerge,format=rgba[out]')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-nostdin', '-filter_complex', graph, '-map', '[out]',
                        '-frames:v', str(len(jobs)), '-start_number', '0', os.path.join(tmp, 'f_%05d.png')],
                       cwd=tmp, check=True)

        pad_x, pad_y = 24.0 * scale, 12.0 * scale
        for i, (cid, _s, _l, _t) in enumerate(jobs):
            text_img = Image.open(os.path.join(tmp, f'f_{i:05d}.png')).convert('RGBA')
            bbox = text_img.getchannel('A').getbbox()
            canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            if bbox:
                x0, y0, x1, y1 = bbox
                pill_w = min(width - 2 * 30.0 * scale, (x1 - x0) + 2 * pad_x)
                cx = (x0 + x1) / 2.0
                ImageDraw.Draw(canvas).rounded_rectangle(
                    [cx - pill_w / 2, y0 - pad_y, cx + pill_w / 2, y1 + pad_y], radius=14.0 * scale, fill=PILL)
            canvas.alpha_composite(text_img)
            canvas.save(os.path.join(out_dir, f'cue_{cid:04d}.png'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ts(seconds):
    cs = int(round(seconds * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def main(argv):
    if len(argv) < 4:
        print('Usage: python render_subs.py <cuesJsonPath> <outPngDir> <yMin> [height] [totalDuration] [canvasWidth] [canvasHeight]')
        return 1
    json_path, out_dir = argv[1], argv[2]
    y_min = float(argv[3])
    sub_h = float(argv[4]) if len(argv) >= 5 else 180.0
    total = float(argv[5]) if len(argv) >= 6 else 300.0
    width = int(argv[6]) if len(argv) >= 7 else 1080
    height = int(argv[7]) if len(argv) >= 8 else 1920
    scale = width / 720.0
    os.makedirs(out_dir, exist_ok=True)

    empty = os.path.join(out_dir, 'empty.png')
    if not os.path.exists(empty):
        Image.new('RGBA', (width, height), (0, 0, 0, 0)).save(empty)

    try:
        with open(json_path, encoding='utf-8') as f:
            cues = json.load(f)
        assert isinstance(cues, list)
    except Exception:
        print(f'Failed to read JSON cues at {json_path}')
        return 1

    jobs = []
    font_path = None
    if any(cue_text(c) for c in cues):
        font_path = find_font()
        if not font_path:
            print('[ERROR] No Khmer font found. Install Khmer OS Battambang or Kantumruy Pro, or set TTSKH_SUB_FONT.')
            return 1
        print(f'[*] Subtitle font: {font_path}')
        for c in cues:
            text = cue_text(c)
            if text and isinstance(c.get('id'), int):
                _px, ass_size, lines, top = layout_cue(text, font_path, y_min, sub_h, width, scale)
                jobs.append((c['id'], ass_size, lines, top))
    print(f'Rendering libass subtitles for {len(jobs)} of {len(cues)} cues (yMin: {y_min}, height: {sub_h})...')
    if jobs:
        render_all(jobs, out_dir, font_path, width, height, scale)
    print('All subtitle PNGs rendered successfully!')

    timed = []
    for c in cues:
        if not isinstance(c.get('id'), int):
            continue
        s = float(c.get('sub_start', c.get('start', 0.0)) or 0.0)
        e = float(c.get('sub_end', c.get('end', 0.0)) or 0.0)
        if e > s:
            timed.append((c['id'], s, e))
    timed.sort(key=lambda x: x[1])

    lines = ['ffconcat version 1.0']
    cur = 0.0
    for idx, s, e in timed:
        s, e = max(cur, s), min(total, e)
        if s >= total:
            break
        if s > cur + 0.01:
            lines += ["file 'empty.png'", f'duration {s - cur:.4f}']
            cur = s
        if e > cur + 0.01:
            name = f'cue_{idx:04d}.png'
            lines += [f"file '{name if os.path.exists(os.path.join(out_dir, name)) else 'empty.png'}'",
                      f'duration {e - cur:.4f}']
            cur = e
    if cur < total - 0.01:
        lines += ["file 'empty.png'", f'duration {total - cur:.4f}']
    lines.append("file 'empty.png'")
    concat = os.path.join(out_dir, 'subs_sample.txt')
    with open(concat, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    print(f'Saved ffconcat subtitle playlist to {concat}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
