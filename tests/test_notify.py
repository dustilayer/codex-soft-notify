import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import notify as n


class Notifications(unittest.TestCase):
    def test_pcm_and_volume(self):
        for event in ('completion', 'approval'):
            for tone in ('soft', 'bell'):
                with wave.open(io.BytesIO(n.sound_bytes(event, .22, tone))) as w:
                    self.assertEqual((w.getnchannels(), w.getsampwidth()), (1, 2))
                    self.assertLess(w.getnframes()/w.getframerate(), 1)
        with wave.open(io.BytesIO(n.sound_bytes('approval', 0))) as w:
            self.assertEqual(set(w.readframes(w.getnframes())), {0})

    def invoke(self, root, payload, player):
        out = io.StringIO()
        self.assertEqual(n.run_hook(root, io.StringIO(json.dumps(payload)), out, player), 0)
        self.assertEqual(json.loads(out.getvalue()), {})

    def test_both_events_and_no_approval_decision(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []
            for event in n.EVENTS:
                self.invoke(Path(d), {'hook_event_name': event}, lambda e,c: calls.append(e))
            self.assertEqual(calls, ['completion', 'approval'])

    def test_subagent_interrupt_unknown_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            for payload in ({'hook_event_name': 'SubagentStop'}, {'hook_event_name':'Interrupt'},
                            {'hook_event_name':'Stop','agent_id':'child'}, {}, []):
                self.invoke(Path(d), payload, lambda *_: self.fail('unexpected sound'))

    def test_continued_turn_still_notifies(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            self.invoke(Path(d), {'hook_event_name':'Stop','stop_hook_active':True}, lambda *a:calls.append(a))
            self.assertEqual(len(calls),1)

    def test_audio_failure_never_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(*_): raise OSError('no device')
            self.invoke(Path(d), {'hook_event_name':'PermissionRequest','tool_input':{'secret':'do not log'}}, fail)
            log=json.dumps(n.delivery.snapshot(Path(d)))
            self.assertNotIn('secret',log)
            self.assertIn('error',log)

    def test_malformed_input(self):
        with tempfile.TemporaryDirectory() as d:
            out=io.StringIO()
            self.assertEqual(n.run_hook(Path(d),io.StringIO('{bad'),out),0)
            self.assertEqual(out.getvalue(),'{}\n')

    def test_independent_mute(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            n.atomic_json(root/'settings.json', n.DEFAULT|{'approval':False})
            self.invoke(root,{'hook_event_name':'PermissionRequest'},lambda *_:self.fail('muted'))

    def test_merge_idempotent_and_preserves_other_handlers(self):
        doc={'description':'mine','hooks':{'Stop':[{'matcher':'','hooks':[{'type':'command','command':'other'}]}],
                                         'SessionStart':[]}}
        first=n.merge_hooks(doc,'ours')
        self.assertEqual(n.merge_hooks(first,'ours'),first)
        self.assertEqual(n.merge_hooks(first,'ours',True),doc)
        self.assertNotIn('PermissionRequest',doc['hooks'])

    def test_invalid_hook_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d); (home/'hooks.json').write_text('{oops')
            with self.assertRaises(json.JSONDecodeError): n.install(home,True)
            self.assertEqual((home/'hooks.json').read_text(),'{oops')
            self.assertFalse((home/'skills').exists())

    def test_install_reinstall_uninstall_preserve_config(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            home=Path(d); config=home/'config.toml'; config.write_text('model = "example"\n')
            original={'hooks':{'Stop':[{'hooks':[{'type':'command','command':'other'}]}]}}
            n.atomic_json(home/'hooks.json',original)
            with patch.object(n,'conflicts',return_value=[]):
                n.install(home)
                first=n.read_json(home/'hooks.json',{})
                n.install(home)
            self.assertEqual(n.read_json(home/'hooks.json',{}),first)
            installed=home/'skills/codex-soft-notify'
            n.uninstall(installed)
            self.assertEqual(n.read_json(home/'hooks.json',{}),original)
            self.assertEqual(config.read_text(),'model = "example"\n')

    def test_conflict_refuses_before_writes(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            with patch.object(n,'conflicts',return_value=['legacy monitor']):
                with self.assertRaises(ValueError): n.install(home)
            self.assertEqual(list(home.iterdir()),[])

    def test_invalid_volume(self):
        with tempfile.TemporaryDirectory() as d:
            n.atomic_json(Path(d)/'settings.json',{'volume':2})
            with self.assertRaises(ValueError): n.settings(Path(d))


if __name__ == '__main__': unittest.main()
