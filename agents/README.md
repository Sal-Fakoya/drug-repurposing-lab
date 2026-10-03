# agents

`lab_director.yaml` is the whole lab: a director plus six sub-agents (literature, insight,
planner, runner, analysis, safety) with tool allowlists and policies.

Ledger kinds the agents may write with `write_ledger`:
`evidence_record`, `hypothesis`, `hypothesis_update`, `experiment_spec`, `verdict`,
`safety_review`, `approval`. Results are written by the runner tool, not by agents.

## H1 to H3 task: record what you learn about Omnigent here

1. Can a custom agent YAML be loaded in your route (CLI session or managed Sandbox)?
2. Does a sub-agent reliably pass an id and receive structured output?
3. Do agent-level policies apply to tool calls made by sub-agents?
4. Do policy events identify which agent made a call?
5. How does an ASK appear in a recorded demo, and where is the approval recorded?
6. Which model ids exist in the workspace? Update `executor.model` in the YAML.
7. Does `max_sessions: 2` give parallel Runner sessions?
8. Can function tools reach Europe PMC from where the session runs?
9. How do you export session records or MLflow traces?
