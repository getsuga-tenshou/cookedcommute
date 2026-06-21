"""Run dbt with .env loaded into the environment.

dbt reads OS environment variables (via env_var() in profiles.yml), not the .env
file. This wrapper loads .env first, then runs `dbt deps` + the requested command
from the dbt/ directory.

Usage:
    python scripts/run_dbt.py            # = dbt build
    python scripts/run_dbt.py test
    python scripts/run_dbt.py run
"""
from __future__ import annotations

import os
import subprocess
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

DBT_DIR = os.path.join(ROOT, "dbt")
args = sys.argv[1:] or ["build"]

subprocess.call(["dbt", "deps", "--profiles-dir", "."], cwd=DBT_DIR)
raise SystemExit(subprocess.call(["dbt", *args, "--profiles-dir", "."], cwd=DBT_DIR))
