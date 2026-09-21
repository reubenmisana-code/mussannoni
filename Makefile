.PHONY: sync fetch-secondary-school extract-secondary-school scaffold-secondary-school render-secondary-school verify-secondary-school convert-secondary-school lint test

sync:
	uv sync

fetch-secondary-school:
	uv run python -m tools.fetch secondary school_results

extract-secondary-school:
	uv run python -m tools.extract secondary school_results

scaffold-secondary-school:
	uv run python -m tools.scaffold secondary school_results

render-secondary-school:
	uv run python -m tools.render secondary school_results

verify-secondary-school:
	uv run python -m tools.compare secondary school_results

convert-secondary-school: extract-secondary-school scaffold-secondary-school render-secondary-school verify-secondary-school

lint:
	uv run ruff check .

test:
	uv run pytest
