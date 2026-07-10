#!/usr/bin/env python3
"""rerank: re-order an existing ranking record under a rubric's scoring policy — no re-judging.

The expensive part of ranking (judges reading pieces, scoring dimensions) is already
persisted in <book>.ranking.json. This script re-aggregates those recorded dimension
scores under any mechanical policy (weighted_mean / median / max / min), applies the
rubric's veto rules, and prints the re-ranked list. `holistic` keeps the judge's
recorded overall (useful to view vetoes without changing the order).

STRICT by design: if the rubric's dimension keys are not all present in every record
entry, the script refuses to run — a record judged under one rubric cannot be
mechanically re-ranked under a rubric with DIFFERENT dimensions (that needs a new
judging pass). This guard exists because the failure mode is silent plausibility.

Run with the project venv (PyYAML lives there):
  .venv/bin/python rerank.py book.ranking.json rubrics/inspiration.md [--scoring max] [--top 20]
"""
import argparse
import json
import statistics
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    raise SystemExit("PyYAML missing. Run with the project venv (.venv/bin/python) "
                     "or: pip install pyyaml")


def load_rubric(path):
    text = Path(path).expanduser().read_text()
    if not text.startswith("---"):
        raise SystemExit("rubric file needs YAML frontmatter between --- markers")
    return yaml.safe_load(text.split("---", 2)[1])


def aggregate(vals, weights, keys, policy):
    if policy == "weighted_mean":
        return sum(vals[k] * weights[k] for k in keys) / max(sum(weights[k] for k in keys), 1e-9)
    seq = [vals[k] for k in keys]
    if policy == "median":
        return statistics.median(seq)
    if policy == "max":
        return max(seq)
    if policy == "min":
        return min(seq)
    raise SystemExit(f"unknown scoring policy: {policy}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("rubric")
    ap.add_argument("--scoring", help="override the rubric's scoring field")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    record = json.loads(Path(args.record).expanduser().read_text())
    rubric = load_rubric(args.rubric)
    policy = args.scoring or rubric.get("scoring", "holistic")
    dims_cfg = {d["key"]: d for d in rubric["dimensions"]}
    keys = list(dims_cfg)
    weights = {k: float(d.get("weight", 1.0)) for k, d in dims_cfg.items()}

    entries = record["ranking"]
    if not entries:
        raise SystemExit("record has an empty ranking")

    # STRICT schema check: every rubric dimension must exist in every entry.
    for r in entries:
        missing = [k for k in keys if k not in r.get("dimensions", {})]
        if missing:
            have = sorted(r.get("dimensions", {}).keys())
            raise SystemExit(
                f"record entry '{r.get('title', r.get('slug'))}' has dimensions {have}, "
                f"but the rubric requires {keys} (missing: {missing}).\n"
                "A record judged under one rubric cannot be mechanically re-ranked under a "
                "rubric with different dimensions — run a new judging pass for this rubric.")

    ranked, vetoed = [], []
    for r in entries:
        dims = r["dimensions"]
        hit = [k for k in keys
               if dims_cfg[k].get("veto_below") is not None and dims[k] < dims_cfg[k]["veto_below"]]
        if hit:
            vetoed.append((r, hit))
            continue
        score = r["overall"] if policy == "holistic" else aggregate(dims, weights, keys, policy)
        ranked.append((score, r))
    # NOTE: the rubric's `tie_break` field is reserved and not implemented yet
    # (records don't carry dates); ties keep the record's existing order.
    ranked.sort(key=lambda x: (-x[0], x[1]["rank"]))

    print(f"# policy={policy}  dimensions={'/'.join(keys)}  ranked={len(ranked)}  vetoed={len(vetoed)}\n")
    for i, (score, r) in enumerate(ranked[: args.top], 1):
        d = r["dimensions"]
        dimtxt = " ".join(f"{k[0]}{d[k]}" for k in keys)
        moved = r["rank"] - i
        arrow = f"(was {r['rank']}, {'+' if moved > 0 else ''}{moved})" if r["rank"] != i else ""
        print(f"{i:3d}. [{score:.1f}] {dimtxt} {r['title']} {arrow}")
    if vetoed:
        print("\n## Vetoed")
        for r, hit in vetoed:
            print(f"- {r['title']} (failed: {', '.join(hit)})")


if __name__ == "__main__":
    main()
