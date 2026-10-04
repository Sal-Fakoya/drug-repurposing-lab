# Limitations and validation still needed

Fill in during the build. Required for submission.

## Leakage controls
- Date filter on all literature retrieval, cutoff 2015 (enforced by policy and by the tool).
- Drug and disease names masked in scoring (enforced by policy, test in tests/).
- Rankings come only from computed scores, never from the LLM.
- Planner reward is label-free. The target drug rank is evaluation only.

## Sources that cannot be rolled back to the cutoff

## Known limits
- Single case (iMCD and sirolimus). Sparse rare disease literature.
- The model may remember the answer when proposing hypotheses. The LLM-only baseline measures this.
- Toy mode uses synthetic data. Toy results are never reported as findings.

## Validation needed before any real-world use
- Laboratory and clinical validation. Outputs are agent-generated hypotheses, not treatment advice.
