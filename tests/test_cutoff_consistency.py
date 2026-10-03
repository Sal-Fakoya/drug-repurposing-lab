import re
from pathlib import Path

import yaml

from lab import CUTOFF_YEAR

ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = ROOT / "agents" / "lab_director.yaml"


def test_policy_cutoff_matches_lab_default():
    spec = yaml.safe_load(YAML_PATH.read_text())
    assert spec["policies"]["cutoff_guard"]["factory_params"]["cutoff_year"] == CUTOFF_YEAR


def test_agent_prompts_use_the_same_year():
    text = YAML_PATH.read_text()
    found = [y for groups in re.findall(
        r"clock set to (\d{4})|pre-(\d{4}) evidence|cutoff_year (\d{4})\.", text)
        for y in groups if y]
    assert found, "expected the cutoff year to appear in the agent prompts"
    assert set(found) == {str(CUTOFF_YEAR)}


def test_env_example_matches():
    line = next(x for x in (ROOT / ".env.example").read_text().splitlines()
                if x.startswith("CUTOFF_YEAR="))
    assert line.split("=")[1].split()[0] == str(CUTOFF_YEAR)
