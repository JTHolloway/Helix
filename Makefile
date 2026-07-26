# Helix. Everything here also works as a plain python3 command;
# make is a convenience, not a requirement.

PY ?= python3
DB ?= sample-family.helix

.PHONY: help all setup sample samples serve test check stats designs clean

help:
	@echo "  make all        bootstrap: sample data, all designs to SVG+PDF, tests"
	@echo "  make serve      open the app in a browser"
	@echo "  make samples    re-render every design to samples/"
	@echo "  make test       run the test suite"
	@echo "  make check      validate the family data"
	@echo "  make stats      who the family structurally depends on"
	@echo "  make designs    list all 19 designs"
	@echo "  make clean      remove generated files (keeps your .helix data)"

all setup:
	$(PY) bootstrap.py

sample:
	$(PY) tools/make_sample.py $(DB) --people 400

samples:
	$(PY) -m helix.cli samples $(DB) -o samples --title "Sample Family"

serve:
	$(PY) -m helix.cli serve $(DB)

test:
	$(PY) -m pytest tests -q

check:
	$(PY) -m helix.cli check $(DB)

stats:
	$(PY) -m helix.cli stats $(DB)

designs:
	$(PY) -m helix.cli designs

clean:
	rm -rf samples gallery .pytest_cache .hypothesis
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "Generated files removed. Your .helix data was not touched."
