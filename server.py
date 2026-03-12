#!/usr/bin/env python3
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import cgi

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "chatbot.db")
STATIC_DIR = os.path.join(ROOT, "static")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('notes','important_questions','question_papers')),
            file_path TEXT NOT NULL,
            uploaded_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(uploaded_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()


def hash_password(raw: str) -> str:
    import hashlib

    salt = secrets.token_hex(8)
    digest = hashlib.sha256((salt + raw).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(raw: str, stored: str) -> bool:
    import hashlib

    if "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    return hashlib.sha256((salt + raw).encode()).hexdigest() == digest


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def parse_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        return json.loads(body.decode() or "{}")

    def auth_user(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        conn = get_db()
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token=?",
            (token,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def serve_static(self, path):
        safe = os.path.normpath(path).lstrip("/")
        target = os.path.join(STATIC_DIR, safe)
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.exists(target):
            return False
        if target.endswith(".html"):
            ctype = "text/html"
        elif target.endswith(".css"):
            ctype = "text/css"
        elif target.endswith(".js"):
            ctype = "application/javascript"
        else:
            ctype = "application/octet-stream"
        with open(target, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/resources":
            conn = get_db()
            rows = conn.execute(
                "SELECT id,title,category,file_path,created_at FROM resources ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            items = [dict(r) for r in rows]
            for it in items:
                it["download_url"] = f"/files/{os.path.basename(it['file_path'])}"
            return self.send_json({"resources": items})

        if parsed.path == "/api/chat-history":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            conn = get_db()
            rows = conn.execute(
                "SELECT role,message,created_at FROM chat_history WHERE user_id=? ORDER BY id ASC",
                (user["id"],),
            ).fetchall()
            conn.close()
            return self.send_json({"history": [dict(r) for r in rows]})

        if parsed.path.startswith("/files/"):
            fname = os.path.basename(parsed.path)
            fpath = os.path.join(UPLOAD_DIR, fname)
            if not os.path.exists(fpath):
                self.send_error(404)
                return
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/" or parsed.path.startswith("/static"):
            sub = "index.html" if parsed.path == "/" else parsed.path.replace("/static/", "")
            if self.serve_static(sub):
                return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/signup":
            data = self.parse_json()
            name = data.get("name", "").strip()
            email = data.get("email", "").strip().lower()
            password = data.get("password", "")
            if not name or not email or len(password) < 6:
                return self.send_json({"error": "Provide name, valid email, and password >= 6 chars"}, 400)
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)",
                    (name, email, hash_password(password), now_iso()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return self.send_json({"error": "Email already exists"}, 409)
            conn.close()
            return self.send_json({"message": "Signup successful"}, 201)

        if parsed.path == "/api/login":
            data = self.parse_json()
            email = data.get("email", "").strip().lower()
            password = data.get("password", "")
            conn = get_db()
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not row or not verify_password(password, row["password"]):
                conn.close()
                return self.send_json({"error": "Invalid credentials"}, 401)
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)", (token, row["id"], now_iso()))
            conn.commit()
            conn.close()
            return self.send_json({"token": token, "user": {"id": row["id"], "name": row["name"], "email": row["email"]}})

        if parsed.path == "/api/upload-resource":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            ctype, pdict = cgi.parse_header(self.headers.get("content-type"))
            if ctype != "multipart/form-data":
                return self.send_json({"error": "multipart/form-data required"}, 400)
            pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"}, keep_blank_values=True)
            title = (form.getfirst("title") or "").strip()
            category = (form.getfirst("category") or "").strip()
            file_item = form["file"] if "file" in form else None
            if not title or category not in {"notes", "important_questions", "question_papers"} or file_item is None:
                return self.send_json({"error": "title, category, and file are required"}, 400)
            filename = os.path.basename(file_item.filename or "upload.pdf")
            if not filename.lower().endswith(".pdf"):
                return self.send_json({"error": "Only PDF files allowed"}, 400)
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
            stored_name = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
            path = os.path.join(UPLOAD_DIR, stored_name)
            with open(path, "wb") as out:
                out.write(file_item.file.read())

            conn = get_db()
            conn.execute(
                "INSERT INTO resources(title,category,file_path,uploaded_by,created_at) VALUES(?,?,?,?,?)",
                (title, category, path, user["id"], now_iso()),
            )
            conn.commit()
            conn.close()
            return self.send_json({"message": "Resource uploaded"}, 201)

        if parsed.path == "/api/chat":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            data = self.parse_json()
            message = (data.get("message") or "").strip()
            if not message:
                return self.send_json({"error": "Message required"}, 400)
            conn = get_db()
            conn.execute(
                "INSERT INTO chat_history(user_id,role,message,created_at) VALUES(?,?,?,?)",
                (user["id"], "user", message, now_iso()),
            )
            resource_rows = conn.execute(
                "SELECT title,category,file_path FROM resources ORDER BY created_at DESC LIMIT 3"
            ).fetchall()
            tips = ", ".join([f"{r['title']} ({r['category']})" for r in resource_rows]) or "No resources uploaded yet"
            response = (
                "Anna University assistant: I can help with study plans, important questions, and notes. "
                f"Latest resources: {tips}. Your question was: {message}"
            )
            conn.execute(
                "INSERT INTO chat_history(user_id,role,message,created_at) VALUES(?,?,?,?)",
                (user["id"], "assistant", response, now_iso()),
            )
            conn.commit()
            conn.close()
            return self.send_json({"reply": response})

        self.send_error(404)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Server running on http://0.0.0.0:{port}")
    server.serve_forever()
