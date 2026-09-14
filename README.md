[繁體中文](README.md) ｜ [简体中文](README.zh-CN.md) ｜ [English](README.en.md)

# Codex Soft Notify

通過 Codex hooks 提供柔和聲音通知的 Windows 工具與 Skill。無需常駐輪詢服務；支持聲音預覽、隊列和本地設置面板。

## 第一次使用

在下載的倉庫文件夾打開 PowerShell。先測試，準備好後再安裝：

```powershell
py -3 -m unittest discover -s tests -v
py -3 scripts/notify.py install
```

進入安裝後的 `~/.codex/skills/codex-soft-notify` 目錄，再試聽或打開設置：

```powershell
py -3 scripts/notify.py preview completion
py -3 scripts/notify.py panel
py -3 scripts/notify.py status
```

移除已註冊處理器：`py -3 scripts/notify.py uninstall`。文件與其他設置會保留。

需要 Windows 和 Python 3.11+。安裝會更新 hooks.json 並備份已有文件。安裝後在 Codex /hooks 中檢查並信任兩個處理器；預覽成功不代表真實 hook 已觸發，也不代表聲音實際可聞。桌面端審批通知的端到端驗證仍需在目標客戶端完成。保留 PROVENANCE.md 中的上游來源和 AI 輔助說明；許可證見 LICENSE。

## 讀代碼或修改時看哪裡

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 助手使用入口 |
| `scripts/notify.py` | 通知與監聽 |
| `scripts/delivery.py` | 通知交付 |
| `scripts/panel.py` | 設置面板服務 |
| `tests` | 自動化測試 |

## 詳細參考

[原有說明](README.original.md) 保留歷史細節和來源署名，語言保持原樣。部分描述屬於舊版本；有差異時以當前源碼和本入口說明為準。

[Detailed English reference](README.original.en.md) · [Provenance](PROVENANCE.md) · [License](LICENSE)
