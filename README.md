# Anna University Education AI Chatbot

Simple full-stack chatbot web app with:
- Login and signup
- PDF upload/download for notes, important questions, and question papers
- Stored user accounts and chat history (SQLite)

## Project Structure
- `server.py` – Python backend + API + static file server + SQLite init
- `static/` – frontend (`index.html`, `app.js`, `styles.css`)
- `uploads/` – uploaded PDF files
- `chatbot.db` – SQLite database file (auto-created)

---

## Run Locally (Development)

### 1) Start the server
```bash
python3 server.py
```

### 2) Open in browser
- `http://localhost:8000`

### 3) Use the app
- Sign up with name/email/password
- Log in
- Upload PDF resources (notes, important questions, question papers)
- Chat and view stored history

---

## Deploy as a Website (VPS / VM)

This is the easiest reliable approach if you want your own domain.

### 1) Install Python and Nginx
```bash
sudo apt update
sudo apt install -y python3 python3-venv nginx
```

### 2) Copy project and run app on a fixed port
```bash
cd /var/www
sudo mkdir -p edu-chatbot
sudo chown -R $USER:$USER edu-chatbot
cd edu-chatbot
# copy your repo files here
PORT=8000 python3 server.py
```

If that works, stop it (`Ctrl+C`) and set up a service.

### 3) Create a systemd service
Create `/etc/systemd/system/edu-chatbot.service`:
```ini
[Unit]
Description=Edu Chatbot Web App
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/var/www/edu-chatbot
Environment=PORT=8000
ExecStart=/usr/bin/python3 /var/www/edu-chatbot/server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable/start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable edu-chatbot
sudo systemctl start edu-chatbot
sudo systemctl status edu-chatbot
```

### 4) Configure Nginx reverse proxy
Create `/etc/nginx/sites-available/edu-chatbot`:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/edu-chatbot /etc/nginx/sites-enabled/edu-chatbot
sudo nginx -t
sudo systemctl reload nginx
```

### 5) Add HTTPS (recommended)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Now your app is live as a normal website.

---

## Deploy on Render / Railway (quick cloud option)

1. Push this repo to GitHub.
2. Create a new Web Service in Render/Railway.
3. Build command: *(none required for this project)*
4. Start command:
   ```bash
   python3 server.py
   ```
5. Set environment variable:
   - `PORT` = platform-provided port (Render/Railway usually inject this automatically).
6. Add a persistent disk/volume and mount it for:
   - `chatbot.db`
   - `uploads/`

> Important: if you do not attach persistent storage, user data, chat history, and uploaded PDFs may be lost after redeploy/restart.

---

## API Endpoints
- `POST /api/signup`
- `POST /api/login`
- `POST /api/upload-resource` (Bearer token + multipart form)
- `GET /api/resources`
- `POST /api/chat`
- `GET /api/chat-history`
- `GET /files/<pdf_name>`
