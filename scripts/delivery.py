"""Transactional queue, explicit-id deduplication, and process playback lock."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

EVENTS = ("completion", "approval")
TERMINAL = ("played", "error", "expired", "interrupted", "muted")


def connect(root):
    folder = Path(root) / "runtime"
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "delivery.sqlite3", timeout=2)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=2000")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY, created REAL NOT NULL, finished REAL,
          event TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
          dedupe TEXT, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(state, created);
        CREATE INDEX IF NOT EXISTS jobs_dedupe ON jobs(dedupe, created);
        CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY, time REAL,
          kind TEXT, event TEXT, outcome TEXT);
        CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY CHECK(id=1),
          token TEXT NOT NULL, lease REAL NOT NULL);
        INSERT OR IGNORE INTO worker VALUES (1,'',0);
    ''')
    return db


def bump(db, name):
    db.execute("INSERT INTO counters VALUES (?,1) ON CONFLICT(name) DO UPDATE SET value=value+1", (name,))


def record_receipt(root, kind, event, outcome):
    db = connect(root)
    try:
        db.execute("INSERT INTO receipts(time,kind,event,outcome) VALUES (?,?,?,?)", (time.time(), kind, event, outcome))
        if kind == "hook" and event in EVENTS:
            bump(db, "hook:" + event + ":invoked")
        db.execute("DELETE FROM receipts WHERE id NOT IN (SELECT id FROM receipts ORDER BY id DESC LIMIT 1000)")
        db.commit()
    finally:
        db.close()


def delivery_key(event, payload):
    # Only explicit request/delivery IDs deduplicate. A shared turn_id alone
    # must not swallow two legitimate approvals or successive Stop events.
    explicit = payload.get("approval_id") or payload.get("request_id") or payload.get("hook_event_id")
    if event == "approval":
        explicit = explicit or payload.get("tool_use_id")
    if not isinstance(explicit, (str, int)) or not str(explicit):
        return None
    scope = str(payload.get("session_id", "")) + ":" + str(payload.get("turn_id", ""))
    return hashlib.sha256((event + ":" + scope + ":" + str(explicit)).encode()).hexdigest()


def enqueue(root, event, kind="hook", payload=None, now=None):
    if event not in EVENTS or kind not in ("hook", "preview", "simulation"):
        raise ValueError("invalid queue event")
    now = time.time() if now is None else now
    key = delivery_key(event, payload or {}) if kind == "hook" else None
    db = connect(root)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE jobs SET state='expired',finished=? WHERE state='pending' AND created<?", (now, now-120))
        bump(db, kind + ":" + event + ":received")
        if key and db.execute("SELECT 1 FROM jobs WHERE dedupe=? AND created>?", (key, now - 30)).fetchone():
            bump(db, "duplicates")
            db.commit()
            return None
        count = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('pending','playing')").fetchone()[0]
        if count >= 500:
            bump(db, "overflow")
            db.commit()
            raise ValueError("sound queue is full")
        cur = db.execute("INSERT INTO jobs(created,event,kind,state,dedupe) VALUES (?,?,?,'pending',?)",
                         (now, event, kind, key))
        job = cur.lastrowid
        db.commit()
        return job
    finally:
        db.close()


@contextmanager
def playback_lock(root, timeout=8):
    folder = Path(root) / "runtime"
    folder.mkdir(parents=True, exist_ok=True)
    f = (folder / "playback.lock").open("a+b")
    # Lock a byte range even in an empty file. Writing an initialization byte
    # can race with another process that has already acquired that range.
    deadline, held = time.monotonic() + timeout, False
    try:
        while not held:
            try:
                f.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(.05)
        yield held
    finally:
        if held:
            f.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def spawn_worker(root):
    db = connect(root)
    token = uuid.uuid4().hex
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT lease FROM worker WHERE id=1").fetchone()[0] > time.time():
            db.commit()
            return False
        db.execute("UPDATE worker SET token=?,lease=? WHERE id=1", (token, time.time()+5))
        db.commit()
    finally:
        db.close()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.Popen([sys.executable, str(Path(root) / "scripts/notify.py"), "drain", "--worker-token", token],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, creationflags=flags)
        return True
    except Exception:
        clear_lease(root, token)
        raise


def clear_lease(root, token):
    db = connect(root)
    try:
        db.execute("UPDATE worker SET lease=0 WHERE id=1 AND token=?", (token,))
        db.commit()
    finally:
        db.close()


def drain(root, player, config_loader, now=time.time, lock_timeout=8, worker_token=None):
    # Contenders wait through the owner's shutdown, preventing the last-enqueue
    # lost-wakeup race. A busy owner drains work from all enqueueing processes.
    with playback_lock(root, lock_timeout) as held:
        if not held:
            if worker_token:
                clear_lease(root, worker_token)
            return 0
        db = connect(root)
        owner = worker_token or uuid.uuid4().hex
        try:
            if worker_token and db.execute("SELECT token FROM worker WHERE id=1").fetchone()[0] != worker_token:
                return 0
            db.execute("UPDATE worker SET token=?,lease=? WHERE id=1", (owner, time.time()+10))
            # A process crash releases the OS lock. Do not replay a possibly
            # already-audible job: exact-once audio cannot be guaranteed.
            db.execute("UPDATE jobs SET state='interrupted',finished=? WHERE state='playing'", (now(),))
            db.commit()
            played = 0
            while True:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE jobs SET state='expired',finished=? WHERE state='pending' AND created<?", (now(), now()-120))
                # Approval first within the ordinary queue, but waiting 5s
                # promotes any older item to avoid completion starvation.
                row = db.execute("""SELECT * FROM jobs WHERE state='pending'
                    ORDER BY CASE WHEN created<? THEN 0 WHEN event='approval' THEN 1 ELSE 2 END, id LIMIT 1""", (now()-5,)).fetchone()
                if not row:
                    # Publish idle under the same transaction as the empty
                    # check. New enqueues can now elect the next worker.
                    db.execute("UPDATE worker SET lease=0 WHERE id=1 AND token=?", (owner,))
                    db.commit()
                    break
                db.execute("UPDATE worker SET lease=? WHERE id=1 AND token=?", (time.time()+10, owner))
                db.execute("UPDATE jobs SET state='playing',attempts=attempts+1 WHERE id=?", (row["id"],))
                db.commit()
                state = "error"
                try:
                    config = config_loader(root)
                    if not config[row["event"]] or config["volume"] == 0:
                        state = "muted"
                    else:
                        player(row["event"], config)
                        state = "played"
                        played += 1
                except Exception:
                    pass
                db.execute("UPDATE jobs SET state=?,finished=? WHERE id=?", (state, now(), row["id"]))
                db.commit()
            # Bounded retained evidence; exclude queued work.
            db.execute("DELETE FROM jobs WHERE state NOT IN ('pending','playing') AND id NOT IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 1000)")
            db.commit()
            return played
        finally:
            db.close()
            clear_lease(root, owner)


def snapshot(root):
    if not (Path(root) / "runtime/delivery.sqlite3").exists():
        return {"pending": 0, "playing": 0, "recent": [], "counters": {}, "receipts": []}
    db = connect(root)
    try:
        counts = dict(db.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state"))
        rows = [dict(r) for r in db.execute("SELECT id,created,finished,event,kind,state FROM jobs ORDER BY id DESC LIMIT 30")]
        return {"pending": counts.get("pending", 0), "playing": counts.get("playing", 0),
                "recent": rows, "counters": dict(db.execute("SELECT name,value FROM counters")),
                "receipts": [dict(r) for r in db.execute("SELECT time,kind,event,outcome FROM receipts ORDER BY id DESC LIMIT 30")]}
    finally:
        db.close()


def cancel_pending(root):
    if not (Path(root) / "runtime/delivery.sqlite3").exists():
        return
    db = connect(root)
    try:
        db.execute("UPDATE jobs SET state='cancelled',finished=? WHERE state='pending'", (time.time(),))
        db.commit()
    finally:
        db.close()
