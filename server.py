#!/usr/bin/env python3
import cgi
import hashlib
import json
import mimetypes
import os
import re
import secrets
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request
from urllib.parse import quote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "chatbot.db")
STATIC_DIR = os.path.join(ROOT, "static")
UPLOAD_DIR = os.path.join(ROOT, "uploads")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
os.makedirs(UPLOAD_DIR, exist_ok=True)

CATEGORY_LABELS = {
    "notes": "notes",
    "important_questions": "important questions",
    "question_papers": "question papers",
}
ALLOWED_EXT = {
    "notes": {".pdf"},
    "question_papers": {".pdf"},
    "important_questions": {".pdf", ".png", ".jpg", ".jpeg", ".webp"},
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.utcnow().isoformat() + "Z"


def hash_password(raw):
    salt = secrets.token_hex(8)
    digest = hashlib.sha256((salt + raw).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(raw, stored):
    if "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    return hashlib.sha256((salt + raw).encode()).hexdigest() == digest


def normalize_subject(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def parse_file_metadata(filename):
    stem, _ = os.path.splitext(filename)
    if "__" in stem:
        subject, title = stem.split("__", 1)
        subject = subject.replace("_", " ").strip()
        title = title.replace("_", " ").strip()
    else:
        subject = "General"
        title = stem.replace("_", " ").strip()
    return subject or "General", title or filename


def build_download_url(path):
    return f"/files/{quote(os.path.basename(path))}"


def parse_requested_category(message):
    text = message.lower()
    if "important" in text and "question" in text:
        return "important_questions"
    if "question paper" in text or "questionpaper" in text:
        return "question_papers"
    if "note" in text or "notes" in text:
        return "notes"
    return None


def detect_subject_from_message(message, subjects):
    msg = normalize_subject(message)
    for subject in subjects:
        normalized = normalize_subject(subject)
        if normalized and normalized in msg:
            return subject
    return None


def get_openai_reply(message, context_lines):
    if not OPENAI_API_KEY:
        return None

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "You are 'educhat bot', an assistant for Anna University students. Keep answers short and practical.",
            },
            {
                "role": "user",
                "content": f"User question: {message}\n\nAvailable resources:\n{context_lines}",
            },
        ],
        "temperature": 0.3,
    }

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except (error.URLError, error.HTTPError, KeyError, IndexError, TimeoutError, json.JSONDecodeError):
        return None


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
            subject TEXT NOT NULL DEFAULT '',
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
    cols = [row[1] for row in conn.execute("PRAGMA table_info(resources)").fetchall()]
    if "subject" not in cols:
        conn.execute("ALTER TABLE resources ADD COLUMN subject TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()


def sync_resources_from_disk(conn):
    added = 0
    for category in CATEGORY_LABELS:
        category_dir = os.path.join(UPLOAD_DIR, category)
        os.makedirs(category_dir, exist_ok=True)
        for fname in os.listdir(category_dir):
            if fname.startswith("."):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXT[category]:
                continue
            fpath = os.path.join(category_dir, fname)
            exists = conn.execute("SELECT 1 FROM resources WHERE file_path = ?", (fpath,)).fetchone()
            if exists:
                continue
            subject, title = parse_file_metadata(fname)
            conn.execute(
                "INSERT INTO resources(title, subject, category, file_path, uploaded_by, created_at) VALUES(?,?,?,?,?,?)",
                (title, subject, category, fpath, None, now_iso()),
            )
            added += 1
    conn.commit()
    return added


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
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
            (token,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def serve_static(self, path):
        target = os.path.join(STATIC_DIR, os.path.normpath(path).lstrip("/"))
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.exists(target):
            return False
        ctype = "application/octet-stream"
        if target.endswith(".html"):
            ctype = "text/html"
        elif target.endswith(".css"):
            ctype = "text/css"
        elif target.endswith(".js"):
            ctype = "application/javascript"
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
            sync_resources_from_disk(conn)
            rows = conn.execute(
                "SELECT id, title, subject, category, file_path, created_at FROM resources ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            items = []
            for row in rows:
                d = dict(row)
                d["download_url"] = build_download_url(d["file_path"])
                d["file_type"] = os.path.splitext(d["file_path"])[1].lower()
                items.append(d)
            return self.send_json({"resources": items})

        if parsed.path == "/api/chat-history":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            conn = get_db()
            rows = conn.execute(
                "SELECT role, message, created_at FROM chat_history WHERE user_id = ? ORDER BY id ASC", (user["id"],)
            ).fetchall()
            conn.close()
            return self.send_json({"history": [dict(r) for r in rows]})

        if parsed.path == "/api/me":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            return self.send_json({"user": {"id": user["id"], "name": user["name"], "email": user["email"]}})

        if parsed.path.startswith("/files/"):
            filename = os.path.basename(parsed.path)
            path = None
            for category in CATEGORY_LABELS:
                candidate = os.path.join(UPLOAD_DIR, category, filename)
                if os.path.exists(candidate):
                    path = candidate
                    break
            if not path:
                self.send_error(404)
                return
            with open(path, "rb") as f:
                data = f.read()
            ctype, _ = mimetypes.guess_type(path)
            ctype = ctype or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
            name = (data.get("name") or "").strip()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            confirm = data.get("confirm_password") or ""
            if not name or not email or len(password) < 6:
                return self.send_json({"error": "Provide name, email, and password (min 6 chars)."}, 400)
            if password != confirm:
                return self.send_json({"error": "Password and confirm password do not match."}, 400)
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users(name, email, password, created_at) VALUES(?,?,?,?)",
                    (name, email, hash_password(password), now_iso()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return self.send_json({"error": "Email already exists."}, 409)
            conn.close()
            return self.send_json({"message": "Signup successful. Please login."}, 201)

        if parsed.path == "/api/login":
            data = self.parse_json()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            conn = get_db()
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row or not verify_password(password, row["password"]):
                conn.close()
                return self.send_json({"error": "Invalid credentials."}, 401)
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", (token, row["id"], now_iso()))
            conn.commit()
            conn.close()
            return self.send_json({"token": token, "user": {"id": row["id"], "name": row["name"], "email": row["email"]}})

        if parsed.path == "/api/sync-resources":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            conn = get_db()
            added = sync_resources_from_disk(conn)
            conn.close()
            return self.send_json({"message": f"Synced successfully. Added {added} file(s)."})

        if parsed.path == "/api/upload-resource":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            ctype, _ = cgi.parse_header(self.headers.get("content-type", ""))
            if ctype != "multipart/form-data":
                return self.send_json({"error": "multipart/form-data required"}, 400)
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("content-type")},
                keep_blank_values=True,
            )
            title = (form.getfirst("title") or "").strip()
            subject = (form.getfirst("subject") or "").strip()
            category = (form.getfirst("category") or "").strip()
            file_item = form["file"] if "file" in form else None
            if not title or not subject or category not in CATEGORY_LABELS or file_item is None:
                return self.send_json({"error": "title, subject, category, and file are required."}, 400)

            filename = os.path.basename(file_item.filename or "upload")
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXT.get(category, set()):
                allowed = ", ".join(sorted(ALLOWED_EXT[category]))
                return self.send_json({"error": f"Invalid file type for {category}. Allowed: {allowed}"}, 400)

            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
            stored_name = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
            category_dir = os.path.join(UPLOAD_DIR, category)
            os.makedirs(category_dir, exist_ok=True)
            file_path = os.path.join(category_dir, stored_name)
            with open(file_path, "wb") as f:
                f.write(file_item.file.read())
            conn = get_db()
            conn.execute(
                "INSERT INTO resources(title, subject, category, file_path, uploaded_by, created_at) VALUES(?,?,?,?,?,?)",
                (title, subject, category, file_path, user["id"], now_iso()),
            )
            conn.commit()
            conn.close()
            return self.send_json({"message": "Resource uploaded."}, 201)

        if parsed.path == "/api/chat":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            data = self.parse_json()
            message = (data.get("message") or "").strip()
            if not message:
                return self.send_json({"error": "Message required."}, 400)

            conn = get_db()
            sync_resources_from_disk(conn)
            conn.execute(
                "INSERT INTO chat_history(user_id, role, message, created_at) VALUES(?,?,?,?)",
                (user["id"], "user", message, now_iso()),
            )
            all_subjects = [r["subject"] for r in conn.execute("SELECT DISTINCT subject FROM resources ORDER BY subject").fetchall() if r["subject"].strip()]
            requested_category = parse_requested_category(message)
            matched_subject = detect_subject_from_message(message, all_subjects)

            reply = None
            if requested_category and not matched_subject:
                if all_subjects:
                    reply = f"I can share {CATEGORY_LABELS[requested_category]}. Which subject do you need? Available subjects: {', '.join(all_subjects)}"
                else:
                    reply = "No resources are uploaded yet. Please add files in uploads folders first."

            if requested_category and matched_subject and not reply:
                rows = conn.execute(
                    "SELECT title, subject, category, file_path FROM resources WHERE category = ? AND lower(subject)=lower(?) ORDER BY created_at DESC LIMIT 5",
                    (requested_category, matched_subject),
                ).fetchall()
                if rows:
                    links = [f"- {r['title']} ({r['subject']}): {build_download_url(r['file_path'])}" for r in rows]
                    reply = "Here are your requested files:\n" + "\n".join(links)
                else:
                    reply = f"No {CATEGORY_LABELS[requested_category]} found for subject '{matched_subject}'."

            if not reply:
                context_rows = conn.execute("SELECT title, subject, category FROM resources ORDER BY created_at DESC LIMIT 10").fetchall()
                context_lines = "\n".join([f"- {r['title']} | {r['subject']} | {CATEGORY_LABELS.get(r['category'], r['category'])}" for r in context_rows])
                reply = get_openai_reply(message, context_lines) or "I am educhat bot. Ask like: 'Give me notes for DBMS' or 'Give me important questions for COA'."

            conn.execute(
                "INSERT INTO chat_history(user_id, role, message, created_at) VALUES(?,?,?,?)",
                (user["id"], "assistant", reply, now_iso()),
            )
            conn.commit()
            conn.close()
            return self.send_json({"reply": reply})

        self.send_error(404)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Server running on http://0.0.0.0:{port}")
    server.serve_forever()
