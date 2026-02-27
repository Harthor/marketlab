PY := $(shell ../tools/python_select.sh)

.PHONY: dev backend frontend install frontend-install frontend-build backend-install backend-check docker-up docker-down docker-logs demo

# Levanta backend + frontend en paralelo en una sola terminal.
dev:
	@cd backend && bash ../tools/bootstrap_venv.sh . --requirements requirements.txt; \
	. .venv/bin/activate >/dev/null 2>&1; \
	python manage.py runserver 0.0.0.0:8000 & \
	BACKEND_PID=$$!; \
	trap 'kill $$BACKEND_PID' EXIT; \
	cd ../frontend && npm run dev

backend:
	cd backend && bash ../tools/bootstrap_venv.sh . --requirements requirements.txt; \
	. .venv/bin/activate >/dev/null 2>&1; \
	python manage.py runserver 0.0.0.0:8000

frontend:
	cd frontend && npm run dev

demo:
	cd frontend && npm run dev:demo

frontend-install:
	@cd frontend && \
	if [ -f package-lock.json ]; then \
	  npm ci; \
	elif [ -f pnpm-lock.yaml ]; then \
	  pnpm i --frozen-lockfile; \
	elif [ -f yarn.lock ]; then \
	  yarn install --frozen-lockfile; \
	else \
	  npm install; \
	fi

frontend-build:
	@cd frontend && \
	if [ -f package-lock.json ]; then \
	  npm run build; \
	elif [ -f pnpm-lock.yaml ]; then \
	  pnpm run build; \
	elif [ -f yarn.lock ]; then \
	  yarn run build; \
	else \
	  npm run build; \
	fi

backend-install:
	@cd backend && bash ../tools/bootstrap_venv.sh . --requirements requirements.txt

backend-check:
	@cd backend && \
	(. .venv/bin/activate >/dev/null 2>&1 || true); \
	$(PY) manage.py check

install: backend-install frontend-install

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
