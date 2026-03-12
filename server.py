#!/usr/bin/env python3
import cgi
import json
import mimetypes
import os
import re
import secrets
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "chatbot.db")
STATIC_DIR = os.path.join(ROOT, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
LEGACY_UPLOAD_DIR = os.path.join(ROOT, "uploads")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MATERIAL_PROMPT = "Which subject do you need?"

UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
LEGACY_UPLOAD_DIR = os.path.join(ROOT, "uploads")

UPLOAD_DIR = os.path.join(ROOT, "uploads")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LEGACY_UPLOAD_DIR, exist_ok=True)



CATEGORY_TABLES = {
    "notes": "notes",
    "question_papers": "question_papers",
    "questionpaper": "question_papers",
    "important_questions": "important_questions",
    "important_question": "important_questions",


}


KEYWORDS = {
    "notes": ["note", "notes"],
    "question_papers": ["question paper", "question papers", "qp", "questionpaper"],
    "important_questions": ["important question", "important questions", "important"],
}

ALLOWED_TYPES = {
    "notes": {"extensions": {".pdf"}},
    "important_questions": {"extensions": {".png", ".jpg", ".jpeg", ".webp"}},
    "question_papers": {"extensions": {".pdf"}},
}

MATERIAL_PROMPT = "Which subject do you need?"



def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def safe_subject(subject: str) -> str:
    return re.sub(r"\s+", " ", subject.strip()).lower()


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
    try:
        conn.execute("ALTER TABLE resources ADD COLUMN subject TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chat_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER NOT NULL,
        pending_category TEXT,
        updated_at DATETIME  DEFAULT CURRENT_TIMESTAMP NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        title TEXT NOT NULL,
        file_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS question_papers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        title TEXT NOT NULL,
        file_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS important_questions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       subject TEXT NOT NULL,
       title TEXT NOT NULL,
       file_name TEXT NOT NULL,
       created_at TEXT NOT NULL
    );
    
    -- legacy-compatible names requested by some manual workflows
        CREATE TABLE IF NOT EXISTS questionpaper (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            file_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS important_question (

        CREATE TABLE IF NOT EXISTS chat_state (
            user_id INTEGER PRIMARY KEY,
            pending_category TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            file_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    conn.execute("""
    
    CREATE TABLE IF NOT EXISTS question_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            file_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
                )

def infer_category(text: str):
    t = text.lower()
    for category, words in KEYWORDS.items():
        if any(w in t for w in words):
            return category
    if "study material" in t or "material" in t:
        return "notes"
    return None


def find_file_by_name(filename: str):
    if not filename:
        return None
    for base in [UPLOAD_DIR, LEGACY_UPLOAD_DIR]:
        direct = os.path.join(base, filename)
        if os.path.exists(direct):
            return direct
        for root, _, files in os.walk(base):
            if filename in files:
                return os.path.join(root, filename)
    return None




def tables_for_category(category: str):
    canonical = CATEGORY_TABLES[category]
    if canonical == "question_papers":
        return ["question_papers", "questionpaper"]
    if canonical == "important_questions":
        return ["important_questions", "important_question"]
    return [canonical]

def list_subjects_for_category(conn, category: str):
    subjects = []
    for table in tables_for_category(category):
        rows = conn.execute(f"SELECT DISTINCT subject FROM {table} ORDER BY subject").fetchall()
        subjects.extend([r["subject"] for r in rows])
    return sorted({safe_subject(s) for s in subjects if s})


def find_subject_in_text(conn, category: str, text: str):
    subjects = list_subjects_for_category(conn, category)
    lowered = text.lower()
    for sub in subjects:
        sub_norm = (sub or "").strip().lower()
        if sub_norm and sub_norm in lowered:
            return sub_norm
    return ""


def fetch_materials(conn, category: str, subject: str):
    subject_norm = safe_subject(subject)
    rows = []
    for table in tables_for_category(category):
        found = conn.execute(
            f"SELECT subject,title,file_name,created_at FROM {table} WHERE lower(subject)=? ORDER BY created_at DESC",
            (subject_norm,),
        ).fetchall()
        rows.extend(found)
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def generate_openai_reply(user_message: str, history_rows):
    if not OPENAI_API_KEY:
        return None

    messages = [{
        "role": "system",
        "content": "You are educhat bot for Anna University. For study materials ask exactly: Which subject do you need?",
    }]
    for row in history_rows[-8:]:
        messages.append({"role": row["role"], "content": row["message"]})
    messages.append({"role": "user", "content": user_message})

    payload = {"model": OPENAI_MODEL, "messages": messages, "temperature": 0.4}
    req = Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def admin_static_file_list():
    result = []
    for folder_name, category in [
        ("Notes", "notes"),
        ("Question_Paper", "question_papers"),
        ("Important_Question", "important_questions"),
    ]:
        category_dir = os.path.join(UPLOAD_DIR, folder_name)
        files = []
        if os.path.isdir(category_dir):
            for name in sorted(os.listdir(category_dir)):
                full = os.path.join(category_dir, name)
                if os.path.isfile(full):
                    files.append(name)
        result.append({"folder": folder_name, "category": category, "files": files})
    return result
   
    conn = sqlite3.connect("database.db")
    conn.execute("""

        CREATE TABLE IF NOT EXISTS important_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            file_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
                )
    conn.commit()
    conn.close()
    
    
   

def infer_category(text: str):
    t = text.lower()
    for category, words in KEYWORDS.items():
        if any(w in t for w in words):
            return category
    if "study material" in t or "material" in t:
        return "notes"
    return None


def find_file_by_name(filename: str):
    if not filename:
        return None
    for base in [UPLOAD_DIR, LEGACY_UPLOAD_DIR]:
        direct = os.path.join(base, filename)
        if os.path.exists(direct):
            return direct
        for root, _, files in os.walk(base):
            if filename in files:
                return os.path.join(root, filename)
    return None


def list_subjects_for_category(conn, category: str):
    table = CATEGORY_TABLES[category]
    rows = conn.execute(f"SELECT DISTINCT subject FROM {table} ORDER BY subject").fetchall()
    return [r["subject"] for r in rows]


def find_subject_in_text(conn, category: str, text: str):
    subjects = list_subjects_for_category(conn, category)
    lowered = text.lower()
    for sub in subjects:
        if sub and sub in lowered:
            return sub
    return ""


def fetch_materials(conn, category: str, subject: str):
    table = CATEGORY_TABLES[category]
    return conn.execute(
        f"SELECT subject,title,file_name,created_at FROM {table} WHERE subject=? ORDER BY created_at DESC",
        (subject,),
    ).fetchall()


def generate_openai_reply(user_message: str, history_rows):
    if not OPENAI_API_KEY:
        return None

    messages = [{
        "role": "system",
        "content": "You are educhat bot for Anna University. For study materials ask exactly: Which subject do you need?",
    }]
    for row in history_rows[-8:]:
        messages.append({"role": row["role"], "content": row["message"]})
    messages.append({"role": "user", "content": user_message})

    payload = {"model": OPENAI_MODEL, "messages": messages, "temperature": 0.4}
    req = Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def admin_static_file_list():
    result = []
    for folder_name, category in [
        ("Notes", "notes"),
        ("Question_Paper", "question_papers"),
        ("Important_Question", "important_questions"),
    ]:
        category_dir = os.path.join(UPLOAD_DIR, folder_name)
        files = []
        if os.path.isdir(category_dir):
            for name in sorted(os.listdir(category_dir)):
                full = os.path.join(category_dir, name)
                if os.path.isfile(full):
                    files.append(name)
        result.append({"folder": folder_name, "category": category, "files": files})
    return result


def safe_subject(subject: str) -> str:
    return re.sub(r"\s+", " ", subject.strip()).lower()

def find_file_by_name(filename: str):
    if not filename:
        return None
    for base in [UPLOAD_DIR, LEGACY_UPLOAD_DIR]:
        direct = os.path.join(base, filename)
        if os.path.exists(direct):
            return direct
        for root, _, files in os.walk(base):
            if filename in files:
                return os.path.join(root, filename)
    return None



def generate_openai_reply(user_message: str, history_rows):
    if not OPENAI_API_KEY:
        return None

    messages = [
        {
            "role": "system",
 
            "content": (
                "You are educhat bot for Anna University. "
                "If asked for notes or study materials, ask exactly: Which subject do you need?"
            ),

            "content": "You are EduChat Bot for Anna University students. Keep responses concise and practical.",
 
        }
    ]
    for row in history_rows[-8:]:
        messages.append({"role": row["role"], "content": row["message"]})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.4,
    }
    req = Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None



def admin_static_file_list():
    result = []
    for folder_name, normalized_category in [
        ("Notes", "notes"),
        ("Important_Question", "important_questions"),
        ("Question_Paper", "question_papers"),
    ]:
        category_dir = os.path.join(UPLOAD_DIR, folder_name)
        files = []
        if os.path.isdir(category_dir):
            for name in sorted(os.listdir(category_dir)):
                full = os.path.join(category_dir, name)
                if os.path.isfile(full):
                    files.append(name)
        result.append({
            "folder": folder_name,
            "category": normalized_category,
            "files": files,
        })
    return result


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
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
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
        query = parse_qs(parsed.query)

        if parsed.path == "/api/me":
            user = self.auth_user()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            return self.send_json({"user": {"id": user["id"], "name": user["name"], "email": user["email"]}})


        if parsed.path == "/api/admin-static-uploads":
            return self.send_json({"base_path": "static/uploads", "categories": admin_static_file_list()})

        if parsed.path == "/api/admin-materials":
            category = (query.get("category", ["notes"])[0] or "notes").strip()
            if category not in CATEGORY_TABLES:
                return self.send_json({"error": "Invalid category"}, 400)
            conn = get_db()
            rows = conn.execute(
                f"SELECT subject,title,file_name,created_at FROM {CATEGORY_TABLES[category]} ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            data = []
            for r in rows:
                item = dict(r)
                item["download_url"] = f"/files/{r['file_name']}"
                data.append(item)
            return self.send_json({"category": category, "materials": data})

        if parsed.path == "/api/resources":
            category = (query.get("category", [""])[0] or "").strip()
            subject = safe_subject(query.get("subject", [""])[0] or "")
            categories = [category] if category in CATEGORY_TABLES else list(CATEGORY_TABLES.keys())
            conn = get_db()
            all_items = []
            for cat in categories:
                table = CATEGORY_TABLES[cat]
                if subject:
                    rows = conn.execute(
                        f"SELECT subject,title,file_name,created_at FROM {table} WHERE subject=? ORDER BY created_at DESC",
                        (subject,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT subject,title,file_name,created_at FROM {table} ORDER BY created_at DESC"
                    ).fetchall()
                for r in rows:
                    all_items.append({
                        "category": cat,
                        "subject": r["subject"],
                        "title": r["title"],
                        "file_name": r["file_name"],
                        "created_at": r["created_at"],
                        "download_url": f"/files/{r['file_name']}",
                    })
            conn.close()
            all_items.sort(key=lambda x: x["created_at"], reverse=True)
            return self.send_json({"resources": all_items})
        if parsed.path == "/api/admin-static-uploads":
            return self.send_json({"base_path": "static/uploads", "categories": admin_static_file_list()})
        if parsed.path == "/api/resources":
            resource_type = (query.get("category", [""])[0] or "").strip()
            subject = safe_subject(query.get("subject", [""])[0] or "")

            sql = "SELECT id,title,subject,category,file_path,created_at FROM resources"
            where = []
            params = []
            if resource_type in ALLOWED_TYPES:
                where.append("category=?")
                params.append(resource_type)
            if subject:
                where.append("subject=?")
                params.append(subject)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC"

            conn = get_db()
            rows = conn.execute(sql, tuple(params)).fetchall()
            conn.close()
            items = []
            for r in rows:
                item = dict(r)
                item["download_url"] = f"/files/{os.path.basename(r['file_path'])}"
                items.append(item)
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
            fpath = find_file_by_name(fname)
            if not fpath:
                self.send_error(404)
                return
            with open(fpath, "rb") as f:
                data = f.read()
            ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
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
            return self.send_json({"message": "Signup successful. Please login."}, 201)

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
            if ctype != "multipart/form-data" or "boundary" not in pdict:
                return self.send_json({"error": "multipart/form-data required"}, 400)

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("content-type", "")},
                keep_blank_values=True,
            )
            title = (form.getfirst("title") or "").strip()
            subject = safe_subject(form.getfirst("subject") or "")
            category = (form.getfirst("category") or "").strip()
            file_item = form["file"] if "file" in form else None
            if not title or not subject or category not in ALLOWED_TYPES or file_item is None:
                return self.send_json({"error": "title, subject, category, and file are required"}, 400)

            filename = os.path.basename(file_item.filename or "upload")
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_TYPES[category]["extensions"]:
                return self.send_json({"error": f"Invalid file type for {category}"}, 400)

            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
            stored_name = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
            category_dir = os.path.join(UPLOAD_DIR, category)
            os.makedirs(category_dir, exist_ok=True)
            path = os.path.join(category_dir, stored_name)
            with open(path, "wb") as out:
                out.write(file_item.file.read())

            flat_path = os.path.join(UPLOAD_DIR, stored_name)
            with open(flat_path, "wb") as out:
                with open(path, "rb") as src:
                    out.write(src.read())

            conn = get_db()
            conn.execute(
                "INSERT INTO resources(title,subject,category,file_path,uploaded_by,created_at) VALUES(?,?,?,?,?,?)",

                (title, subject, category, path, user["id"], now_iso()),

                (title, subject, category, flat_path, user["id"], now_iso()),

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



            text = message.lower()
            wants_material = any(word in text for word in ["notes", "important question", "question paper", "qp", "study material", "material"])



            conn = get_db()
            conn.execute(
                "INSERT INTO chat_history(user_id,role,message,created_at) VALUES(?,?,?,?)",
                (user["id"], "user", message, now_iso()),
            )


            category = infer_category(message)
            pending = conn.execute("SELECT pending_category FROM chat_state WHERE user_id=?", (user["id"],)).fetchone()

            response = ""
            if category:
                subject = find_subject_in_text(conn, category, message)
                if not subject:
                    conn.execute(
                        "INSERT INTO chat_state(user_id,pending_category,updated_at) VALUES(?,?,?) "
                        "ON CONFLICT(user_id) DO UPDATE SET pending_category=excluded.pending_category, updated_at=excluded.updated_at",
                        (user["id"], category, now_iso()),
                    )
                    response = MATERIAL_PROMPT
                else:
                    rows = fetch_materials(conn, category, subject)
                    if rows:
                        response_lines = [f"Here are {category.replace('_', ' ')} for {subject}:"]
                        for r in rows:
                            response_lines.append(f"- {r['title']}: /files/{r['file_name']}")
                        response = "\n".join(response_lines)
                    else:
                        response = f"No {category.replace('_', ' ')} found for {subject}."
                    conn.execute("DELETE FROM chat_state WHERE user_id=?", (user["id"],))
            elif pending and pending["pending_category"] in CATEGORY_TABLES:
                pending_category = pending["pending_category"]
                subject = safe_subject(message)
                rows = fetch_materials(conn, pending_category, subject)
                if rows:
                    response_lines = [f"Here are {pending_category.replace('_', ' ')} for {subject}:"]
                    for r in rows:
                        response_lines.append(f"- {r['title']}: /files/{r['file_name']}")
                    response = "\n".join(response_lines)
                else:
                    response = f"No {pending_category.replace('_', ' ')} found for {subject}."
                conn.execute("DELETE FROM chat_state WHERE user_id=?", (user["id"],))


            previous_assistant = conn.execute(
                "SELECT message FROM chat_history WHERE user_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
                (user["id"],),
            ).fetchone()

            response = ""
            if wants_material:
                response = MATERIAL_PROMPT
            elif previous_assistant and previous_assistant["message"] == MATERIAL_PROMPT:
                subject = safe_subject(message)
                rows = conn.execute(
                    "SELECT title,category,file_path FROM resources WHERE subject=? ORDER BY created_at DESC",
                    (subject,),
                ).fetchall()
                if rows:
                    lines = [f"Available materials for {subject}:"]
                    for r in rows:
                        category_name = r["category"].replace("_", " ")
                        url = f"/files/{os.path.basename(r['file_path'])}"
                        lines.append(f"- {category_name}: {r['title']} -> {url}")
                    response = "\n".join(lines)
                else:
                    response = f"No materials found for {subject}. Please check subject spelling and database entries."

            text = message.lower()
            wants_material = any(word in text for word in ["notes", "important question", "question paper", "qp", "material"])
            requested_category = "notes"
            if "important" in text:
                requested_category = "important_questions"
            elif "question paper" in text or "qp" in text:
                requested_category = "question_papers"

            subject_rows = conn.execute("SELECT DISTINCT subject FROM resources ORDER BY subject ASC").fetchall()
            subjects = [r["subject"] for r in subject_rows if r["subject"]]
            matched_subject = ""
            for subject in subjects:
                if subject in text:
                    matched_subject = subject
                    break

            response = ""
            if wants_material and not matched_subject:
                available = ", ".join(subjects[:12]) or "No subjects uploaded yet"
                response = f"Sure! Which subject do you need? Available subjects: {available}."
            elif wants_material and matched_subject:
                rows = conn.execute(
                    "SELECT title,category,file_path FROM resources WHERE subject=? AND category=? ORDER BY created_at DESC",
                    (matched_subject, requested_category),
                ).fetchall()
                if rows:
                    lines = [f"Here are the {requested_category.replace('_', ' ')} for {matched_subject}:"]
                    for r in rows[:5]:
                        url = f"/files/{os.path.basename(r['file_path'])}"
                        lines.append(f"- {r['title']}: {url}")
                    response = "\n".join(lines)
                else:
                    response = f"I couldn't find {requested_category.replace('_', ' ')} for {matched_subject}."


            else:
                history_rows = conn.execute(
                    "SELECT role,message FROM chat_history WHERE user_id=? ORDER BY id ASC",
                    (user["id"],),
                ).fetchall()
                ai_reply = generate_openai_reply(message, history_rows)



                response = ai_reply or (
                    "I am educhat bot. Ask me Anna University questions. "
                    "If you need notes, question papers, or important questions, I will ask your subject."
                )

 

                if ai_reply:
                    response = ai_reply
                else:
                    response = (

                        "I am educhat bot. Ask me Anna University questions. "
                        "For notes, important questions, or question papers, I will ask your subject."

                        "I am EduChat Bot 🤖. I can help with Anna University study guidance and provide notes, "
                        "important questions, and question papers by subject. Ask like: 'Give notes for data structures'."

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
