# InsightForge Frontend

React + Vite UI for the Secure AI Insights Assistant.

This app:
- Provides a chat interface
- Shows tool traces for explainability
- Renders charts for SQL tool results

## Run

```bash
cd frontend
npm install
npm run dev
```

By default the frontend calls the backend at `http://localhost:8000`.

If you run the backend on a different URL/port, set:

```bash
VITE_BACKEND_URL=http://localhost:8000
```

See the repo root `README.md` for full end-to-end setup.
