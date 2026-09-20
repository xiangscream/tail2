import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from tail2_mvp.bridge import Bridge, BridgeError
from tail2_mvp.events import Trace, read_events, read_state
from tail2_mvp.status import StatusServer

ECHO = "import sys,json\nfor l in sys.stdin:\n r=json.loads(l); print(json.dumps({'id':r['id'],'ok':True,'result':r}),flush=True)"


class TraceTests(unittest.TestCase):
    def test_event_state(self):
        with tempfile.TemporaryDirectory() as d, Trace(Path(d)) as t:
            t.emit("probe.request",{"op":"framing.set"})
            t.emit("probe.response",{"ok":True})
            s=read_state(Path(d)); self.assertIsNone(s["visual_check"])
            self.assertEqual(s["requested"]["op"],"framing.set")
            self.assertEqual(len(read_events(Path(d))),3)

    def test_single_writer_and_new_run(self):
        with tempfile.TemporaryDirectory() as d:
            with Trace(Path(d)) as t:
                old=t.run_id
                with self.assertRaises(RuntimeError): Trace(Path(d))
            with Trace(Path(d)) as t:
                self.assertNotEqual(old,t.run_id)
                self.assertEqual(read_state(Path(d))["run_id"],t.run_id)
                self.assertIsNone(read_state(Path(d))["sdk_reported"])

    def test_incomplete_line(self):
        with tempfile.TemporaryDirectory() as d, Trace(Path(d)):
            with (Path(d)/"events.jsonl").open("a") as f: f.write('{"incomplete":')
            self.assertEqual(len(read_events(Path(d))),1)


class BridgeTests(unittest.TestCase):
    def use(self, code):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        trace=Trace(Path(temp.name)); self.addCleanup(trace.close)
        b=Bridge([sys.executable,"-u","-c",code],trace); self.addCleanup(b.close)
        return b

    def test_correlated_request(self):
        b=self.use(ECHO)
        self.assertEqual(b.request("hello",request_id="first")["id"],"first")

    def test_duplicate(self):
        b=self.use(ECHO); b.request("capture.device",request_id="one")
        with self.assertRaises(ValueError): b.request("capture.device",request_id="one")

    def test_wrong_id(self):
        b=self.use("import sys,json\nfor l in sys.stdin: print(json.dumps({'id':'other','ok':True}),flush=True)")
        with self.assertRaises(BridgeError): b.request("hello")
        self.assertTrue(b.dead)

    def test_non_json_quarantines(self):
        b=self.use("import sys\nfor l in sys.stdin: print('sdk log on stdout',flush=True)")
        with self.assertRaises(BridgeError): b.request("hello")
        with self.assertRaises(BridgeError): b.request("hello")

    def test_timeout_indeterminate(self):
        b=self.use("import sys,time\nfor l in sys.stdin: time.sleep(5)")
        with self.assertRaises(BridgeError): b.request("capture.device",timeout=.1)
        self.assertEqual(read_events(b.trace.directory)[-1]["data"]["execution"],"indeterminate")

    def test_invalid_request(self):
        b=self.use(ECHO)
        for args in ([], {"x":float("nan")}):
            with self.assertRaises(ValueError): b.request("hello",args)
        with self.assertRaises(ValueError): b.request("hello",timeout=-1)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.server=StatusServer(Path(self.temp.name))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)

    def get(self,path="/",method="GET",headers=None):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
        try:
            c.request(method,path,headers=headers or {})
            r=c.getresponse(); return r.status,r.read(),dict(r.getheaders())
        finally: c.close()

    def test_empty_state(self):
        status,data,_=self.get("/api/state")
        self.assertEqual(status,200); self.assertEqual(json.loads(data)["agent"],"not_connected")

    def test_page_headers(self):
        status,data,headers=self.get()
        self.assertEqual(status,200); self.assertIn(b"Capability Observer",data)
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])

    def test_no_writes_or_files(self):
        for path in ("/../../README.md","/api/control","/private/frame.jpg"):
            self.assertEqual(self.get(path)[0],404)
        self.assertEqual(self.get("/api/state",method="POST")[0],405)

    def test_origin_host(self):
        self.assertEqual(self.get(headers={"Host":"evil.example"})[0],403)
        self.assertEqual(self.get(headers={"Origin":"https://evil.example"})[0],403)

    def test_events(self):
        with Trace(Path(self.temp.name)) as trace: trace.emit("probe.request",{"op":"hello"})
        status,data,_=self.get("/api/events")
        self.assertEqual(status,200); self.assertEqual(len(json.loads(data)),2)


@unittest.skipUnless(os.environ.get("TAIL2_PROBE"), "compiled native probe not supplied")
class NativeTests(unittest.TestCase):
    def run_lines(self, lines):
        p=subprocess.run([os.environ["TAIL2_PROBE"]],input="\n".join(lines)+"\n",text=True,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
        return [json.loads(line) for line in p.stdout.splitlines()]

    def test_hello(self):
        r=self.run_lines(['{"id":"1","op":"hello"}'])[0]
        self.assertTrue(r["ok"]); self.assertFalse(r["result"]["control_enabled"])

    def test_candidates_unknown(self):
        r=self.run_lines(['{"id":"1","op":"candidates.probe"}'])[0]
        self.assertEqual(r["result"]["status"],"UNKNOWN")
        self.assertFalse(r["result"]["callable_reader_found"])

    def test_bad_request(self):
        r=self.run_lines(['broken','{"id":"2","op":"hello"}'])
        self.assertFalse(r[0]["ok"]); self.assertTrue(r[1]["ok"])

    def test_duplicate_no_execution(self):
        r=self.run_lines(['{"id":"1","op":"hello"}','{"id":"1","op":"hello"}'])
        self.assertFalse(r[1]["ok"]); self.assertIn("duplicate",r[1]["error"])

    def test_no_selected_device(self):
        r=self.run_lines(['{"id":"1","op":"capture.device"}'])[0]
        self.assertFalse(r["ok"]); self.assertEqual(r["sdk_calls"],[])

    def test_shutdown(self):
        r=self.run_lines(['{"id":"1","op":"shutdown"}','{"id":"2","op":"hello"}'])
        self.assertEqual(len(r),1); self.assertTrue(r[0]["result"]["closed"])
