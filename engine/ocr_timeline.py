#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_timeline.py - cross-platform (Windows/Linux) replacement for auto_extract_timeline.swift.

Same command line and same JSON output as the Swift/Apple Vision tool:
    python ocr_timeline.py <videoPath> <outJsonPath> [yMin] [yMax] [startSec] [endSec]

Frames are decoded by FFmpeg (4 per second, like the Swift tool) and read with
RapidOCR (PaddleOCR Chinese models on ONNX Runtime). Only the subtitle band is
OCR'd, and frames whose band did not change are not OCR'd again.
"""
import json
import os
import subprocess
import sys

import numpy as np

STEP = 0.25            # seconds between scanned frames (same as Swift tool)
MIN_SCORE = 0.5        # drop low-confidence OCR lines
SAME_TEXT_CHANGE = 0.12  # share of subtitle pixels that may change before the band is OCR'd again


def log(msg):
    print(msg, flush=True)


def probe(video):
    """Return (width, height, duration) as FFmpeg will output the frames (rotation applied)."""
    out = subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration',
        '-of', 'json', video], text=True, encoding='utf-8')
    info = json.loads(out)
    s = info['streams'][0]
    w, h = int(s['width']), int(s['height'])
    rot = 0
    try:
        rot = int(float(s.get('tags', {}).get('rotate', 0)))
    except (TypeError, ValueError):
        pass
    for sd in s.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = int(float(sd['rotation']))
    if abs(rot) % 180 == 90:
        w, h = h, w
    try:
        dur = float(info.get('format', {}).get('duration', 0))
    except (TypeError, ValueError):
        dur = 0.0
    return w, h, dur


def grab_frame(video, t, w, h):
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-nostdin', '-ss', f'{t:.3f}', '-i', video,
         '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        stdout=subprocess.PIPE, check=False).stdout
    if len(raw) < w * h * 3:
        return None
    return np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3)


def load_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        sys.stderr.write('RapidOCR is not installed. Run: pip install rapidocr_onnxruntime\n')
        sys.exit(2)
    # Subtitle strips are thin: detect at their own size (the default upscales them to 736px),
    # skip the rotation classifier, and share CPU threads fairly between parallel workers.
    threads = int(os.environ.get('TTSKH_OCR_THREADS', '0')) or max(1, (os.cpu_count() or 4) // 2)
    gpu = gpu_available()
    log(f'OCR device: {"GPU (DirectML)" if gpu else "CPU"}')
    return RapidOCR(det_limit_side_len=640, det_limit_type='max', use_cls=False, intra_op_num_threads=threads,
                    det_use_dml=gpu, rec_use_dml=gpu)


def gpu_available():
    """Windows GPU OCR through DirectML (any DirectX 12 GPU: NVIDIA, AMD, Intel).
    Needs the onnxruntime-directml package; TTSKH_OCR_DEVICE=cpu turns it off."""
    if os.environ.get('TTSKH_OCR_DEVICE', 'auto').lower() == 'cpu' or sys.platform != 'win32':
        return False
    try:
        import onnxruntime
        return 'DmlExecutionProvider' in onnxruntime.get_available_providers()
    except Exception:
        return False


def ocr_lines(engine, img, subtitles_only=True):
    """Return [(top_y, height, text)] for an RGB numpy image.
    subtitles_only keeps horizontally centred lines of about the main line's height,
    dropping signs, labels and other small scene text."""
    # RapidOCR expects BGR like OpenCV.
    result, _ = engine(np.ascontiguousarray(img[:, :, ::-1]))
    w = img.shape[1]
    lines = []
    for box, text, score in result or []:
        text = (text or '').strip()
        if not text or float(score) < MIN_SCORE:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        lines.append((min(ys), max(ys) - min(ys), text, (min(xs) + max(xs)) / 2))
    if subtitles_only and lines:
        tallest = max(l[1] for l in lines)
        lines = [l for l in lines if abs(l[3] - w / 2) < w * 0.15 and l[1] >= tallest * 0.6]
    return [l[:3] for l in lines]


def detect_band(engine, video, w, h, dur):
    log('Auto-detecting subtitle vertical band across test frames...')
    found = []
    top_half = int(h * 0.5)
    for fraction in [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]:
        frame = grab_frame(video, dur * fraction, w, h)
        if frame is None:
            continue
        for top, box_h, _text in ocr_lines(engine, frame[top_half:], subtitles_only=False):
            y = top + top_half
            if h * 0.55 < y < h * 0.92 and h * 0.02 <= box_h <= h * 0.10:
                found.append(y)
    if not found:
        log('Warning: Could not auto-detect subtitle band. Using default lower third.')
        return h * 0.68, h * 0.88
    found.sort()
    median = found[len(found) // 2]
    y_min = max(h * 0.55, median - h * 0.06)
    y_max = min(h * 0.95, median + h * 0.10)
    log(f'Auto-detected subtitle band: {y_min:.1f} .. {y_max:.1f} (median: {median:.1f}, frameH: {h})')
    return y_min, y_max


def write_progress(out_json, done, total):
    """Frames scanned so far, read by the review studio's progress bar."""
    try:
        with open(out_json + '.progress', 'w', encoding='utf-8') as f:
            f.write(f'{done} {total}')
    except OSError:
        pass


def text_mask(band):
    """Bright pixels (white or yellow subtitle fill), at half resolution, in the central 70%."""
    w = band.shape[1]
    small = band[::2, int(w * 0.15):int(w * 0.85):2].astype(np.uint16)
    luma = (small[:, :, 0] * 77 + small[:, :, 1] * 150 + small[:, :, 2] * 29) >> 8
    return luma > 200


def same_text_pixels(mask, prev):
    """True when the subtitle pixels did not change, so the previous OCR result still holds.
    Moving backgrounds do not matter; a new or different line changes the bright pixels a lot."""
    union = int(np.count_nonzero(mask | prev))
    if union < 40:          # nothing bright in either frame: still no subtitle
        return True
    return np.count_nonzero(mask ^ prev) / union < SAME_TEXT_CHANGE


def clean(s):
    for ch in (' ', '，', '。', '！', '？'):
        s = s.replace(ch, '')
    return s


def merge_blips(cues, start_t, max_t):
    """A one-frame cue that is a misread of the line right next to it (a fade-in/out frame
    read as e.g. half the line) becomes part of that line instead of a separate cue.
    Real short lines, and cues cut by the scan start/end, are kept."""
    from difflib import SequenceMatcher
    cues = list(cues)
    i = 0
    while i < len(cues):
        text, s, e = cues[i]
        at_edge = s <= start_t + 1e-6 or e >= max_t - 1e-6
        if e - s <= STEP + 1e-6 and not at_edge:
            best, best_ratio = None, 0.0
            for j in (i - 1, i + 1):
                if 0 <= j < len(cues) and abs((cues[j][1] if j > i else cues[j][2]) - (e if j > i else s)) < 1e-6:
                    a, b = clean(text), clean(cues[j][0])
                    ratio = 1.0 if a and a in b else SequenceMatcher(None, a, b).ratio()
                    if ratio > best_ratio:
                        best, best_ratio = j, ratio
            if best is not None and best_ratio >= 0.6:
                t2, s2, e2 = cues[best]
                cues[best] = (t2, min(s, s2), max(e, e2))
                del cues[i]
                continue
        i += 1
    return cues


def main(argv):
    if len(argv) < 3:
        log('Usage: python ocr_timeline.py <videoPath> <outJsonPath> [yMin] [yMax] [startSec] [endSec]')
        return 1
    video, out_json = argv[1], argv[2]
    y_min = float(argv[3]) if len(argv) >= 4 else 0.0
    y_max = float(argv[4]) if len(argv) >= 5 else 0.0
    start_t = float(argv[5]) if len(argv) >= 6 else 0.0

    w, h, dur = probe(video)
    max_t = float(argv[6]) if len(argv) >= 7 else (dur if dur > 0 else 300.0)
    engine = load_engine()

    if y_min == 0.0 or y_max == 0.0:
        y_min, y_max = detect_band(engine, video, w, h, dur)
    else:
        log(f'Using specified subtitle band: {y_min:.1f} .. {y_max:.1f}')

    # A text line "belongs" to the band when its top edge is inside [yMin, yMax]
    # (same rule as the Swift tool), so crop one line height below yMax to keep whole lines,
    # but no further: that would also OCR e.g. an English line under the Chinese one.
    crop_top = max(0, min(h - 2, int(y_min)))
    crop_bottom = max(crop_top + 2, min(h, int(y_max + h * 0.05)))
    band_h = crop_bottom - crop_top

    log(f'Scanning video frames {start_t:.1f}s -> {max_t:.1f}s (step: {STEP:.2f}s)...')
    span = max(0.0, max_t - start_t)
    cmd = ['ffmpeg', '-v', 'error', '-nostdin', '-ss', f'{start_t:.3f}', '-t', f'{span:.3f}', '-i', video,
           '-vf', f'fps={1 / STEP:g},crop={w}:{band_h}:0:{crop_top}',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    frame_bytes = w * band_h * 3
    total_frames = max(1, int(span / STEP))
    raw_frames = []
    prev_band, prev_text = None, ''
    ocr_calls = 0
    k = 0
    try:
        while True:
            t = round(start_t + k * STEP, 3)
            if t >= max_t:
                break
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            band = np.frombuffer(buf, np.uint8).reshape(band_h, w, 3)
            mask = text_mask(band)
            if prev_band is not None and same_text_pixels(mask, prev_band):
                text = prev_text
            else:
                try:
                    lines = ocr_lines(engine, band)
                except Exception as exc:  # mirror Swift: OCR engine failure is fatal
                    sys.stderr.write(f'OCR failed: {exc}\n')
                    return 2
                ocr_calls += 1
                inside = sorted((top, txt) for top, _bh, txt in lines if y_min <= top + crop_top <= y_max)
                text = ''.join(txt for _top, txt in inside).strip()
                prev_band, prev_text = mask, text
            raw_frames.append((t, text))
            if int(t * 4) % 100 == 0:
                log(f'Progress: {t:.1f}s / {max_t:.1f}s')
            if k % 20 == 0:
                write_progress(out_json, k, total_frames)
            k += 1
    finally:
        proc.stdout.close()
        proc.wait()

    # Group contiguous identical frames (same rules as the Swift tool)
    grouped = []
    cur_text, cur_start, cur_end = '', 0.0, 0.0
    for t, text in raw_frames:
        if not text:
            if cur_text:
                grouped.append((cur_text, cur_start, min(cur_end + STEP, max_t)))
                cur_text = ''
        elif not cur_text:
            cur_text, cur_start, cur_end = text, t, t
        elif clean(cur_text) == clean(text):
            if len(text) > len(cur_text):
                cur_text = text
            cur_end = t
        else:
            grouped.append((cur_text, cur_start, min(cur_end + STEP, max_t)))
            cur_text, cur_start, cur_end = text, t, t
    if cur_text:
        grouped.append((cur_text, cur_start, min(cur_end + STEP, max_t)))

    write_progress(out_json, total_frames, total_frames)
    cues = merge_blips([s for s in grouped if s[2] - s[1] > 0], start_t, max_t)
    log(f'\nDetected {len(cues)} visual subtitle cues! ({len(raw_frames)} frames, {ocr_calls} OCR calls)')
    output = [{'id': i + 1, 'start': s, 'end': e, 'duration': e - s, 'chinese': txt}
              for i, (txt, s, e) in enumerate(cues)]
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f'Saved to {out_json}')

    # Report the detected band in the padded 1080x1920 portrait render canvas.
    scale = min(1080.0 / w, 1920.0 / h)
    pad = (1920.0 - h * scale) / 2.0
    top = max(0, int((pad + y_min * scale - 20) / 2) * 2)
    bottom = min(1920, int((pad + y_max * scale + 60) / 2) * 2)
    with open(out_json + '.band.json', 'w', encoding='utf-8') as f:
        json.dump({'y': top, 'height': max(2, bottom - top)}, f)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
