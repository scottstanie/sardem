.PHONY: build install test clean upload
SRC_DIR = sardem

default: install

install:
	pip install -U .

build:
	python setup.py build_ext --inplace

install-edit:
	pip install -e .

test:
	@echo "Running doctests and unittests: nose must be installed"
	nosetests -v --with-doctest

clean:
	rm -f *.so
	rm -f $(SRC_DIR)/*.so

REPO?=pypi  # Set if not speficied (as pypitest, e.g.)

upload:
	rm -rf dist
	python setup.py sdist
	twine upload dist/*.tar.gz -r $(REPO)
