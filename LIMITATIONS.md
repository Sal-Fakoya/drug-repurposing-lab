# Limitations and validation still needed

Fill in during the build. Required for submission.

## Leakage controls
- Date filter on all literature retrieval, cutoff 2013 (enforced by policy and by the tool).
- Drug and disease names masked in scoring (enforced by policy, test in tests/).
- Rankings come only from computed scores, never from the LLM.
- Planner reward is label-free. The target drug rank is evaluation only.
- Canary check on the bare model: TODO (store the answer and disclose it here).

## Sources that cannot be rolled back to the cutoff
- TODO (Thierry, H1 to H3): list each source and what could not be pinned.

## Known limits
- Single case (iMCD and sirolimus). Sparse rare disease literature.
- The model may remember the answer when proposing hypotheses. The LLM-only baseline measures this.
- Toy mode uses synthetic data. Toy results are never reported as findings.

## Validation needed before any real-world use
- Laboratory and clinical validation. Outputs are agent-generated hypotheses, not treatment advice.
