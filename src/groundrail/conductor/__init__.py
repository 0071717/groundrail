"""Conductor: orchestration and child-agent management for Groundrail.

Agents may ONLY write to orchestrations/, findings/, and quarantine/ paths
inside ``.groundrail/``. They may NEVER write to canonical indexes or
knowledge artifacts (unit-index, analysis/, source/).
"""
