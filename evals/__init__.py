"""
Raqib evaluation harness.

Turns the agent from "it demos well" into "here are the numbers." Three
suites, one regenerable report:

* golden   — run the agent against labelled cases, score verdict accuracy,
             SAR schema validity, policy grounding, and numeric grounding.
* redteam  — fire an adversarial-document corpus at the guardrail layer and
             measure prompt-injection catch rate per attack family.
* report   — aggregate the above (plus token/latency/cost) into EVALS.md.

Everything is deterministic to run (same cases, same corpus) even though the
model itself is not — which is exactly why the --repeat calibration mode
exists: it measures that non-determinism instead of hiding it.
"""
