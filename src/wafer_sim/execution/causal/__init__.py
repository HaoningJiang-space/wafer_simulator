"""Explicit state and exact transitions for the bounded G1 component contract.

R1 has no macro engine or alternative evidence modes. Legacy G1 and the G2.1
prototype remain independent references rather than being redirected here.
"""
from .state import CausalState, CausalSnapshot, initialize
from .transition import step_one_cycle, run, result

__all__ = ['CausalState', 'CausalSnapshot', 'initialize', 'step_one_cycle', 'run', 'result']
