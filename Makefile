PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python)
PYTHON_SOURCES := backend ml scripts tests
JS_SOURCES := outputs/tennis-ai-app/app.js $(wildcard outputs/tennis-ai-app/js/*.js) work/backtest_courtiq_model.js

.PHONY: test lint format format-check js-check check run

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check $(PYTHON_SOURCES)

format:
	$(PYTHON) -m ruff format $(PYTHON_SOURCES)

format-check:
	$(PYTHON) -m ruff format --check $(PYTHON_SOURCES)

js-check:
	@for file in $(JS_SOURCES); do node --check "$$file"; done

check: lint js-check test

run:
	$(PYTHON) scripts/run_courtiq.py
