.PHONY: test mypy lint format pylint coverage browse-coverage

test:
	uv run python -m unittest

mypy:
	uv run mypy -p ffmpeg_wrapper

lint:
	uv run ruff check

format:
	uv run ruff format --diff

pylint:
	uv run pylint ffmpeg_wrapper

coverage:
	uv run coverage run -m unittest && uv run coverage report && uv run coverage html

browse-coverage:
	firedragon htmlcov/index.html
