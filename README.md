# veh-scientist

Mechanism-grounded autonomous vibration energy harvesting (VEH) scientist.

This repository is building toward an agentic research stack for topological/truncation-resonance-guided piezoelectric VEH design. The current implementation is centered on an executable **discovery replay** for the truncation-resonance paper path: corpus ingestion, claim graphing, derivation artifacts, L1 chain replay, L2 beam replay, L3 MATLAB/COMSOL call-chain manifests, anchor-aware gap ranking, report generation, smoke checks, and a local dashboard.

## Current Scope

- L1 mechanism verification for periodic / diatomic-chain TR screening logic.
- L2 beam oracle for dispersion, stopbands, finite-beam candidate TRs, and harvesting proxies.
- L3 validation call chain for MATLAB and COMSOL:
  - shared request manifests,
  - MATLAB `.m` driver generation,
  - COMSOL `mph` bridge invocation,
  - structured result JSONs,
  - failure is recorded explicitly when external runtimes are unavailable.
- Discovery replay runtime, report generator, regression smoke, and local dashboard.

## Repository Layout

```text
src/veh_scientist/
  coordinator/   Legacy research loop scaffolding
  discover/      Replay/discovery program, L1/L2/L3, report, smoke, anchors
  interfaces/    Shared schemas
  taskcard/      Task parsing and validation
  web/           Local dashboard server

configs/tasks/   Example discover/replay task cards
scripts/         Replay, dashboard, report, and smoke entry scripts
tests/unit/      Unit and stack-level tests
frontend/        Static dashboard frontend assets
```

## Installation

Requirements:

- Python 3.10+
- MATLAB or Octave for live MATLAB validation execution
- COMSOL + `mph` for live COMSOL-backed validation

Create an environment and install the package:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Development tools:

```bash
pip install -e "[dev]"
```

COMSOL integration extras:

```bash
pip install -e "[comsol]"
```

## Common Workflows

Run the full replay, including report assembly and regression smoke:

```bash
python scripts/run_replay_tr.py configs/tasks/tr_discover_replay.yaml --output-dir results/discovery
```

Plan only:

```bash
python scripts/run_replay_tr.py configs/tasks/tr_discover_replay.yaml --plan-only
```

Rebuild the report bundle from an existing run:

```bash
python scripts/build_discovery_report.py --task-card configs/tasks/tr_discover_replay.yaml --output-dir results/discovery
```

Re-run the regression smoke checks:

```bash
python scripts/run_regression_smoke.py --task-card configs/tasks/tr_discover_replay.yaml --output-dir results/discovery
```

Serve the local dashboard:

```bash
python scripts/serve_dashboard.py --host 127.0.0.1 --port 8000
```

Run the unit test suite:

```bash
pytest tests/unit
```

## L3 Tooling Notes

The L3 layer is no longer a skipped hook. The replay now materializes and attempts real tool invocations:

- MATLAB / Octave:
  - writes `veh_l3_validate.m`,
  - writes `matlab_request.json`,
  - attempts execution via `matlab`, `octave`, or `VEHSCI_MATLAB_CMD`,
  - captures stdout/stderr and structured result JSON.
- COMSOL:
  - writes `comsol_request.json`,
  - launches the Python `mph` bridge,
  - captures stdout/stderr and structured result JSON.

If external runtimes are missing, the run is marked **failed** with explicit notes, but the call chain and artifacts are still preserved for reproducibility and later reruns on a properly provisioned machine.

## Dashboard

The dashboard now supports:

- one-click replay execution,
- recent-run listing,
- load latest run,
- report rebuild,
- smoke rerun,
- rendering of L3 anchors, gap ranking, tool runs, smoke status, and artifacts.

## Outputs

Replay outputs are written under:

```text
results/discovery/<task_id>/
  01_corpus/
  02_claims/
  03_hypotheses/
  04_derivations/
  05_experiments/
  06_verification/
  07_gap_design/
  08_reporting/
  09_smoke/
  program_state.json
```

Generated artifacts, caches, virtual environments, and large reference dumps are intentionally excluded from version control.
