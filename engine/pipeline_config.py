# -*- coding: utf-8 -*-
"""
pipeline_config.py — Central Configuration for the CDrama Dubbing Pipeline
===========================================================================
Every script in the pipeline imports constants from here.
To change a setting, edit ONLY this file — all scripts inherit it instantly.

CORE RULE — 100% PIPELINE PARITY GUARANTEE:
  The 5-Minute Sample Pipeline (pipeline_worker.py) and Full Movie Pipeline (pipeline_full_movie.py)
  MUST ALWAYS BE IDENTICAL IN QUALITY, FILTERS, BLUR LOGIC, AND SUBTITLE ENGINE.
  THE ONLY DIFFERENCE IS DURATION (300s sample vs Full duration).
  Any improvement or fix made to one MUST be immediately reflected in the other.

HOW TO MOVE TO A NEW MACHINE:
  1. Clone the repo
  2. Set BASE_DIR and DOWNLOADS_DIR to your local paths
  3. Everything else adjusts automatically
"""

import os

# Guarantee Homebrew tools (ffmpeg, ffprobe, edge-tts, etc.) are always in PATH
if os.name != "nt" and "/opt/homebrew/bin" not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"

from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
#  PATHS  — dynamic resolution using Path(__file__).parent and home
# ═══════════════════════════════════════════════════════════════════
BASE_DIR       = str(Path(__file__).resolve().parent)
DOWNLOADS_DIR  = os.environ.get('DOWNLOADS_DIR', str(Path.home() / 'Downloads'))

# Derived paths — do not edit
RENDER_SUBS_BIN    = os.path.join(BASE_DIR, 'render_subs_bin')
BUILD_THUMBNAIL_SW = os.path.join(BASE_DIR, 'build_thumbnail_universal.swift')
WATERMARK_PNG      = os.path.join(BASE_DIR, 'watermark_small_v1_pure_text.png')
RENDER_SCRIPT      = os.path.join(BASE_DIR, 'render_sample_universal.py')
BUILD_AUDIO_SCRIPT = os.path.join(BASE_DIR, 'build_audio_universal.py')
TTS_SCRIPT         = os.path.join(BASE_DIR, 'synthesize_tts_universal.py')
REPAIR_SCRIPT      = os.path.join(BASE_DIR, 'repair_clips.py')

# ═══════════════════════════════════════════════════════════════════
#  SAMPLE PIPELINE SETTINGS
# ═══════════════════════════════════════════════════════════════════
SAMPLE_DURATION_SEC  = 300       # 5 minutes
SAMPLE_THUMBNAIL_SEC = 40        # frame timestamp for thumbnail extraction

# ═══════════════════════════════════════════════════════════════════
#  RENDER QUALITY SETTINGS
# ═══════════════════════════════════════════════════════════════════
TARGET_HEIGHT        = 1080      # 1080p portrait canvas (1080×1920 → rotate to 1920×1080)
PORTRAIT_W           = 1080
PORTRAIT_H           = 1920
LANDSCAPE_W          = 1920
LANDSCAPE_H          = 1080
VIDEO_BITRATE_1080P  = '10000k'  # h264_videotoolbox bitrate
VIDEO_BITRATE_720P   = '4500k'
AUDIO_BITRATE        = '192k'
AUDIO_SAMPLE_RATE    = 48000
BLUR_SIGMA_1080P     = 40       # cover blur strength (was 18: English text stayed readable)
BLUR_SIGMA_720P      = 27
BLUR_DOWNSCALE       = 4        # blur a 1/4-size copy, then scale up: same look, ~2x faster render
COVER_DARKEN         = 0.05     # slight darkening of the cover band so leftover letter shapes vanish
COLOR_CONTRAST       = 1.04
COLOR_SATURATION     = 1.06
FILM_GRAIN           = 'c0s=3:c0f=t+u'
FEATHER_PX_BASE      = 14       # feather pixels at 720p width; scales with resolution

# ═══════════════════════════════════════════════════════════════════
#  AUDIO ENGINE SETTINGS
# ═══════════════════════════════════════════════════════════════════
ATEMPO_CAP           = 1.30     # max speed-up allowed before clipping line
ATEMPO_WARN          = 1.25     # warn if speed needed exceeds this
MAX_SILENCE_BORROW   = 0.300    # seconds of next-cue silence we can borrow
SILENCE_THRESHOLD    = 0.008    # amplitude below which Edge-TTS output is silence
FADE_MS              = 15       # crossfade duration in ms (anti-click)
INCLUDE_BGM          = False    # Don't include background music & SFX; pure dialogue master
BGM_VOLUME_DB        = -18.0    # Demucs background blend level (-18 dBFS)
BGM_VOLUME_LINEAR    = 0.126    # 10^(BGM_VOLUME_DB / 20)
LOUDNORM_TARGET_I    = -14      # EBU R128 integrated loudness target (LUFS)
LOUDNORM_TRUE_PEAK   = -1.5     # EBU R128 true peak target (dBTP)
LOUDNORM_LRA         = 11       # loudness range (LU)

# ═══════════════════════════════════════════════════════════════════
#  OCR / BLUR BAND DETECTION SETTINGS
# ═══════════════════════════════════════════════════════════════════
BLUR_DETECT_FRAMES   = 30       # how many frames to sample for band detection
BLUR_BAND_P_TOP      = 5        # percentile of top-edges to use as y_min
BLUR_BAND_P_BOTTOM   = 95       # percentile of bottom-edges to use as y_max
BLUR_H_MIN_720P      = 130      # min blur band height at 720p
BLUR_H_MAX_720P      = 240      # max blur band height at 720p (up to 360px at 1080p)
BLUR_Y_FALLBACK      = 820      # fallback y_min if OCR detection fails (720p)
BLUR_H_FALLBACK      = 160      # fallback blur_h if OCR detection fails (720p)
CONTACT_SHEET_FRAMES = 12       # number of frames in the QA contact sheet

# ═══════════════════════════════════════════════════════════════════
#  TTS SETTINGS
# ═══════════════════════════════════════════════════════════════════
TTS_WORKERS          = 8        # concurrent edge-tts calls
TTS_RETRIES          = 4        # retries per clip on network error
TTS_MIN_FILE_BYTES   = 400      # file smaller than this is considered failed
TTS_DEFAULT_VOICE    = 'km-KH-PisethNeural'
TTS_DEFAULT_RATE     = '+14%'
TTS_DEFAULT_PITCH    = '+0Hz'

# ═══════════════════════════════════════════════════════════════════
#  QA GATE THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
QA_ATEMPO_WARN_PCT   = 10.0     # warn if >10% of cues need >ATEMPO_WARN speed
QA_ATEMPO_FAIL_PCT   = 35.0     # fail gate if >35% of cues exceed cap
QA_LUFS_TOLERANCE    = 1.5      # ±LUFS tolerance around target
QA_MAX_SUBTITLE_CHARS = 85      # Khmer characters per subtitle before wrap risk
QA_OVERLAP_TOLERANCE  = 0.05    # seconds of cue overlap to ignore

# ═══════════════════════════════════════════════════════════════════
#  CUE REFINEMENT SETTINGS (Timestamp Continuity & Sentence Reconnection)
# ═══════════════════════════════════════════════════════════════════
CUE_MERGE_GAP_SEC    = 1.6      # Timestamp Continuity: max gap (<1.6s) to merge consecutive duplicate/fragment cues
CUE_MERGE_SIM_RATIO  = 0.75     # min text similarity ratio to merge
CUE_PAD_MIN_DUR      = 2.5      # cues shorter than this get silence padding
CUE_PAD_MIN_GAP      = 0.15     # min gap needed to absorb padding
CUE_PAD_MAX_ABS      = 0.35     # max padding absorbed per cue (s)
KHMER_CHARS_PER_SEC  = 15.0     # natural spoken rate for Khmer line budget (12.0 - 16.5)
KHMER_BUDGET_SLACK   = 8        # extra chars of tolerance beyond budget
MAX_SILENCE_BORROW   = 1.500    # 1.5-second silence borrowing guard into scene pauses
FILTER_REGULATORY_WATERMARKS = True # No Subtitle Bounding Box Leaks: Purge （京）网微剧备字, 粤A, license plates, app credits

# ═══════════════════════════════════════════════════════════════════
#  FULL-MOVIE SOURCE FILE PRIORITY ORDER
# ═══════════════════════════════════════════════════════════════════
FULL_SOURCE_CANDIDATES = [
    'full_source.mp4',
    'source_720p_hd.mp4',
    'source_720p.mp4',
    'full_source_720p.mp4',
    'source_full.mp4',
    'source.mp4',
]
FULL_SOURCE_MIN_BYTES = 50_000_000  # must be >50 MB to be a valid full movie

# ═══════════════════════════════════════════════════════════════════
#  KHMER YOUTUBE TAGS (shared across all movies)
# ═══════════════════════════════════════════════════════════════════
YOUTUBE_TAGS_COMMON = (
    'រឿងភាគចិននិយាយខ្មែរ, ចិននិយាយខ្មែរ, cdrama khmer dub, '
    'រឿងពេញ, សម្រាយរឿង, drama khmer 2026, full movie khmer, '
    'khmer dubbed chinese drama, រឿងខ្មែរ, ភាពយន្តខ្មែរ'
)
