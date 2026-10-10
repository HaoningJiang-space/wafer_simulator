"""One unprofiled G2.1 cost worker; same counters-only output in every mode."""
import argparse
from pathlib import Path
import resource
import time
from wafer_sim.adapters.causal_macro import run
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.analysis.causal_macro_single import compact_reference
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json


def main():
    require_active_server()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--mode',choices=('g1','macro_off','macro_on'),required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh worker output required')
    inp=read_json(args.input);before=time.perf_counter();cpu_before=time.process_time()
    if args.mode=='g1':
        prediction=simulate(inp['contract'],inp['messages'],inp['cycle_limit'])
        compact=compact_reference(prediction)
        metrics=dict(physical_cycle_updates=prediction['processed_cycles'],logical_cycles=prediction['final_cycle'],skipped_cycles=0,macros=0)
        internal_evidence='original full G1'
    else:
        result=run(inp['contract'],inp['messages'],inp['cycle_limit'],compress=args.mode=='macro_on',evidence='counters')
        compact=result.compact();metrics=result.metrics()
        metrics.pop('batches');metrics.pop('checkpoints');internal_evidence='same derived core, counters only'
    prediction_seconds=time.perf_counter()-before;prediction_cpu_seconds=time.process_time()-cpu_before
    write_json(args.output,dict(mode=args.mode,complete=True,compact=compact,metrics=metrics,
        prediction_seconds=prediction_seconds,prediction_cpu_seconds=prediction_cpu_seconds,
        internal_evidence=internal_evidence,process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))


if __name__=='__main__':main()
