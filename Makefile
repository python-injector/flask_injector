SOURCES := flask_injector.py flask_injector_tests.py

.PHONY: test
test:
	nosetests -v $(SOURCES)
	PYTHONPATH=.:$(PYTHONPATH) python example.py
	flake8 --max-line-length=110 $(SOURCES)
