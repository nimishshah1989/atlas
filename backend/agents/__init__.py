"""ATLAS agent modules — computation agents that classify, detect, and write findings.

Agents:
- rs_analyzer: Classify equities into RRG quadrants, detect transitions (AGENT 1)
- sector_analyst: Sector quadrant classification, rotation and breadth-RS divergence (AGENT 2)
- decisions_generator: Generate actionable buy/sell/hold decisions from RS data (AGENT 3)
- goldilocks_analyst: Cross-validate Goldilocks stock ideas against RS quadrant data (AGENT 4)
- mf_decisions_generator: MF-specific buy/sell/hold decisions from MF RS data
- investor_personas: 4 LLM-powered investor personas (jhunjhunwala, value-investor,
  momentum-trader, contrarian) — each with distinct investment philosophy, reads RS
  data via JIP, calls LLM, writes findings to atlas_intelligence with full provenance
"""
