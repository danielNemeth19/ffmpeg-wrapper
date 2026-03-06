.PHONY: test mypy lint format pylint coverage browse-coverage build clean

test:
	uv run python -m unittest

mypy:
	uv run mypy -p pyffmpeg_wrapper

lint:
	uv run ruff check

format:
	uv run ruff format --diff

pylint:
	uv run pylint pyffmpeg_wrapper

coverage:
	uv run coverage run -m unittest && uv run coverage report && uv run coverage html

browse-coverage:
	firedragon htmlcov/index.html

build:
	@echo "🚀 Creating wheel file"
	uv build

clean:
	rm -rf dist/
