"""Canonical spoken timeline shared by mixing and quality checks."""
import math


def spoken_timeline(cues, total_duration):
    if not math.isfinite(total_duration) or total_duration <= 0:
        raise ValueError('Invalid master duration')
    spoken = []
    seen = set()
    for cue in cues:
        if cue.get('is_spoken_dialogue') is False:
            continue
        text = (cue.get('khmer_spoken') or '').strip()
        if text in ('', '-', '—'):
            if cue.get('is_spoken_dialogue') is True:
                raise ValueError(f"Spoken cue {cue['id']} has no speech text")
            continue
        start = float(cue.get('speech_start', cue.get('start', 0)))
        end = float(cue.get('speech_end', cue.get('end', 0)))
        if cue['id'] in seen:
            raise ValueError(f"Duplicate speech cue {cue['id']}")
        seen.add(cue['id'])
        if not all(math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= total_duration + 0.05:
            raise ValueError(f"Cue {cue['id']} has invalid speech timing: {start}–{end}")
        spoken.append(dict(cue, start=start, end=min(end, total_duration), speech_start=start, speech_end=min(end, total_duration)))
    spoken.sort(key=lambda cue: cue['start'])
    for previous, current in zip(spoken, spoken[1:]):
        if current['start'] < previous['end'] - 0.05:
            raise ValueError(f"Speech overlap: cues {previous['id']} and {current['id']}")
    return spoken
