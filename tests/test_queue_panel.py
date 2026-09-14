import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audio_design as audio
import delivery as q
import notify as n
import panel


class SoundDesign(unittest.TestCase):
    def test_cli_custom_design_and_exclusive_export(self):
        with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()):
            home=Path(d)
            with patch.object(n,'conflicts',return_value=[]):n.install(home)
            script=home/'skills/codex-soft-notify/scripts/notify.py'
            base=[sys.executable,str(script)]
            custom=subprocess.run(base+['design','approval','--notes','420,620,820','--note-ms','200','--gap-ms','30'],capture_output=True,text=True)
            self.assertEqual(custom.returncode,0,custom.stderr)
            target=home/'custom.wav'
            export=subprocess.run(base+['export-sound','approval',str(target)],capture_output=True,text=True)
            self.assertEqual(export.returncode,0,export.stderr)
            with wave.open(str(target)) as w:self.assertAlmostEqual(w.getnframes()/w.getframerate(),.66,places=3)
            first=target.read_bytes()
            repeated=subprocess.run(base+['export-sound','approval',str(target)],capture_output=True,text=True)
            self.assertNotEqual(repeated.returncode,0)
            self.assertEqual(target.read_bytes(),first)
    def test_command_paths_are_shell_quoted(self):
        command=n.hook_command(Path('C:/Example & Work/声音'))
        self.assertIn('"C:',command)
        self.assertIn(' hook',command)
        with self.assertRaises(ValueError):n.hook_command(Path('C:/unsafe%PATH%'))
    def test_design_duration_exportable_pcm(self):
        design={'notes':[500,700,900],'note_ms':200,'gap_ms':100}
        with wave.open(io.BytesIO(audio.render('completion', .2, 'soft', design))) as w:
            self.assertEqual(w.getnframes(),round(.8*w.getframerate()))
            self.assertEqual(w.getcomptype(),'NONE')

    def test_invalid_design_values(self):
        good={'notes':[500],'note_ms':300,'gap_ms':50}
        for bad in ({'notes':[]},{'notes':[0]},{'notes':[float('nan')]},{'notes':[True]},
                    {'notes':[500]*5},{'note_ms':119},{'note_ms':300.5},{'gap_ms':201}):
            with self.subTest(bad=bad),self.assertRaises(ValueError): audio.validate_design(good|bad)
        for volume in [float('nan'),float('inf'),-1,True]:
            with self.assertRaises(ValueError): audio.render('completion',volume)

    def test_invalid_save_preserves_old_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);n.save_settings(root,n.DEFAULT)
            previous=(root/'settings.json').read_bytes()
            with self.assertRaises(ValueError): n.save_settings(root,n.DEFAULT|{'volume':3})
            self.assertEqual(previous,(root/'settings.json').read_bytes())


class Queue(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def run_queue(self, calls, **kwargs):
        return q.drain(self.root, lambda event,config:calls.append(event), lambda root:n.DEFAULT, **kwargs)

    def test_approval_priority_and_fifo(self):
        base=100.0
        for index,event in enumerate(['completion','approval','completion','approval']):
            q.enqueue(self.root,event,now=base+index*.01)
        calls=[];self.run_queue(calls,now=lambda:base+1)
        self.assertEqual(calls,['approval','approval','completion','completion'])

    def test_fairness_for_old_completion(self):
        q.enqueue(self.root,'completion',now=90);q.enqueue(self.root,'approval',now=99)
        calls=[];self.run_queue(calls,now=lambda:100)
        self.assertEqual(calls,['completion','approval'])

    def test_dedupe_only_explicit_same_request(self):
        payload={'session_id':'one','turn_id':'turn','request_id':'request'}
        self.assertIsNotNone(q.enqueue(self.root,'approval',payload=payload,now=100))
        self.assertIsNone(q.enqueue(self.root,'approval',payload=payload,now=101))
        self.assertIsNotNone(q.enqueue(self.root,'approval',payload=payload|{'request_id':'different'},now=102))
        self.assertIsNotNone(q.enqueue(self.root,'approval',payload=payload|{'session_id':'two'},now=102))
        self.assertIsNotNone(q.enqueue(self.root,'approval',payload=payload,now=132))
        for _ in range(2):self.assertIsNotNone(q.enqueue(self.root,'approval',payload={'turn_id':'same'}))
        self.assertEqual(q.snapshot(self.root)['counters']['duplicates'],1)

    def test_expired_and_crashed_not_replayed(self):
        first=q.enqueue(self.root,'completion',now=1)
        second=q.enqueue(self.root,'approval',now=500)
        db=q.connect(self.root);db.execute("UPDATE jobs SET state='playing' WHERE id=?",(second,));db.commit();db.close()
        calls=[];self.run_queue(calls,now=lambda:501)
        self.assertEqual(calls,[])
        self.assertEqual({r['state'] for r in q.snapshot(self.root)['recent']},{'interrupted','expired'})

    def test_failure_does_not_block_next_event(self):
        q.enqueue(self.root,'approval');q.enqueue(self.root,'completion')
        def player(event,config):
            if event=='approval': raise OSError('device gone')
        q.drain(self.root,player,lambda root:n.DEFAULT)
        self.assertEqual({r['state'] for r in q.snapshot(self.root)['recent']},{'played','error'})

    def test_mute_applied_at_playback_time(self):
        q.enqueue(self.root,'approval')
        q.drain(self.root,lambda *_:self.fail('muted'),lambda root:n.DEFAULT|{'approval':False})
        self.assertEqual(q.snapshot(self.root)['recent'][0]['state'],'muted')

    def test_receipts_do_not_keep_payload_content(self):
        output=io.StringIO()
        with patch.object(q,'spawn_worker'):
            n.run_hook(self.root,io.StringIO(json.dumps({'hook_event_name':'PermissionRequest',
                'tool_input':{'secret':'never store this'},'session_id':'raw-session','request_id':'raw-id'})),output)
        self.assertEqual(output.getvalue(),'{}\n')
        data=json.dumps(q.snapshot(self.root))
        for forbidden in ['never store this','raw-session','raw-id']:self.assertNotIn(forbidden,data)
        self.assertEqual(q.snapshot(self.root)['counters']['hook:approval:invoked'],1)

    def test_hook_failure_still_returns_empty_decision(self):
        output=io.StringIO()
        with patch.object(q,'spawn_worker',side_effect=OSError('cannot launch')):
            self.assertEqual(n.run_hook(self.root,io.StringIO('{"hook_event_name":"Stop"}'),output),0)
        self.assertEqual(output.getvalue(),'{}\n')
        self.assertEqual(q.snapshot(self.root)['pending'],1)
        self.assertEqual(q.snapshot(self.root)['receipts'][0]['outcome'],'error')

    def test_queue_bound_visible_failure(self):
        db=q.connect(self.root)
        db.executemany("INSERT INTO jobs(created,event,kind,state) VALUES (?,'approval','hook','pending')",[(time.time(),)]*500)
        db.commit();db.close()
        with self.assertRaises(ValueError):q.enqueue(self.root,'completion')
        self.assertEqual(q.snapshot(self.root)['counters']['overflow'],1)

    def test_cancel_pending_does_not_replay(self):
        q.enqueue(self.root,'approval');q.cancel_pending(self.root)
        calls=[];self.run_queue(calls)
        self.assertEqual(calls,[])
        self.assertEqual(q.snapshot(self.root)['recent'][0]['state'],'cancelled')

    def test_burst_elects_one_worker_and_failed_launch_releases(self):
        with patch.object(q.subprocess,'Popen') as launch:
            self.assertTrue(q.spawn_worker(self.root))
            for _ in range(12):self.assertFalse(q.spawn_worker(self.root))
            self.assertEqual(launch.call_count,1)
        db=q.connect(self.root);db.execute('UPDATE worker SET lease=0');db.commit();db.close()
        with patch.object(q.subprocess,'Popen',side_effect=OSError('blocked')):
            with self.assertRaises(OSError):q.spawn_worker(self.root)
        with patch.object(q.subprocess,'Popen') as launch:
            self.assertTrue(q.spawn_worker(self.root))

    def test_late_enqueue_is_drained_and_next_worker_can_start(self):
        q.enqueue(self.root,'completion')
        calls=[]
        def play(event,config):
            calls.append(event)
            if len(calls)==1:q.enqueue(self.root,'approval')
        q.drain(self.root,play,lambda root:n.DEFAULT)
        self.assertEqual(calls,['completion','approval'])
        self.assertEqual(q.snapshot(self.root)['pending'],0)
        with patch.object(q.subprocess,'Popen'):
            self.assertTrue(q.spawn_worker(self.root))

    def test_real_process_serialization_and_exact_count(self):
        script=self.root/'worker-test.py'
        script.write_text('''import sys,time,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import delivery as q
root=Path(sys.argv[2])
def play(event,config):
    with (root/'intervals.jsonl').open('a') as f:f.write(json.dumps(['start',time.time()])+'\\n')
    time.sleep(.06)
    with (root/'intervals.jsonl').open('a') as f:f.write(json.dumps(['end',time.time()])+'\\n')
q.drain(root,play,lambda root:{'volume':.2,'completion':True,'approval':True})
''')
        for _ in range(8):q.enqueue(self.root,'approval',kind='simulation')
        children=[subprocess.Popen([sys.executable,str(script),str(Path(q.__file__).parent),str(self.root)]) for _ in range(4)]
        try:
            for child in children:self.assertEqual(child.wait(timeout=15),0)
        finally:
            for child in children:
                if child.poll() is None: child.kill();child.wait()
        times=[json.loads(x) for x in (self.root/'intervals.jsonl').read_text().splitlines()]
        self.assertEqual([x[0] for x in times],['start','end']*8)
        self.assertTrue(all(r['state']=='played' for r in q.snapshot(self.root)['recent']))


class Panel(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.server,self.url=panel.make_server(self.root,'test-token')
        self.base=self.url.split('/?')[0]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,token='test-token',origin=None):
        headers={'X-Soft-Notify-Token':token,'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        data=json.dumps(body).encode() if body is not None else None
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=data,headers=headers),timeout=3)

    def test_requires_token_and_same_origin(self):
        for token,origin in [('wrong',None),('test-token','https://example.org')]:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/settings',n.DEFAULT,token,origin)
            self.assertEqual(caught.exception.code,403)
        self.assertFalse((self.root/'settings.json').exists())

    def test_static_refresh_is_public_but_state_is_protected(self):
        (self.root/'assets').mkdir()
        (self.root/'assets/panel.html').write_text('<h1>Static shell</h1>')
        with urllib.request.urlopen(self.base+'/',timeout=3) as res:
            self.assertEqual(res.status,200)
            self.assertNotIn(b'test-token',res.read())
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/state',token='')

    def test_settings_roundtrip_and_invalid_rejected(self):
        value=n.DEFAULT|{'volume':.18,'designs':{'approval':{'notes':[400,600],'note_ms':200,'gap_ms':40}}}
        with self.request('/api/settings',value) as res:self.assertEqual(json.load(res),value)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/settings',value|{'volume':8})
        self.assertEqual(n.settings(self.root),value)

    def test_draft_render_does_not_fabricate_played_evidence(self):
        with self.request('/api/render',{'event':'approval','volume':.2,'tone':'soft','design':audio.PRESETS['approval']}) as res:
            self.assertEqual(res.headers['Content-Type'],'audio/wav')
            with wave.open(io.BytesIO(res.read())) as w:self.assertEqual(w.getnchannels(),1)
        state=n.state_snapshot(self.root)
        self.assertEqual(state['queue']['recent'],[])
        self.assertEqual(state['trust']['state'],'unknown')

    def test_preview_never_proves_hook_delivery_or_trust(self):
        q.enqueue(self.root,'completion',kind='preview')
        q.drain(self.root,lambda *_:None,lambda root:n.DEFAULT)
        state=n.state_snapshot(self.root)
        self.assertEqual(state['queue']['recent'][0]['kind'],'preview')
        self.assertEqual(state['trust']['state'],'unknown')

    def test_manual_check_binds_to_installed_configuration(self):
        with tempfile.TemporaryDirectory() as home, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(n,'conflicts',return_value=[]):n.install(Path(home))
            root=Path(home)/'skills/codex-soft-notify'
            n.confirm_trust(root)
            self.assertEqual(n.state_snapshot(root)['trust']['state'],'manually_confirmed')
            path=Path(home)/'hooks.json';doc=n.read_json(path,{})
            doc['hooks']['Stop'][0]['hooks'][0]['timeout']=7;n.atomic_json(path,doc)
            self.assertEqual(n.state_snapshot(root)['trust']['state'],'unknown')


if __name__=='__main__':unittest.main()
