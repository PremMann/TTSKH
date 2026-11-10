import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from workflow import atomic, ROOT

class Socket:
    def __init__(self,request):self.input=io.BytesIO(request);self.output=bytearray()
    def makefile(self,*args):return self.input
    def sendall(self,data):self.output.extend(data)


def request(path,body=None,token=True,extra=None):
    content=json.dumps(body).encode() if body is not None else b''
    headers={'Host':'127.0.0.1:2525','Content-Length':str(len(content))}
    if token:headers['X-25method-Token']=server.TOKEN
    headers.update(extra or {})
    raw=(('POST' if body is not None else 'GET')+' '+path+' HTTP/1.0\r\n'+'\r\n'.join(k+': '+v for k,v in headers.items())+'\r\n\r\n').encode()+content
    sock=Socket(raw);server.Handler(sock,('127.0.0.1',999),SimpleNamespace(server_port=2525))
    head,payload=bytes(sock.output).split(b'\r\n\r\n',1)
    return int(head.split()[1]),payload

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'source.mp4').write_bytes(b'0123456789')
        (self.root/'characters.txt').write_text('Story')
        cfg=json.loads((ROOT/'project.json').read_text());cfg['source']=str(self.root/'source.mp4');cfg['character_prompt']=str(self.root/'characters.txt')
        atomic(self.root/'project.json',cfg)
        self.patch=patch.multiple(server,ROOT=self.root,STATE=self.root/'queue.json',JOBS=[{'id':'a','config':str(self.root/'project.json'),'name':'A','status':'new'}],TASKS=[],ACTIVE=None)
        self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_post_requires_token(self):self.assertEqual(request('/api/remove',{'job':'a'},token=False)[0],403)
    def test_host_guard(self):self.assertEqual(request('/api/state',extra={'Host':'evil.test'})[0],403)
    def test_video_range(self):
        status,body=request('/media?job=a&kind=source',extra={'Range':'bytes=2-5'})
        self.assertEqual((status,body),(206,b'2345'))
    def test_enqueue_and_busy_save(self):
        self.assertEqual(request('/api/enqueue',{'jobs':['a'],'stage':'prepare'})[0],200)
        self.assertEqual(server.TASKS,[{'job':'a','stage':'prepare','cue':None}])
        self.assertEqual(request('/api/save',{'job':'a','cues':[]})[0],400)
        self.assertEqual(request('/api/enqueue',{'jobs':['a'],'stage':'review'})[0],400)
    def test_unapproved_export_not_queued(self):
        self.assertEqual(request('/api/enqueue',{'jobs':['a'],'stage':'export'})[0],400)
        self.assertEqual(server.TASKS,[])
    def test_add_movie_and_limit(self):
        for n in range(9):self.assertEqual(request('/api/add',{'source':str(self.root/'source.mp4'),'name':str(n)})[0],200)
        self.assertEqual(request('/api/add',{'source':str(self.root/'source.mp4')})[0],400)
        self.assertEqual(len(server.JOBS),10)
    def test_settings_bounds(self):self.assertEqual(request('/api/settings',{'job':'a','blur_y_1080':1900,'blur_height_1080':200})[0],400)
    def test_sequential_queue_order(self):
        server.JOBS.append({'id':'b','config':str(self.root/'project.json'),'name':'B','status':'new'})
        self.assertEqual(request('/api/enqueue',{'jobs':['b','a'],'stage':'review'})[0],200)
        self.assertEqual([t['job'] for t in server.TASKS],['b','a'])

if __name__=='__main__':unittest.main()
