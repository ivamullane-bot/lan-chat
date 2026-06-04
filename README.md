# LAN Chat 💬

> 局域网即时通讯 + 文件快传 · 运行在 Docker 上

[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://www.docker.com)
[![License](https://img.shields.io/badge/License-MIT-green)]()

---

## 🚀 快速开始

```bash
git clone https://github.com/ivamullane-bot/lan-chat.git
cd lan-chat
docker compose up -d
```

访问 **http://<你的NAS局域网IP>:3333**

| 默认账号 | 密码 |
|---------|------|
| `admin` | `admin123` |

---

## ✨ 功能总览

| 功能 | 说明 |
|------|------|
| 💬 **实时聊天** | WebSocket 即时通讯，输入提示，消息持久化 |
| 📁 **文件快传** | 拖拽上传，图片预览，**二维码扫码下载**，最大 500MB |
| 👥 **免密账号** | 可选无密码，点击即登录 |
| 💬 **私聊系统** | 点用户旁的 💬 按钮进入私密聊天 |
| ↻ **消息转发** | 转发时引用原文件，**不重复占用存储** |
| 📱 **桌面通知** | 页面后台时弹出 OS 通知 + 提示音 |
| 📱 **手机适配** | 响应式设计，手机浏览器完美使用 |
| 🗄 **自动归档** | 30天压缩 → 60天删除，支持 ★ 永久保留 |
| 💾 **存储配额** | 默认 10GB/用户，管理员可随时调整 |
| 🔧 **管理员面板** | 管理用户、配额、消息、归档策略 |
| 📱 **PWA 支持** | 可安装为桌面应用，离线缓存 |
| 🎨 **高级简约** | 暗色主题，玻璃质感，极致体验 |

---

## 📁 项目结构

```
lan-chat/
├── app.py                       # 后端 (Flask + SocketIO)
├── Dockerfile                   # Docker 构建
├── docker-compose.yml           # 一键部署
├── requirements.txt             # 服务端依赖
├── notifier.py                  # 桌面通知伴侣脚本
├── static/
│   ├── index.html               # 前端（高级简约UI）
│   ├── manifest.json            # PWA 清单
│   ├── sw.js                    # Service Worker
│   ├── favicon.ico
│   └── icon-*.png               # PWA 图标
└── data/                        # 持久化数据（自动生成）
    ├── users.json               # 用户账号与配额
    ├── messages.json            # 聊天消息
    ├── files/                   # 上传的文件
    └── archives/                # 30天前压缩归档
```

---

## 🧩 技术栈

- **后端**: Python 3.11 + Flask + Flask-SocketIO + Gevent
- **前端**: 纯 HTML/CSS/JS（无框架依赖）
- **实时通信**: WebSocket (SocketIO)
- **数据库**: JSON 文件存储
- **容器**: Docker + docker-compose

---

## 📱 桌面通知伴侣

即使关闭浏览器，也能收到新消息通知：

```bash
pip install -r notifier-requirements.txt
python notifier.py http://<NAS-IP>:3333
```

---

## ⚙️ 自定义配置

编辑 `docker-compose.yml` 环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LAN_CHAT_ADMIN` | admin | 管理员用户名 |
| `LAN_CHAT_ADMIN_PASSWORD` | admin123 | 管理员密码 |
| `LAN_CHAT_HOST` | 自动检测 | NAS 局域网 IP |
| `SECRET_KEY` | — | Flask 密钥 |

---

## 📜 归档策略

| 时间 | 动作 |
|------|------|
| > 30 天 | 消息自动压缩到 `.json.gz` |
| > 60 天 | 压缩包和文件自动删除 |
| ★ 永久 | 标记的文件永不删除 |

后台线程每小时自动检查。

---

## 📄 开源协议

MIT License
