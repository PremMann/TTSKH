"""Real FFmpeg regressions; no online speech or translation requests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import workflow
from audio_safe import check_fit, build

class AudioTests(unittest.TestCase):
    def test_long_line_blocks_without_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);rate=24000;t=np.arange(rate*3)/rate
            # libsndfile detects WAV headers despite fixture's MP3 name.
            sf.write(root/'cue_0001.mp3',.2*np.sin(2*np.pi*220*t),rate,format='WAV')
            cues=[dict(id=1,start=0,end=.5,khmer_spoken='សួស្តី')]
            self.assertEqual(check_fit(cues,root,1)[0]['kind'],'speech_too_long')
            with self.assertRaises(ValueError):build(cues,root,root/'master.wav',1)
            self.assertFalse((root/'master.wav').exists())
    def test_streamed_audio_preserves_complete_clip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);rate=24000;t=np.arange(rate)/rate
            sf.write(root/'cue_0001.mp3',.2*np.sin(2*np.pi*220*t),rate,format='WAV')
            cues=[dict(id=1,start=.5,end=2,khmer_spoken='សួស្តី')]
            build(cues,root,root/'master.wav',3)
            data,sr=sf.read(root/'master.wav');self.assertAlmostEqual(len(data)/sr,3,places=2)
            self.assertGreater(np.max(np.abs(data[int(1.3*sr):int(1.4*sr)])),.01)
            self.assertLess(np.max(np.abs(data[:int(.4*sr)])),.001)

if __name__=='__main__':unittest.main()
