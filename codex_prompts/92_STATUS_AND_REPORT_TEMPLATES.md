# Codex 执行状态文件模板

## EXECUTION_STATUS.md

```markdown
# Refactor Execution Status

- Frozen document set: v1.0
- Baseline commit:
- Current branch:
- Current phase:
- Last updated:

| Phase | Status | Start Commit | End Commit | Gate | Report |
|---|---|---|---|---|---|
| P00 | not_started | | | | |
...
```

## DECISION_LOG.md

```markdown
# Decision Log

## ADR-XXX — Title
- Status: proposed / accepted / rejected / superseded
- Date:
- Trigger:
- Frozen documents affected:
- Options:
- Decision:
- Compatibility/migration impact:
- Evaluation impact:
```

## RISK_REGISTER.md

```markdown
# Risk Register

| ID | Phase | Risk | Probability | Impact | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|
```

## Phase Report

```markdown
# Pxx Phase Report

## Scope and inputs
## Repository audit
## Implemented task IDs
## Key decisions
## Files changed
## API/database/config changes
## Tests and commands
## Evaluation results
## Compatibility and migration
## Risks and remaining work
## Exit Gate evidence
## Next-phase readiness
```
