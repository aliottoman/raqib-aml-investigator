"""
Eval CLI.

  python -m evals redteam            # guardrail sweep (no model credits needed)
  python -m evals golden             # live golden-case suite (needs OCI key)
  python -m evals golden --repeat 3  # + verdict calibration
  python -m evals report             # regenerate EVALS.md from both suites
  python -m evals report --skip-golden   # red-team-only report

Golden runs need a valid OPENAI_API_KEY_CHICAGO; the red-team sweep only needs
~/.oci/config (guardrails sign with IAM, not the Bearer key).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import config
from src import rules
from evals import redteam, report
from evals.cases import GOLDEN_CASES
from evals.runner import run_case
from evals.scoring import score, summarize

EVALS_MD = config.PROJECT_ROOT / "EVALS.md"
LAST_GOLDEN = config.PROJECT_ROOT / "evals" / ".last_golden.json"


def _run_golden(repeat: int = 1) -> list[dict]:
    """Run every golden case (repeat× each) and collect scored results."""
    rules.run_screening()  # ensure the alert queue exists before we open cases
    out = []
    for case in GOLDEN_CASES:
        print(f"▶ {case.alert_id}  {case.label}", flush=True)
        runs, repeat_scores = [], []
        for i in range(max(1, repeat)):
            r = run_case(case.alert_id)
            runs.append(r)
            if r.sar:
                repeat_scores.append({"filed": bool(r.sar["sar_filing_required"]),
                                      "risk_score": int(r.sar.get("risk_score", 0))})
            tag = f" (run {i+1}/{repeat})" if repeat > 1 else ""
            print(f"   {r.latency_s}s · {r.total_tokens:,} tok · "
                  f"{'ok' if r.ok else 'ERROR: ' + r.error}{tag}", flush=True)
        primary = runs[0]
        checks = score(case, primary)
        passed, total = summarize(checks)
        for c in checks:
            print(f"     [{'PASS' if c.passed else 'FAIL'}] {c.name}", flush=True)
        out.append({
            "alert_id": case.alert_id, "label": case.label,
            "passed": passed, "checks": total, "error": primary.error,
            "failed_checks": [{"name": c.name, "detail": c.detail} for c in checks if not c.passed],
            "sar": primary.sar,
            "latency_s": statistics.mean([r.latency_s for r in runs]),
            "prompt_tokens": primary.prompt_tokens, "completion_tokens": primary.completion_tokens,
            "total_tokens": primary.total_tokens,
            "repeat_scores": repeat_scores if repeat > 1 else [],
        })
    # Persist so `report --cached` can rebuild EVALS.md without re-billing inference.
    LAST_GOLDEN.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _run_redteam():
    print(f"▶ red-team sweep — {len(redteam.CORPUS)} documents", flush=True)
    results = redteam.sweep()
    s = redteam.summarize(results)
    print(f"   catch rate {s['caught_expected']}/{s['total_expected']} = {s['catch_rate']:.0%} · "
          f"false positives {s['benign_flagged']}/{s['benign_total']}", flush=True)
    for fam, d in s["families"].items():
        print(f"     {fam:20} {d['caught']}/{d['total']}", flush=True)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evals")
    ap.add_argument("suite", choices=["golden", "redteam", "report"])
    ap.add_argument("--repeat", type=int, default=1, help="runs per golden case (calibration)")
    ap.add_argument("--skip-golden", action="store_true", help="report: red-team only")
    ap.add_argument("--cached", action="store_true",
                    help="report: reuse the last golden run (no inference billed)")
    args = ap.parse_args(argv)

    if args.suite == "redteam":
        _run_redteam()
        return 0

    if args.suite == "golden":
        if not config.live_configured():
            print("Live OCI credentials required (OPENAI_API_KEY_CHICAGO). Aborting.", file=sys.stderr)
            return 2
        _run_golden(args.repeat)
        return 0

    # report
    golden, golden_error = None, None
    if args.cached and LAST_GOLDEN.exists():
        golden = json.loads(LAST_GOLDEN.read_text())
        print(f"Using cached golden run from {LAST_GOLDEN.name} ({len(golden)} cases).", flush=True)
    elif not args.skip_golden and config.live_configured():
        golden = _run_golden(args.repeat)
        # If every case errored (e.g. expired key), don't report quality failures
        # that never happened — surface the shared error instead.
        if golden and all(g["sar"] is None for g in golden):
            golden_error = next((g["error"] for g in golden if g.get("error")), "all runs errored")
            golden = None
    elif not args.skip_golden:
        print("No live credentials — writing a red-team-only report.", file=sys.stderr)
    results = _run_redteam()
    EVALS_MD.write_text(report.build_markdown(golden, results, golden_error), encoding="utf-8")
    print(f"\n✓ wrote {EVALS_MD}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
