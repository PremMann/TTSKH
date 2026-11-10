#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/khmer_validator.py — Unicode-Aware Khmer Language Validation & Audio Verification
======================================================================================
Validates translation text to protect Microsoft Edge-TTS Khmer neural voices
(km-KH-PisethNeural and km-KH-SreymomNeural) from silent failure or errors caused
by Chinese CJK characters or empty text.
"""

import os
import re
from typing import Dict, Any, Union, Optional, Tuple

# Unicode character block ranges
# Khmer: U+1780..U+17FF (Basic Khmer), U+19E0..U+19FF (Khmer Symbols)
KHMER_REGEX = re.compile(r'[\u1780-\u17ff\u19e0-\u19ff]')

# Comprehensive Unicode-aware CJK Ideographs (Standard + Supplementary Ranges):
# - U+4E00..U+9FFF: CJK Unified Ideographs
# - U+3400..U+4DBF: CJK Extension A
# - U+F900..U+FAFF: CJK Compatibility Ideographs
# - U+2E80..U+2FD5: CJK Radicals Supplement & Kangxi Radicals
# - U+31C0..U+31EF: CJK Strokes
# - U+2FF0..U+2FFF: Ideographic Description Characters
# - U+20000..U+2EBEF: CJK Extensions B, C, D, E, F
# - U+30000..U+323AF: CJK Extensions G, H
CJK_REGEX = re.compile(
    r'[\u4e00-\u9fff'
    r'\u3400-\u4dbf'
    r'\uf900-\ufaff'
    r'\u2e80-\u2fd5'
    r'\u31c0-\u31ef'
    r'\u2ff0-\u2fff'
    r'\U00020000-\U0002A6DF'
    r'\U0002A700-\U0002B73F'
    r'\U0002B740-\U0002B81F'
    r'\U0002B820-\U0002CEAF'
    r'\U0002CEB0-\U0002EBEF'
    r'\U00030000-\U0003134F'
    r'\U00031350-\U000323AF]'
)

# Non-verbal symbols or empty placeholders
SKIP_SYMBOLS = {'.', '..', '...', '…', '-', '—', '_', 'None', 'none', 'null', 'NULL'}


class SynthesisSafetyError(RuntimeError):
    """Raised when an invalid cue attempts to enter the speech synthesis boundary."""
    pass


def validate_khmer_text(text: Union[str, None]) -> Dict[str, Any]:
    """
    Validates a text string for use with Khmer TTS engines.

    Returns dict:
      {
        "status": "VALID_KHMER" | "CHINESE_ONLY" | "MIXED_CJK_KHMER" | "EMPTY" | "NEEDS_REVIEW",
        "is_valid_for_tts": bool,
        "has_khmer": bool,
        "has_cjk": bool,
        "khmer_chars_count": int,
        "cjk_chars_count": int,
        "message": str
      }
    """
    if text is None:
        return {
            "status": "EMPTY",
            "is_valid_for_tts": False,
            "has_khmer": False,
            "has_cjk": False,
            "khmer_chars_count": 0,
            "cjk_chars_count": 0,
            "message": "Translation is missing (null)"
        }

    s = str(text).strip()
    if not s or s in SKIP_SYMBOLS:
        return {
            "status": "EMPTY",
            "is_valid_for_tts": False,
            "has_khmer": False,
            "has_cjk": False,
            "khmer_chars_count": 0,
            "cjk_chars_count": 0,
            "message": "Translation is empty or non-verbal"
        }

    khmer_matches = KHMER_REGEX.findall(s)
    cjk_matches = CJK_REGEX.findall(s)
    has_khmer = len(khmer_matches) > 0
    has_cjk = len(cjk_matches) > 0

    # CASE A: Valid Khmer translation
    # Contains meaningful Khmer characters and NO Chinese CJK characters.
    # Legitimate punctuation, numbers, and Latin acronyms (CEO, VIP, OK) are allowed.
    if has_khmer and not has_cjk:
        return {
            "status": "VALID_KHMER",
            "is_valid_for_tts": True,
            "has_khmer": True,
            "has_cjk": False,
            "khmer_chars_count": len(khmer_matches),
            "cjk_chars_count": 0,
            "message": "Valid Khmer translation"
        }

    # CASE B: Chinese-only translation
    # Contains Chinese CJK characters and NO Khmer characters.
    # CRITICAL: Edge-TTS Khmer voices fail with NoAudioReceived on this!
    if has_cjk and not has_khmer:
        return {
            "status": "CHINESE_ONLY",
            "is_valid_for_tts": False,
            "has_khmer": False,
            "has_cjk": True,
            "khmer_chars_count": 0,
            "cjk_chars_count": len(cjk_matches),
            "message": "Chinese text in Khmer translation field (blocked from TTS)"
        }

    # CASE C: Mixed Chinese and Khmer
    # Contains both Khmer and CJK characters (untranslated fragment).
    if has_khmer and has_cjk:
        return {
            "status": "MIXED_CJK_KHMER",
            "is_valid_for_tts": False,
            "has_khmer": True,
            "has_cjk": True,
            "khmer_chars_count": len(khmer_matches),
            "cjk_chars_count": len(cjk_matches),
            "message": "Mixed Chinese and Khmer text (requires review)"
        }

    # CASE E: Non-Khmer (e.g. English-only or pure numbers/symbols)
    return {
        "status": "NEEDS_REVIEW",
        "is_valid_for_tts": False,
        "has_khmer": False,
        "has_cjk": False,
        "khmer_chars_count": 0,
        "cjk_chars_count": 0,
        "message": "Non-Khmer text (contains no Khmer characters)"
    }


def is_valid_for_tts(text: Union[str, None]) -> bool:
    """Convenience helper returning True only if text is safe for Khmer TTS."""
    return validate_khmer_text(text)["is_valid_for_tts"]


def validate_synthesis_safety(
    cue_or_text: Union[Dict[str, Any], str],
    cue_id: Optional[int] = None,
    movie_name: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Strict Synthesis Safety Gate (Requirement 5):
    Ensures that only confirmed, approved spoken dialogue can reach Edge-TTS.
    Rejects:
      - Visual captions (must have empty spoken text and tts_enabled=False)
      - Uncertain classifications or pending reviews
      - Any Hanzi character (standard + supplementary ranges)
      - Empty speech, placeholders, or "-"
      - Source language fallback text

    Raises SynthesisSafetyError if a cue is invalid for synthesis.
    """
    movie_tag = f"[{movie_name}] " if movie_name else ""

    if isinstance(cue_or_text, dict):
        cue = cue_or_text
        cid = cue.get("id", cue_id or 0)

        # 1. Classification check
        cls = cue.get("speech_classification")
        is_spk = cue.get("is_spoken_dialogue")
        if cls == "uncertain":
            raise SynthesisSafetyError(f"{movie_tag}Cue #{cid}: Attempted to synthesize uncertain cue without human classification.")
        if cls == "visual_caption" or is_spk is False:
            raise SynthesisSafetyError(f"{movie_tag}Cue #{cid}: Attempted to synthesize visual caption as speech.")

        # 2. Approval check
        if cue.get("approval_status") == "needs_review" or cue.get("flagged"):
            raise SynthesisSafetyError(f"{movie_tag}Cue #{cid}: Blocked from TTS because it is flagged for review.")

        text = (cue.get("khmer_spoken") or cue.get("khmer_translation") or "").strip()
    else:
        cid = cue_id or 0
        text = str(cue_or_text).strip()

    # 3. Payload content validation
    if not text:
        raise SynthesisSafetyError(f"{movie_tag}Cue #{cid}: Spoken text payload is empty.")

    if text in SKIP_SYMBOLS:
        raise SynthesisSafetyError(f"{movie_tag}Cue #{cid}: Fallback placeholder or '-' provided as spoken content.")

    cjk_matches = CJK_REGEX.findall(text)
    if cjk_matches:
        offending = "".join(set(cjk_matches))
        raise SynthesisSafetyError(
            f"{movie_tag}Cue #{cid}: Contains un-translated Han characters '{offending}'. "
            f"Synthesis blocked to prevent Edge-TTS crash."
        )

    val = validate_khmer_text(text)
    if not val["is_valid_for_tts"]:
        raise SynthesisSafetyError(f"{movie_tag}Cue #{cid}: Validation failed: {val['message']}.")

    return True, "OK"


import threading
_sf_lock = threading.Lock()

def verify_audio_file(audio_path: str, min_bytes: int = 1000, min_duration: float = 0.1) -> Dict[str, Any]:
    """
    Verifies that generated audio file exists, is non-empty, and contains actual audible speech.
    """
    if not os.path.exists(audio_path):
        return {"valid": False, "reason": "File does not exist", "duration": 0.0, "size": 0}

    size = os.path.getsize(audio_path)
    if size < min_bytes:
        return {"valid": False, "reason": f"File too small ({size} bytes < {min_bytes})", "duration": 0.0, "size": size}

    try:
        import soundfile as sf
        with _sf_lock:
            info = sf.info(audio_path)
        if info.duration < min_duration:
            return {"valid": False, "reason": f"Duration too short ({info.duration:.3f}s < {min_duration}s)", "duration": info.duration, "size": size}
        return {"valid": True, "reason": "OK", "duration": round(info.duration, 3), "size": size}
    except Exception as e:
        # If soundfile fails, fallback to ffprobe
        import subprocess
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5)
            dur = float(res.stdout.strip())
            if dur < min_duration:
                return {"valid": False, "reason": f"Duration too short ({dur:.3f}s)", "duration": dur, "size": size}
            return {"valid": True, "reason": "OK (ffprobe)", "duration": round(dur, 3), "size": size}
        except Exception:
            return {"valid": False, "reason": f"Audio file unreadable / corrupt: {e}", "duration": 0.0, "size": size}
