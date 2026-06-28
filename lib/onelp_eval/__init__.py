"""OneLP capstone evaluation toolkit.

Modules:
  mc_engine        — faithful Python port of the production Monte Carlo engine
  extraction_eval  — F1 / confusion-matrix utilities (mirrors tests/eval/validators.ts)
  portfolio        — calibrated reference portfolio + ground-truth history generator
  plotting         — shared figure styling
"""
__all__ = ["mc_engine", "extraction_eval", "portfolio", "plotting"]
