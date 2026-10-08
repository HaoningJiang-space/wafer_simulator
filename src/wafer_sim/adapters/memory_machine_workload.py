"""Declared logical-worker and object-role placement, outside machine/workload."""
from wafer_sim.execution.plan import Placement


def place(metadata,mode):
    if mode not in {'near','opposite','single_controller'}:
        raise ValueError('Unknown declared data placement')
    workers=metadata['dimensions']['workers'];homes={}
    for name,info in metadata['data_roles'].items():
        worker,role=info['worker'],info['role']
        if role=='input':homes[name]='host-memory' if worker==0 else f'sram-{worker}'
        elif role=='intermediate':homes[name]=f'sram-{worker}'
        elif role in {'first_weight','second_weight','output'}:
            tile=worker if mode=='near' else (worker+workers//2)%workers if mode=='opposite' else 0
            bank=1 if role=='second_weight' else 0
            homes[name]=f'dram-{tile}-{bank}'
        else:raise ValueError('Unknown logical object role')
    return Placement({op:f'c{worker}' for op,worker in metadata['operation_workers'].items()},homes)
