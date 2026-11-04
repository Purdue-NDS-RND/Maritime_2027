.DEFAULT_GOAL := test
PYTHON ?= python3
.PHONY: test demo analytic compile

test:
	$(PYTHON) -m pytest tests -q

demo:
	$(PYTHON) -m perception_synthetic.demo --adapter synthetic --scenario stationary --output ../simulation/logs/perception/stationary

analytic:
	$(PYTHON) -m perception_synthetic.demo --adapter synthetic --scenario analytic --output ../simulation/logs/perception/analytic

compile:
	$(PYTHON) -m compileall -q maritime_perception perception_synthetic launch
