"""Convert sampled OCR regions into a conservative time-varying blur track."""
import math


def build_blur_track(boxes, samples, duration, source_height, fallback_y=820, fallback_h=160):
    scale = 1280 / max(1, source_height)
    regions = []
    for index, time in enumerate(samples):
        found = [b for b in boxes if int(b.get('frame', -1)) == index]
        if not found:
            continue
        top = min(b['top'] for b in found) * scale
        bottom = max(b['bottom'] for b in found) * scale
        regions.append({'time': float(time), 'y': max(0, int(top - 20)),
                        'height': max(130, min(400, int(bottom - top + 50)))})
    if not regions:
        return {'mode': 'fallback', 'sample_count': len(samples), 'regions': [
            {'start': 0, 'end': duration, 'y': fallback_y, 'height': fallback_h}]}
    track = []
    for index, region in enumerate(regions):
        start = 0 if index == 0 else (regions[index-1]['time'] + region['time']) / 2
        end = duration if index == len(regions)-1 else (region['time'] + regions[index+1]['time']) / 2
        track.append(dict(start=round(start, 3), end=round(end, 3), y=region['y'], height=region['height']))
    merged = []
    for region in track:
        if merged and abs(merged[-1]['y'] - region['y']) <= 8 and abs(merged[-1]['height'] - region['height']) <= 8:
            previous = merged[-1]
            bottom = max(previous['y'] + previous['height'], region['y'] + region['height'])
            previous['y'] = min(previous['y'], region['y'])
            previous['height'] = bottom - previous['y']
            previous['end'] = region['end']
        else:
            merged.append(region)
    # Keep expression depth bounded for long films, preserving full region coverage.
    while len(merged) > 60:
        combined = []
        for index in range(0, len(merged), 2):
            pair = merged[index:index+2]
            top = min(r['y'] for r in pair)
            bottom = max(r['y'] + r['height'] for r in pair)
            combined.append(dict(start=pair[0]['start'], end=pair[-1]['end'], y=top, height=bottom-top))
        merged = combined
    return {'mode': 'dynamic', 'sample_count': len(samples), 'regions': merged}


def blur_expressions(track, canvas_height, factor=1.5):
    regions = track.get('regions', [])
    if not regions:
        raise ValueError('Blur track has no regions')
    if len(regions) > 500:
        raise ValueError('Too many blur regions')
    # A stable crop height avoids reinitializing the filter graph every frame.
    height = max(2, min(canvas_height, math.ceil(max(r['height'] for r in regions) * factor / 2) * 2))
    positions = []
    for region in regions:
        start, end = float(region['start']), float(region['end'])
        y = max(0, min(canvas_height-height, math.floor(region['y'] * factor / 2) * 2))
        if not all(math.isfinite(x) for x in (start, end, y)) or end <= start:
            raise ValueError('Invalid dynamic blur interval')
        positions.append((start, end, y))
    expression = str(positions[-1][2])
    for start, end, y in reversed(positions[:-1]):
        expression = f'if(lt(t,{end:.3f}),{y},{expression})'
    return height, expression
