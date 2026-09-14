# Codex Soft Notify

Quiet Windows sounds for Codex: descending notes on `Stop`, ascending notes on `PermissionRequest`.

Inspired by [YANG301/codex-sound-notifications](https://github.com/YANG301/codex-sound-notifications), with credit to its antecedent [zty42/codex-sound-notifications](https://github.com/zty42/codex-sound-notifications). Development was AI-assisted and included reading upstream code; this is not a clean-room claim. See [provenance review](PROVENANCE.md).

Python 3.11+, standard library only. No resident polling service, external network calls, game recordings, or third-party sound assets. Default volume: 22%; the default two-note sound lasts 0.65 seconds.

## New in 0.2

- A local sound workbench: 1–4 frequencies, note duration, gaps, draft playback, settings save, WAV export.
- A SQLite queue with a cross-process playback lock. Approvals get priority; old jobs age into priority after five seconds. Deduplication requires explicit request IDs.
- An evidence panel that distinguishes configuration, a manual /hooks check, hook entry, and playback API success. Preview never proves real hook delivery.

Run `py -3 scripts/notify.py panel` from the installed directory. The panel binds only to loopback on a random port, requires a random API token, and uses no external assets. Keep its session URL private. Closing the panel server does not disable hooks.

## Install

Download this repository and run from its directory:

```powershell
py -3 scripts/notify.py install
```

Files are installed under `~/.codex/skills/codex-soft-notify`. The installer merges `hooks.json`, backs it up when present, and leaves `config.toml` and `notify` unchanged. It refuses known legacy conflicts by default. See [migration](MIGRATION.md).

Open `/hooks` in Codex and review/trust this project's two handlers. Configuration, trust, and actual playback are separate checks. No trust bypass is provided.

Run these commands from the **installed** skill directory:

```powershell
py -3 scripts/notify.py preview completion
py -3 scripts/notify.py preview approval
py -3 scripts/notify.py set --volume 0.15 --tone soft
py -3 scripts/notify.py set --approval off
py -3 scripts/notify.py design approval --notes 520,660,880 --note-ms 200 --gap-ms 40
py -3 scripts/notify.py export-sound approval my-approval.wav
py -3 scripts/notify.py status
py -3 scripts/notify.py uninstall
```

`bell` is an alternative tone. Volume is 0–1; 0 mutes both sounds. `--completion on|off` and `--approval on|off` are independent. Uninstall removes only the exact registered handlers and cancels pending jobs. It retains files and unrelated configuration. A sound already playing may finish; close the panel to avoid new previews.

## Limits and verification

Preview proves only local playback. Check `/hooks` in the client you actually use, then test a normal completion and a genuinely needed approval. The local SQLite store separates preview, simulation, and hook records. It stores metadata and hashed request identifiers, not prompts, command arguments, approval reasons, or raw session IDs. Hashes are not an anonymity guarantee; do not publish runtime data. Diagnostics export excludes hashes and paths. Recent history is bounded near 1000 records. Playback API success does not prove the sound was audible.

This refactored version has **not yet passed live end-to-end client verification**. An earlier prototype's approval hook was shown Active in CLI 0.153.4. Desktop approval delivery is unverified. Some UI permission flows may not emit `PermissionRequest`. The trust card records only a user's manual check bound to the current hook configuration, not API verification. Direct synthetic input to the hook command also appears as hook entry; this is not cryptographic evidence. `Stop` is not a task-success signal; other Stop hooks can continue work. Sounds are serialized within one installation. Jobs older than 120 seconds expire; the queue limit is 500. Explicit duplicate IDs merge for 30 seconds. Crashed playback is marked interrupted instead of replayed; use `drain`, or a new event after the short worker lease expires (up to 10 seconds), to recover pending work. Audio exactly-once delivery is not promised. Changing Python or relocating the installation requires reinstalling and checking trust again.

See [official hook semantics](https://learn.chatgpt.com/docs/hooks), [review and roadmap](REVIEW.md), and the [Chinese guide](README.md).

## Development and attribution

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary directories. Windows CI is configured for Python 3.11 and 3.13; remote CI results remain pending until pushed.

Inspired by [YANG301/codex-sound-notifications](https://github.com/YANG301/codex-sound-notifications). The review found no identical upstream files or Python functions. The release includes no Tarkov or SND recordings. MIT applies to this project's new material, not to upstream material.

