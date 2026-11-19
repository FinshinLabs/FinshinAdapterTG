# Changelog

本项目的所有重要更改都将记录在此文件中。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 🔧 Changed

- **适配器入口多交平台显示名**：`parts()` 把装配、通道探测、引擎预热与显示名 `Telegram` 四件一起交出。
- **代理探测错误按配置项身份交出**：探测错误表的代理项键带上来源与段两段身份，与面板标红共用同一个配置项。

## [0.1.0] - 2026-11-14

### ✨ Added

- **Telegram 平台适配器**：实现接口包 `finshin-sdk` 的适配器契约，由本体装载。

### 🔧 Changed

- **接口包版本要求带上限**：声明写成 `finshin-sdk>=0.1.0,<0.2.0`，这一版只配 0.1.x 的接口包。
