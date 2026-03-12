# EduChat Bot (Anna University)

Full-stack web app for an education chatbot with:
- Separate **Login** and **Signup** pages
- User account storage in SQLite
- Chat page with sidebar history and user email
- Upload/store study material by type and subject:
  - Notes (`.pdf`)
  - Question Papers (`.pdf`)
  - Important Questions (`.png/.jpg/.jpeg/.webp`)
- Chat history saved per user
- Optional OpenAI integration (`OPENAI_API_KEY`)

## Run

```bash
python3 server.py
```

Open: `http://localhost:8000`

## OpenAI (optional)

```bash
export OPENAI_API_KEY="your_key"
export OPENAI_MODEL="gpt-4o-mini"   # optional
python3 server.py
```

If API key is missing, EduChat Bot uses built-in fallback responses.

## Main API

- `POST /api/signup`
- `POST /api/login`
- `GET /api/me`
- `POST /api/upload-resource` (auth)
- `GET /api/resources`
- `POST /api/chat` (auth)
- `GET /api/chat-history` (auth)
- `GET /files/<filename>`
