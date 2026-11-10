#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
synthesize_tts_universal.py
Robust Multi-Threaded Edge-TTS Synthesizer:
1. Hash-based Cache Validation (text, voice, pitch, rate) — invalidates stale clips on cue edits.
2. Exponential Backoff Retries on network/handshake throttling.
3. Accurate accounting: skips non-verbal/empty cues without marking them as failures.
4. Preserves prosodic punctuation (?, !, commas) for natural Khmer pauses and question tones.
5. Strict exit codes: exits 1 if any dialogue cue fails synthesis.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def _get_edge_tts_base_cmd():
    b = shutil.which('edge-tts')
    if b:
        return [b]
    if os.path.exists('/opt/homebrew/bin/edge-tts'):
        return ['/opt/homebrew/bin/edge-tts']
    return [sys.executable, '-m', 'edge_tts']

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.khmer_validator import (
    validate_khmer_text, is_valid_for_tts, verify_audio_file,
    validate_synthesis_safety, SynthesisSafetyError
)
from pipeline_config import (
    TTS_WORKERS, TTS_RETRIES, TTS_MIN_FILE_BYTES,
    TTS_DEFAULT_VOICE, TTS_DEFAULT_RATE, TTS_DEFAULT_PITCH
)

def compute_cue_hash(text, voice, pitch, rate):
    content = f"{text}|{voice}|{pitch}|{rate}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]

def clean_spoken_text(text):
    """
    Cleans text while preserving question marks, exclamation marks, and commas
    for natural Cambodian sentence intonation and pauses.
    """
    # Remove XML/HTML tags and weird symbols, but keep letters, spaces, ?, !, commas, and Khmer punctuation
    cleaned = re.sub(r'[\r\n\t]+', ' ', text)
    cleaned = re.sub(r'[~`"@#$%^&*()_=\[\]{}|\\/<>;:]+', ' ', cleaned)
    # Collapse multiple spaces
    cleaned = re.sub(r' +', ' ', cleaned).strip()
    return cleaned

def synthesize_cue(cue, out_dir, manifest, movie_name=""):
    cid = cue.get('id', 0)

    # 1. Visual captions and explicitly non-spoken cues: strictly SKIP synthesis
    if cue.get('is_spoken_dialogue') is False or cue.get('tts_enabled') is False or cue.get('speech_classification') == 'visual_caption':
        return "SKIP"

    # If cue is not marked spoken and spoken text is empty/placeholder, skip cleanly
    text = (cue.get('khmer_spoken') or '').strip()
    if not text and cue.get('is_spoken_dialogue') is not True:
        return "SKIP"

    # 2. Strict Safety Gate at synthesis boundary (Requirement 5)
    try:
        validate_synthesis_safety(cue, cue_id=cid, movie_name=movie_name)
    except SynthesisSafetyError as err:
        print(f"[!] Cue {cid}: correct the reviewed Khmer text before synthesis: {err}")
        return "FAIL"

    # 4. Confirm voice is a valid Khmer voice
    voice = cue.get('voice', TTS_DEFAULT_VOICE)
    if voice not in ['km-KH-PisethNeural', 'km-KH-SreymomNeural']:
        voice = TTS_DEFAULT_VOICE

    rate = cue.get('rate') or TTS_DEFAULT_RATE
    pitch = str(cue.get('pitch', TTS_DEFAULT_PITCH)).strip()
    if pitch in ('0Hz', '0', ''):
        pitch = '+0Hz'
    elif not (pitch.startswith('+') or pitch.startswith('-')):
        pitch = f"+{pitch}"

    cue_hash = compute_cue_hash(text, voice, pitch, rate)
    out_mp3 = os.path.join(out_dir, f"cue_{cid:04d}.mp3")
    hash_file = os.path.join(out_dir, f"cue_{cid:04d}.hash")

    # Cache check: file must exist, meet minimum size, contain valid audio, AND match content hash
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > TTS_MIN_FILE_BYTES:
        cached_hash = None
        if os.path.exists(hash_file):
            try:
                with open(hash_file, "r") as hf:
                    cached_hash = hf.read().strip()
            except Exception:
                pass
        elif str(cid) in manifest:
            cached_hash = manifest[str(cid)]

        if cached_hash == cue_hash:
            aud = verify_audio_file(out_mp3, min_bytes=TTS_MIN_FILE_BYTES, min_duration=0.1)
            if aud["valid"]:
                return "OK"

    for stale_path in (out_mp3, hash_file):
        if os.path.exists(stale_path):
            os.remove(stale_path)

    clean_text = clean_spoken_text(text)
    if not clean_text:
        clean_text = text

    cmd = _get_edge_tts_base_cmd() + [
        '--voice', voice,
        f'--pitch={pitch}',
        f'--rate={rate}',
        '--text', clean_text,
        '--write-media', out_mp3
    ]

    # Retry loop with exponential backoff (0.5s, 1.0s, 2.0s, 4.0s)
    last_error = "No synthesis attempts configured"
    for attempt in range(TTS_RETRIES):
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            res = None
            last_error = "Speech service timed out after 45 seconds. Check your internet connection and retry."
        except OSError as exc:
            res = None
            last_error = f"Unable to start speech synthesis: {exc}"
        if res is not None and res.returncode != 0:
            stderr = res.stderr if isinstance(res.stderr, str) else ""
            last_error = stderr.strip().splitlines()[-1] if stderr.strip() else f"Speech process exited with code {res.returncode}"
            if "DNSError" in last_error or "nodename nor servname" in last_error:
                last_error = "Cannot reach Microsoft speech service (DNS lookup failed). Check your internet connection and DNS, then retry."
        if res is not None and res.returncode == 0:
            # 5. Verify audio file has audible duration and non-empty buffer
            aud = verify_audio_file(out_mp3, min_bytes=TTS_MIN_FILE_BYTES, min_duration=0.1)
            if aud["valid"]:
                try:
                    with open(hash_file, "w") as hf:
                        hf.write(cue_hash)
                except Exception:
                    pass
                return "OK"
            else:
                last_error = f"Speech service returned invalid audio: {aud.get('reason', 'unknown reason')}"
                # Corrupt / silent / zero-duration output
                if os.path.exists(out_mp3):
                    try:
                        os.remove(out_mp3)
                    except Exception:
                        pass

        # Never leave a partial response available for mixing or a later retry.
        if os.path.exists(out_mp3):
            os.remove(out_mp3)
        if attempt + 1 < TTS_RETRIES:
            time.sleep(0.5 * (2 ** attempt))

    print(f"[!] Failed to synthesize cue {cid}: {last_error}")
    return "FAIL"

def synthesize_all_cues(cues_file, out_dir, concurrency=TTS_WORKERS, progress=None, movie_name=""):
    os.makedirs(out_dir, exist_ok=True)
    with open(cues_file, 'r', encoding='utf-8') as f:
        cues = json.load(f)

    manifest_path = os.path.join(out_dir, "tts_manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest = json.load(mf)
        except Exception:
            manifest = {}

    dialogue_cues = [c for c in cues if (c.get('khmer_spoken') or c.get('khmer_sub') or c.get('khmer') or '').strip()]
    print(f"Synthesizing {len(dialogue_cues)} dialogue cues ({len(cues)} total) via Microsoft Edge-TTS (workers={concurrency})...")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(synthesize_cue, cue, out_dir, manifest, movie_name): cue['id'] for cue in cues}
        results = []
        for future in as_completed(futures):
            results.append((futures[future], future.result()))
            if progress:
                progress(len(results), len(cues))

    # Update manifest
    updated_manifest = {}
    for c in cues:
        cid = c['id']
        hash_file = os.path.join(out_dir, f"cue_{cid:04d}.hash")
        if os.path.exists(hash_file):
            try:
                with open(hash_file, "r") as hf:
                    updated_manifest[str(cid)] = hf.read().strip()
            except Exception:
                pass
    try:
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(updated_manifest, mf)
    except Exception:
        pass

    succeeded = sum(1 for _, res in results if res == "OK")
    skipped = sum(1 for _, res in results if res == "SKIP")
    failed = [cid for cid, res in results if res == "FAIL"]

    print(f"Finished synthesizing: {succeeded} audio clips ready, {skipped} non-verbal cues skipped, {len(failed)} failed.")
    return len(failed) == 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 synthesize_tts_universal.py <cues_json> <tts_out_dir> [concurrency]")
        sys.exit(1)

    _cues_file = sys.argv[1]
    _out_dir = sys.argv[2]
    _concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else TTS_WORKERS

    ok = synthesize_all_cues(_cues_file, _out_dir, _concurrency)
    sys.exit(0 if ok else 1)
