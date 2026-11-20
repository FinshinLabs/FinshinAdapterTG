# Telegram 适配器

[![主仓 FinshinImpact](https://img.shields.io/badge/主仓-FinshinImpact-blue.svg)](https://github.com/FinshinLabs/FinshinImpact)
[![Aiogram Version](https://img.shields.io/badge/aiogram-3.x-green.svg)](https://docs.aiogram.dev/)

本体与 Telegram 之间的那一层，用 `aiogram 3.x` 长轮询，实现接口包 `finshin-sdk` 的适配器契约，由本体装载。其余依赖见仓根的 `pyproject.toml`。

## 放在哪儿

本仓不单独开发：clone 进主仓的 `finshin/adapter/tg`，改动在那棵目录里做，代码在 `src` 那一层。挂载与更新的步骤见 [挂载子仓](https://github.com/FinshinLabs/FinshinImpact/blob/main/docs/development.md#挂载子仓)。

## 跑法

```powershell
# 在主仓根执行
python -m pytest finshin/adapter/tg/tests
```

改过 `src/` 先重装再跑：`.venv\Scripts\uv.exe sync --all-packages --reinstall-package finshin-adapter-tg`，测试读的是装进环境的那一份。

## 声明与规范

- 声明字段、依赖 pin 与版本号单源见 [新增平台适配器](https://github.com/FinshinLabs/FinshinImpact/blob/main/docs/development.md#新增平台适配器)。
- 构建、tag 与 release 附件见 [子仓供件](https://github.com/FinshinLabs/FinshinImpact/blob/main/docs/release-workflow.md#子仓供件)。
- 写法与检查见 [代码规范](https://github.com/FinshinLabs/FinshinImpact/blob/main/docs/coding-style.md) 与 [规范扫描器](https://github.com/FinshinLabs/FinshinImpact/blob/main/docs/style-checker.md)，本仓不另立一套规范。
