import pytest

from lab import ledger, tools


@pytest.fixture(autouse=True)
def fresh_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(ledger, "ROOT", tmp_path)
    monkeypatch.setattr(tools, "BUDGET_TOTAL", 20.0)
    ledger.reset()
    yield
