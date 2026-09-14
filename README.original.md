# Codex Soft Notify

轻一点的提醒。完成时下降双音，需要批准时上升双音。

受 [YANG301/codex-sound-notifications](https://github.com/YANG301/codex-sound-notifications) 启发；同时致谢它引用的 [zty42/codex-sound-notifications](https://github.com/zty42/codex-sound-notifications)。实现过程由 AI 辅助，曾阅读上游源码；不宣称未经参考的独立原创。详见 [来源核查](PROVENANCE.md)。

Windows · Python 3.11+ · 无第三方依赖 · 按需队列 · 本地声音工作台

[English](README.en.md) · [旧版迁移](MIGRATION.md) · [验证与改进](REVIEW.md)

## 工作方式

| 事件 | 声音 | 含义 |
| --- | --- | --- |
| `Stop` | 下降双音 | Agent 准备结束回复；不代表任务成功 |
| `PermissionRequest` | 上升双音 | Codex 即将请求审批 |

默认音量为 22%，默认双音长 0.65 秒。音量调整只影响本工具；不修改系统音量。不扫描聊天，不读取工具参数，不替用户批准操作。音频由代码合成，不包含游戏音效或第三方录音。

## 0.2 的三个新增功能

- **声音设计器**：1–4 个音符，各自定义频率，调整时长与间隔；浏览器试听草稿，保存到本机，导出 PCM WAV。
- **多任务队列**：SQLite 持久排队、跨进程播放互斥；审批优先，等待超过 5 秒的旧项提升优先级。按明确请求 ID 去重，不合并同一轮中的不同审批。
- **验证面板**：分别显示配置、手动检查过的信任、钩子入口调用、播放 API 返回结果；试听与模拟记录单独显示。

面板只绑定 `127.0.0.1` 的随机端口，用随机会话令牌保护 API。不加载外部字体或脚本，不收集遥测。关闭面板不禁用钩子。

## 安装

下载仓库并解压，在项目目录打开 PowerShell：

```powershell
py -3 scripts/notify.py install
```

需要 Python 3.11 或更新版本；没有 `py` 时可使用 `python` 或 Python 可执行文件的完整路径。

安装器将技能复制到 `~/.codex/skills/codex-soft-notify`，合并 `~/.codex/hooks.json`，不改写 `config.toml` 或 Codex 的 `notify`。已有 JSON 钩子文件会先备份。重复安装不会重复添加本工具钩子。检测到旧方案或内联钩子时，会先停止并说明冲突。

接着，在 Codex 中输入 `/hooks`，审阅并信任本工具的 `Stop` 与 `PermissionRequest`。不要信任不认识的其他钩子。切回实际使用的客户端，检查它是否加载了配置；必要时重新打开会话。

**已安装 ≠ 已信任 ≠ 已验证自动播放。** 安装命令不会自动信任钩子，也不会关闭审批。

## 打开声音工作台

进入安装后的技能目录，运行：

```powershell
py -3 scripts/notify.py panel
```

浏览器会打开本机面板。可编辑完成/审批音、保存、试听或导出 WAV。面板服务需要这个命令继续运行；点击“关闭面板服务”或在终端按 Ctrl+C 停止。会话 URL 含本机 API 令牌，不要分享它。

信任卡片默认显示“尚未核实”。只有你亲自在实际客户端 `/hooks` 看到这两项 Active 后，才点击“我已核实”。此操作只记录手动检查及配置指纹，**不授权、不修改或绕过 Codex 信任**；钩子配置改变后检查记录失效。

## 个性化

以下命令在**安装后的技能目录**执行：

```powershell
cd "$env:USERPROFILE\.codex\skills\codex-soft-notify"
py -3 scripts/notify.py preview completion
py -3 scripts/notify.py preview approval
py -3 scripts/notify.py set --volume 0.15
py -3 scripts/notify.py set --tone bell
py -3 scripts/notify.py set --tone soft
py -3 scripts/notify.py set --approval off
py -3 scripts/notify.py set --completion on
py -3 scripts/notify.py design approval --notes 520,660,880 --note-ms 200 --gap-ms 40
py -3 scripts/notify.py design approval --reset
py -3 scripts/notify.py export-sound completion my-completion.wav
py -3 scripts/notify.py status
```

如果使用了自定义 `CODEX_HOME`，请进入它下面的 `skills/codex-soft-notify`。`volume` 范围 0–1；设为 0 可全部静音。两种事件有独立开关。切换音色或音量无需修改钩子命令。自定义音符覆盖预设音符；`design EVENT --reset` 取消该事件自定义设计。导出命令拒绝覆盖已有文件。

## 验证

1. `preview` 能响：只证明播放器可用。
2. `/hooks` 显示本工具已信任且 Active：证明当前客户端接受了钩子。
3. 用一条普通任务验证完成音；在下一次确有需要的审批中验证审批音。
4. `status` / 面板显示来源和结果。`hook` 是进入钩子入口，`preview` 是本机试听，`simulation` 是显式测试。直接向 hook 命令注入 JSON 也会显示 hook；这不是经过客户端签名的证明。
5. `played` 只表示播放 API 返回成功，听觉效果取决于设备和系统音量。浏览器“试听草稿”不写钩子证据。

运行数据位于 `runtime/delivery.sqlite3`：记录时间、事件、来源、状态以及请求标识的不可直接读出原文的 SHA-256 摘要，不保存聊天、审批理由、工具参数或原始会话标识。摘要并非匿名保证，不建议公开整个 runtime 目录。数据库保留最近约 1000 项历史和计数；待处理队列最多 500 项。面板导出的诊断 JSON 不含摘要或本地路径。

### 队列的可靠性边界

- 播放器只在有任务时启动，退出后不轮询。面板独立运行。
- 新审批不会打断已经播放的声音；同优先级先到先播，避免同时发声。
- 同一明确请求 ID 在 30 秒内合并；没有明确 ID 时不猜测去重。
- 等待超过 120 秒的声音标记 `expired`，不会突然重放旧提醒；满队列记为 `overflow`。
- 进程崩溃时的播放项标记 `interrupted`，不自动重播，因为无法知道是否已经可听见。短 worker 租约（最多 10 秒）到期后，下一次通知或“唤醒待播放项”恢复剩余队列；也可直接运行 `drain`。
- 不承诺音频严格恰好播放一次。发生播放故障记录 `error`，不影响正常审批流程。

## 卸载

在安装后的目录运行：

```powershell
py -3 scripts/notify.py uninstall
```

只移除安装清单中属于本工具的两种钩子处理器，并取消尚未播放的队列项，保留其他钩子与文件。已经开始的声音可能完成播放；请同时关闭面板，避免再排入试听。需要彻底清理时，再手动删除 `codex-soft-notify` 技能目录。不要用备份覆盖整个配置，以免撤销后来新增的其他钩子。

## 兼容性与限制

- 面向 Windows 和支持 `Stop` / `PermissionRequest` 的 Codex 客户端。没有 macOS/Linux 播放后端。
- 原型中的审批钩子曾在 Codex CLI 0.153.4 显示 Active；**本版本尚未经过真实客户端的完整触发验证**。
- 桌面端真实审批音未验证。某些应用权限弹窗可能不映射到该钩子，不能承诺覆盖所有确认窗口。
- 其他 `Stop` 钩子可能要求继续工作，因此声音代表一次停止事件，不是最终成功证据。
- 不订阅 `SubagentStop` 或 `Interrupt`。已知子代理标识会被忽略；未知未来事件格式需再次验证。
- 安装记录 Python 的绝对路径；更换 Python 或移动安装目录后请重新安装并重新检查信任。

事件语义与信任规则参考 [Codex 官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks)。

## 开发

```powershell
python -m unittest discover -s tests -v
```

测试使用临时目录，不修改真实 Codex 配置；GitHub Actions 配置覆盖 Windows + Python 3.11/3.13，远端结果需推送后确认。

## 来源

灵感来自 [YANG301/codex-sound-notifications](https://github.com/YANG301/codex-sound-notifications) 和实际使用中的安装体验。本项目采用新的原生钩子实现和代码合成音频。当前核查未发现上游完整文件或函数的直接复制；发布包不包含 Tarkov / SND 音频。MIT 声明仅针对本项目新增内容，不构成对上游内容的重新授权。

