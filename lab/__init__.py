"""Drug repurposing lab: tools, scoring, ledger and policies used by the Omnigent agents."""
import os

# CUTOFF_YEAR is exclusive: evidence must be published BEFORE 1 January of this year.
# CUTOFF_YEAR=2013 means publications dated up to and including 2012-12-31.
CUTOFF_YEAR = int(os.environ.get("CUTOFF_YEAR", "2013"))
MODE = os.environ.get("LAB_MODE", "toy")  # "toy" = synthetic offline data, "real" = loaders
