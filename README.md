# 🔍 BidMonitor AI - 智能招投标监控系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## 📖 项目简介

BidMonitor AI 是一款功能强大的招投标信息监控系统，支持：

- 🌐 **多网站监控** - 支持40+招标网站（政府采购、电力、能源等）
- 🤖 **AI 智能过滤** - 使用 AI 二次筛选，精准匹配相关信息
- 📧 **多渠道通知** - 邮件、短信、微信、语音电话
- 🖥️ **双端部署** - Windows 桌面版 + 服务器 Web 版
- 🔄 **自动运行** - 定时监控，24小时不间断

## 🚀 快速开始

### Windows 桌面版

`ash
# 安装依赖
pip install -r requirements.txt

# 运行
python run.py
`

### 服务器 Web 版

`ash
cd server
pip install -r requirements.txt
python app.py
# 访问 http://localhost:8080
`

详细部署请参考 `server/DEPLOY.md`

## ✨ 功能特性

### 1. 关键词配置
- 包含关键词：匹配任意一个即命中
- 排除关键词：过滤不相关内容
- 必含关键词：标题必须包含

### 2. 多网站支持
- 政府采购网、中国招标网、中国能建、国家电网...
- 支持自定义网站配置
- 浏览器模式绕过反爬：CloakBrowser 隐身优先，Selenium 兜底，requests 最终兜底
- CloakBrowser 内置指纹补丁 + 拟人行为（humanize），Docker 镜像已预打包专用 Chromium

### 3. 通知方式
- 📧 邮件通知（支持多邮箱）
- 📱 短信通知（阿里云/腾讯云）
- 💬 微信推送（PushPlus）
- 📞 语音电话（阿里云）

### 4. AI 智能过滤
- 支持 DeepSeek、OpenAI 等 API
- 自动过滤无关招标信息

## 📁 项目结构

`
BidMonitor-AI/
├── src/                 # 核心代码
│   ├── gui.py           # 桌面 GUI
│   ├── monitor_core.py  # 监控核心
│   ├── ai_guard.py      # AI 过滤
│   ├── crawler/         # 爬虫模块
│   ├── notifier/        # 通知模块
│   └── database/        # 数据存储
├── server/              # 服务器版
│   ├── app.py           # FastAPI 应用
│   ├── static/          # Web 前端
│   └── setup.sh         # 部署脚本
├── run.py               # 启动入口
└── requirements.txt     # 依赖列表
`

## 🔧 配置说明

首次运行后，在界面中配置：

1. **关键词** - 根据需求设置监控关键词
2. **通知方式** - 配置邮箱/短信/微信等
3. **网站源** - 选择需要监控的网站
4. **AI 过滤** - （可选）配置 API Key

配置会自动保存到 `user_config.json`

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

⭐ 如果这个项目对你有帮助，请给个 Star！
