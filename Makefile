.PHONY: setup doctor sync catalog fetch extract fonts convert convert-secondary convert-primary convert-one render status lint format test check

# Install poppler and the licensed report faces. Idempotent; re-run after any env reset.
setup:
	bash scripts/setup-environment.sh

# Report whether the environment can produce trustworthy measurements.
doctor:
	uv run python -m tools.doctor

REPORT ?=
LEVEL ?=
# Rendering engine: chromium (default) or weasyprint. Passed through as --engine when set.
ENGINE ?=

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
	uv run python -m tools.convert --all $(if $(ENGINE),--engine $(ENGINE),)

convert-secondary:
	uv run python -m tools.convert --all --only secondary $(if $(ENGINE),--engine $(ENGINE),)

convert-primary:
	uv run python -m tools.convert --all --only primary $(if $(ENGINE),--engine $(ENGINE),)

# Single report, e.g. make convert-one LEVEL=secondary REPORT=school_results ENGINE=weasyprint
convert-one:
	uv run python -m tools.convert $(LEVEL) $(REPORT) $(if $(ENGINE),--engine $(ENGINE),)

# Render one report to PDF, e.g. make render LEVEL=primary REPORT=council_best_students ENGINE=weasyprint
render:
	uv run python -m tools.render $(LEVEL) $(REPORT) $(if $(ENGINE),--engine $(ENGINE),)

status:
	uv run python -m tools.status

lint:
	uv run ruff check .

format:
	uv run ruff format tools tests

test:
	uv run pytest

check: lint test
