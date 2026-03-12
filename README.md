# EduChat Bot (Anna University)

Full-stack web app for an education chatbot with:
- Separate **Login** and **Signup** pages
 codex/develop-frontend-and-backend-for-edu-chat-0kpdwv
- Chat page with left sidebar chat history (open/close toggle)
- User account storage and chat history in SQLite
- Subject-based study material lookup (notes / important questions / question papers)

- User account storage in SQLite
- Chat page with sidebar history and user email
- Upload/store study material by type and subject:
  - Notes (`.pdf`)
  - Question Papers (`.pdf`)
  - Important Questions (`.png/.jpg/.jpeg/.webp`)
- Chat history saved per user
 codex/create-frontend-and-backend-for-education-ai-chatbot
- Optional OpenAI integration (`OPENAI_API_KEY`)

## Run

```bash
python3 server.py
```

Open: `http://localhost:8000`
 codex/develop-frontend-and-backend-for-edu-chat-0kpdwv

## OpenAI (optional)


## OpenAI (optional)

 codex/create-frontend-and-backend-for-education-ai-chatbot
```bash
export OPENAI_API_KEY="your_key"
export OPENAI_MODEL="gpt-4o-mini"   # optional
python3 server.py
```
 codex/develop-frontend-and-backend-for-edu-chat-0kpdwv

If API key is missing, EduChat Bot uses fallback responses.

## Admin file placement

Place manually uploaded files in `static/uploads`.

To get an exact file inventory for DB entry mapping, call:

- `GET /api/admin-static-uploads`

Expected manual folder names under `static/uploads`:
- `Notes`
- `Important_Question`
- `Question_Paper`


If API key is missing, EduChat Bot uses built-in fallback responses.
 codex/create-frontend-and-backend-for-education-ai-chatbot

## Main API

- `POST /api/signup`
- `POST /api/login`
- `GET /api/me`
 codex/develop-frontend-and-backend-for-edu-chat-0kpdwv
- `POST /api/upload-resource` (auth; optional)
- `GET /api/resources`
- `GET /api/admin-static-uploads`

- `POST /api/upload-resource` (auth)
- `GET /api/resources`
 codex/create-frontend-and-backend-for-education-ai-chatbot
- `POST /api/chat` (auth)
- `GET /api/chat-history` (auth)
- `GET /files/<filename>`
