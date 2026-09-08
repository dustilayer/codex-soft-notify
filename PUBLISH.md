# 上传 GitHub

建议仓库名：`codex-soft-notify`。简介：`Quiet Windows sounds for Codex completion and approval hooks.`

## 网页上传

1. 在 GitHub 创建空仓库。
2. 解压发布包，将 `codex-soft-notify` 目录**里面**的项目文件上传到仓库根目录。
3. 确认 `README.md` 在根目录，`.github/workflows/tests.yml` 也已上传。
4. 查看 Actions 结果。当前版本适合标为 `v0.2.0-preview`，完成客户端实测后再标稳定版。

## 使用 Git

在解压后的项目目录运行以下命令；最后一行使用你实际创建的仓库地址：

```powershell
git init
git add .
git commit -m "Initial Codex Soft Notify preview"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/codex-soft-notify.git
git push -u origin main
```

`YOUR-NAME` 需替换为自己的 GitHub 用户名。推送到现有仓库前先检查已有文件与分支。

`.gitignore` 已排除本地设置、运行日志、hook 备份与 Python 缓存。发布包不含个人 Codex 配置、认证文件、会话数据或旧游戏音效。
