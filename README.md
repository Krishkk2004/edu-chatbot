# educhat bot (Anna University)

A simple education chatbot website with:
- Login + signup flow
- Subject-based file storage
- PDF uploads for notes and question papers
- PDF/image uploads for important questions
- Chat page with left-side history panel
- SQLite storage for users, files, and chat history
- Optional OpenAI responses (when API key is configured)

## Run locally
```bash
python3 server.py
```
Open: `http://localhost:8000`

## OpenAI (optional)
```bash
export OPENAI_API_KEY="your_key"
python3 server.py
```

## Manual file upload (without form)
You can manually place files in these folders:
- `uploads/notes` -> only `.pdf`
- `uploads/question_papers` -> only `.pdf`
- `uploads/important_questions` -> `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`

Recommended naming format:
- `SUBJECT__TITLE.pdf`
- `SUBJECT__TITLE.png`

Example:
- `DBMS__Unit_1_Notes.pdf`
- `COA__2_marks_important_questions.jpg`

Then either:
- Click **Sync Manual Uploads** in webpage, or
- Call `POST /api/sync-resources` with Bearer token.

## API endpoints
- `POST /api/signup` `{name,email,password,confirm_password}`
- `POST /api/login` `{email,password}`
- `GET /api/me` (Bearer token)
- `POST /api/upload-resource` (Bearer token + multipart: title, subject, category, file)
- `POST /api/sync-resources` (Bearer token)
- `GET /api/resources`
- `POST /api/chat` (Bearer token)
- `GET /api/chat-history` (Bearer token)
- `GET /files/<filename>`
