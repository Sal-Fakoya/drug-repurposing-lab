"""Drug repurposing lab: tools, scoring, ledger and policies used by the Omnigent agents."""
import os

# CUTOFF_YEAR is exclusive: evidence must be published BEFORE 1 January of this year.
# CUTOFF_YEAR=2015 means publications dated up to and including 2014-12-31.
CUTOFF_YEAR = int(os.environ.get("CUTOFF_YEAR", "2015"))
MODE = os.environ.get("LAB_MODE", "toy")  # "toy" = synthetic offline data, "real" = loaders


def method_b_include_hhv8() -> bool:
    """Default for method B: count co-mentions from HHV-8-related records too (LAB env, read live)."""
    return os.environ.get("LAB_METHOD_B_INCLUDE_HHV8", "1").strip().lower() not in {
        "0", "false", "no", "off"}
