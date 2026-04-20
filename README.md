# veh-scientist

Mechanism-grounded autonomous vibration energy harvesting (VEH) scientist.

This repository is building toward an agentic research stack for topological-resonance-guided piezoelectric VEH design. The current implementation is centered on a periodic beam benchmark and a multi-fidelity verification workflow spanning analytical, reduced-order, and high-fidelity simulation layers.

## Current Scope

- L1 mechanism verification for periodic / diatomic-chain-style screening logic.
- L2 beam oracle for dispersion, finite-chain response, and harvesting metrics.
- L3 cross-validation hooks for MATLAB and COMSOL.
- Agent/runtime/dashboard scaffolding for the broader VEH Scientist system.

The implementation blueprint and roadmap live in:

- `veh_scientist_project_blueprint.md`
- `veh_scientist_agent_instructions.md`

## Repository Layout

```text
src/veh_scientist/
  agents/        Agent config, definitions, providers, runtime
  analysis/      Objectives and reporting helpers
  codesign/      Structure-transducer-electrical translation logic
  coordinator/   Research loop orchestration
  critic/        Decision and critique layer
  interfaces/    Shared schemas
  mechanism/     Mechanism screening and gating logic
  memory/        Persistent memory abstractions
  proposals/     Proposal generation
  taskcard/      Task parsing and validation
  verifiers/     L1/L2/L3 verification backends
  web/           Simple dashboard server

configs/tasks/   Example task cards
scripts/         Validation, sweep, and dashboard entry scripts
tests/unit/      Unit and stack-level tests
frontend/        Static dashboard frontend assets
```

## Installation

Requirements:

- Python 3.10+
- MATLAB for MATLAB-based validation scripts
- COMSOL + `mph` for COMSOL-backed validation

Create an environment and install the package:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development tools:

```bash
pip install -e ".[dev]"
```

For COMSOL integration:

```bash
pip install -e ".[comsol]"
```

## Common Workflows

Run the unit test suite:

```bash
pytest
```

Run the Python / MATLAB / COMSOL beam cross-validation workflow:

```bash
python scripts/beam_oracle_validation.py
```

Serve the local dashboard:

```bash
python scripts/serve_dashboard.py
```

Outputs are typically written under `results/`, which is intentionally excluded from version control.

## Notes

- This repository currently tracks source, scripts, tests, configs, and frontend assets.
- Large generated artifacts, virtual environments, cached files, and reference-material dumps are ignored.
- The current research focus is the topological-resonance periodic beam benchmark rather than the full end-to-end autonomous scientist loop.

## Discover / Replay Scaffold

The `tr-science` branch introduces a first-pass discovery-planning layer for
replaying the truncation-resonance paper development path before wiring the full
solver stack into it.

New pieces in this branch:

- `DiscoverTaskCard` and related replay/discovery schemas under `interfaces/`
- task-card parsing and validation for `task_type: discover`
- `discover/` package for corpus ordering, claim graph building, hypothesis
  ladder generation, derivation-card generation, gap ranking, and evidence
  scaffolding
- `configs/tasks/tr_discover_replay.yaml` as the first end-to-end replay task
- `scripts/run_replay_tr.py` to materialize a replay program as JSON

Run the replay planner:

```bash
python scripts/run_replay_tr.py configs/tasks/tr_discover_replay.yaml
```

Run the new discovery-layer tests:

```bash
pytest tests/unit/test_discover_taskcard.py \
  tests/unit/test_hypothesis_ladder.py \
  tests/unit/test_derivation_cards.py \
  tests/unit/test_gap_ranker.py \
  tests/unit/test_replay_tr.py
```


## Executable Replay and Dashboard

The latest replay layer is no longer planning-only. It now executes:

- corpus resolution with PDF ingestion and gap-statement generation
- claim-graph extraction grounded in the resolved corpus
- structured derivation artifacts with SymPy-generated equations
- an executable L1 diatomic-chain replay for TR, localization, harvesting, and parameter sweeps
- an executable L2 bilayer Timoshenko-beam replay for stopbands and candidate TR locations
- ranked gap selection and evidence/report assembly
- a local frontend/backend dashboard for running the replay interactively

Run the full replay from the CLI:

```bash
python scripts/run_replay_tr.py configs/tasks/tr_discover_replay.yaml --output-dir results/discovery
```

Plan only without running solvers:

```bash
python scripts/run_replay_tr.py configs/tasks/tr_discover_replay.yaml --plan-only
```

Serve the local dashboard:

```bash
python scripts/serve_dashboard.py --host 127.0.0.1 --port 8000
```

The dashboard lets you launch the replay, inspect stages, browse claims and hypotheses,
see ranked gaps, and open generated artifacts directly from the browser.
