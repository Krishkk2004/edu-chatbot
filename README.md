# EduChat Bot (Anna University)

This app has:
- Login page with Signup link
- Separate Signup page (after successful signup it returns to Login)
- Home chat page after login
- Left sidebar chat history with open/close button
- Logged-in email shown at sidebar bottom
- No upload form in chat page

## Run

```bash
python3 server.py
```

Open: `http://localhost:8000`

## Backend SQLite structure for study materials

`chatbot.db` contains separate material tables:
- `notes`
- `question_papers`
- `important_questions`

Each table has:
- `subject`
- `title`
- `file_name`
- `created_at`

Developer/admin should:
1. Place files inside `static/uploads` (or subfolders).
2. Insert metadata rows into these SQLite tables.

When users ask for materials, bot asks:
- `Which subject do you need?`

Then it fetches from the matching SQLite table and returns download links as `/files/<file_name>`.

## Admin helper endpoints

- `GET /api/admin-static-uploads` → exact files available in:
  - `static/uploads/Notes`
  - `static/uploads/Question_Paper`
  - `static/uploads/Important_Question`
- `GET /api/admin-materials?category=notes|question_papers|important_questions`

## Optional OpenAI

```bash
export OPENAI_API_KEY="your_key"
export OPENAI_MODEL="gpt-4o-mini"
python3 server.py
```

If API key is not set, fallback reply is used.
