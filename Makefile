SOURCES := flask_injector.py flask_injector_tests.py

.PHONY: test
test:
	flake8 --max-line-length=110 $(SOURCES)
	nosetests -v $(SOURCES)
	PYTHONPATH=. python example.py
