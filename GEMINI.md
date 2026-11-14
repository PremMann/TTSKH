# 25method — setup guide for Gemini (Antigravity) on a Windows PC

## Your job

Set up and verify this Chinese-drama → Khmer dubbing studio on this Windows PC, then tell me how to start it.

**The Windows port is already finished and tested.** Do not rewrite, refactor or "fix" the code: OCR, subtitle rendering,
translation, the server and the UI all work on Windows. Your work is installing tools, creating the environment,
running the checks and reporting. Only change code if a check fails, and then explain the failure and ask me first.

## Rules

- Use PowerShell. Ask before installing anything; tell me what each install is for.
- Never delete or overwrite my videos, `input/`, `work/`, `jobs/`, `output/` or `project.json` values I set.
- Never type passwords, tokens or sign-in codes for me. When a sign-in is needed (agy, GitHub), tell me what to do.
- Do not start a full-movie job or any translation/TTS run without asking: they use online services and quota.
- Report honestly: a skipped or failed check is not a pass.

## How the project works (for orientation only)

- `Start_25method.bat` starts the studio at http://127.0.0.1:2525. `Setup_Windows.bat` creates `.venv` and installs packages.
- `run.py doctor` checks every requirement. `server.py` + `web/index.html` are the review studio.
- On Windows the pipeline uses: `engine/ocr_timeline.py` (RapidOCR, Chinese subtitle OCR on the GPU through DirectML, or CPU),
  `engine/translate.py` (Gemini through the `agy` CLI), Edge TTS Khmer voices, `engine/render_subs.py`
  (FFmpeg libass, correct Khmer shaping) and `engine/render_sample_universal.py` (FFmpeg libx264).
- The `.swift` files and `Start_25method.command` are for the Mac only. Ignore them.

## Steps

1. **Check what is installed** (report versions, change nothing yet):
   ```powershell
   python --version; git --version; ffmpeg -version | Select-Object -First 1; Get-Command agy -ErrorAction SilentlyContinue
   nvidia-smi
   ```
   Note: `python` may be only the Microsoft Store shortcut; that counts as not installed.

2. **Install what is missing** (ask me first):
   - Python 3.12 64-bit: `winget install Python.Python.3.12` (3.13+ is not supported by RapidOCR yet)
   - Git: `winget install Git.Git`
   - FFmpeg full build (needs `libx264` and `libass`): `winget install Gyan.FFmpeg`
   - Antigravity CLI: `irm https://antigravity.google/cli/install.ps1 | iex`, then I run `agy` once and sign in.
   - A Khmer font: Battambang or Kantumruy Pro (Google Fonts) or Khmer OS Battambang. I install it by right-click → Install.
   After installs, open a new PowerShell so PATH updates.

3. **Project location.** The project must be in a short path such as `C:\TTSKH` (long paths break `pip install`).
   If it is not there yet: `git clone https://github.com/PremMann/TTSKH C:\TTSKH`

4. **Environment.** Run `Setup_Windows.bat` in `C:\TTSKH`, or the same steps by hand:
   ```powershell
   cd C:\TTSKH
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-windows.txt
   ```

5. **Checks** (all from `C:\TTSKH`):
   ```powershell
   .\.venv\Scripts\python.exe run.py doctor
   .\.venv\Scripts\python.exe -m unittest discover -s tests
   .\.venv\Scripts\python.exe tests\smoke_movie.py
   agy models
   ```
   Expected:
   - doctor: everything `OK` except `source video` (that is fine until a movie is added), plus `INFO: OCR device: GPU (DirectML)`.
   - unittest: 21 of 22 pass. `test_long_line_blocks_without_truncation` is a known failure that is not Windows-related.
     Any other failure is real.
   - smoke test ends with `PASS: full audio, Khmer subtitle rendering, ...` (it runs real OCR on a generated clip; no online services).
   - `agy models` lists Gemini models. If it asks to sign in, tell me to run `agy` and sign in.

6. **Optional quick Gemini check** (ask me first, uses a tiny amount of quota):
   ```powershell
   agy --model gemini-3.8-flash-low --disable-slash-commands --print "Translate to Khmer, reply with Khmer only: 你好"
   ```
   It must print Khmer text. If the model name is not in `agy models`, use one that is and tell me, so I set it in
   the studio (Story, characters & recovery → Translation model).

7. **Start the studio:** double-click `Start_25method.bat`, or
   ```powershell
   .\.venv\Scripts\python.exe -X utf8 -u run.py serve --open-browser
   ```
   Keep that window open. The studio is at http://127.0.0.1:2525.

## Report back

List what you installed, the result of each check (pass / known failure / failed / skipped), and the exact command to start
the studio. Then remind me of the workflow below.

## Workflow in the studio (for me)

1. **+ Add movie**: pick the video, replace the (bracket) placeholders with the drama's characters, fixed English speaker names and voices.
2. Test a 3-minute clip first: **Prepare full review**. Progress shows under the buttons; **Stop** cancels.
3. **Picture layout**: check the cover hides the original subtitles (example for a Chinese line above an English line:
   OCR band 1180–1380, cover top 1200, height 212 hides only the Chinese line and leaves the English one visible).
   OCR and cover values are per drama.
4. Watch **Dubbed review**, fix speakers and lines, **Save corrections**, **Rebuild review**, then **Approve** and **Export**.

Speed on a 6-core PC with a DirectX 12 graphics card: OCR about 4x faster than real time on the GPU, rendering about real time
(roughly 1 hour 15 minutes for a 60-minute movie, including translation and voices). `run.py doctor` shows `INFO: OCR device`;
if it says CPU, run `Setup_Windows.bat` again (it installs `onnxruntime-directml`). With a recent NVIDIA driver,
setting `TTSKH_VIDEO_ENCODER=h264_nvenc` renders faster still.
