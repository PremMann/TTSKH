# Verification — 9 November 2026

## Passed

- 22 automated regression tests covering real streamed audio, prevention of truncated speech, OCR worker retries/failed chunks, single-character entry retention, conservative cleanup, translation context/caching/ID checks, speech/subtitle validation, character casting, review approval and invalidation, API host/token checks, video range reads, queue order/limits, busy edit protection, and export gating.
- Python syntax compilation, module imports and CLI argument parsing.
- JavaScript syntax check of the browser interface.
- Both Swift processing tools compiled on this Mac. The inherited AVFoundation calls produce deprecation warnings on newer macOS versions.
- Real six-second offline render with generated image/video and tone clips: CoreText Khmer subtitle images, disk-streamed complete speech, 270° clockwise rotation, 1920×1080 video, 48 kHz audio, approximately six-second duration, −14.0 LUFS loudness, decoding, review approval and export.
- Hardware encoding was unavailable in the test environment; software H.264 fallback completed successfully.
- The generated frame was visually inspected for subtitle presence and rotation. Preferred Khmer fonts were absent; macOS font fallback produced Khmer glyphs.

## Not verified here

- Full OCR on actual video: AVFoundation returned Cannot Decode / OSStatus −12911 under this environment. Worker failures correctly retried and stopped the pipeline. The smoke test's separate audio/render mode passed; it does not count as an OCR pass.
- A live browser session: this environment denied binding a localhost server port, and the browser blocked local file URLs. Request handlers were exercised in process, including byte-range video responses, but visual/browser interaction verification remains outstanding.
- Online agy translation/model availability and Edge TTS: no live service calls were made. Synthetic clips were used for offline rendering tests.
- A complete production movie: no source movie was supplied for 25method.

Run `python tests/smoke_movie.py` on the host Mac to exercise OCR and rendering together, then use the source movie for full production acceptance. The launcher opens the browser only after the server binds successfully.
