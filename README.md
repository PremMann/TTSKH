# 25method — local Khmer dubbing review studio

Movie 25's subtitle-first method, with stronger checks and a local browser review interface. The source movie is read in place; generated files stay inside this project. No original Movie 25 media is bundled.

## Start

Double-click **Start_25method.command** on your Mac. Keep its Terminal window open. The interface opens at **http://127.0.0.1:2525**.

Or:

```sh
cd /Users/premmann/Next/cdrama_dubbing/25method
python3 run.py serve
```

If port 2525 is busy, use `python3 run.py serve --port 2526` and open http://127.0.0.1:2526.

## Setup on another Mac

Requires Python 3.9+, FFmpeg/ffprobe, Xcode Command Line Tools (Apple Vision/CoreText), and an authenticated `agy` CLI with an available translation model. Install a Khmer font such as Khmer OS Battambang or Kantumruy Pro for predictable subtitle rendering. Translation and Edge TTS need internet access.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py doctor
python run.py serve
```

The inherited model default is `gemini-3.8-flash-low`. Change it in Story settings to a model available to your agy account. The doctor checks local executables/modules, not authentication or remote availability. Swift binaries are compiled locally when needed; a first compilation can take several minutes.

## Setup on Windows

On Windows the Apple-only parts are replaced automatically:

- OCR: `engine/ocr_timeline.py` (RapidOCR, the PaddleOCR Chinese models on ONNX Runtime) instead of Apple Vision.
- Subtitle images: `engine/render_subs.py` (FFmpeg libass, which shapes Khmer correctly) instead of CoreText.
- Video encoding: `libx264`. Set `TTSKH_VIDEO_ENCODER=h264_nvenc` to use an NVIDIA GPU (it needs a recent NVIDIA driver; if it fails the render falls back to libx264).

Install once (PowerShell):

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
irm https://antigravity.google/cli/install.ps1 | iex   # then run: agy   (to sign in)
```

Install a Khmer font (Khmer OS Battambang or Kantumruy Pro). Then double-click **Setup_Windows.bat** (creates `.venv`, installs packages, runs the doctor) and afterwards **Start_25method.bat**. Keep the project in a short path such as `C:\TTSKH`; very long paths can break `pip install`.

OCR runs on the GPU through DirectML (`onnxruntime-directml`, installed by `Setup_Windows.bat`; any DirectX 12 card), about 3x faster than the CPU. `TTSKH_OCR_DEVICE=cpu` forces the CPU. Only the subtitle band is read and unchanged frames are skipped. On Windows at most 3 OCR workers run at once, whatever `ocr_workers` says. Set `TTSKH_SUB_FONT` to a .ttf path to force the subtitle font. On a Mac, `TTSKH_ENGINE=python` uses the same Python engines instead of Swift.

## Full-movie workflow

1. **Add movie**: enter its full local video path, name, and character descriptions. The default prompt is Movie 25's cast; replace it for another story.
2. Select **1–10 movies → Generate reviews**. Each runs sequentially through OCR, translation, speech and a full-length review render. Failure on one movie does not prevent the next queued movie from running.
3. Review the original and dubbed movie. Click an entry to seek to its scene. Check Khmer dialogue, subtitles, voice and timing. Use **Next issue** to navigate flags.
4. **Save corrections**. Character voice/pitch/rate edits apply to all entries assigned to that character. Mark the speaker checked after inspecting the scene. Use **Regenerate this line** and **Listen** for individual voice corrections.
5. Use **Rebuild review** after changes to text, casting, timing or picture layout. The review always covers the full movie, never only 45–60 seconds. Confirming an unchanged speaker alone does not require a new render.
6. Watch the updated review, then **Approve reviewed movie**. All speaker checks and speech errors must be resolved. Select approved movies and **Export approved** to export them sequentially.

The export copies the exact reviewed movie rather than rerendering different content after approval. Export: `jobs/<movie-id>/output/25method_KhmerDub_1080p.mp4`. Download links appear after export. The default CLI project uses `output/` directly.

If speech is too long, preparation stops and the issue appears in the editor. Shorten the Khmer sentence or extend its speech window without overlapping the next line; regenerate and rebuild. The app does not clip speech to force it to fit.

## Layout

The inherited output is **1920×1080 with 270° clockwise rotation** (90° counterclockwise). Subtitle graphics rotate with the source, matching Movie 25's render order. In Picture layout, display the current original frame, use the OCR cover suggestion, then adjust the cover top/height. Values are even pixel coordinates on the **1080×1920 portrait canvas before rotation**. Inspect the final review after saving. The suggestion is a fixed cover band, not per-frame tracking or background reconstruction.

Audio is clean Khmer dialogue with Piseth/Sreymom voices and pitch/rate variations. Original Chinese speech, music and effects are excluded. This version does not add voice cloning or lip synchronization.

## Reliability changes

- OCR worker failures retry three times, retain logs, and block incomplete extraction. Only successful chunks are resumed. An all-empty extraction fails. A successfully scanned silent/no-subtitle section may be empty.
- One-character replies are retained. Fuzzy merging and automatic sentence joining were removed. Original OCR entries and their IDs are retained for review.
- Translation batches include surrounding Chinese dialogue. Unspoken signs can be marked as text-only; uncertain speakers still require human review. Character casting is consistent across entries.
- Translation caches include source entries, context, prompt and model; outputs validate returned IDs and voices.
- Speech/subtitle timing, non-finite values, overlaps, voice settings and movie boundaries are checked.
- Audio is written sequentially to disk, avoiding whole-movie audio arrays. Every overlong line blocks output; normalization failures are not replaced with unchecked audio.
- Review renders use a temporary output, validate playback/duration/dimensions/audio, and only then replace the previous review. Changed media settings invalidate approval.
- Edits preserve earlier dialogue versions in `work/history/`. The queue persists. On restart, unfinished tasks become Interrupted and require an explicit retry; they do not silently restart paid/network operations.
- The review server binds only to loopback, checks its host and uses a session token for mutations. Do not expose it publicly.

## CLI

Configure `project.json` for a single movie, or pass `--project jobs/<id>/project.json`:

```sh
python run.py ocr
python run.py translate
python run.py tts
python run.py review
# Edit and check speakers through the browser, then rebuild if necessary.
python run.py approve
python run.py export
```

`prepare` runs OCR/translation when there is no master dialogue, then produces a full review. Existing dialogue is kept on retry. `render` is an alias for approved export. `tts --cue 12` regenerates one entry. Manual retranslating replaces the master dialogue after saving its prior version.

`curated_cues` can point to reviewed opening entries. The builder continues at the last curated end time, as in Movie 25's original 142-entry opening. An OCR entry crossing that boundary must be reconciled explicitly. With `null`, translation begins at the start.

## Tests and remaining limits

```sh
python -m unittest discover -s tests -v
python tests/smoke_movie.py
# If Apple Vision is unavailable, independently exercise audio/rendering:
python tests/smoke_movie.py --skip-ocr
```

The smoke test uses a generated six-second image/video and tone clips; it does not call online translation or speech services. It checks actual media processing, not translation accuracy or emotional voice quality. Temporary fixtures are retained for diagnosis.

OCR does not hear dialogue that lacks visible subtitles. Speaker attribution and screen-text classification remain AI inferences. Review the entire movie, especially short replies, rapid turn-taking, names, and missing dialogue. The curated Movie 25 files and final historical export are unavailable, so exact parity cannot be claimed. Online translation/TTS and full-length production still need testing with your source movie.

`reference/build_movie25_authentic.py` preserves the historical implementation; `engine/` contains the independent processing modules. No files in the parent KHMovie pipeline are changed.
