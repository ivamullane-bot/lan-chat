# LAN Chat — 局域网聊天 & 文件快传

高级简约风格的局域网即时通讯与文件传输工具，运行在 Docker 上。

## 快速启动

```bash
# 进入项目目录，然后：
docker compose up -d
```

访问：`http://<你的NAS局域网IP>:3333`

## 功能

| 功能 | 说明 |
|------|------|
| 💬 **实时聊天** | WebSocket 即时通讯，输入提示，消息持久化 |
| 📁 **文件快传** | 拖拽上传，图片预览，二维码扫码下载，最大 500MB |
| 👥 **免密账号** | 可选无密码，点击即登录 |
| 📱 **桌面通知** | 页面在后台时弹出 OS 原生通知 + 提示音 |
| 🗄 **自动归档** | 30天压缩 → 60天删除，支持★永久保留 |
| 💾 **存储配额** | 默认10GB/用户，管理员可随时调整 |
| 🔧 **管理员面板** | 管理用户、配额、消息、归档策略 |
| 🎨 **高级简约** | 暗色主题，玻璃质感，响应式适配 |

## 默认管理员

- **账号**: `admin`
- **密码**: `admin123`

首次启动自动创建，侧边栏底部 ⚙ 进入管理面板。

## 📱 桌面通知（浏览器关闭后也能收到消息）

```bash
# 在你自己的电脑上（不是NAS）：
pip install -r notifier-requirements.txt
python notifier.py http://<NAS-IP>:3333
```

- 即使浏览器/网页已关闭，也能收到新消息 OS 弹窗
- 支持 Windows/macOS/Linux 原生通知
- 按 `Ctrl+C` 退出

## 聊天记录归档策略

| 时间 | 动作 |
|------|------|
| **> 30 天** | 消息自动压缩到 `data/archives/YYYY-MM.json.gz` |
| **> 60 天** | 压缩包自动删除，文件从磁盘清理 |
| **★ 永久保留** | 在消息或文件面板点 ☆ 标记，永不删除 |

后台每小时检查一次。

## 管理存储配额

- 普通用户默认 **10GB**
- 管理员 **无限制**
- 管理员面板可对任意用户设置 GB/MB 级别配额

## 自定义

编辑 `docker-compose.yml` 中的环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LAN_CHAT_ADMIN` | admin | 管理员用户名 |
| `LAN_CHAT_ADMIN_PASSWORD` | admin123 | 管理员密码 |
| `SECRET_KEY` | — | Flask 密钥，建议改随机字符串 |

## 数据持久化

所有数据存储在 `./data/` 目录，删除容器不会丢失：
- `users.json` — 用户账号、配额、永久文件列表
- `messages.json` — 当前消息
- `files/` — 上传的文件
- `archives/` — 超过30天的压缩归档

## 项目结构

```
lan-chat/
├── app.py                       # 后端服务
├── Dockerfile                   # Docker 构建
├── docker-compose.yml           # 一键部署
├── notifier.py                  # 桌面通知伴侣脚本
├── requirements.txt             # 服务端依赖
├── notifier-requirements.txt    # 通知伴侣依赖
├── static/
│   ├── index.html               # 前端（全部内嵌）
│   ├── manifest.json            # PWA 清单
│   ├── sw.js                    # Service Worker
│   ├── favicon.ico
│   ├── icon-192.png
│   └── icon-512.png
└── data/                        # 持久化数据
```
