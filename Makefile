.PHONY: test lint coverage browse-coverage mypy

test:
	uv run python -m unittest

lint:
	uv run pylint conv

coverage:
	uv run coverage run -m unittest && uv run coverage report && uv run coverage html

browse-coverage:
	firedragon htmlcov/index.html

mypy:
	uv run mypy conv.py
