import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflow import Project, validate, atomic
from engine.parallel_extract_full_timeline import run_chunk


def cue(**updates):
    return dict(dict(id=1,start=0,end=1,speaker='Yan Jin',voice='km-KH-PisethNeural',khmer_spoken='សួស្តី',khmer_sub='សួស្តី',pitch='-4Hz',rate='+10%',speaker_reviewed=False),**updates)

class WorkflowTests(unittest.TestCase):
    def test_valid_cue(self):validate([cue()],2)
    def test_invalid_actual_timing(self):
        for update in [dict(speech_start=-1),dict(speech_end=3),dict(sub_start=float('nan')),dict(sub_end=0),dict(id='../bad'),dict(rate='fast')]:
            with self.subTest(update=update),self.assertRaises(ValueError):validate([cue(**update)],2)
    def test_overlap(self):
        with self.assertRaises(ValueError):validate([cue(),cue(id=2,start=.5,end=1.5)],2)
    def test_screen_text(self):validate([cue(is_spoken_dialogue=False,khmer_spoken='',speaker='',voice='')],2)
    def test_duplicate(self):
        with self.assertRaises(ValueError):validate([cue(),cue()],2)
    def test_ocr_failure_retries_and_blocks(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d,patch('engine.parallel_extract_full_timeline.subprocess.run',side_effect=subprocess.CalledProcessError(2,'ocr')) as mock:
            with self.assertRaises(RuntimeError):run_chunk('ocr','video',str(Path(d)/'chunk.json'),0,0,0,1)
            self.assertEqual(mock.call_count,3)
            self.assertFalse((Path(d)/'chunk.json.complete').exists())
    def test_empty_successful_chunk_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/'chunk.json'
            with patch('engine.parallel_extract_full_timeline.subprocess.run',side_effect=lambda *a,**k:dest.write_text('[]')):
                self.assertEqual(run_chunk('ocr','video',str(dest),0,0,0,1)[2],0)
            self.assertTrue(Path(str(dest)+'.complete').exists())
    def test_approval_requires_current_review_and_checked_speakers(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);(home/'source.mp4').write_bytes(b'source');(home/'characters.txt').write_text('story')
            atomic(home/'project.json',{'source':'source.mp4','character_prompt':'characters.txt'})
            p=Project(home/'project.json');atomic(p.cues_file,[cue()])
            with patch.object(p,'duration',return_value=2):
                with self.assertRaises(ValueError):p.approve()
                p.preview.write_bytes(b'review');atomic(p.work/'preview.json',{'digest':p.digest()})
                with self.assertRaises(ValueError):p.approve()
                original=p.digest();atomic(p.cues_file,[cue(speaker_reviewed=True)])
                self.assertEqual(original,p.digest())
                p.approve();p.export()
                self.assertTrue((home/'output/25method_KhmerDub_1080p.mp4').exists())
                atomic(p.cues_file,[cue(speaker_reviewed=True,khmer_spoken='អរគុណ')])
                with self.assertRaises(ValueError):p.export()
    def test_cast_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);atomic(home/'project.json',{})
            p=Project(home/'project.json')
            with patch.object(p,'duration',return_value=4),self.assertRaises(ValueError):p.save([cue(),cue(id=2,start=2,end=3,voice='km-KH-SreymomNeural')])

if __name__=='__main__':unittest.main()
