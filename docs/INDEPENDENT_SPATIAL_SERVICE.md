# Independent Spatial Service (D0)

D0 asks whether accurate empty-network communication service is sufficient
for the existing layout decision. Its [registration](INDEPENDENT_SPATIAL_SERVICE_PROTOCOL.md)
fixes calibration and evaluation before application results are available.

The predictor preserves the complete U1 binding and local resource calendar.
At DRAM-message readiness it looks up the physical-machine identity, source
endpoint, destination endpoint and payload size in an independently measured
component table. It schedules an all-message completion boundary after that
duration. Concurrent DRAM transfers do not reserve endpoint or link calendars.
This excludes dynamic sharing and traffic-history state by construction.
Native C2C/IO still runs as in U1, with a conservative shared simulation clock.

The implementation is in
[`adapters/independent_spatial_service.py`](../src/wafer_sim/adapters/independent_spatial_service.py).
It uses the ordinary timed executor without changing admission, dependencies,
data publication, staging lifetime or bank/controller service. The independent
[`analysis/independent_spatial_service.py`](../src/wafer_sim/analysis/independent_spatial_service.py)
checks communication costs and native passthrough; the existing completion
audit checks every service, DAG phase, retained object and retirement.

Calibration resolves independent routes on empty instances of the physical
network using the frozen native routing policy. This is different evidence
from the routes of a completed S application: those cannot enter prediction.
The endpoint table deliberately gives the independent-service hypothesis
accurate costs on every required pair, rather than requiring a fitted generic
hop/bandwidth formula. It has a finite domain and rejects unsupported machines,
endpoints and sizes. A new workload may require new independent probes; the
present result does not establish interpolation or generalization.

The table also measures partial flits and short messages separately. For
example, a 16-byte request rounds to one native flit; long-message sustained
injection behavior cannot be applied to it as a universal bytes/cycle rate.
Absolute idle-ready clocks are checked separately from payload/path coverage.
All-flit captures stay on the experiment server; the table contains service
metrics, component path histograms and capture hashes, not application events.

Both calibration and complete-work evaluation run on hn072. The commands are:

```bash
cd /Projects/haoning/wafer_simulator/source
export PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
../.venv/bin/python scripts/test_wow_target_remote.py ../runs/d0-tests-NEW
../.venv/bin/python -m wafer_sim.experiments.independent_spatial_service \
  --calibrate --tests ../runs/d0-tests-NEW/SEMANTICS.json \
  --output /Projects/haoning/wafer_simulator/runs/d0-calibration-NEW
../.venv/bin/python -m wafer_sim.experiments.independent_spatial_service \
  --tests ../runs/d0-tests-NEW/SEMANTICS.json \
  --calibration /Projects/haoning/wafer_simulator/runs/d0-calibration-NEW \
  --output /Projects/haoning/wafer_simulator/runs/d0-applications-NEW
../.venv/bin/python -m wafer_sim.analysis.independent_spatial_study \
  /Projects/haoning/wafer_simulator/runs/d0-applications-NEW \
  /Projects/haoning/wafer_simulator/runs/d0-analysis-NEW
```

Use fresh absolute output directories. Calibration is independently verified
before application workers receive its immutable table. Full-work U1 and S
must reproduce all accepted event hashes; D0 must pass complete-DAG, byte,
service and capacity audits even if its accuracy budgets fail. Runtime/RSS
measurements distinguish recurring prediction from calibration, initialization,
serialization and verification. This is a conditional fixed-clock model
comparison, without hardware, thermal or equal-physical-cost claims.
