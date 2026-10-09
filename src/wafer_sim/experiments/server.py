"""Private experiment-server locations and authorization; no machine semantics."""
import os
from pathlib import Path
import platform

ROOTS = {'ee4e072': Path('/Projects/haoning/wafer_simulator'),
         'eex005': Path('/home/wangziheng/wafer_simulator')}


def runtime_root():
    host = platform.node().split('.')[0]
    if host not in ROOTS:
        raise RuntimeError('Execution belongs on the registered experiment server')
    root = Path(os.environ.get('WAFER_REMOTE_ROOT', str(ROOTS[host]))).resolve()
    if not root.is_relative_to(ROOTS[host]):
        raise ValueError('Runtime must remain within its registered project directory')
    return root


def require_active_server():
    if platform.node().split('.')[0] != 'ee4e072':
        raise RuntimeError('New experiments run on hn072@143.89.78.72 (ee4e072); eex005 is retired')
    return runtime_root()
