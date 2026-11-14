"""Stream dialogue to disk; never discard the end of a spoken line."""
import json
import math
import re
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from build_audio_universal import trim_silence
from core.speech_timing import spoken_timeline
from pipeline_config import AUDIO_SAMPLE_RATE, ATEMPO_CAP, MAX_SILENCE_BORROW


def windows(cues, duration):
    speech = spoken_timeline(cues, duration)
    for i, cue in enumerate(speech):
        limit = speech[i+1]['start'] if i+1 < len(speech) else duration
        available = min(limit, cue['end'] + MAX_SILENCE_BORROW) - cue['start']
        if available <= 0:
            raise ValueError(f'Cue {cue["id"]}: no available speech window')
        yield cue, available


def check_fit(cues, clips, duration):
    issues = []
    for cue, available in windows(cues, duration):
        try:
            data, sr = sf.read(Path(clips) / f'cue_{cue["id"]:04d}.mp3', dtype='float32')
            actual = len(trim_silence(data, sr)) / sr
            speed = max(1, actual / available)
            if speed > ATEMPO_CAP:
                issues.append({'id': cue['id'], 'kind': 'speech_too_long', 'message': f'Needs {speed:.2f}× speed; shorten the Khmer line or extend its timing.', 'seconds': actual, 'available': available})
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append({'id': cue['id'], 'kind': 'missing_audio', 'message': str(exc)})
    return issues


def build(cues, clips, output, duration):
    output = Path(output)
    issues = check_fit(cues, clips, duration)
    (output.parent / 'audio_issues.json').write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding='utf-8')
    fatal = [i for i in issues if i.get('kind') == 'missing_audio']
    if fatal:
        raise ValueError(f'{len(fatal)} missing audio files must be corrected; see audio_issues.json')
    sr = AUDIO_SAMPLE_RATE
    raw = output.with_name('master_raw.wav')
    silence = np.zeros((sr, 2), dtype=np.float32)
    cursor = 0
    with sf.SoundFile(raw, 'w', samplerate=sr, channels=2, subtype='PCM_24') as writer:
        def pad(count):
            while count > 0:
                size = min(count, sr)
                writer.write(silence[:size])
                count -= size
        for cue, available in windows(cues, duration):
            target = round(cue['start'] * sr)
            if target < cursor:
                target = cursor
            pad(target - cursor)
            source = Path(clips) / f'cue_{cue["id"]:04d}.mp3'
            data, rate = sf.read(source, dtype='float32')
            trimmed = trim_silence(data, rate)
            speed = max(1.0, len(trimmed) / rate / available)
            # Feed trimmed PCM so encoder silence does not distort the fit calculation.
            result = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'f32le', '-ar', str(rate), '-ac', '2', '-i', 'pipe:0', '-af', f'atempo={speed:.8f}', '-ar', str(sr), '-ac', '2', '-f', 'f32le', 'pipe:1'], input=trimmed.astype('<f4').tobytes(), capture_output=True, check=True)
            audio = np.frombuffer(result.stdout, dtype='<f4').reshape(-1, 2).copy()
            # Clip any tiny sub-frame FFmpeg rounding drift to available window
            limit = round(available * sr)
            if len(audio) > limit:
                audio = audio[:limit]
            fade = min(round(.01 * sr), len(audio)//2)
            if fade:
                audio[:fade] *= np.linspace(0, 1, fade)[:, None]
                audio[-fade:] *= np.linspace(1, 0, fade)[:, None]
            writer.write(audio)
            cursor = target + len(audio)
        pad(round(duration * sr) - cursor)
    measurement = subprocess.run(['ffmpeg', '-v', 'info', '-i', str(raw), '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    stats = json.loads(re.findall(r'\{[^{}]+\}', measurement.stderr)[-1])
    if not all(math.isfinite(float(stats[k])) for k in ['input_i','input_tp','input_lra','input_thresh','target_offset']):
        raise ValueError('Loudness measurement is invalid')
    filt = f'loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:measured_I={stats["input_i"]}:measured_TP={stats["input_tp"]}:measured_LRA={stats["input_lra"]}:measured_thresh={stats["input_thresh"]}:offset={stats["target_offset"]}'
    pending = output.with_name('master_pending.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-af', filt, '-ar', str(sr), '-ac', '2', str(pending)], check=True)
    if abs(sf.info(pending).duration - duration) > .05:
        raise ValueError('Master audio duration mismatch')
    pending.replace(output)
    raw.unlink()
    return str(output)
