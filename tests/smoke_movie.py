"""Offline six-second OCR → audio → subtitles → rotated MP4 → approval/export test."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflow import Project, ROOT, atomic


def main():
    with nullcontext(tempfile.mkdtemp(prefix='25method-smoke-')) as directory:
        root=Path(directory)
        print('Fixture:', root, flush=True)
        frame=Image.new('RGB',(360,640),'#18324b');draw=ImageDraw.Draw(frame)
        draw.rectangle((0,0,180,160),fill='red')
        draw.rectangle((180,0,360,160),fill='lime')
        font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',48)
        draw.text((156,470),'好',font=font,fill='white')
        frame.save(root/'frame.png')
        subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-i',str(root/'frame.png'),'-t','6','-r','25','-pix_fmt','yuv420p',str(root/'source.mp4')],check=True)
        cfg=json.loads((ROOT/'project.json').read_text());cfg.update(source='source.mp4',character_prompt='characters.txt',ocr_workers=2,ocr_y_min=450,ocr_y_max=600,blur_y_1080=1380,blur_height_1080=280)
        (root/'characters.txt').write_text('Fixture only')
        atomic(root/'project.json',cfg)
        p=Project(root/'project.json')
        if '--skip-ocr' not in sys.argv:
            p.ocr()
            raw=json.loads((p.work/'full_visual_cues_raw.json').read_text())
            assert any(c['chinese']=='好' for c in raw),raw
            assert all(c['end']<=6 for c in raw)
        else:
            print('OCR intentionally skipped; this run verifies audio and rendering only')
        cues=[dict(id=1,start=.5,end=2,chinese='好',khmer_spoken='សួស្តី',khmer_sub='សួស្តី',speaker='Fixture',voice='km-KH-PisethNeural',rate='+10%',pitch='+0Hz',speaker_reviewed=True),dict(id=2,start=3,end=5,chinese='好',khmer_spoken='អរគុណ',khmer_sub='អរគុណ',speaker='Fixture',voice='km-KH-PisethNeural',rate='+10%',pitch='+0Hz',speaker_reviewed=True)]
        p.save(cues);p.clips.mkdir()
        for i in (1,2):
            rate=24000;t=np.arange(rate)/rate
            sf.write(root/f'tone{i}.wav',.18*np.sin(2*np.pi*(180+i*45)*t),rate)
            subprocess.run(['ffmpeg','-v','error','-y','-i',str(root/f'tone{i}.wav'),str(p.clips/f'cue_{i:04d}.mp3')],check=True)
        with patch.object(p,'tts'):
            p.render_review()
        p.approve();p.export()
        final=p.home/'output/25method_KhmerDub_1080p.mp4'
        media=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)]))
        v=next(s for s in media['streams'] if s['codec_type']=='video');a=next(s for s in media['streams'] if s['codec_type']=='audio')
        assert (v['width'],v['height'])==(1920,1080)
        assert int(a['sample_rate'])==48000
        assert abs(float(media['format']['duration'])-6)<.15
        # Verify 270° clockwise placement: red top-left becomes lower-left.
        subprocess.run(['ffmpeg','-v','error','-y','-ss','1','-i',str(final),'-frames:v','1',str(root/'result.png')],check=True)
        picture=Image.open(root/'result.png');r,g,b=picture.getpixel((100,950));assert r>g*2 and r>b*2,(r,g,b)
        r,g,b=picture.getpixel((100,100));assert g>r*2 and g>b*2,(r,g,b)
        # Persist a non-user fixture frame in /tmp for visual QA only.
        picture.save('/tmp/25method-smoke-render.png')
        print('PASS: full audio, Khmer subtitle rendering, 270-degree rotation, 1080p/48kHz playback, approval and export')

if __name__=='__main__':main()
