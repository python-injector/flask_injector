SOURCES := flask_injector.py flask_injector_tests.py
IS_PYTHON3 := $(shell python --version |grep "Python 3")

ifdef IS_PYTHON3
	SOURCES := $(SOURCES) flask_injector_tests_py3.py
endif


.PHONY: test
test:
	flake8 --max-line-length=110 $(SOURCES)
	nosetests -v $(SOURCES)
	PYTHONPATH=. python example.py
