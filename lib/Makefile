RUNTEST=python3 -m unittest -v -b

ALLMODULES=$(patsubst %.py, %, $(wildcard test_*.py))

all:
	${RUNTEST} ${ALLMODULES}

% : test_%.py
	${RUNTEST} test_$@
