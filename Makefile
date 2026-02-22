.PHONY: test coverage browse-coverage mypy

test:
	python -m unittest

coverage:
	coverage run -m unittest && coverage report && coverage html

browse-coverage:
	firedragon htmlcov/index.html

mypy:
	mypy conv.py
