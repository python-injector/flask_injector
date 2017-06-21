SOURCES := flask_injector.py flask_injector_tests.py

.PHONY: test
test: mypy
	nosetests -v $(SOURCES)
	PYTHONPATH=.:$(PYTHONPATH) python example.py
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
