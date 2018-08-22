.PHONY: build test clean upload

build:
	python setup.py build_ext --inplace

test:
	@echo "Running doctests and unittests: nose must be installed"
	nosetests -v --with-doctest

clean:
	rm -f *.o
	rm -f $(TARGET)

REPO?=pypi  # Set if not speficied (as test, e.g.)

upload:
	rm -rf dist
	python setup.py sdist
	twine upload dist/*.tar.gz -r $(REPO)
