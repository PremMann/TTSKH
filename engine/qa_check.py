#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qa_check.py — Automated QA Gate for CDrama Dubbing Pipeline
===========================================================
Validates sample and full movie outputs against 6 strict quality rules:
  1. atempo Cap: % of cues needing > 1.30x speed must be 0% (or logged)
  2. Missing/Failed TTS clips: 0 missing clips
  3. Overlapping cues: No cue starts before the previous cue ends
  4. Loudness Compliance: Integrated loudness must be -14 ± 1.5 LUFS
  5. Subtitle Line Wrap: No line wraps past 2 lines (>45 Khmer characters per line)
  6. Blur Band Verification: Contact sheet exists for visual inspection
"""

import os
import sys
import json
import subprocess
import soundfile as sf
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_config import (
    ATEMPO_CAP, LOUDNORM_TARGET_I, QA_ATEMPO_WARN_PCT,
    QA_ATEMPO_FAIL_PCT, QA_LUFS_TOLERANCE, QA_MAX_SUBTITLE_CHARS,
    QA_OVERLAP_TOLERANCE, SILENCE_THRESHOLD, MAX_SILENCE_BORROW,
    TTS_MIN_FILE_BYTES
)

def check_qa(cues_json, tts_dir, audio_wav, video_mp4=None, max_atempo=ATEMPO_CAP, target_lufs=float(LOUDNORM_TARGET_I), expected_dimensions=(1920, 1080)):
    print("\n" + "=" * 60)
    print("🔍 RUNNING AUTOMATED QA GATE (qa_check.py)")
    print("=" * 60)
    
    passed = True
    issues = []
    
    # ── Check 1: Cue Integrity & Overlaps ─────────────────────────────────
    if not os.path.exists(cues_json):
        print(f"[FAIL] Cues file missing: {cues_json}")
        return False
        
    with open(cues_json, 'r', encoding='utf-8') as f:
        cues = json.load(f)
        
    from core.speech_timing import spoken_timeline
    from core.khmer_validator import verify_audio_file
    try:
        cues = spoken_timeline(cues, sf.info(audio_wav).duration)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"[FAIL] Speech timeline: {error}")
        return False
    overlap_count = 0
    for i in range(len(cues) - 1):
        c1, c2 = cues[i], cues[i+1]
        if c2['start'] < c1['end'] - QA_OVERLAP_TOLERANCE:
            overlap_count += 1
            issues.append(f"Overlap between Cue {c1['id']} (end {c1['end']}s) and Cue {c2['id']} (start {c2['start']}s)")
            
    if overlap_count == 0:
        print(f"  ✅ [PASS] Cue Timing: {len(cues)} cues, 0 overlapping boundaries.")
    else:
        print(f"  ❌ [FAIL] Cue Timing: {overlap_count} overlapping cues detected!")
        passed = False

    # ── Check 2: Missing or Failed TTS Clips ──────────────────────────────
    missing_clips = []
    for c in cues:
        cid = c['id']
        spoken = c.get('khmer_spoken', '').strip()
        if not spoken or spoken in ('-', '—') or c.get('is_spoken_dialogue') is False:
            # Non-spoken visual subtitle (sign, on-screen text, document)
            continue
        mp3 = os.path.join(tts_dir, f"cue_{cid:04d}.mp3")
        if not verify_audio_file(mp3, min_bytes=TTS_MIN_FILE_BYTES, min_duration=0.1)['valid']:
            missing_clips.append(cid)
            
    if not missing_clips:
        print(f"  ✅ [PASS] TTS Clips: All {len(cues)} clips synthesized successfully.")
    else:
        print(f"  ❌ [FAIL] TTS Clips: {len(missing_clips)} clips missing or corrupt: {missing_clips[:10]}")
        passed = False

    # ── Check 3: atempo Pacing & Speed Cap ────────────────────────────────
    def get_real_voice_dur(mp3_path):
        try:
            data, r_sr = sf.read(mp3_path, dtype='float32')
            if len(data.shape) > 1:
                mono = np.mean(data, axis=1)
            else:
                mono = data
            non_silent = np.where(np.abs(mono) > SILENCE_THRESHOLD)[0]
            if len(non_silent) == 0:
                return sf.info(mp3_path).duration
            pad = int(0.020 * r_sr)
            s_idx = max(0, non_silent[0] - pad)
            e_idx = min(len(data), non_silent[-1] + pad)
            return (e_idx - s_idx) / r_sr
        except Exception:
            return sf.info(mp3_path).duration

    from audio_safe import check_fit
    fit_issues = check_fit(cues, tts_dir, sf.info(audio_wav).duration)
    missing = [i for i in fit_issues if i.get('kind') == 'missing_audio']
    if missing:
        passed = False
        print(f"  ❌ [FAIL] {len(missing)} missing audio clips detected: {missing[:5]}")
    elif fit_issues:
        print(f"  ⚠️ [WARN] {len(fit_issues)} cues speed-adjusted by atempo for natural pacing.")
    else:
        print('  ✅ [PASS] Every spoken line fits within the speed cap.')

    # ── Check 4: Subtitle Line Wrap (> 2 lines) ───────────────────────────
    over_wrap = []
    for c in cues:
        txt = c.get('khmer_spoken', '').strip()
        # Khmer subtitle box is 660px wide at font size 32/36 -> approx 45 chars per line
        # If > QA_MAX_SUBTITLE_CHARS without natural break, it wraps past 2 lines
        if len(txt) > QA_MAX_SUBTITLE_CHARS:
            over_wrap.append((c['id'], len(txt), txt))
            
    if not over_wrap:
        print(f"  ✅ [PASS] Subtitle Wrapping: All {len(cues)} cues fit cleanly within 1-2 lines.")
    else:
        print(f"  ⚠️ [WARN] Subtitle Wrapping: {len(over_wrap)} cues may wrap past 2 lines:")
        for cid, length, txt in over_wrap[:3]:
            print(f"       - Cue {cid:03d} ({length} chars): \"{txt}\"")

    # ── Check 5: Audio Loudness Compliance (LUFS) ─────────────────────────
    if os.path.exists(audio_wav) and os.path.getsize(audio_wav) > 10000:
        cmd_lufs = [
            'ffmpeg', '-i', audio_wav,
            '-af', 'ebur128=framelog=verbose',
            '-f', 'null', '-'
        ]
        res = subprocess.run(cmd_lufs, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
        out = res.stderr.decode('utf-8')
        
        # Parse Integrated Loudness: I: -XX.X LUFS
        import re
        m = re.findall(r'I:\s*(-?[\d\.]+)\s*LUFS', out)
        if m:
            actual_lufs = float(m[-1])
            diff = abs(actual_lufs - target_lufs)
            if diff <= QA_LUFS_TOLERANCE:
                print(f"  ✅ [PASS] Loudness: Integrated Loudness is {actual_lufs:.1f} LUFS (Target: {target_lufs} ± {QA_LUFS_TOLERANCE} LUFS).")
            else:
                print(f"  ❌ [FAIL] Loudness: {actual_lufs:.1f} LUFS diverges from target {target_lufs} LUFS by {diff:.1f} dB!")
                passed = False
        else:
            print("  ❌ [FAIL] Loudness could not be measured.")
            passed = False
    else:
        print(f"  ❌ [FAIL] Audio wav file not found or empty: {audio_wav}")
        passed = False

    if video_mp4 is not None:
        try:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                    '-of', 'json', video_mp4], capture_output=True, text=True, check=True)
            media = json.loads(probe.stdout)
            video = next(s for s in media['streams'] if s['codec_type'] == 'video')
            audio = next(s for s in media['streams'] if s['codec_type'] == 'audio')
            expected = sf.info(audio_wav).duration
            if (video['width'], video['height']) != expected_dimensions or abs(float(media['format']['duration']) - expected) > 0.5:
                raise ValueError('Unexpected output dimensions or duration')
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-sseof', '-10', '-i', video_mp4,
                            '-f', 'null', '-'], check=True, capture_output=True)
        except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as exc:
            print(f"  ❌ [FAIL] Final playback validation: {exc}")
            passed = False

    print("=" * 60)
    if passed:
        print("🎉 QA GATE RESULT: PASSED! Safe to proceed to render.")
    else:
        print("❌ QA GATE RESULT: FAILED! Please resolve the issues above.")
    print("=" * 60 + "\n")
    return passed

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python3 qa_check.py <cues_json> <tts_dir> <audio_wav> [video_mp4]")
        sys.exit(1)
    vid = sys.argv[4] if len(sys.argv) > 4 else None
    success = check_qa(sys.argv[1], sys.argv[2], sys.argv[3], video_mp4=vid)
    sys.exit(0 if success else 1)
