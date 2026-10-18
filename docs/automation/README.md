# Investment Autopilot v1

A dormant, metadata-only control plane for safe independent engineering work.
Read [policy](OPERATING_POLICY.md), [queue contract](QUEUE_CONTRACT.md),
[proposed seeds](SEED_QUEUE.md), [agent handoffs](HANDOFFS.md) and
[owner activation steps and access limitations](ACTIVATION.md).

`automation/control.py` uses only the Python standard library. A native runner
follows the contract and supplies verified events; the module never runs research,
workers, CI or merges. GitHub Issues hold reviewed task specifications and a
single GitHub Git ref serializes the machine journal. No scheduler or workflow
is added. It is cooperative orchestration, not a security boundary.

Offline rehearsal (the example uses fake Issue #1 and must never be activated):

```sh
.venv/bin/python -m automation.control --file docs/automation/synthetic-queue.json
.venv/bin/python -m pytest -q tests/automation
```

Tests use invented metadata and temporary local bare Git remotes. They exercise
duplicate deliveries, identical-event competing writers, dependency cycles,
resource overlap, the two-slot limit, pending CI, two-repair exhaustion, exact-head
independent review, hard owner gates and durable restart. No remote research
workflow or live queue is needed. Full repository validation follows the existing
Tests workflow; exact run outcomes belong in the PR evidence, not assumed here.

Implementation does not alter AGENTS.md, research contracts, existing workflows,
production logic or historical data. Existing KR A0 ownership must be reconciled
before queue activation. Subscription features and GitHub API permissions still
need owner-side verification; activation instructions explicitly identify the
manual alternative when native support is unavailable.
