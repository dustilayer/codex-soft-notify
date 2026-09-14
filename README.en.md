[繁體中文](README.md) ｜ [简体中文](README.zh-CN.md) ｜ [English](README.en.md)

# Codex Soft Notify

A Windows tool and Skill for gentle sounds through Codex hooks. It needs no resident polling service and supports previews, a queue and a local settings panel.

## Start here

Open a PowerShell terminal in the downloaded folder. Test, then install when ready:

```powershell
py -3 -m unittest discover -s tests -v
py -3 scripts/notify.py install
```

From the installed `~/.codex/skills/codex-soft-notify` directory, preview or open settings:

```powershell
py -3 scripts/notify.py preview completion
py -3 scripts/notify.py panel
py -3 scripts/notify.py status
```

To remove the registered handlers: `py -3 scripts/notify.py uninstall`. Files and unrelated settings are retained.

Requires Windows and Python 3.11+. Installation updates hooks.json and backs up an existing file. Review and trust both handlers in Codex /hooks after installation. A successful preview does not prove real hook delivery or audible sound. Desktop approval delivery still needs end-to-end verification in the target client. PROVENANCE.md retains upstream and AI-assistance information; see LICENSE.

## Where to read or change code

| File | Purpose |
|---|---|
| `SKILL.md` | Assistant entry point |
| `scripts/notify.py` | Notifications and watching |
| `scripts/delivery.py` | Notification delivery |
| `scripts/panel.py` | Settings panel server |
| `tests` | Automated tests |

## Detailed reference

[Original guide](README.original.md) preserves earlier details and attribution in its original language. Some statements describe an older version; use current source code and this entry guide to resolve differences.

[Detailed English reference](README.original.en.md) · [Provenance](PROVENANCE.md) · [License](LICENSE)
