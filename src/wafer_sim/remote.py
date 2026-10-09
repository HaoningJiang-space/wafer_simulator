"""Compatibility imports for historical private experiment entry points.

New orchestration imports experiments.server. Public compile/execute/audit
functions have no server dependency. Runtime paths are never machine resources.
"""
from wafer_sim.experiments.server import ROOTS, runtime_root, require_active_server
