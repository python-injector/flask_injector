.PHONY: test
test:
	flake8 --max-line-length=110 *.py
	nosetests -v
	PYTHONPATH=. python example.py
