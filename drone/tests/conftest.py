from copy import deepcopy

import pytest

from maritime_perception.validation import load_json
from perception_synthetic.generator import generate, load_scenario


@pytest.fixture
def settings(tmp_path):
    generate(load_scenario("analytic"), tmp_path/"session")
    return deepcopy(load_json(tmp_path/"session/config.json"))


@pytest.fixture
def events(tmp_path, settings):
    import json
    return [json.loads(raw) for raw in (tmp_path/"session/measurements.jsonl").read_text().splitlines()]
