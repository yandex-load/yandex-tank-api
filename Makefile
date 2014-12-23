.PHONY: deps

all: deps
	PYTHONPATH=.venv ; . .venv/bin/activate

.venv:
	if [ ! -e ".venv/bin/activate_this.py" ] ; then virtualenv --clear .venv ; fi

deps: .venv requirements.txt
	PYTHONPATH=.venv ; . .venv/bin/activate && .venv/bin/pip install -U -r requirements.txt

test: .venv setup.py
	PYTHONPATH=.venv ; . .venv/bin/python setup.py test

clean:
	rm -rf .venv build *.egg-info
	rm -f `find . -name \*.pyc -print0 | xargs -0`
