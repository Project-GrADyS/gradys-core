#!/usr/bin/env bash
# Runs every gate. All three must pass before a change lands.
#
# The static suites are the primary contract: mypy and pyright disagreed on three of the
# five encodings tried while designing this, so a single checker is not enough. Both
# versions are pinned in pyproject.toml; treat a bump as an API-affecting change.
set -uo pipefail

cd "$(dirname "$0")"
status=0

echo "== pytest =="
python -m pytest tests/ -q || status=1

echo
echo "== mypy (strict, --warn-unused-ignores) =="
# tests/static/negative.py must be SILENT: every expected error is suppressed with a
# `# type: ignore[...]`, so an error that stops firing surfaces as an unused ignore.
python -m mypy || status=1

echo
echo "== pyright (strict, reportUnnecessaryTypeIgnoreComment) =="
python -m pyright --pythonpath "$(command -v python)" || status=1

echo
if [ "$status" -eq 0 ]; then
    echo "all gates passed"
else
    echo "FAILED"
fi
exit "$status"
