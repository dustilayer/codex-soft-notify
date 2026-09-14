"""Small, local-only Windows sound hooks. Python 3.11+, no dependencies."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import wave
import hashlib

import audio_design
import delivery

ROOT = Path(__file__).resolve().parents[1]
EVENTS = {"Stop": "completion", "PermissionRequest": "approval"}
DEFAULT = {"volume": 0.22, "tone": "soft", "completion": True, "approval": True, "designs": {}}
MARKER = "Codex Soft Notify"


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else copy.deepcopy(default)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".soft-notify-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def settings(root):
    value = DEFAULT | read_json(root / "settings.json", {})
    if type(value["volume"]) not in (int, float) or not 0 <= value["volume"] <= 1:
        raise ValueError("volume must be between 0 and 1")
    if value["tone"] not in ("soft", "bell"):
        raise ValueError("tone must be soft or bell")
    if any(type(value[k]) is not bool for k in ("completion", "approval")):
        raise ValueError("event switches must be booleans")
    designs = value["designs"]
    if not isinstance(designs, dict) or set(designs) - set(EVENTS.values()):
        raise ValueError("designs must contain completion and/or approval")
    for design in designs.values():
        audio_design.validate_design(design)
    return value


def sound_bytes(event, volume=0.22, tone="soft", design=None):
    return audio_design.render(event, volume, tone, design)


def play(event, config):
    import winsound
    winsound.PlaySound(sound_bytes(event, config["volume"], config["tone"],
                                  config.get("designs", {}).get(event)), winsound.SND_MEMORY)


def record(root, kind, event, outcome):
    # SQLite serializes evidence writes without retaining payload content.
    delivery.record_receipt(root, kind, event, outcome)


def hook_event(payload):
    if not isinstance(payload, dict):
        return None
    # Subagents and interrupts never map to completion.
    if payload.get("agent_id") or payload.get("thread_source") == "subagent":
        return None
    return EVENTS.get(payload.get("hook_event_name"))


def run_hook(root, stream, output, dispatch=None):
    """Enqueue quickly; never make approval or continuation decisions."""
    event, outcome = None, "ignored"
    try:
        raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("payload too large")
        payload = json.loads(raw)
        event = hook_event(payload)
        config = settings(root)
        if event and config[event] and config["volume"] > 0:
            if dispatch:
                dispatch(event, payload)
            else:
                delivery.enqueue(root, event, payload=payload)
                # Also wake a previously queued item after a duplicate retry.
                delivery.spawn_worker(root)
            outcome = "queued"
        elif event:
            outcome = "muted"
    except Exception:
        outcome = "error"
    finally:
        try:
            record(root, "hook", event, outcome)
        except Exception:
            pass
        output.write("{}\n")
    return 0


def hook_command(root):
    executable = Path(sys.executable)
    paths = [str(executable), str(root / "scripts" / "notify.py")]
    # Command text may pass through a shell. Quote even paths without spaces;
    # reject expansion/control characters instead of guessing the host shell.
    if any(any(char in path for char in ('"', '%', '!', '\r', '\n')) for path in paths):
        raise ValueError("hook paths cannot contain quotes, %, !, or line breaks")
    return ' '.join('"' + path + '"' for path in paths) + ' hook'


def owned(handler, command):
    return isinstance(handler, dict) and handler.get("command") == command


def merge_hooks(document, command, remove=False):
    result = copy.deepcopy(document)
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for event in EVENTS:
        kept = []
        for group in hooks.get(event, []):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError("invalid existing hook group")
            remaining = [h for h in group["hooks"] if not owned(h, command)]
            if remaining or not group["hooks"]:
                kept.append(group | {"hooks": remaining})
        if not remove:
            kept.append({"hooks": [{"type": "command", "command": command,
                                    "timeout": 5, "statusMessage": MARKER}]})
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    return result


def conflicts(home):
    found = []
    path = home / "config.toml"
    if path.exists():
        text = path.read_text(encoding="utf-8-sig")
        config = tomllib.loads(text)
        if config.get("hooks"):
            found.append("config.toml contains inline hooks; review before combining hook sources")
        if "codex-sound-notifications" in text or "approval-sound.ps1" in text:
            found.append("legacy sound hook found; remove only its handler before migration")
    roaming = os.environ.get("APPDATA")
    if roaming:
        startup = Path(roaming) / "Microsoft/Windows/Start Menu/Programs/Startup/CodexSoundNotifications.vbs"
        if startup.exists():
            found.append("legacy completion monitor startup found; disable it and stop that monitor before migration")
    return found


def install(home, allow_existing=False):
    warnings = conflicts(home)
    if warnings and not allow_existing:
        raise ValueError("\n".join(warnings) + "\nNo changes made. See MIGRATION.md.")
    dest = home / "skills" / "codex-soft-notify"
    manifest = dest / "runtime" / "install.json"
    if dest.exists() and dest.resolve() != ROOT.resolve() and not manifest.exists():
        raise ValueError("destination already exists and is not a managed installation")
    # Parse existing hooks before touching the installation.
    hooks_path = home / "hooks.json"
    original = read_json(hooks_path, {})
    command = hook_command(dest)
    previous = read_json(manifest, {}).get("command")
    if previous:
        original = merge_hooks(original, previous, remove=True)
    updated = merge_hooks(original, command)
    if dest.resolve() != ROOT.resolve():
        for relative in (
            "scripts/notify.py", "scripts/audio_design.py",
            "scripts/delivery.py", "scripts/panel.py", "assets/panel.html",
            "SKILL.md", "agents/openai.yaml",
            "README.md", "README.zh-CN.md", "README.en.md",
            "README.original.md", "README.original.en.md",
            "MIGRATION.md", "PROVENANCE.md", "LICENSE",
        ):
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
    if not (dest / "settings.json").exists():
        atomic_json(dest / "settings.json", DEFAULT)
    if hooks_path.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(hooks_path, dest / ("hooks-backup-" + stamp + ".json"))
    atomic_json(hooks_path, updated)
    atomic_json(manifest, {"command": command, "home": str(home)})
    print("Installed:", dest)
    print("Next: open /hooks in Codex, review and trust Stop and PermissionRequest.")
    print("Configured only; live playback and desktop compatibility are not yet verified.")
    for warning in warnings:
        print("Review:", warning)


def uninstall(root):
    manifest = read_json(root / "runtime/install.json", {})
    if not manifest:
        raise ValueError("no installation manifest; nothing removed")
    path = Path(manifest["home"]) / "hooks.json"
    if path.exists():
        original = read_json(path, {})
        updated = merge_hooks(original, manifest["command"], remove=True)
        atomic_json(path, updated)
    delivery.cancel_pending(root)
    print("Removed this installation's hook handlers. Other hooks and files kept.")


def state_snapshot(root):
    manifest = read_json(root / "runtime/install.json", {})
    active, fingerprint = [], None
    if manifest:
        path = Path(manifest["home"]) / "hooks.json"
        doc = read_json(path, {})
        handlers = []
        for event in EVENTS:
            for group in doc.get("hooks", {}).get(event, []):
                for handler in group.get("hooks", []):
                    if owned(handler, manifest["command"]):
                        active.append(event)
                        handlers.append({"event": event, "group": group})
        fingerprint = hashlib.sha256(json.dumps(handlers, sort_keys=True).encode()).hexdigest()
    check = read_json(root / "runtime/trust-check.json", {})
    checked = bool(len(set(active)) == 2 and check.get("fingerprint") == fingerprint)
    queue = delivery.snapshot(root)
    receipts = queue["receipts"]
    return {"time": dt.datetime.now(dt.timezone.utc).isoformat(),
            "configured_events": list(dict.fromkeys(active)), "settings": settings(root),
            "trust": {"state": "manually_confirmed" if checked else "unknown",
                      "checked_at": check.get("time") if checked else None,
                      "source": "user confirmation from /hooks; not an API trust check"},
            "fingerprint": fingerprint, "queue": queue, "receipts": receipts}


def confirm_trust(root):
    value = state_snapshot(root)
    if len(value["configured_events"]) != 2:
        raise ValueError("install both hooks before recording a manual check")
    atomic_json(root / "runtime/trust-check.json", {"fingerprint": value["fingerprint"],
                "time": dt.datetime.now(dt.timezone.utc).isoformat()})


def status(root):
    print(json.dumps(state_snapshot(root), ensure_ascii=False, indent=2))


def save_settings(root, value):
    # Validate with the same schema without changing the current file first.
    merged = copy.deepcopy(DEFAULT) | value
    if set(merged) != set(DEFAULT):
        raise ValueError("unknown setting")
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        atomic_json(temp / "settings.json", merged)
        checked = settings(temp)
    atomic_json(root / "settings.json", checked)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("hook")
    ins = sub.add_parser("install")
    ins.add_argument("--codex-dir", type=Path)
    ins.add_argument("--allow-existing-hooks", action="store_true")
    sub.add_parser("uninstall")
    sub.add_parser("status")
    worker = sub.add_parser("drain")
    worker.add_argument("--worker-token", help=argparse.SUPPRESS)
    pane = sub.add_parser("panel")
    pane.add_argument("--no-open", action="store_true")
    design = sub.add_parser("design")
    design.add_argument("event", choices=list(EVENTS.values()))
    design.add_argument("--notes", help="comma-separated frequencies in Hz")
    design.add_argument("--note-ms", type=int, default=300)
    design.add_argument("--gap-ms", type=int, default=50)
    design.add_argument("--reset", action="store_true")
    export = sub.add_parser("export-sound")
    export.add_argument("event", choices=list(EVENTS.values()))
    export.add_argument("path", type=Path)
    sub.add_parser("confirm-trust-check", help="record that you personally checked /hooks; does not trust hooks")
    preview = sub.add_parser("preview")
    preview.add_argument("event", choices=list(EVENTS.values()))
    config = sub.add_parser("set")
    config.add_argument("--volume", type=float)
    config.add_argument("--tone", choices=["soft", "bell"])
    config.add_argument("--completion", choices=["on", "off"])
    config.add_argument("--approval", choices=["on", "off"])
    args = parser.parse_args()
    if args.action == "hook":
        return run_hook(ROOT, sys.stdin, sys.stdout)
    try:
        if args.action == "install":
            if sys.platform != "win32":
                raise ValueError("Windows is required for installation")
            home = args.codex_dir or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            install(home.expanduser().resolve(), args.allow_existing_hooks)
        elif args.action == "uninstall":
            uninstall(ROOT)
        elif args.action == "status":
            status(ROOT)
        elif args.action == "drain":
            delivery.drain(ROOT, play, settings, worker_token=args.worker_token)
        elif args.action == "panel":
            import panel
            panel.serve(ROOT, not args.no_open)
        elif args.action == "confirm-trust-check":
            confirm_trust(ROOT)
            print("Recorded a manual check only; no Codex trust state changed.")
        elif args.action == "design":
            value = settings(ROOT)
            if args.reset:
                value["designs"].pop(args.event, None)
            else:
                if not args.notes:
                    raise ValueError("--notes is required, or use --reset")
                value["designs"][args.event] = {"notes": [float(x) for x in args.notes.split(",")],
                    "note_ms": args.note_ms, "gap_ms": args.gap_ms}
            save_settings(ROOT, value)
            print("Design saved.")
        elif args.action == "export-sound":
            value = settings(ROOT)
            # Exclusive create avoids silently overwriting an existing file.
            with args.path.open("xb") as f:
                f.write(sound_bytes(args.event, value["volume"], value["tone"], value["designs"].get(args.event)))
            print("WAV exported.")
        elif args.action == "preview":
            delivery.enqueue(ROOT, args.event, "preview")
            delivery.drain(ROOT, play, settings)
            print("Preview queue processed; inspect status for playback outcome. This is not hook verification.")
        elif args.action == "set":
            value = settings(ROOT)
            for key in DEFAULT:
                new = getattr(args, key, None)
                if new is not None:
                    value[key] = new == "on" if key in EVENTS.values() else new
            if not 0 <= value["volume"] <= 1:
                raise ValueError("volume must be 0..1")
            save_settings(ROOT, value)
            print(json.dumps(value))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
