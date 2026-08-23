# Frontend

React + Vite app covering the two human-facing HLD screens: the Human Review Interface and
the Situation Routing Dashboard.

## Run

```bash
cd frontend
npm install
npm run dev
```

Expects the backend at `http://127.0.0.1:8000`. Override with a `.env` file:

```
VITE_API_URL=http://127.0.0.1:8000
```

## Structure

- `src/api/client.js` — fetch wrapper used by both pages
- `src/pages/ReviewPage.jsx` — lists pending situations (`GET /situations?status=pending`), approve/reject (`POST /situations/{id}/decision`)
- `src/pages/DashboardPage.jsx` — confirmed situations + counts (`GET /situations?status=confirmed`, `GET /analytics/summary`)
