"""Imports scripts/toy_loop.py as a module for tests."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "toy_loop", Path(__file__).resolve().parent.parent / "scripts" / "toy_loop.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
run_loop = _mod.run
