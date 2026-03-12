# EduChat Bot (Anna University)

Full-stack web app for an education chatbot with:
- Separate **Login** and **Signup** pages
- Chat page with left sidebar chat history (open/close toggle)
- User account storage and chat history in SQLite
- Subject-based study material lookup (notes / important questions / question papers)
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

If API key is missing, EduChat Bot uses fallback responses.

## Admin file placement

Place manually uploaded files in `static/uploads`.

To get an exact file inventory for DB entry mapping, call:

- `GET /api/admin-static-uploads`

Expected manual folder names under `static/uploads`:
- `Notes`
- `Important_Question`
- `Question_Paper`

## Main API

- `POST /api/signup`
- `POST /api/login`
- `GET /api/me`
- `POST /api/upload-resource` (auth; optional)
- `GET /api/resources`
- `GET /api/admin-static-uploads`
- `POST /api/chat` (auth)
- `GET /api/chat-history` (auth)
- `GET /files/<filename>`
