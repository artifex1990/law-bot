#!/bin/sh
set -e

# Миграции перед стартом (PostgreSQL / SQLite)
if command -v alembic >/dev/null 2>&1; then
  alembic upgrade head
fi

exec python -m src.main
