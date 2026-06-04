#!/usr/bin/env python3
"""
LAN Chat · 桌面通知伴侣
====================
在系统托盘运行，即使浏览器关闭也能收到新消息通知。
依赖: pip install python-socketio plyer

用法:
  python notifier.py http://192.168.100.199:3333
"""

import sys, os, json, time, threading, uuid
from datetime import datetime
from pathlib import Path

import socketio

DESKTOP = False
try:
    from plyer import notification as plyer_notify
    DESKTOP = True
except ImportError:
    pass

# ── Config ──────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).resolve().parent / "data" / "notifier_config.json"

def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def notify(title, body):
    """Show desktop notification."""
    if DESKTOP:
        try:
            plyer_notify.notify(
                title=title,
                message=body,
                app_name="LAN Chat",
                timeout=5,
            )
            return
        except Exception:
            pass
    # Fallback: console
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {title}: {body}")


def main():
    if len(sys.argv) < 2:
        print("用法: python notifier.py <服务器URL>")
        print("示例: python notifier.py http://192.168.100.199:3333")
        sys.exit(1)

    server_url = sys.argv[1].rstrip("/")
    config = load_config()
    username = config.get("username", "")
    password = config.get("password", "")

    if not username:
        print(f"连接到 {server_url} …")
        username = input("用户名 (留空=仅监听): ").strip()
        if username:
            pw = input("密码 (没有直接回车): ").strip()
            save_config({"username": username, "password": pw})
            password = pw
        else:
            save_config({"username": "", "password": ""})

    # Auto-login to get session
    import urllib.request, urllib.parse

    sio = socketio.Client()
    connected = False
    my_name = ""

    def on_connect():
        nonlocal connected
        print(f"[✓] 已连接到 {server_url}")
        connected = True
        if username:
            sio.emit("join", {"username": username})

    def on_disconnect():
        print(f"[!] 连接断开，3秒后重连…")
        time.sleep(3)
        try:
            sio.connect(server_url, transports=["websocket", "polling"])
        except Exception as e:
            print(f"[!] 重连失败: {e}")

    @sio.on("new_message")
    def on_msg(msg):
        if msg.get("username") == username:
            return  # skip own messages
        sender = msg.get("display_name") or msg.get("username") or "未知"
        if msg.get("type") == "file" and msg.get("file"):
            body = f"[文件] {msg['file']['name']} ({msg['file'].get('size_display', '')})"
        else:
            body = msg.get("text", "")[:120]
        notify(f"📩 {sender}", body)

    @sio.on("system_msg")
    def on_system(msg):
        text = msg.get("text", "")
        if "加入了" in text or "离开了" in text:
            notify("👤 " + text, "")

    @sio.on("connect_error")
    def on_error(data):
        print(f"[!] 连接错误: {data}")

    # Connect
    print(f"⏳ 正在连接 {server_url} …")
    try:
        sio.connect(server_url, transports=["websocket", "polling"])
    except Exception as e:
        print(f"[✗] 连接失败: {e}")
        print("提示: 确认服务器地址正确并且正在运行")
        sys.exit(1)

    print("=" * 45)
    print(f"  LAN Chat 通知伴侣")
    print(f"  服务器: {server_url}")
    print(f"  用户:   {username or '(仅监听)'}")
    print(f"  按 Ctrl+C 退出")
    print("=" * 45)

    try:
        sio.wait()
    except KeyboardInterrupt:
        print("\n退出")
        sio.disconnect()


if __name__ == "__main__":
    main()
