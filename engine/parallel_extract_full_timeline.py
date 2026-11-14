#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parallel_extract_full_timeline.py
Runs high-speed parallel OCR timeline extraction on full-length drama video (2+ hours).
Splits video into N concurrent chunks, processes via Apple Neural Engine / Vision OCR,
and merges sorted visual subtitle segments into a master JSON timeline.
"""

import os
import sys
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_chunk(bin_path, video_path, chunk_json, y_min, y_max, start_t, end_t):
    from pathlib import Path
    stamp = Path(chunk_json + '.complete')
    def read_valid():
        cues = json.loads(Path(chunk_json).read_text(encoding='utf-8'))
        if not isinstance(cues, list):
            raise ValueError('OCR result must be an array')
        for cue in cues:
            if not start_t <= cue['start'] < cue['end'] <= end_t + .01 or not cue.get('chinese'):
                raise ValueError('OCR cue outside chunk or missing text')
        return cues
    if stamp.exists() and Path(chunk_json).exists():
        cues = read_valid()
        return start_t, end_t, len(cues), 0, cues
    base = [bin_path] if isinstance(bin_path, str) else list(bin_path)
    cmd = [*base, video_path, chunk_json, str(y_min), str(y_max), str(start_t), str(end_t)]
    t0 = time.time()
    log = Path(chunk_json + '.log')
    error = None
    for attempt in range(3):
        try:
            with log.open('a', encoding='utf-8') as handle:
                handle.write(f'Attempt {attempt + 1}\n')
                handle.flush()
                subprocess.run(cmd, stdout=handle, stderr=handle, check=True, timeout=max(120, (end_t-start_t)*10))
            cues = read_valid()
            stamp.write_text('complete')
            return start_t, end_t, len(cues), time.time()-t0, cues
        except (subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
            error = exc
    raise RuntimeError(f'OCR chunk {start_t}-{end_t} failed: {error}; see {log}')

def default_ocr_command():
    """Apple Vision binary on a Mac when compiled, otherwise the RapidOCR Python engine."""
    here = os.path.dirname(os.path.abspath(__file__))
    bin_path = os.path.join(here, 'auto_extract_timeline_bin')
    if sys.platform == 'darwin' and os.environ.get('TTSKH_ENGINE') != 'python' and os.path.exists(bin_path):
        return [bin_path]
    return [sys.executable, os.path.join(here, 'ocr_timeline.py')]


def extract_full_timeline(video_path, out_json, num_workers=6, y_min=1200, y_max=1560, ocr_command=None):
    ocr_command = list(ocr_command or default_ocr_command())
    if not os.path.exists(ocr_command[-1]):
        print(f"[!] OCR engine not found: {ocr_command[-1]}")
        sys.exit(1)

    if not 1 <= num_workers <= 12:
        raise ValueError('OCR workers must be between 1 and 12')
    if ocr_command[-1].endswith('.py'):
        # Each RapidOCR worker loads its own model; split the CPU threads between workers.
        cap = max(1, min(3, (os.cpu_count() or 2) // 4))
        if num_workers > cap:
            print(f"[*] RapidOCR: using {cap} workers instead of {num_workers} to fit CPU/RAM")
            num_workers = cap
        os.environ['TTSKH_OCR_THREADS'] = str(max(1, (os.cpu_count() or 2) // num_workers))

    # Get duration
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    total_dur = float(res.stdout.strip())
    print(f"[*] Total Video Duration: {total_dur:.1f}s ({total_dur/60:.1f} min)")
    print(f"[*] Launching {num_workers} parallel Vision OCR workers (Subtitle Y: {y_min}..{y_max})...")

    chunk_dur = total_dur / num_workers
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(out_json)), 'ocr_chunks')
    os.makedirs(temp_dir, exist_ok=True)

    tasks = []
    for i in range(num_workers):
        st = round(i * chunk_dur, 2)
        et = round(min(total_dur, (i + 1) * chunk_dur), 2)
        chunk_file = os.path.join(temp_dir, f"chunk_{i:02d}.json")
        tasks.append((ocr_command, video_path, chunk_file, y_min, y_max, st, et))

    all_cues = []
    t_start = time.time()
    # Workers only wait on OCR subprocesses, so threads are enough (and work the same on Windows).
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(run_chunk, *t) for t in tasks]
        for f in as_completed(futures):
            st, et, count, dur, cues = f.result()
            print(f"[+] Chunk {st:.0f}s - {et:.0f}s: detected {count} cues in {dur:.1f}s")
            all_cues.extend(cues)

    # Sort all cues by start time
    all_cues.sort(key=lambda x: x['start'])

    # Merge consecutive identical cues across chunk boundaries
    merged = []
    for c in all_cues:
        txt = c.get('chinese', '').strip()
        if not txt:
            continue
        if merged and merged[-1]['chinese'] == txt and abs(c['start'] - merged[-1]['end']) < .01:
            merged[-1]['end'] = c['end']
            merged[-1]['duration'] = merged[-1]['end'] - merged[-1]['start']
        else:
            merged.append(c)

    # Re-index
    for i, c in enumerate(merged):
        c['id'] = i + 1

    if not merged:
        raise ValueError('No subtitles found. Check OCR band and source before translating.')
    with open(out_json + '.pending', 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    os.replace(out_json + ".pending", out_json)
    total_time = time.time() - t_start
    print(f"\n[🎉] Complete! Extracted {len(merged)} total visual cues across {total_dur/60:.1f} min in {total_time:.1f}s ({total_dur/total_time:.1f}x realtime).")
    print(f"[+] Saved to: {out_json}")
    return out_json

if __name__ == '__main__':
    video = sys.argv[1] if len(sys.argv) > 1 else '25_yan_lu/full_source.mp4'
    out = sys.argv[2] if len(sys.argv) > 2 else '25_yan_lu/full_visual_cues_raw.json'
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    ymin = float(sys.argv[4]) if len(sys.argv) > 4 else 1200
    ymax = float(sys.argv[5]) if len(sys.argv) > 5 else 1560
    extract_full_timeline(video, out, num_workers=workers, y_min=ymin, y_max=ymax)
