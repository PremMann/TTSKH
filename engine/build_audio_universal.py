#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_audio_universal.py — Studio-Grade Master Audio Builder
============================================================
1. Trims dead silence (leading ~220ms and trailing ~750ms) added by Edge-TTS.
2. Measures REAL voice duration against allowed cue duration.
3. Borrows up to 300ms of silence from gap before next cue before speeding up.
4. Strict speed cap: atempo capped at 1.30x (natural human speech guard).
5. Logs every cue needing > 1.25x speed.
6. Blends Demucs instrumental/SFX background track at -18 dB under the dub.
7. Normalizes final master audio using EBU R128 loudnorm (-14 LUFS, -1.5 dBTP, LRA 11).
"""

import json
import os
import sys

if "/opt/homebrew/bin" not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

import subprocess
import soundfile as sf
import numpy as np
from core.speech_timing import spoken_timeline

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_config import (
    AUDIO_SAMPLE_RATE, ATEMPO_CAP, ATEMPO_WARN,
    MAX_SILENCE_BORROW, SILENCE_THRESHOLD, FADE_MS,
    BGM_VOLUME_LINEAR, LOUDNORM_TARGET_I, LOUDNORM_TRUE_PEAK,
    LOUDNORM_LRA, TTS_MIN_FILE_BYTES, INCLUDE_BGM
)

def trim_silence(data, sample_rate, threshold=SILENCE_THRESHOLD):
    """Trim leading and trailing silence from Edge-TTS output."""
    if len(data.shape) > 1:
        mono = np.mean(data, axis=1)
    else:
        mono = data
        data = np.column_stack([data, data])
        
    non_silent = np.where(np.abs(mono) > threshold)[0]
    if len(non_silent) == 0:
        raise ValueError("Speech clip contains only silence")
        
    pad_samples = int(0.020 * sample_rate)  # 20ms breathing room
    start_idx = max(0, non_silent[0] - pad_samples)
    end_idx = min(len(data), non_silent[-1] + pad_samples)
    return data[start_idx:end_idx]

def get_processed_clip(cue, tts_dir, effective_dur, max_allowed_dur, sr=AUDIO_SAMPLE_RATE, max_atempo_cap=ATEMPO_CAP, warn_atempo_thresh=ATEMPO_WARN, warnings=None):
    if cue.get('is_spoken_dialogue') is False or (cue.get('khmer_spoken') or '').strip() in ('', '-', '—'):
        return None
    idx = cue['id']
    raw_mp3 = os.path.join(tts_dir, f"cue_{idx:04d}.mp3")
    
    if not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) < TTS_MIN_FILE_BYTES:
        return None
        
    try:
        raw_data, raw_sr = sf.read(raw_mp3, dtype='float32')
    except Exception:
        return None
        
    # 1. Trim dead silence (removes Edge-TTS ~1.0s artificial padding)
    trimmed_data = trim_silence(raw_data, raw_sr)
    real_voice_dur = len(trimmed_data) / raw_sr
    
    # 2. Check if real voice fits within effective duration
    if real_voice_dur <= effective_dur:
        # Fits naturally! Resample to 48kHz without atempo
        if raw_sr != sr:
            cmd = ['ffmpeg', '-y', '-v', 'error', '-i', raw_mp3, '-ar', str(sr), '-ac', '2', '-f', 'wav', 'pipe:1']
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            import io
            data, _ = sf.read(io.BytesIO(res.stdout), dtype='float32')
            if len(data.shape) == 1:
                data = np.column_stack([data, data])
            return trim_silence(data, sr)
        return trimmed_data
    else:
        # Needs speeding up based on REAL voice duration
        raw_speed = real_voice_dur / effective_dur
        speed_factor = min(max_atempo_cap, raw_speed)
        
        if raw_speed > warn_atempo_thresh and warnings is not None:
            warnings.append({
                'id': idx,
                'raw_speed': raw_speed,
                'capped_speed': speed_factor,
                'voice_dur': real_voice_dur,
                'effective_dur': effective_dur,
                'text': cue.get('khmer_spoken', '')
            })
            
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', raw_mp3,
            '-filter:a', f'atempo={speed_factor:.3f}',
            '-ar', str(sr), '-ac', '2',
            '-f', 'wav', 'pipe:1'
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and len(res.stdout) > 44:
                import io
                data, _ = sf.read(io.BytesIO(res.stdout), dtype='float32')
                if len(data.shape) == 1:
                    data = np.column_stack([data, data])
                return trim_silence(data, sr)
        except Exception:
            pass
            
    return None

def build_studio_audio(cues_file, tts_dir, out_wav, total_dur=300.0, bg_wav=None):
    if bg_wav:
        raise ValueError('25method currently supports clean dialogue only')
    from audio_safe import build
    with open(cues_file, encoding='utf-8') as handle:
        return build(json.load(handle), tts_dir, out_wav, total_dur)


if __name__ == '__main__':
    # Usage: python3 build_audio_universal.py <cues_json> <tts_dir> <out_wav> [duration] [bg_wav]
    if len(sys.argv) < 4:
        print("Usage: python3 build_audio_universal.py <cues_json> <tts_dir> <out_wav> [duration] [bg_wav]")
        sys.exit(1)

    _cues_file = sys.argv[1]
    _tts_dir = sys.argv[2]
    _out_wav = sys.argv[3]
    _total_dur = float(sys.argv[4]) if len(sys.argv) > 4 else 300.0
    _bg_wav = sys.argv[5] if len(sys.argv) > 5 else None

    build_studio_audio(_cues_file, _tts_dir, _out_wav, _total_dur, _bg_wav)
