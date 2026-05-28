# Bug Hunter Proof

## Before

```python
p = persona or load_persona()
```

## After

```python
p = persona or load_persona(provider_kind=detect_provider_kind(provider))
```

## Why

Without provider_kind, load_persona() uses the base spec and never applies provider overlays. The harness produces scores that diverge from production because the persona rules differ.

## Evidence

| Field | Value |
|---|---|
| PR | [18](https://github.com/vibeforge1111/spark-character/pull/18) |
| Repo | vibeforge1111/spark-character |
| Severity | high |
| Files changed | `src/spark_character/harness_adapter.py` |
| Branch | `fix/harness-adapter-missing-provider-overlay` |
| Validated | pass (0 errors, 0 warnings) |