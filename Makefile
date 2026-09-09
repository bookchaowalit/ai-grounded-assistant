PYTHON ?= python3
export PYTHONPATH := src

.PHONY: test check demo evaluate

test:
	$(PYTHON) -m unittest discover -s tests -v

check:
	$(PYTHON) -m compileall -q src tests
	$(PYTHON) -m book_grounded_ai.cli validate

demo:
	$(PYTHON) -m book_grounded_ai.cli ask --question "Where should approved source evidence live?" --json

evaluate:
	$(PYTHON) -m book_grounded_ai.cli evaluate --json

