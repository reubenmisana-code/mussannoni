.PHONY: setup doctor sync catalog fetch extract fonts convert convert-secondary convert-primary convert-one status lint format test check

# Install poppler and the licensed report faces. Idempotent; re-run after any env reset.
setup:
	bash scripts/setup-environment.sh

# Report whether the environment can produce trustworthy measurements.
doctor:
	uv run python -m tools.doctor

REPORT ?=
LEVEL ?=

sync:
	uv sync

# Rebuild the 46-entry catalog from the two live listing pages.
catalog:
	uv run python -m tools.catalog

# Fetch every reference PDF. Existing files are never replaced without --force.
fetch:
	uv run python -m tools.fetch --all

extract:
	uv run python -m tools.extract --all

fonts:
	uv run python -m tools.fonts

# Full loop for the whole corpus: scaffold, render, tune, render, compare.
convert:
	uv run python -m tools.convert --all

convert-secondary:
	uv run python -m tools.convert --all --only secondary

convert-primary:
	uv run python -m tools.convert --all --only primary

# Single report, e.g. make convert-one LEVEL=secondary REPORT=school_results
convert-one:
	uv run python -m tools.convert $(LEVEL) $(REPORT)

status:
	uv run python -m tools.status

lint:
	uv run ruff check .

format:
	uv run ruff format tools tests

test:
	uv run pytest

check: lint test
