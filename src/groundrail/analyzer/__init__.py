"""Analyzer: AI unit analysis with provenance, uncertainty, and stale binding.

Reads the deterministic unit index, sends one bounded unit at a time to a
configurable AI command, and stores schema-valid analyses that default to
``state: inferred``. Secrets are scanned out before any prompt is built.
"""
