"""MVMA-v1: market valuation x earnings x macro ETF exposure research (outcome-free stage).

This package holds the PR-1 deliverables of the research proposal: a source probe, the pure point-in-time
feature and signal definitions, and the frozen protocol. Nothing in it reads a forward ETF return, a NAV or a
portfolio outcome; `tests/test_mvma_v1_outcome_firewall.py` enforces that by AST scan.
"""
