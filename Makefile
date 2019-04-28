SOURCES := flask_injector.py flask_injector_tests.py

.PHONY: ci
ci: test lint

.PHONY: test
test:
	nosetests -v $(SOURCES) \
		--with-coverage --cover-package=flask_injector --cover-html --cover-branches --cover-xml
	PYTHONPATH=.:$(PYTHONPATH) python example.py

.PHONY: lint
lint: flake8 mypy black-check

.PHONY: flake8
flake8:
	flake8 --max-line-length=110 $(SOURCES)

.PHONY: mypy
mypy:
	python -m mypy \
		--ignore-missing-imports --follow-imports=skip \
		--disallow-untyped-defs \
		--warn-no-return \
		--warn-redundant-casts \
		--strict-optional \
		flask_injector.py

.PHONY: black-check
black-check:
	black --check .
