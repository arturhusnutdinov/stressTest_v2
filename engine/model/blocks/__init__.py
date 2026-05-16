"""
Financial model blocks extracted from ThreeStatementModel core.

Each block is a standalone function:
  solve_*(state, prev, historic, config, **kwargs) -> YearState

This allows independent testing and gradual refactoring.
"""
