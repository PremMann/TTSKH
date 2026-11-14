"""Project operations used by both CLI and local review server."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / 'engine'
sys.path.insert(0, str(ENGINE))
MAC = sys.platform == 'darwin'


def _extend_path():
    """Add the usual install folders of ffmpeg/agy/edge-tts for this OS to PATH."""
    home = Path.home()
    if os.name == 'nt':
        local = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
        extra = [local / 'agy' / 'bin', home / '.local' / 'bin', Path(sys.executable).parent]
    else:
        extra = [Path('/Applications/Gemini.app/Contents/Helpers'), home / '.local' / 'bin',
                 Path('/opt/homebrew/bin'), Path('/usr/local/bin')]
    current = os.environ.get('PATH', '')
    add = [str(p) for p in extra if p.is_dir() and str(p) not in current]
    if add:
        os.environ['PATH'] = os.pathsep.join(add + [current])


_extend_path()
VOICES = ('km-KH-PisethNeural', 'km-KH-SreymomNeural')


def atomic(file, value):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(file.suffix + '.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(file)


def replace_when_free(source, target, attempts=10):
    """os.replace that waits for Windows to release a target that is open in a player."""
    import time
    for attempt in range(attempts):
        try:
            return Path(source).replace(target)
        except PermissionError:
            if attempt == attempts-1:
                raise PermissionError(f'{Path(target).name} is open in another program (video player or browser). Close it and run the step again.')
            time.sleep(1)


def validate(cues, duration=None):
    if not isinstance(cues, list) or not cues:
        raise ValueError('Dialogue list is empty')
    seen, previous = set(), -1
    for c in cues:
        if type(c.get('id')) is not int or c['id'] < 1 or c['id'] in seen:
            raise ValueError('Cue IDs must be unique positive integers')
        seen.add(c['id'])
        start, end = float(c['start']), float(c['end'])
        if not all(math.isfinite(t) for t in (start,end)) or not 0 <= start < end or start < previous:
            raise ValueError(f'Cue {c["id"]}: invalid or unsorted timing')
        previous = start
        for prefix in ['sub', 'speech']:
            a, b = float(c.get(prefix+'_start',start)), float(c.get(prefix+'_end',end))
            if not all(math.isfinite(t) for t in (a,b)) or not 0 <= a < b or (duration is not None and b > duration + .01):
                raise ValueError(f'Cue {c["id"]}: invalid {prefix} timing')
        if duration is not None and end > duration + .01:
            raise ValueError(f'Cue {c["id"]}: exceeds movie duration')
        if c.get('is_spoken_dialogue') is False:
            continue
        if not c.get('speaker') or c.get('voice') not in VOICES:
            raise ValueError(f'Cue {c["id"]}: missing speaker or unsupported voice')
        text = c.get('khmer_spoken','')
        if not isinstance(text,str) or not re.search(r'[\u1780-\u17ff]',text) or re.search(r'[\u4e00-\u9fff]',text):
            raise ValueError(f'Cue {c["id"]}: speech must be Khmer, without Chinese text')
        if not re.fullmatch(r'[+-]\d+%', c.get('rate','+10%')) or not re.fullmatch(r'[+-]\d+Hz', c.get('pitch','+0Hz')):
            raise ValueError(f'Cue {c["id"]}: invalid voice rate or pitch')
    subtitles=sorted(cues,key=lambda c:float(c.get('sub_start',c['start'])))
    for left,right in zip(subtitles,subtitles[1:]):
        if float(right.get('sub_start',right['start'])) < float(left.get('sub_end',left['end']))-.001:
            raise ValueError(f'Subtitle overlap: cues {left["id"]} and {right["id"]}')
    from core.speech_timing import spoken_timeline
    spoken_timeline(cues, duration if duration is not None else max(float(c.get('speech_end',c['end'])) for c in cues))


def compile_swift(name):
    binary = ENGINE / ('auto_extract_timeline_bin' if name == 'auto_extract_timeline' else 'render_subs_bin')
    source = ENGINE / (name+'.swift')
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        cache = ROOT / 'work' / 'swift-cache'
        cache.mkdir(parents=True,exist_ok=True)
        subprocess.run(['swiftc','-module-cache-path',str(cache),'-O',str(source),'-o',str(binary)],check=True)
    return binary


def use_swift():
    """Apple Vision/CoreText engines on a Mac with swiftc; Python engines everywhere else."""
    return MAC and os.environ.get('TTSKH_ENGINE') != 'python' and bool(shutil.which('swiftc'))


def ocr_engine():
    """Return (command, source file) of the OCR engine for this machine."""
    if use_swift():
        return [str(compile_swift('auto_extract_timeline'))], ENGINE/'auto_extract_timeline.swift'
    script = ENGINE/'ocr_timeline.py'
    return [sys.executable, str(script)], script


def subtitle_engine():
    if use_swift():
        return [str(compile_swift('render_subs_universal'))]
    return [sys.executable, str(ENGINE/'render_subs.py')]


class Project:
    def __init__(self, config=ROOT/'project.json'):
        self.config = Path(config).resolve()
        self.home = self.config.parent
        self.cfg = json.loads(self.config.read_text(encoding='utf-8'))
        self.work = self.home/'work'
        self.work.mkdir(exist_ok=True)
        self.cues_file = self.work/'all_cues_master.json'
        self.clips = self.work/'tts'
    @property
    def preview(self):
        """Current review movie. Each rebuild writes a new file, because on Windows the
        review that is playing in the browser cannot be replaced while it is open."""
        stamp=self.work/'preview.json'
        if stamp.exists():
            try:
                name=json.loads(stamp.read_text(encoding='utf-8')).get('file')
                if name: return self.work/name
            except (ValueError,OSError): pass
        return self.work/'review.mp4'
    def remove_old_reviews(self):
        current=self.preview.name
        for old in list(self.work.glob('review_*.mp4'))+[self.work/'review.mp4']:
            if old.name!=current and old.exists():
                try: old.unlink()
                except OSError: pass   # still open in a player; removed after the next rebuild
    def path(self, value):
        p=Path(value)
        return p if p.is_absolute() else self.home/p
    @property
    def source(self): return self.path(self.cfg['source'])
    def duration(self):
        result=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(self.source)],text=True)
        duration=float(result)
        if not math.isfinite(duration) or duration <= 0: raise ValueError('Invalid source duration')
        return duration
    def cues(self): return json.loads(self.cues_file.read_text(encoding='utf-8'))
    def digest(self):
        h=hashlib.sha256(json.dumps([{k:v for k,v in c.items() if k != 'speaker_reviewed'} for c in self.cues()],sort_keys=True).encode())
        h.update(json.dumps(self.cfg,sort_keys=True).encode())
        for file in [self.source, self.path(self.cfg['character_prompt'])]:
            st=file.stat(); h.update(f'{file}:{st.st_size}:{st.st_mtime_ns}'.encode())
        return h.hexdigest()
    def save(self,cues):
        validate(cues,self.duration())
        if self.cues_file.exists():
            history=self.work/'history';history.mkdir(exist_ok=True)
            import time
            shutil.copy2(self.cues_file,history/f'{time.time_ns()}.json')
        # A character has one cast voice, pitch and rate across the movie.
        cast={}
        for cue in cues:
            if cue.get('is_spoken_dialogue') is not False:
                settings=(cue['voice'],cue.get('pitch','+0Hz'),cue.get('rate','+10%'))
                if cue['speaker'] in cast and cast[cue['speaker']] != settings:
                    raise ValueError(f'Conflicting voice settings for {cue["speaker"]}; apply the same casting to that character')
                cast[cue['speaker']]=settings
        atomic(self.cues_file,cues)
        if self.clips.exists():
            from audio_safe import check_fit
            atomic(self.work/'audio_issues.json',check_fit(cues,self.clips,self.duration()))
    def issues(self):
        cues=self.cues() if self.cues_file.exists() else []
        result=[]
        for c in cues:
            if c.get('is_spoken_dialogue') is not False and not c.get('speaker_reviewed'):
                result.append({'id':c['id'],'kind':'speaker','message':'Check speaker assignment against the scene.'})
            if len(c.get('khmer_sub',''))>85:
                result.append({'id':c['id'],'kind':'subtitle','message':'Long subtitle: check readability in playback.'})
        report=self.work/'audio_issues.json'
        if report.exists(): result.extend(json.loads(report.read_text(encoding='utf-8')))
        return result
    def ocr(self):
        st=self.source.stat()
        command,engine_source=ocr_engine()
        identity=[str(self.source),st.st_size,st.st_mtime_ns,self.cfg['ocr_workers'],self.cfg['ocr_y_min'],self.cfg['ocr_y_max'],hashlib.sha256(engine_source.read_bytes()).hexdigest()]
        stamp=self.work/'ocr_input.json'
        if stamp.exists() and json.loads(stamp.read_text(encoding='utf-8')) != identity:
            # Preserve previous extraction and its caches instead of reusing stale work.
            import time
            old=self.work/f'ocr_archive_{time.time_ns()}';old.mkdir()
            for f in ['ocr_chunks','full_visual_cues_raw.json']:
                if (self.work/f).exists(): shutil.move(str(self.work/f),str(old/f))
        atomic(stamp,identity)
        from parallel_extract_full_timeline import extract_full_timeline
        extract_full_timeline(str(self.source),str(self.work/'full_visual_cues_raw.json'),self.cfg['ocr_workers'],self.cfg['ocr_y_min'],self.cfg['ocr_y_max'],ocr_command=command)
        bands=[json.loads(f.read_text(encoding='utf-8')) for f in (self.work/'ocr_chunks').glob('*.band.json')]
        if bands:
            top=min(b['y'] for b in bands);bottom=max(b['y']+b['height'] for b in bands)
            atomic(self.work/'blur_suggestion.json',{'y':top,'height':bottom-top})

    def translate(self):
        import translate
        translate.SAMPLE15M_PATH=str(self.path(self.cfg['curated_cues'])) if self.cfg.get('curated_cues') else None
        if translate.SAMPLE15M_PATH: validate(json.loads(Path(translate.SAMPLE15M_PATH).read_text(encoding='utf-8')),self.duration())
        translate.RAW_VISUAL_PATH=str(self.work/'full_visual_cues_raw.json')
        translate.CACHE_DIR=str(self.work/'scene_cache')
        translate.MASTER_OUT_PATH=str(self.work/'translated_draft.json')
        translate.DRAMA_INSTRUCTIONS=self.path(self.cfg['character_prompt']).read_text(encoding='utf-8')
        translate.MODEL=self.cfg['model']
        translate.main()
        cues=json.loads(Path(translate.MASTER_OUT_PATH).read_text(encoding='utf-8'))
        # Fix each character's initial casting to its first assignment, reviewable in UI.
        cast={}
        for c in cues:
            cast.setdefault(c['speaker'],(c['voice'],c.get('pitch','+0Hz'),c.get('rate','+10%')))
            c['voice'],c['pitch'],c['rate']=cast[c['speaker']]
        self.save(cues)
    def tts(self, cue_id=None):
        from synthesize_tts_universal import synthesize_all_cues, synthesize_cue
        cues=self.cues();validate(cues,self.duration())
        self.clips.mkdir(exist_ok=True)
        if cue_id is not None:
            cue=next(c for c in cues if c['id']==cue_id)
            if synthesize_cue(cue,str(self.clips),{}) not in ('OK','SKIP'): raise ValueError('Voice generation failed')
        elif not synthesize_all_cues(str(self.cues_file),str(self.clips),self.cfg['tts_workers']):
            raise ValueError('Voice generation failed; retry after checking the log')
        from audio_safe import check_fit
        atomic(self.work/'audio_issues.json',check_fit(cues,self.clips,self.duration()))
    def render_review(self):
        from audio_safe import build
        from render_sample_universal import render_video
        from PIL import Image
        cues=self.cues();duration=self.duration();validate(cues,duration)
        self.tts()
        build(cues,self.clips,self.work/'master.wav',duration)
        y,height=int(self.cfg['blur_y_1080']),int(self.cfg['blur_height_1080'])
        if y<0 or height<2 or y+height>1920 or y%2 or height%2: raise ValueError('Blur values must be even and inside 1920 pixels')
        subs=self.work/'subtitles'
        if subs.exists(): shutil.rmtree(subs)
        subprocess.run([*subtitle_engine(),str(self.cues_file),str(subs),str(y),str(height),str(duration),'1080','1920'],check=True)
        watermark=self.path(self.cfg['watermark']) if self.cfg.get('watermark') else self.work/'transparent.png'
        if not self.cfg.get('watermark'): Image.new('RGBA',(2,2)).save(watermark)
        render_subs_flag = bool(self.cfg.get('render_subtitles', False))
        if render_subs_flag:
            for c in cues:
                if c.get('khmer_sub') and not (subs/f'cue_{c["id"]:04d}.png').is_file():
                    raise ValueError(f'Subtitle image missing for cue {c["id"]}')
        import time
        name=f'review_{time.time_ns()}.mp4'
        pending=self.work/(name+'.pending.mp4')
        render_video(str(self.source),str(self.work/'mask.png'),str(subs/'subs_sample.txt'),str(watermark),str(self.work/'master.wav'),str(pending),y,height,duration=duration,already_1080p=True,render_subtitles=render_subs_flag,progress_path=str(self.work/'render_progress.txt'))
        from qa_check import check_qa
        if not check_qa(str(self.cues_file),str(self.clips),str(self.work/'master.wav'),str(pending)):
            pending.unlink(missing_ok=True)
            raise ValueError('Final playback/audio QA failed; see task log')
        pending.replace(self.work/name)
        atomic(self.work/'preview.json',{'digest':self.digest(),'file':name})
        self.remove_old_reviews()
    def approve(self):
        validate(self.cues(),self.duration())
        stamp=self.work/'preview.json'
        if not self.preview.exists() or not stamp.exists() or json.loads(stamp.read_text(encoding='utf-8'))['digest']!=self.digest():
            raise ValueError('Generate and review the full movie after your latest changes before approving')
        if any(i['kind'] in ('speaker','speech_too_long','missing_audio') for i in self.issues()):
            raise ValueError('Confirm speaker assignments and fix speech issues first')
        atomic(self.work/'approval.json',{'digest':self.digest()})
    def export(self):
        self.approve_current()
        folder=self.home/'output';folder.mkdir(exist_ok=True)
        pending=folder/'25method_KhmerDub_1080p.pending.mp4'
        shutil.copy2(self.preview,pending)
        replace_when_free(pending,folder/'25method_KhmerDub_1080p.mp4')
    def approve_current(self):
        for name in ['approval.json','preview.json']:
            file=self.work/name
            if not file.exists() or json.loads(file.read_text(encoding='utf-8'))['digest']!=self.digest():
                raise ValueError('The current full review movie must be approved before export')
        if not self.preview.exists(): raise ValueError('Review movie missing')
    def prepare(self):
        if not self.cues_file.exists():
            self.ocr();self.translate()
        self.render_review()
