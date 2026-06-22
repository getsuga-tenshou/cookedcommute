.PHONY: help ingest-once ingest-loop load dbt dbt-test dash test lint fmt clean

help:
	@echo "CookedCommute dev commands (Azure ELT into Snowflake):"
	@echo "  make ingest-once - fetch live feeds once, land raw to lake/ADLS"
	@echo "  make ingest-loop - continuous local ingestion loop (stand-in for the Functions)"
	@echo "  make load        - load landed lake files into Snowflake RAW (PUT + COPY)"
	@echo "  make dbt         - dbt deps + build (staging + marts) on Snowflake"
	@echo "  make dbt-test    - dbt data-quality tests"
	@echo "  make dash        - run the dashboard (FastAPI API + MapLibre frontend)"
	@echo "  make test        - pytest (parsers/logic)"
	@echo "  make lint        - ruff check"

ingest-once:
	python -m ingestion.pipeline --once

ingest-loop:
	python -m ingestion.run_local

load:
	python -m ingestion.warehouse

dbt:
	python scripts/run_dbt.py build

dbt-test:
	python scripts/run_dbt.py test

dash:
	uvicorn backend.api:app --reload

test:
	pytest -q

lint:
	ruff check .

fmt:
	ruff format .

clean:
	rm -rf lake dbt/target dbt/logs
