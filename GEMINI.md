# 25method — Gemini handoff for a Windows PC

## Goal

Help me set up and run this Chinese-drama-to-Khmer dubbing project on my PC. Assume Windows 10/11 with PowerShell unless I specify otherwise. Inspect the repository and machine before changing anything. Implement the compatibility changes needed, verify them, and explain how to start the local review studio.

This file is a handoff guide, not a completed Windows port. The existing project uses macOS-only components. Installing Python dependencies alone will not make the full pipeline work on Windows.

## Project overview

- `run.py`: CLI entry point and dependency doctor.
- `server.py`, `web/`: local browser review studio, normally at http://127.0.0.1:2525.
- `workflow.py`: project configuration, OCR, translation, speech, review, approval, export.
- `project.json`: default single-movie settings; paths resolve relative to this file.
- `characters.txt`: story and casting instructions; update for each drama.
- `engine/parallel_extract_full_timeline.py`: chunked OCR with retries and resumable results.
- `engine/auto_extract_timeline.swift`: Apple Vision/AVFoundation Chinese subtitle OCR.
- `engine/translate.py`: context-aware translation through the `agy` executable.
- `engine/synthesize_tts_universal.py`, `engine/audio_safe.py`: Edge TTS and speech fitting.
- `engine/render_subs_universal.swift`: Cocoa/CoreText subtitle graphics and render assets.
- `engine/render_sample_universal.py`: FFmpeg video rendering.
- `tests/`, `VALIDATION.md`, `README.md`: existing checks and known limitations.

Pipeline: source video → visible Chinese subtitle OCR → Khmer translation and casting → speech → full-length review → manual corrections and speaker checks → approval → export.

## Preserve my existing work

Do not delete or overwrite source videos, archives, existing translations, generated voice clips, review videos, or exports. Inspect `input/`, `work/`, `output/`, `archive_movie_*`, and `jobs/` if present. Back up configuration before editing it. Preserve dialogue history and review gates. Do not start full-movie translation or TTS automatically during setup; these use network services and may incur costs or quotas.

Copy the complete project to the PC, including any media and work I want to continue. A Mac `.venv`, compiled Swift binaries, and `Start_25method.command` are not Windows launchers or portable dependencies. Create a new environment on the PC.

## First inspect the machine

Use PowerShell to check Python, FFmpeg, available memory, GPU, and translation tooling. Verify commands actually work, not just that files exist:

```powershell
py --version
ffmpeg -version
ffprobe -version
Get-Command agy, gemini -ErrorAction SilentlyContinue
```

Use a supported 64-bit Python version compatible with the chosen OCR dependencies. The current README specifies Python 3.9+, but a new OCR library may require a newer version. Ensure FFmpeg includes `libx264`. Install a Khmer font and verify actual shaping in rendered output.

From the project folder, create a fresh environment. Activation is optional when using its Python directly:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The current requirements are `edge-tts`, `numpy`, `soundfile`, and `Pillow`; they do not provide a Windows OCR backend or a translation client.

## Required compatibility work

1. **Portable paths and process handling.** Remove unconditional Mac/user-specific PATH prefixes from `workflow.py`, `engine/translate.py`, and `engine/pipeline_config.py`. Use platform-aware discovery and explicit configurable executables. Audit subprocess calls, UTF-8 text I/O, filenames with spaces, and Windows multiprocessing. Keep process creation under appropriate main guards.

2. **Windows OCR backend.** Apple Vision and AVFoundation cannot be made available by installing Swift on Windows or WSL. Implement a Windows-capable backend, selecting and documenting a Chinese OCR engine after checking its official installation requirements. Preserve the existing extraction contract: timestamps, Chinese text, cue IDs, chunk boundaries, band suggestions, retries, logs, completion markers, and input-sensitive cache invalidation. Inspect the Swift implementation and consumers before defining the replacement. Invalidate incompatible old OCR caches without deleting them. Retain short replies and avoid aggressive merging. Do not silently substitute speech recognition for subtitle OCR.

3. **Portable render assets.** Replace the Cocoa/CoreText dependency on Windows with a renderer that correctly shapes Khmer and produces every asset consumed by the existing FFmpeg pipeline. Inspect the Swift implementation for the full output contract, including masks, image names, and timing manifests. `Project.render_review()` currently invokes the Swift renderer even when `render_subtitles` is false; merely disabling subtitles does not remove this dependency. Inspect actual Khmer glyphs visually. Do not assume that a font file alone guarantees correct shaping.

4. **FFmpeg encoding.** The renderer tries `h264_videotoolbox` and falls back to `libx264`. Select a supported encoder for Windows, preserving a reliable software fallback. Hardware encoding is optional. Preserve the inherited 1080×1920 portrait processing canvas followed by 270° clockwise rotation to a 1920×1080 output unless I request a layout change.

5. **Gemini translation integration.** Using Gemini to edit this project does not configure its runtime translator. The current runtime invokes `agy --model ... --disable-slash-commands --print PROMPT`; those flags are not a documented contract for a different CLI. Check the installed tool's help and official documentation. Either retain working `agy` or implement a configurable Gemini CLI/API adapter with explicit authentication instructions, timeout/error handling, UTF-8, and JSON parsing. Never embed credentials or log secrets. Validate returned cue IDs, Khmer text, voice assignments, and context-sensitive caching. The existing `gemini-3.8-flash-low` model string is inherited configuration, not proof of availability; choose a model actually accessible to my account and include the provider/model in cache identity.

6. **Doctor and launcher.** Update `run.py doctor` to check the backend selected on this platform instead of unconditionally requiring `swiftc` and `agy`. Distinguish local dependency checks from authenticated remote tests. Add a Windows launcher using the project's virtual-environment interpreter, with visible errors and correct working-directory handling. Keep the server bound to loopback and retain host/token protections.

Check official documentation for any new dependency or Gemini interface before choosing installation commands. Document new requirements, model downloads, and optional GPU setup. Keep the Mac backend working where practical.

## Movie configuration

The current default source is `input/source.mp4`. Copy my movie there or update `project.json` to its real PC location. JSON Windows paths must use forward slashes or escaped backslashes, for example `D:/Movies/drama.mp4`. Do not reuse `/Users/premmann/...` paths.

Inspect `characters.txt` before translating a new story. Preserve my existing cast if continuing the same drama. OCR and blur coordinates are movie-specific; inspect source frames and the resulting review instead of assuming the existing values fit every movie. `curated_cues` is currently null and `render_subtitles` is currently false.

## Verification before production

Run the existing regression suite, resolve platform failures, and add focused checks for the new backend contracts:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run.py doctor
.\.venv\Scripts\python.exe tests/smoke_movie.py
```

Adapt the smoke fixture/backend selection if it assumes Apple tools. `--skip-ocr` can isolate media processing, but does not establish that Windows OCR works. Prior Mac results in `VALIDATION.md` are not Windows validation.

Verify a short real Chinese-subtitled clip, Khmer shaping when subtitles are enabled, complete audio without clipping, output dimensions/duration, browser playback/seeking, corrections, approval invalidation, and export. Run a small authenticated translation and TTS check before any full-movie job, with my authorization for service use. Report unavailable credentials or hardware honestly; do not label skipped checks as passing.

## Start after compatibility checks pass

```powershell
.\.venv\Scripts\python.exe run.py serve --open-browser
```

Keep the terminal open. Open http://127.0.0.1:2525 if the browser does not open. For another port use `serve --port 2526 --open-browser`.

In the UI: add movie and cast → generate review → inspect the full movie → save corrections → regenerate affected speech and rebuild → check speakers → approve → export. Queue jobs use `jobs/<movie-id>/output/25method_KhmerDub_1080p.mp4`; the default CLI project exports under `output/`.

## Quality requirements

- Never clip speech to force it into a window; flag overlong lines for correction.
- Preserve manual speaker review, timing checks, consistent cast voices, and approval/export gating.
- Export the exact approved review, without an unreviewed rerender.
- Keep original media read-only and the server local.
- OCR cannot capture dialogue that has no visible subtitle. Speaker attribution needs human review.
- Preserve the current dialogue-only audio behavior; original Chinese speech, music, and effects are excluded.

When finished, list the files changed, checks that passed or remain blocked, and the exact Windows launch command. Distinguish a working UI from a verified end-to-end pipeline.

## Prompt to give Gemini

> Read GEMINI.md, README.md, and VALIDATION.md. Inspect this Windows PC and the repository. Implement the compatibility work in GEMINI.md while preserving my media, translations, and review safeguards. Set up a fresh environment, verify the pipeline with a short clip, and create a Windows launcher. Use a translation model available to my account. Do not start full-movie network jobs during setup. Tell me exactly how to launch the app and identify any remaining blockers.
