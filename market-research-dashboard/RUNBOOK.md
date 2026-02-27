# market-research-dashboard — Runbook

# Frontend (choose correct package manager)
# npm ci && npm run build
# pnpm i --frozen-lockfile && pnpm build
# yarn install --frozen-lockfile && yarn build

# Demo mode
export VITE_DEMO_MODE=1
# run dev command for your setup (npm/pnpm/yarn)

# Backend (choose installed dependencies in backend/ requirements)
cd backend
bash ../../tools/bootstrap_venv.sh . --requirements requirements.txt
source .venv/bin/activate
python -m pip install -r requirements.txt

# Apply auth/session hardening (Option A) + migrations
python manage.py migrate

# Required for real-mode run discovery:
export MARKETLAB_WORKSPACE="/abs/path/to/workspace_root"   # e.g. /Users/.../market-sentiment-lab

# Run server and health-check endpoint
python manage.py runserver 8000
# in another terminal:
curl -s http://127.0.0.1:8000/api/runs | python -m json.tool

# Optional validation:
python -c "import django; print(django.get_version())"
