#!/usr/bin/env python3
"""25method: full-movie dubbing, review, correction and approved export."""
import argparse
import importlib.util
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
        checks={n:bool(shutil.which(n)) for n in ['ffmpeg','ffprobe','swiftc','agy']}
        checks.update({n:importlib.util.find_spec(n) is not None for n in ['edge_tts','numpy','soundfile','PIL']})
        checks['source video']=project.source.is_file()
        for name,ok in checks.items():print(f'{"OK" if ok else "MISSING"}: {name}')
        return 0 if all(checks.values()) else 1
    if args.stage=='tts':project.tts(args.cue)
    else:getattr(project,{'review':'render_review','render':'export'}.get(args.stage,args.stage))()
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(f'STOP: {exc}',file=sys.stderr)
        sys.exit(1)
