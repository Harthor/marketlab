.PHONY: bootstrap demo test train_naive train_ridge leaderboard

bootstrap:
	bash scripts/bootstrap.sh

demo:
	. .venv/bin/activate && bash scripts/run_demo.sh

test:
	. .venv/bin/activate && pytest -q

train_naive:
	. .venv/bin/activate && forecast train --dataset data/research_ready.parquet --target returns_1d --model naive0 --config configs/default.yaml

train_ridge:
	. .venv/bin/activate && forecast train --dataset data/research_ready.parquet --target returns_1d --model ridge --config configs/default.yaml

leaderboard:
	. .venv/bin/activate && forecast leaderboard
