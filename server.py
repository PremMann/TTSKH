"""Loopback review app. One background process runs at a time."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs
from workflow import Project, ROOT, atomic

STATE=ROOT/'work'/'queue.json'
LOCK=threading.RLock()
TOKEN=secrets.token_urlsafe(24)
JOBS=[]
TASKS=[]
ACTIVE=None


def persist():atomic(STATE,{'jobs':JOBS,'tasks':TASKS})
def get_job(key):
    return next(j for j in JOBS if j['id']==key)
def get_project(key):return Project(get_job(key)['config'])
def busy(key):return ACTIVE==key or any(t['job']==key for t in TASKS)


def worker():
    global ACTIVE
    while True:
        with LOCK:
            task=TASKS.pop(0) if TASKS else None
            if task:
                job=get_job(task['job']);ACTIVE=job['id'];job.update(status='running',stage=task['stage'],error='');persist()
        if not task:
            time.sleep(.3);continue
        try:
            project=Project(job['config'])
            log=project.work/'task.log'
            command=[sys.executable,'-u',str(ROOT/'run.py'),task['stage'],'--project',job['config']]
            if task.get('cue') is not None: command+=['--cue',str(task['cue'])]
            with log.open('w') as stream:
                result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
            ok=result.returncode==0
            detail='\n'.join(log.read_text(errors='replace').splitlines()[-8:])
        except Exception as exc:ok=False;detail=str(exc)
        with LOCK:
            job.update(status=('ready' if ok else 'needs attention'),error=('' if ok else detail))
            ACTIVE=None;persist()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def json(self,obj,status=200):
        data=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def allowed_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def file(self,path):
        path=Path(path)
        size=path.stat().st_size
        start,end=0,size-1
        requested=self.headers.get('Range')
        if requested:
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
            if not match:
                self.send_error(416);return
            start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
            if start> end:self.send_error(416);return
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type',mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store')
        if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as stream:
            stream.seek(start);remaining=end-start+1
            while remaining:
                data=stream.read(min(1024*1024,remaining))
                if not data:break
                self.wfile.write(data);remaining-=len(data)
    def do_GET(self):
        if not self.allowed_host():self.send_error(403);return
        parsed=urlparse(self.path);params=parse_qs(parsed.query)
        try:
            if parsed.path=='/':return self.file(ROOT/'web'/'index.html')
            if parsed.path=='/api/state':
                with LOCK:return self.json({'jobs':JOBS,'tasks':TASKS,'active':ACTIVE,'token':TOKEN})
            project=get_project(params['job'][0])
            if parsed.path=='/api/project':
                cues=project.cues() if project.cues_file.exists() else []
                current=False
                stamp=project.work/'preview.json'
                if stamp.exists() and project.cues_file.exists():current=json.loads(stamp.read_text())['digest']==project.digest()
                log=project.work/'task.log'
                return self.json({'cues':cues,'characters':project.path(project.cfg['character_prompt']).read_text(),'suggestion':json.loads((project.work/'blur_suggestion.json').read_text()) if (project.work/'blur_suggestion.json').exists() else None,'config':project.cfg,'issues':project.issues(),'exported':(project.home/'output'/'25method_KhmerDub_1080p.mp4').exists(),'preview':project.preview.exists(),'current':current,'log':log.read_text(errors='replace')[-12000:] if log.exists() else ''})
            if parsed.path=='/media':
                kind=params.get('kind',['source'])[0]
                if kind=='source':file=project.source
                elif kind=='review':file=project.preview
                elif kind=='audio':file=project.clips/f'cue_{int(params["cue"][0]):04d}.mp3'
                elif kind=='output':file=project.home/'output'/'25method_KhmerDub_1080p.mp4'
                elif kind=='frame':file=project.work/'layout.jpg'
                else:raise ValueError('Unknown media')
                return self.file(file)
            self.send_error(404)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.json({'error':str(exc)},400)
    def do_POST(self):
        if not self.allowed_host() or self.headers.get('X-25method-Token')!=TOKEN:
            self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length>8*1024*1024:raise ValueError('Request too large')
            data=json.loads(self.rfile.read(length))
            with LOCK:
                if self.path=='/api/add':
                    source=Path(data['source']).expanduser().resolve()
                    if not source.is_file():raise ValueError('Source video path does not exist')
                    if len(JOBS)>=10:raise ValueError('Queue supports up to 10 movies; remove a finished job first')
                    key=secrets.token_hex(6);home=ROOT/'jobs'/key;home.mkdir(parents=True)
                    cfg=json.loads((ROOT/'project.json').read_text());cfg['source']=str(source)
                    cfg['curated_cues']=None;cfg['character_prompt']=str(home/'characters.txt')
                    (home/'characters.txt').write_text(data.get('characters') or (ROOT/'characters.txt').read_text())
                    atomic(home/'project.json',cfg)
                    JOBS.append({'id':key,'name':data.get('name') or source.stem,'config':str(home/'project.json'),'status':'new','stage':'','error':''});persist()
                    return self.json({'id':key})
                if self.path=='/api/enqueue':
                    stage=data['stage']
                    if stage not in ['prepare','ocr','translate','tts','review','export']:raise ValueError('Unknown stage')
                    keys=data['jobs']
                    if not 1<=len(keys)<=10 or len(set(keys))!=len(keys):raise ValueError('Select 1–10 different movies')
                    for key in keys:
                        get_job(key)
                        if busy(key):raise ValueError('Movie already queued or running')
                        if stage=='export':get_project(key).approve_current()
                    for key in keys:
                        TASKS.append({'job':key,'stage':stage,'cue':data.get('cue')});get_job(key)['status']='queued'
                    persist();return self.json({'ok':True})
                key=data['job'];project=get_project(key)
                if busy(key):raise ValueError('Wait for this movie’s current task to finish before editing')
                if self.path=='/api/save':project.save(data['cues'])
                elif self.path=='/api/approve':project.approve();get_job(key)['status']='approved';persist()
                elif self.path=='/api/remove':
                    JOBS.remove(get_job(key));persist() # Files intentionally retained.
                elif self.path=='/api/settings':
                    cfg=project.cfg.copy()
                    for name in ['blur_y_1080','blur_height_1080','ocr_y_min','ocr_y_max','model']:
                        if name in data:cfg[name]=data[name]
                    y,h=int(cfg['blur_y_1080']),int(cfg['blur_height_1080'])
                    if y<0 or h<2 or y+h>1920 or y%2 or h%2:raise ValueError('Blur bounds must be even and fit inside 1920 pixels')
                    atomic(project.config,cfg)
                    if 'characters' in data:project.path(cfg['character_prompt']).write_text(data['characters'])
                elif self.path=='/api/layout':
                    t=max(0,min(float(data.get('time',0)),project.duration()-.05))
                    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(project.source),'-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2','-frames:v','1',str(project.work/'layout.jpg')],check=True)
                else:raise ValueError('Unknown operation')
                return self.json({'ok':True})
        except Exception as exc:self.json({'error':str(exc)},400)


def serve(port=2525,open_browser=False):
    global JOBS,TASKS
    ROOT.joinpath('work').mkdir(exist_ok=True)
    if STATE.exists():
        state=json.loads(STATE.read_text());JOBS=state['jobs'];TASKS=[]
        for job in JOBS:
            if job['status'] in ('running','queued'):
                job.update(status='interrupted',error='Server restarted. Retry the stage shown; cached work is retained.')
    else:
        JOBS=[{'id':'default','name':'Movie 25 method','config':str(ROOT/'project.json'),'status':'new','stage':'','error':''}] if Project(ROOT/'project.json').source.is_file() else []
    persist()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=worker,daemon=True).start()
    print(f'25method: http://127.0.0.1:{port}',flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(.5,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
    server.serve_forever()

if __name__=='__main__':serve()
