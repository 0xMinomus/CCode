#!/usr/bin/python3
"""Explicitly unavailable account backend for a local-only smoke test."""
from http.server import HTTPServer,BaseHTTPRequestHandler
import json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
LOG=ROOT/'runtime/no-login/account-backend-requests.jsonl'
class Handler(BaseHTTPRequestHandler):
 def request(self):
  record={'time':time.time(),'method':self.command,'path':self.path.split('?')[0]}
  with LOG.open('a') as f:f.write(json.dumps(record)+'\n')
  body=json.dumps({'error':'Account backend disabled for test','code':503}).encode()
  self.send_response(503);self.send_header('Content-Type','application/json');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 do_GET=request;do_POST=request;do_PUT=request;do_DELETE=request;do_OPTIONS=request
 def log_message(self,*args):pass
if __name__=='__main__':
 LOG.parent.mkdir(parents=True,exist_ok=True);print('Unavailable account backend on 127.0.0.1:28081',flush=True)
 HTTPServer(('127.0.0.1',28081),Handler).serve_forever()
