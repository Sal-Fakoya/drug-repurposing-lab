#!/usr/bin/env bash
# Runs the lab through Omnigent. Needs Python 3.12+, `omnigent setup` done, and `pip install -e .`
set -euo pipefail
omnigent run agents/lab_director.yaml \
  -p "Run the replay for idiopathic multicentric Castleman disease with cutoff 2013."
