"""Audit a supplied periphery input and execution without study or server state."""
from wafer_sim.adapters.periphery_case import case_from_record
from wafer_sim.analysis.memory_periphery import audit_periphery


def audit_input(record, result):
    case = case_from_record(record)
    return audit_periphery(case.workload, case.placement, case.compiled, case.binding,
                           case.transactions, case.policy, result)
