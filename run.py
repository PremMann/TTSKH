#!/usr/bin/env python3
"""25method: full-movie dubbing, review, correction and approved export."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
from workflow import Project, ROOT, validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['doctor','ocr','translate','tts','review','prepare','approve','render','export','serve'])
    parser.add_argument('--project',type=Path,default=ROOT/'project.json')
    parser.add_argument('--cue',type=int)
    parser.add_argument('--port',type=int,default=2525)
    parser.add_argument('--open-browser',action='store_true')
    args=parser.parse_args()
    if args.stage=='serve':
        from server import serve
        serve(args.port,open_browser=args.open_browser);return
    project=Project(args.project)
    if args.stage=='doctor':
        from workflow import use_swift
        checks={n:bool(shutil.which(n)) for n in ['ffmpeg','ffprobe','agy']}
        checks.update({n:importlib.util.find_spec(n) is not None for n in ['edge_tts','numpy','soundfile','PIL']})
        if use_swift():
            checks['swiftc (Apple Vision OCR)']=True
        else:
            checks['rapidocr_onnxruntime (OCR)']=importlib.util.find_spec('rapidocr_onnxruntime') is not None
            import subprocess
            try:filters=subprocess.run(['ffmpeg','-hide_banner','-filters'],capture_output=True,text=True,errors='replace').stdout
            except OSError:filters=''
            checks['ffmpeg libass (Khmer subtitles)']=' subtitles ' in filters
            sys.path.insert(0,str(ROOT/'engine'))
            from render_subs import find_font
            font=find_font();checks[f'Khmer font ({font or "none found"})']=bool(font)
        checks['source video']=project.source.is_file()
        for name,ok in checks.items():print(f'{"OK" if ok else "MISSING"}: {name}')
        return 0 if all(checks.values()) else 1
    if args.stage=='tts':project.tts(args.cue)
    else:getattr(project,{'review':'render_review','render':'export'}.get(args.stage,args.stage))()
    return 0


if __name__=='__main__':
    # Khmer/Chinese JSON needs UTF-8; Windows Python defaults to the ANSI code page.
    if os.name=='nt' and not sys.flags.utf8_mode and os.environ.get('PYTHONUTF8')!='0':
        import subprocess
        os.environ['PYTHONUTF8']='1'
        try:sys.exit(subprocess.call([sys.executable,'-X','utf8',*sys.argv]))
        except KeyboardInterrupt:sys.exit(130)
    try:sys.exit(main())
    except Exception as exc:
        print(f'STOP: {exc}',file=sys.stderr)
        sys.exit(1)
