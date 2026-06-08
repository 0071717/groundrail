"""Flow and impact composition.

Composes deterministic unit references and AI analyses into call graphs, flows,
and impact reports. The cardinal rule (AGENTS.md, docs/09): composition preserves
uncertainty. Call resolution is heuristic, so every edge is ``inferred`` and every
path takes the confidence of its weakest link — an inferred chain is never
upgraded to verified.
"""
