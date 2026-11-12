# Telegram 适配器

[![主仓 FinshinImpact](https://img.shields.io/badge/主仓-FinshinImpact-blue.svg)](https://github.com/lym2006/FinshinImpact)

本体与 Telegram 之间的那一层，实现接口包 `finshin-sdk` 的适配器契约，由本体装载。

## 放在哪儿

本仓不单独开发。先 clone 主仓 `FinshinImpact`，再把本仓 clone 进它的 `finshin/adapter/tg`，改动在那棵目录里做，代码在 `src` 那一层，声明按 `package-dir` 把它映射成包名。

改完生效跑 `.venv\Scripts\uv.exe sync --all-packages --reinstall-package finshin-adapter-tg`，普通 sync 不重装子仓那棵。

## 跑法

```powershell
# 在主仓根执行
python -m pytest finshin/adapter/tg/tests
```

跑用例要在主仓根，接口包与引擎库由主仓环境提供。

## 规范归主仓

- 挂载、更新与摘掉见 [docs/development.md](https://github.com/lym2006/FinshinImpact/blob/main/docs/development.md) 的「挂载子仓」一节。
- 声明字段、依赖 pin 与版本号单源见同一文件的「新增平台适配器」一节。
- 构建、tag 与 release 附件见 [docs/release-workflow.md](https://github.com/lym2006/FinshinImpact/blob/main/docs/release-workflow.md) 的「子仓供件」一节。
- 编码规范见 [docs/coding-style.md](https://github.com/lym2006/FinshinImpact/blob/main/docs/coding-style.md)，静态检查与豁免见 [docs/style-checker.md](https://github.com/lym2006/FinshinImpact/blob/main/docs/style-checker.md)。
- 本仓不另立一套规范。
