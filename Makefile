.PHONY: format format-check lint test clean help

help:
	@echo "Available commands:"
	@echo "  make format       - Format code with ruff"
	@echo "  make format-check - Check code formatting without changes"
	@echo "  make lint         - Lint code with ruff"
	@echo "  make test         - Run pytest"
	@echo "  make clean        - Remove build artifacts"

format:
	uv run ruff format app/ tests/

format-check:
	uv run ruff format --check app/ tests/

lint:
	uv run ruff check app/ tests/

lint-fix:
	uv run ruff check --fix app/ tests/

test:
	uv run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache build/ dist/ *.egg-info/
