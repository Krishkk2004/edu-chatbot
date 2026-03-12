# Anna University Education AI Chatbot

Simple full-stack chatbot web app with:
- Login and signup
- PDF upload/download for notes, important questions, and question papers
- Stored user accounts and chat history (SQLite)

## Run
```bash
python3 server.py
```
Open `http://localhost:8000`.

## API Endpoints
- `POST /api/signup`
- `POST /api/login`
- `POST /api/upload-resource` (Bearer token + multipart form)
- `GET /api/resources`
- `POST /api/chat`
- `GET /api/chat-history`
