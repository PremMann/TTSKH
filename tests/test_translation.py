import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import translate

class TranslationTests(unittest.TestCase):
    def test_short_replies_and_separate_speakers_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/'raw.json';output=root/'master.json'
            cues=[{'id':i+1,'start':float(i),'end':i+.75,'chinese':text} for i,text in enumerate(['好','不好','你好','你好啊']*4)]
            raw.write_text(json.dumps(cues),encoding='utf-8')
            seen=[]
            def batch(entries,index,total,context=None):
                seen.append((entries,context));return entries
            with patch.multiple(translate,SAMPLE15M_PATH=None,RAW_VISUAL_PATH=str(raw),MASTER_OUT_PATH=str(output),CACHE_DIR=str(root/'cache')),patch.object(translate,'translate_batch',side_effect=batch):
                translate.main()
            result=json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual([c['chinese'] for c in result],[c['chinese'] for c in cues])
            self.assertEqual([c['original_ids'] for c in result],[[i+1] for i in range(16)])
            self.assertTrue(all(context for _,context in seen))
    def test_wrong_ids_rejected(self):
        import subprocess
        entries=[dict(id=1,start=0,end=1,duration=1,chinese='好')]
        result=subprocess.CompletedProcess([],0,stdout=json.dumps([dict(id=99,khmer_spoken='សួស្តី',speaker='Yan',voice='km-KH-PisethNeural')]),stderr='')
        with tempfile.TemporaryDirectory() as d,patch.object(translate,'CACHE_DIR',d),patch.object(translate.subprocess,'run',return_value=result) as run,patch.object(translate.time,'sleep'):
            self.assertIsNone(translate.translate_batch(entries,1,1))
            self.assertEqual(run.call_count,3)
    def test_changed_prompt_invalidates_cache(self):
        import subprocess
        entries=[dict(id=1,start=0,end=1,duration=1,chinese='好')]
        result=subprocess.CompletedProcess([],0,stdout=json.dumps([dict(id=1,khmer_spoken='សួស្តី',speaker='Yan',voice='km-KH-PisethNeural')]),stderr='')
        with tempfile.TemporaryDirectory() as d,patch.object(translate,'CACHE_DIR',d),patch.object(translate.subprocess,'run',return_value=result) as run:
            translate.translate_batch(entries,1,1)
            translate.translate_batch(entries,1,1)
            self.assertEqual(run.call_count,1)
            with patch.object(translate,'DRAMA_INSTRUCTIONS','changed story'):
                translate.translate_batch(entries,1,1)
            self.assertEqual(run.call_count,2)

if __name__=='__main__':unittest.main()
