.PHONY: venv lint test ingest-demo

PYTHON ?= python3

venv:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"

lint:
	. .venv/bin/activate && ruff check .

test:
	. .venv/bin/activate && pytest -q

ingest-demo:
	. .venv/bin/activate && python scripts/make_demo_prices.py \
		--symbols DEMO \
		--start 2024-01-01 \
		--end 2024-06-30 \
		--timeframe 1d
