[繁體中文](README.md) ｜ [简体中文](README.zh-CN.md) ｜ [English](README.en.md)

# Codex Soft Notify

通过 Codex hooks 提供柔和声音通知的 Windows 工具与 Skill。无需常驻轮询服务；支持声音预览、队列和本地设置面板。

## 第一次使用

在下载的仓库文件夹打开 PowerShell。先测试，准备好后再安装：

```powershell
py -3 -m unittest discover -s tests -v
py -3 scripts/notify.py install
```

进入安装后的 `~/.codex/skills/codex-soft-notify` 目录，再试听或打开设置：

```powershell
py -3 scripts/notify.py preview completion
py -3 scripts/notify.py panel
py -3 scripts/notify.py status
```

移除已注册处理器：`py -3 scripts/notify.py uninstall`。文件与其他设置会保留。

需要 Windows 和 Python 3.11+。安装会更新 hooks.json 并备份已有文件。安装后在 Codex /hooks 中检查并信任两个处理器；预览成功不代表真实 hook 已触发，也不代表声音实际可闻。桌面端审批通知的端到端验证仍需在目标客户端完成。保留 PROVENANCE.md 中的上游来源和 AI 辅助说明；许可证见 LICENSE。

## 读代码或修改时看哪里

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 助手使用入口 |
| `scripts/notify.py` | 通知与监听 |
| `scripts/delivery.py` | 通知交付 |
| `scripts/panel.py` | 设置面板服务 |
| `tests` | 自动化测试 |

## 详细参考

[原有说明](README.original.md) 保留历史细节和来源署名，语言保持原样。部分描述属于旧版本；有差异时以当前源码和本入口说明为准。

[Detailed English reference](README.original.en.md) · [Provenance](PROVENANCE.md) · [License](LICENSE)
