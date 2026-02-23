.PHONY: test coverage browse-coverage mypy

test:
	uv run python -m unittest

coverage:
	uv run coverage run -m unittest && uv run coverage report && uv run coverage html

browse-coverage:
	firedragon htmlcov/index.html

mypy:
	uv run mypy conv.py
