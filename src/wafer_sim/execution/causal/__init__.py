"""Explicit state and exact transitions for the bounded G1 component contract.

Legacy G1 and the G2.1 prototype remain independent references rather than
being redirected here. Evidence modes do not change exact service decisions.
"""
from .state import CausalState, CausalSnapshot, MessageProgress, initialize
from .transition import step_one_cycle, run, result, completion_summary, compact_record
from .evidence import FullEvidence, CompactEvidence, CountersEvidence

__all__ = ['CausalState', 'CausalSnapshot', 'MessageProgress', 'initialize',
    'step_one_cycle', 'run', 'result', 'completion_summary', 'compact_record',
    'FullEvidence', 'CompactEvidence', 'CountersEvidence']
