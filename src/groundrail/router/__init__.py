"""Router: turns indexed + analysed artifacts into Kiro-ready context.

Builds the retrieval index, selects evidence under a token budget with explicit
inclusion rules (stale and low-confidence excluded by default), runs Kiro, and
audits the answer's citations. This is where Groundrail becomes useful day-to-day.
"""
