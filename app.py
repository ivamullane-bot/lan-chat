#!/usr/bin/env python3
"""
LAN Chat — 局域网聊天 + 文件快传
Flask + SocketIO 后端
v2: QR码下载 · 存储配额 · 30天压缩/60天删除 · 永久保留
"""

import os, json, uuid, time, hashlib, mimetypes, socket, gzip, threading
from datetime import datetime, timedelta
from pathlib import Path

import flask
from flask import Flask, request, jsonify, send_file, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import qrcode
from io import BytesIO
import base64

# ── Config ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FILES_DIR = DATA_DIR / "files"
ARCHIVES_DIR = DATA_DIR / "archives"
USERS_FILE = DATA_DIR / "users.json"
MESSAGES_FILE = DATA_DIR / "messages.json"
MAX_FILE_SIZE = 500 * 1024 * 1024       # 500 MB
DEFAULT_QUOTA = 10 * 1024 * 1024 * 1024  # 10 GB
RETENTION_DAYS_COMPRESS = 30              # 30天 → 压缩
RETENTION_DAYS_DELETE = 60                # 60天 → 删除
ADMIN_USERNAME = os.environ.get("LAN_CHAT_ADMIN", "admin")
ADMIN_PASSWORD = os.environ.get("LAN_CHAT_ADMIN_PASSWORD", "admin123")

DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "lan-chat-secret-change-me")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# ── LAN IP auto-detect ─────────────────────────────────────────────
def _get_lan_ip():
    """Get the primary LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"

LAN_IP = _get_lan_ip()

# ── Data helpers ────────────────────────────────────────────────────
def _load_json(path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _load_users():
    return _load_json(USERS_FILE, {})

def _save_users(data):
    _save_json(USERS_FILE, data)

def _load_messages():
    return _load_json(MESSAGES_FILE, [])

def _save_messages(data):
    _save_json(MESSAGES_FILE, data)

def _hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

def _format_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def _online_list():
    return [
        {"username": u["username"], "display_name": u["display_name"],
         "is_admin": u["is_admin"]}
        for u in online_users.values()
    ]

def dm_room(u1, u2):
    """Canonical room name for a DM between two users."""
    return "dm_" + "_".join(sorted([u1, u2]))

# ── User defaults ───────────────────────────────────────────────────
def _user_defaults(username, display_name=None, is_admin=False):
    return {
        "password": "",
        "is_admin": is_admin,
        "display_name": display_name or username,
        "avatar": None,
        "created_at": datetime.now().isoformat(),
        "storage_quota": -1 if is_admin else DEFAULT_QUOTA,
        "used_storage": 0,
        "permanent_files": [],
    }

def _ensure_admin():
    users = _load_users()
    if ADMIN_USERNAME not in users:
        users[ADMIN_USERNAME] = _user_defaults(
            ADMIN_USERNAME, "管理员", is_admin=True
        )
        users[ADMIN_USERNAME]["password"] = _hash_pw(ADMIN_PASSWORD)
        _save_users(users)
        print(f"[OK] Admin account created: {ADMIN_USERNAME}")

def _migrate_users():
    """Add missing fields to existing users (schema migration)."""
    users = _load_users()
    changed = False
    for name, u in users.items():
        is_admin = u.get("is_admin", False)
        if "storage_quota" not in u:
            u["storage_quota"] = -1 if is_admin else DEFAULT_QUOTA
            changed = True
        if "used_storage" not in u:
            u["used_storage"] = 0
            changed = True
        if "permanent_files" not in u:
            u["permanent_files"] = []
            changed = True
        if "display_name" not in u:
            u["display_name"] = name
            changed = True
    if changed:
        _save_users(users)
        print(f"[OK] Migrated {len(users)} user(s) to latest schema")

_ensure_admin()
_migrate_users()

# ── Online users tracking ───────────────────────────────────────────
online_users = {}  # sid -> {username, display_name, is_admin}

# ── REST API ────────────────────────────────────────────────────────
@app.route("/api/server-info")
def api_server_info():
    return jsonify({
        "lan_ip": LAN_IP,
        "port": 3333,
        "host": f"http://{LAN_IP}:3333",
    })

@app.route("/api/users", methods=["GET"])
def api_users():
    users = _load_users()
    result = []
    for name, info in users.items():
        used = info.get("used_storage", 0)
        quota = info.get("storage_quota", DEFAULT_QUOTA)
        result.append({
            "username": name,
            "display_name": info.get("display_name", name),
            "is_admin": info.get("is_admin", False),
            "has_password": bool(info.get("password")),
            "avatar": info.get("avatar"),
            "created_at": info.get("created_at", ""),
            "online": any(u["username"] == name for u in online_users.values()),
            "storage_used": used,
            "storage_used_display": _format_size(used),
            "storage_quota": quota,
            "storage_quota_display": "无限制" if quota == -1 else _format_size(quota),
            "storage_percent": min(100, round(used / quota * 100, 1)) if quota > 0 else 0,
            "permanent_files": info.get("permanent_files", []),
        })
    result.sort(key=lambda u: u["created_at"], reverse=True)
    return jsonify(result)

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username:
        return jsonify({"ok": False, "error": "请输入用户名"}), 400
    if len(username) > 32:
        return jsonify({"ok": False, "error": "用户名最长32个字符"}), 400

    users = _load_users()

    if username in users:
        user = users[username]
        if user.get("password") and _hash_pw(password) != user["password"]:
            return jsonify({"ok": False, "error": "密码错误"}), 403
    else:
        if username == ADMIN_USERNAME:
            return jsonify({"ok": False, "error": "管理员账号已存在"}), 403
        if username.lower() in ("admin", "root", "system"):
            return jsonify({"ok": False, "error": "用户名不可用"}), 403
        users[username] = _user_defaults(
            username,
            display_name=data.get("display_name", username),
        )
        if password:
            users[username]["password"] = _hash_pw(password)
        _save_users(users)

    u = users[username]
    return jsonify({
        "ok": True,
        "user": {
            "username": username,
            "display_name": u.get("display_name", username),
            "is_admin": u.get("is_admin", False),
            "storage_used": u.get("used_storage", 0),
            "storage_quota": u.get("storage_quota", DEFAULT_QUOTA),
        }
    })

# ── QR Code ─────────────────────────────────────────────────────────
@app.route("/api/qr/<file_id>/<path:filename>")
def api_qr(file_id, filename):
    """Generate a QR code PNG for a file download URL."""
    download_url = f"http://{LAN_IP}:3333/api/files/{file_id}/{filename}"
    qr = qrcode.make(download_url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return flask.send_file(buf, mimetype="image/png")

@app.route("/api/qr-data/<file_id>/<path:filename>")
def api_qr_data(file_id, filename):
    """Return QR code as base64 data URI for embedding."""
    download_url = f"http://{LAN_IP}:3333/api/files/{file_id}/{filename}"
    qr = qrcode.make(download_url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return jsonify({"qr_data_uri": f"data:image/png;base64,{b64}"})

# ── File Upload ─────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "没有文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "文件名不能为空"}), 400

    username = request.form.get("username", "unknown")
    users = _load_users()
    user = users.get(username)
    if not user:
        return jsonify({"ok": False, "error": "用户不存在"}), 403

    # ── Quota check ──
    quota = user.get("storage_quota", DEFAULT_QUOTA)
    used = user.get("used_storage", 0)
    estimated = file.seek(0, 2)
    file.seek(0)
    if quota != -1 and used + estimated > quota:
        free = quota - used
        return jsonify({
            "ok": False,
            "error": f"存储空间不足（剩余 {_format_size(free)}，需 {_format_size(estimated)}）"
        }), 403

    file_id = str(uuid.uuid4())[:8]
    original_name = file.filename
    safe_name = f"{file_id}_{original_name}"
    file_path = FILES_DIR / safe_name
    file.save(file_path)
    file_size = file_path.stat().st_size

    if file_size > MAX_FILE_SIZE:
        file_path.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": "文件超过500MB限制"}), 400

    # ── Update used_storage ──
    user["used_storage"] = user.get("used_storage", 0) + file_size
    _save_users(users)

    mime_type, _ = mimetypes.guess_type(original_name)
    is_image = mime_type and mime_type.startswith("image/")

    file_info = {
        "id": file_id,
        "name": original_name,
        "size": file_size,
        "size_display": _format_size(file_size),
        "mime": mime_type or "application/octet-stream",
        "is_image": is_image,
        "preview_url": f"/api/files/{file_id}/{original_name}" if is_image else None,
        "url": f"/api/files/{file_id}/{original_name}",
        "uploaded_by": username,
        "uploaded_at": datetime.now().isoformat(),
        "permanent": False,
    }
    return jsonify({"ok": True, "file": file_info})

# ── File Download ───────────────────────────────────────────────────
@app.route("/api/files/<file_id>/<filename>")
def api_download(file_id, filename):
    for f in FILES_DIR.iterdir():
        if f.name.startswith(file_id + "_"):
            # Update file access time for retention
            mime, _ = mimetypes.guess_type(filename)
            resp = send_file(
                f, mimetype=mime or "application/octet-stream",
                as_attachment=False, download_name=filename,
            )
            return resp
    abort(404)

# ── Messages ────────────────────────────────────────────────────────
@app.route("/api/messages", methods=["GET"])
def api_messages():
    limit = request.args.get("limit", 200, type=int)
    before = request.args.get("before", type=int)
    room = request.args.get("room", "lobby")
    msgs = _load_messages()
    msgs = [m for m in msgs if m.get("room", "lobby") == room]
    if before:
        msgs = [m for m in msgs if m["ts"] < before]
    msgs = msgs[-limit:]
    return jsonify(msgs)

@app.route("/api/files-list", methods=["GET"])
def api_files_list():
    msgs = _load_messages()
    file_msgs = [m for m in msgs if m.get("file")]
    files = []
    seen = set()
    for m in reversed(file_msgs):
        fid = m["file"]["id"]
        if fid not in seen:
            seen.add(fid)
            fi = dict(m["file"])
            fi["permanent"] = m.get("permanent", False)
            fi["msg_id"] = m.get("id")
            # Check if file still exists on disk
            fi["exists"] = any(
                p.name.startswith(fid + "_") for p in FILES_DIR.iterdir()
            )
            files.append(fi)
    return jsonify(files)

# ── Permanent toggle ────────────────────────────────────────────────
@app.route("/api/permanent", methods=["POST"])
def api_permanent():
    data = request.json or {}
    username = data.get("username", "")
    file_id = data.get("file_id", "")
    permanent = data.get("permanent", True)

    users = _load_users()
    if username not in users:
        return jsonify({"ok": False, "error": "用户不存在"}), 403

    u = users[username]
    perms = set(u.get("permanent_files", []))
    if permanent:
        perms.add(file_id)
    else:
        perms.discard(file_id)
    u["permanent_files"] = list(perms)
    _save_users(users)

    # Also mark in messages
    msgs = _load_messages()
    changed = 0
    for m in msgs:
        if m.get("file") and m["file"]["id"] == file_id:
            m["permanent"] = permanent
            changed += 1
    if changed:
        _save_messages(msgs)

    return jsonify({"ok": True, "permanent": permanent})

# ── Admin APIs ──────────────────────────────────────────────────────
@app.route("/api/admin/users", methods=["DELETE"])
def api_admin_delete_user():
    username = request.json.get("username", "")
    req_user = request.json.get("admin_user", "")
    users = _load_users()
    if req_user not in users or not users[req_user].get("is_admin"):
        return jsonify({"ok": False, "error": "无权限"}), 403
    if username == ADMIN_USERNAME:
        return jsonify({"ok": False, "error": "不能删除管理员"}), 403
    if username in users:
        # Free storage
        used = users[username].get("used_storage", 0)
        if used > 0:
            _free_user_files(username, users)
        del users[username]
        _save_users(users)
        for sid, info in list(online_users.items()):
            if info["username"] == username:
                socketio.emit("kicked", {"reason": "账户已被管理员删除"}, to=sid)
                leave_room("lobby", sid)
                del online_users[sid]
        socketio.emit("user_list", _online_list(), to="lobby")
    return jsonify({"ok": True})

@app.route("/api/admin/quota", methods=["POST"])
def api_admin_quota():
    data = request.json or {}
    req_user = data.get("admin_user", "")
    target_user = data.get("username", "")
    new_quota = data.get("quota", DEFAULT_QUOTA)

    users = _load_users()
    if req_user not in users or not users[req_user].get("is_admin"):
        return jsonify({"ok": False, "error": "无权限"}), 403
    if target_user not in users:
        return jsonify({"ok": False, "error": "用户不存在"}), 404

    users[target_user]["storage_quota"] = new_quota
    _save_users(users)
    return jsonify({"ok": True, "quota": new_quota})

def _free_user_files(username, users):
    """Delete files uploaded by a user and free storage."""
    msgs = _load_messages()
    freed = 0
    for m in msgs:
        if m.get("file") and m.get("username") == username:
            fid = m["file"]["id"]
            fname = m["file"]["name"]
            for p in FILES_DIR.iterdir():
                if p.name.startswith(fid + "_"):
                    freed += p.stat().st_size
                    p.unlink(missing_ok=True)
                    break
    if username in users:
        users[username]["used_storage"] = max(0, users[username].get("used_storage", 0) - freed)

# ── Retention Background Task ───────────────────────────────────────
RETENTION_INTERVAL = 3600  # check every hour

def _retention_task():
    """Archive msgs > 30 days, delete archives > 60 days, clean stale files."""
    while True:
        try:
            _run_retention()
        except Exception as e:
            print(f"[Retention] Error: {e}")
        time.sleep(RETENTION_INTERVAL)

def _run_retention():
    now = time.time()
    cutoff_compress = now - RETENTION_DAYS_COMPRESS * 86400
    cutoff_delete = now - RETENTION_DAYS_DELETE * 86400

    users = _load_users()
    all_permanent = set()
    for u in users.values():
        all_permanent.update(u.get("permanent_files", []))

    # ── Messages: archive old ──
    msgs = _load_messages()
    to_keep = []
    to_archive = []
    for m in msgs:
        mts = m.get("ts", 0) / 1000
        is_file_msg = m.get("file") is not None
        is_permanent = is_file_msg and m["file"]["id"] in all_permanent
        if is_permanent or mts >= cutoff_compress:
            to_keep.append(m)
        else:
            to_archive.append(m)

    if to_archive:
        by_month = {}
        for m in to_archive:
            dt = datetime.fromtimestamp(m["ts"] / 1000)
            key = dt.strftime("%Y-%m")
            by_month.setdefault(key, []).append(m)
        for month, ms in by_month.items():
            ap = ARCHIVES_DIR / f"{month}.json.gz"
            existing = []
            if ap.exists():
                try:
                    with gzip.open(ap, "rt", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.extend(ms)
            with gzip.open(ap, "wt", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False)

        _save_messages(to_keep)
        print(f"[Retention] Archived {len(to_archive)} messages")

    # ── Delete old archives ──
    deleted_archives = 0
    for ap in ARCHIVES_DIR.glob("*.json.gz"):
        try:
            mtime = ap.stat().st_mtime
            if mtime < cutoff_delete:
                ap.unlink()
                deleted_archives += 1
        except Exception:
            pass
    if deleted_archives:
        print(f"[Retention] Deleted {deleted_archives} old archives")

    # ── Files: cleanup stale (non-permanent, >60 days) ──
    freed_total = 0
    for m in msgs + to_archive:
        if not m.get("file"):
            continue
        fid = m["file"]["id"]
        if fid in all_permanent:
            continue
        fname = m["file"].get("name", "")
        fts_str = m["file"].get("uploaded_at", "")
        try:
            fts = datetime.fromisoformat(fts_str).timestamp()
        except Exception:
            fts = m.get("ts", 0) / 1000
        if fts < cutoff_delete:
            for p in FILES_DIR.iterdir():
                if p.name.startswith(fid + "_"):
                    fsz = p.stat().st_size
                    p.unlink(missing_ok=True)
                    # Free quota for uploader
                    uploader = m.get("username", "")
                    if uploader in users:
                        users[uploader]["used_storage"] = max(
                            0, users[uploader].get("used_storage", 0) - fsz
                        )
                        freed_total += fsz
                    break
    if freed_total:
        _save_users(users)
        print(f"[Retention] Cleaned files, freed {_format_size(freed_total)}")

# ── SocketIO Events ────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    pass

@socketio.on("disconnect")
def on_disconnect():
    user = online_users.pop(request.sid, None)
    if user:
        leave_room("lobby", request.sid)
        socketio.emit("system_msg", {
            "text": f"{user['display_name']} 离开了聊天室",
            "type": "leave",
        }, to="lobby")
        socketio.emit("user_list", _online_list(), to="lobby")

@socketio.on("join")
def on_join(data):
    username = data.get("username", "")
    users_data = _load_users()
    if username not in users_data:
        emit("error", {"text": "用户不存在"})
        return

    user_info = users_data[username]
    online_users[request.sid] = {
        "username": username,
        "display_name": user_info.get("display_name", username),
        "is_admin": user_info.get("is_admin", False),
    }
    join_room("lobby", request.sid)

    emit("joined", {"username": username})
    socketio.emit("system_msg", {
        "text": f"{user_info.get('display_name', username)} 加入了聊天室",
        "type": "join",
    }, to="lobby")
    socketio.emit("user_list", _online_list(), to="lobby")

@socketio.on("join_dm")
def on_join_dm(data):
    """Join a DM room with another user."""
    user = online_users.get(request.sid)
    if not user:
        return
    target = data.get("target", "")
    if not target or target == user["username"]:
        return
    room = dm_room(user["username"], target)
    join_room(room, request.sid)
    emit("dm_joined", {"room": room, "target": target})

@socketio.on("leave_dm")
def on_leave_dm(data):
    """Leave a DM room, go back to lobby."""
    user = online_users.get(request.sid)
    if not user:
        return
    target = data.get("target", "")
    if not target:
        return
    room = dm_room(user["username"], target)
    leave_room(room, request.sid)
    emit("dm_left", {"room": room})

@socketio.on("new_message")
def on_new_message(data):
    user = online_users.get(request.sid)
    if not user:
        return

    text = data.get("text", "").strip()
    file_info = data.get("file")
    room = data.get("room", "lobby")
    forward = data.get("forward")  # {from: ..., file: {...}, text: ...}

    if not text and not file_info and not forward:
        return

    if forward:
        msg_type = "forward"
    elif file_info:
        msg_type = "file"
    else:
        msg_type = "text"

    msg = {
        "id": str(uuid.uuid4())[:8],
        "type": msg_type,
        "username": user["username"],
        "display_name": user["display_name"],
        "is_admin": user["is_admin"],
        "text": text,
        "file": file_info,
        "forward": forward,
        "permanent": False,
        "room": room,
        "ts": int(time.time() * 1000),
        "time": datetime.now().strftime("%H:%M"),
    }

    msgs = _load_messages()
    msgs.append(msg)
    _save_messages(msgs)

    # Emit to the correct room (lobby or DM room)
    socketio.emit("new_message", msg, to=room)

@socketio.on("delete_message")
def on_delete_message(data):
    user = online_users.get(request.sid)
    if not user or not user["is_admin"]:
        emit("error", {"text": "无权限"})
        return

    msg_id = data.get("id")
    msgs = _load_messages()
    # Free file storage if deleting a file message
    for m in msgs:
        if m.get("id") == msg_id and m.get("file"):
            fid = m["file"]["id"]
            for p in FILES_DIR.iterdir():
                if p.name.startswith(fid + "_"):
                    fsz = p.stat().st_size
                    p.unlink(missing_ok=True)
                    # Free uploader's quota
                    uploader = m.get("username", "")
                    users = _load_users()
                    if uploader in users:
                        users[uploader]["used_storage"] = max(
                            0, users[uploader].get("used_storage", 0) - fsz
                        )
                        _save_users(users)
                    break
            break

    msgs = [m for m in msgs if m.get("id") != msg_id]
    _save_messages(msgs)
    socketio.emit("message_deleted", {"id": msg_id}, to="lobby")

@socketio.on("typing")
def on_typing(data):
    user = online_users.get(request.sid)
    if not user:
        return
    is_typing = data.get("typing", False)
    socketio.emit("typing_indicator", {
        "username": user["username"],
        "display_name": user["display_name"],
        "typing": is_typing,
    }, to="lobby")

@socketio.on("clear_messages")
def on_clear_messages(data):
    user = online_users.get(request.sid)
    if not user or not user["is_admin"]:
        emit("error", {"text": "无权限"})
        return
    _save_messages([])
    socketio.emit("messages_cleared", to="lobby")

# ── Serve Frontend ─────────────────────────────────────────────────
@app.route("/")
def index():
    return flask.send_from_directory(BASE_DIR / "static", "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    """Serve static assets (manifest.json, sw.js, icons, etc.)."""
    safe_dir = (BASE_DIR / "static").resolve()
    requested = (safe_dir / filename).resolve()
    if safe_dir in requested.parents and requested.exists():
        return flask.send_from_directory(safe_dir, filename)
    abort(404)

# ── Main ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start retention background thread
    rt = threading.Thread(target=_retention_task, daemon=True)
    rt.start()

    print("=" * 55)
    print(f"  LAN Chat v2")
    print(f"  LAN IP:     http://{LAN_IP}:3333")
    print(f"  Admin:      {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print(f"  Default quota: 10 GB/user")
    print(f"  Retention:  {RETENTION_DAYS_COMPRESS}d compress / {RETENTION_DAYS_DELETE}d delete")
    print("=" * 55)
    socketio.run(app, host="0.0.0.0", port=3333, debug=False, allow_unsafe_werkzeug=True)
