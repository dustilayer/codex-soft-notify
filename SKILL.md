---
name: codex-soft-notify
description: Install, personalize, diagnose, or remove quiet Windows sound notifications for Codex completion and approval hooks. Use for completion sounds, approval sounds, volume, muting, and sound-hook troubleshooting.
---

# Codex Soft Notify

Windows, Python 3.11+, standard library only. Use `scripts/notify.py`. `panel` opens the local sound workbench; `design` and `export-sound` customize and export synthesized tones.

- Inspect `status` before changing an existing installation. Read README.md for commands and MIGRATION.md when older sound monitors/hooks exist.
- `install` records the current Python executable and creates two user hooks. Run with the Python installation the user intends to keep. Preserve unrelated hooks and `config.toml`.
- `set --volume 0.22 --tone soft`, `set --approval off`, and `set --completion off` customize the installed copy. Preview is not proof of automatic notification.
- Trust must be reviewed through Codex `/hooks`; never fabricate a trust record or bypass hook trust. Explain that configuration, trust, and real delivery are separate states.
- Hook output is always `{}` and exit 0, even when enqueueing or sound fails. Playback is queued in SQLite and performed by an on-demand worker. Do not make permission decisions or modify tools from a sound hook.
- `Stop` means the agent is stopping, not that the task succeeded. Other Stop hooks may continue a task. Do not promise every desktop approval mechanism maps to PermissionRequest.
- Do not deploy a new completion hook alongside an existing completion monitor without planning migration. Installation is blocked when known conflicts are detected.
- `status` and the panel distinguish manual trust checks, hook entry, previews and playback API outcomes. The confirmation button only records a user check; never call it as if it granted trust. Queue recovery: `drain`; interrupted sounds are not replayed.
- Tests: `python -m unittest discover -s tests -v`. Deliver source changes with the tests; never publish local settings, hook backups, logs, or personal paths.
