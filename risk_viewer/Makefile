.PHONY: backend frontend

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8001

frontend:
	cd frontend && npm run dev
