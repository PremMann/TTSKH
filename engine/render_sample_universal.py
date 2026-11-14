#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_sample_universal.py
Universal 1080p / 720p Video Renderer with:
- True Grayscale Luma Feathering for alphamerge (eliminates hard blur band edges)
- Dynamic Bounds Clamping & Even-Dimension Guarantees
- Input Dimension Probing to avoid unintended stretching
- Bitrate-Optimized Film Grain (no temporal noise bloat)
- Production Flags: -nostdin and -movflags +faststart
"""

import os
import json
import sys
import subprocess
import time
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_config import (
    PORTRAIT_W, PORTRAIT_H, LANDSCAPE_W, LANDSCAPE_H,
    VIDEO_BITRATE_1080P, VIDEO_BITRATE_720P,
    AUDIO_BITRATE, AUDIO_SAMPLE_RATE,
    BLUR_SIGMA_1080P, BLUR_SIGMA_720P,
    COLOR_CONTRAST, COLOR_SATURATION, FILM_GRAIN, FEATHER_PX_BASE,
    BLUR_DOWNSCALE, COVER_DARKEN
)


def is_blank_image(path):
    """True when an overlay image is missing or fully transparent (nothing to draw)."""
    if not path or not os.path.exists(path):
        return True
    try:
        with Image.open(path) as img:
            return img.mode in ('RGBA', 'LA') and img.getchannel('A').getextrema()[1] == 0
    except Exception:
        return False

def probe_video_dimensions(video_path):
    """Probe input video dimensions to verify aspect ratio."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0", video_path
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        w, h = map(int, out.split("x"))
        return w, h
    except Exception:
        return 1080, 1920

def render_video(video_in, mask_png, sub_concat, watermark_png, audio_in, output_mp4,
                 raw_y_min, raw_blur_h=120.0, duration=300, target_h=1080, already_1080p=False,
                 render_subtitles=False, dynamic_blur_path=None, progress_path=None):
    os.makedirs(os.path.dirname(os.path.abspath(output_mp4)), exist_ok=True)

    src_w, src_h = probe_video_dimensions(video_in)
    print(f"[*] Source dimensions probed: {src_w}x{src_h}")

    if target_h == 1080:
        pw, ph = PORTRAIT_W, PORTRAIT_H
        lw, lh = LANDSCAPE_W, LANDSCAPE_H
        
        # Safe coordinate resolution
        if already_1080p or raw_y_min >= 1000:
            y_min = int(round(raw_y_min))
            blur_h = int(round(raw_blur_h))
        else:
            scale_factor = 1080.0 / 720.0  # 1.5
            y_min = int(round(raw_y_min * scale_factor))
            blur_h = int(round(raw_blur_h * scale_factor))
            
        blur_sigma = BLUR_SIGMA_1080P
        bitrate = VIDEO_BITRATE_1080P
    else:
        pw, ph = 720, 1280
        lw, lh = 1280, 720
        y_min = int(round(raw_y_min))
        blur_h = int(round(raw_blur_h))
        blur_sigma = BLUR_SIGMA_720P
        bitrate = VIDEO_BITRATE_720P

    # Ensure even dimensions for video codecs and alphamerge
    if y_min % 2 != 0:
        y_min += 1
    if blur_h % 2 != 0:
        blur_h += 1

    # Bounds clamp: ensure crop doesn't overflow canvas height
    y_min = max(0, min(y_min, ph - 2))
    blur_h = max(2, min(blur_h, ph - y_min))
    if blur_h % 2 != 0:
        blur_h -= 1

    y_expression = str(y_min)
    if dynamic_blur_path and os.path.exists(dynamic_blur_path):
        from core.dynamic_blur import blur_expressions
        with open(dynamic_blur_path, encoding='utf-8') as file:
            track = json.load(file)
        blur_h, y_expression = blur_expressions(track, ph, pw / 720)
        print(f"[*] Applying {track.get('mode')} blur track")

    # Ensure feather mask is generated in Mode 'L' (grayscale luma gradient for alphamerge)
    need_mask_regen = True
    if os.path.exists(mask_png):
        try:
            with Image.open(mask_png) as m_img:
                if m_img.size == (pw, blur_h) and m_img.mode == "L":
                    need_mask_regen = False
        except Exception:
            pass

    if need_mask_regen:
        feather_px = int(round(FEATHER_PX_BASE * (pw / 720.0)))
        print(f"[*] Generating matching true grayscale feather mask: {pw}x{blur_h} (feather={feather_px}px) -> {mask_png}")
        m_img = Image.new("L", (pw, blur_h), 0)
        m_pixels = m_img.load()
        for y in range(blur_h):
            if feather_px > 0:
                if y < feather_px:
                    val = int(255 * (y / float(feather_px)))
                elif y > blur_h - 1 - feather_px:
                    val = int(255 * ((blur_h - 1 - y) / float(feather_px)))
                else:
                    val = 255
            else:
                val = 255
            for x in range(pw):
                m_pixels[x, y] = val
        os.makedirs(os.path.dirname(os.path.abspath(mask_png)), exist_ok=True)
        m_img.save(mask_png)

    # Filtergraph: true grayscale luma alphamerge + subtitle overlay + watermark
    # Note: Noise filter uses static/uniform noise to avoid eating video bitrate
    grain_filter = "noise=c0s=2:c0f=u" if "t+u" in FILM_GRAIN else FILM_GRAIN
    
    # Blur a small copy and scale it back up: the same soft look as a full-size gblur at a
    # fraction of the cost. Overlays with nothing to draw (no subtitles, no watermark) are skipped.
    down = max(1, int(BLUR_DOWNSCALE))
    small_w, small_h = max(2, pw // down // 2 * 2), max(2, blur_h // down // 2 * 2)
    blur_chain = (f"scale={small_w}:{small_h}:flags=area,gblur=sigma={blur_sigma / down:.2f}:steps=3,"
                  f"scale={pw}:{blur_h}:flags=bicubic" if down > 1 else f"gblur=sigma={blur_sigma}")
    if COVER_DARKEN:
        blur_chain += f",eq=brightness=-{COVER_DARKEN}"
    draw_subs = render_subtitles
    draw_watermark = not is_blank_image(watermark_png)

    inputs = [*(["-ss", "0", "-t", str(duration)] if duration > 0 else ["-ss", "0"]), "-i", video_in,
              "-loop", "1", "-i", mask_png]
    index = 2
    graph = [
        f"[0:v]scale={pw}:{ph}:force_original_aspect_ratio=decrease,pad={pw}:{ph}:(ow-iw)/2:(oh-ih)/2,split=2[v_base][v_crop]",
        f"[v_crop]crop={pw}:{blur_h}:0:'{y_expression}',{blur_chain}[blurred]",
        "[blurred][1:v]alphamerge[feathered]",
        f"[v_base][feathered]overlay=0:y='{y_expression}':eval=frame[v_sub]",
    ]
    if draw_subs:
        inputs += ["-f", "concat", "-safe", "0", "-i", sub_concat]
        graph[-1] = graph[-1].replace("[v_sub]", "[clean_v]")
        graph.append(f"[clean_v][{index}:v]overlay=0:0[v_sub]")
        index += 1
    rotate = f"[v_sub]transpose=2,setsar=1,eq=contrast={COLOR_CONTRAST}:saturation={COLOR_SATURATION},{grain_filter}"
    if draw_watermark:
        inputs += ["-loop", "1", "-i", watermark_png]
        graph.append(rotate + "[v_rot]")
        graph.append(f"[v_rot][{index}:v]overlay=x='(W-w)/2+sin(t*0.45)*(W-w)*0.45':y='(H-h)/2+cos(t*0.65)*(H-h)*0.40'[v_out]")
        index += 1
    else:
        graph.append(rotate + "[v_out]")
    inputs += ["-i", audio_in]
    filter_complex = ";".join(graph)

    # Mac: VideoToolbox. Elsewhere: libx264, or TTSKH_VIDEO_ENCODER (e.g. h264_nvenc).
    encoder = os.environ.get("TTSKH_VIDEO_ENCODER") or ("h264_videotoolbox" if sys.platform == "darwin" else "libx264")
    cmd = [
        "ffmpeg", "-y",
        "-nostdin",
        *(["-progress", progress_path, "-stats_period", "2"] if progress_path else []),
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", f"{index}:a",
        "-c:v", encoder,
        *(["-preset", "fast"] if encoder == "libx264" else []),
        "-b:v", bitrate,
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-movflags", "+faststart",
        "-shortest",
        *(["-t", str(duration)] if duration > 0 else []),
        output_mp4
    ]

    print(f"[*] Rendering {lw}x{lh} ({target_h}p) 270-degree rotated landscape video with {encoder} to {output_mp4}...")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode and encoder != "libx264":
        print(f"[!] {encoder} unavailable; retrying with software H.264 (libx264)")
        i = cmd.index(encoder)
        cmd[i:i + 1] = ["libx264", "-preset", "fast"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        print(result.stderr[-3000:])
        raise subprocess.CalledProcessError(result.returncode, cmd[:1], stderr=result.stderr)
    print(f"[+] Rendered in {time.time()-t0:.1f}s: {output_mp4}")
    return output_mp4


if __name__ == '__main__':
    # Fixed argument check: argv[7] is raw_y_min, so requires at least 8 arguments
    if len(sys.argv) < 8:
        print("Usage: python3 render_sample_universal.py <video_in> <mask_png> <sub_concat> <watermark_png> <audio_in> <output_mp4> <y_min> [blur_height] [duration] [target_height] [already_1080p]")
        sys.exit(1)

    _raw_blur_h = float(sys.argv[8]) if len(sys.argv) > 8 else 120.0
    _duration = int(float(sys.argv[9])) if len(sys.argv) > 9 else 300
    _target_h = int(float(sys.argv[10])) if len(sys.argv) > 10 else 1080
    _already_1080 = sys.argv[11].lower() in ('true', '1', 'yes') if len(sys.argv) > 11 else False

    render_video(
        video_in=sys.argv[1],
        mask_png=sys.argv[2],
        sub_concat=sys.argv[3],
        watermark_png=sys.argv[4],
        audio_in=sys.argv[5],
        output_mp4=sys.argv[6],
        raw_y_min=float(sys.argv[7]),
        raw_blur_h=_raw_blur_h,
        duration=_duration,
        target_h=_target_h,
        already_1080p=_already_1080
    )
