"""
DL-Learner parameter sweep on AMD_final_clean.owl.

Generates configs varying algorithm, accuracy method, noise, time, and depth,
runs each, and aggregates pred.acc / F-measure of the top result into a
comparison table.

Usage:
    python evaluation/dl-learner/param_sweep.py \
        --base experiment6_vegf_inhibitors.conf \
        --dllearner-jar dllearner-1.5.0/bin/cli \
        --owl ontology/AMD_final_clean.owl
"""

import argparse
import csv
import re
import subprocess
import sys
from itertools import product
from pathlib import Path


SWEEP_GRID = {
    "la.type":                          ["celoe", "ocel"],
    "la.accuracyMethod.type":           ["pred_acc", "fmeasure", "jaccard"],
    "la.maxExecutionTimeInSeconds":     [30, 60, 120],
    "la.noisePercentage":               [0, 10, 25],
}

# CELOE in DL-Learner 1.5 only supports pred_acc and fmeasure with its
# OEHeuristicRuntime; jaccard breaks the monotonicity assumption.
INVALID_COMBOS = {
    ("celoe", "jaccard"),
}


def base_template(owl_path: str, pos_examples: list[str], neg_examples: list[str],
                  params: dict) -> str:
    """Build one config string with given params."""
    pos_block = ",\n    ".join(f'"{p}"' for p in pos_examples)
    neg_block = ",\n    ".join(f'"{n}"' for n in neg_examples)

    lines = [
        f'ks.type = "OWL File"',
        f'ks.fileName = "{owl_path}"',
        f'reasoner.type = "closed world reasoner"',
        f'reasoner.sources = {{ ks }}',
        f'lp.type = "posNegStandard"',
        f'lp.positiveExamples = {{\n    {pos_block}\n}}',
        f'lp.negativeExamples = {{\n    {neg_block}\n}}',
    ]

    # Copy params so the caller's dict isn't mutated when we pop the metric key.
    params = dict(params)
    accuracy_method = params.pop("la.accuracyMethod.type", None)
    if accuracy_method:
        lines.append(f'acc.type = "{accuracy_method}"')

    for k, v in params.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        else:
            lines.append(f'{k} = {v}')

    if accuracy_method:
        lines.append('lp.accuracyMethod = acc')

    return "\n".join(lines) + "\n"


def parse_conf(path: Path) -> tuple[list[str], list[str]]:
    """Extract positive/negative example IRIs from an existing .conf."""
    text = path.read_text(encoding="utf-8")

    def grab(label: str) -> list[str]:
        m = re.search(rf'lp\.{label}Examples\s*=\s*\{{(.*?)\}}', text, re.DOTALL)
        if not m:
            return []
        return re.findall(r'"([^"]+)"', m.group(1))

    return grab("positive"), grab("negative")


def run_dllearner(conf_path: Path, jar: str, timeout: int = 360) -> tuple[bool, str]:
    """Run DL-Learner on one config; return (ok, output)."""
    jar_str = str(jar)
    if jar_str.lower().endswith(".bat"):
        cmd = [jar_str, str(conf_path)]
        shell = True
    elif jar_str.lower().endswith(".jar"):
        cmd = ["java", "-jar", jar_str, str(conf_path)]
        shell = False
    else:
        cmd = [jar_str, str(conf_path)]
        shell = False

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=shell)
        return True, r.stdout + "\n---STDERR---\n" + r.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def extract_top_solution(output: str) -> dict:
    """Pull the #1 ranked solution + its pred.acc and F-measure from output."""
    m = re.search(
        r"1:\s*(.+?)\s*\(pred\.\s*acc\.?:\s*([\d.]+%?)\s*,\s*F-measure:\s*([\d.]+%?)\)",
        output,
    )
    if m:
        return {"expression": m.group(1).strip(),
                "pred_acc":   m.group(2),
                "f_measure":  m.group(3)}
    return {"expression": "", "pred_acc": "", "f_measure": ""}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True,
                   help="Base .conf to take pos/neg examples from")
    p.add_argument("--dllearner-jar", required=True)
    p.add_argument("--owl", required=True,
                   help="Path to OWL relative to project root")
    p.add_argument("--conf-dir", default="evaluation/dl-learner",
                   help="Directory containing base .conf files")
    p.add_argument("--out-dir", default="evaluation/dl-learner/sweep_results",
                   help="Where to write generated configs and results")
    args = p.parse_args()

    base_conf = Path(args.conf_dir) / args.base
    if not base_conf.exists():
        print(f"Base conf not found: {base_conf}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)
    configs_dir = out_dir / "configs"
    logs_dir = out_dir / "logs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    pos, neg = parse_conf(base_conf)
    print(f"Base: {args.base} | pos={len(pos)} neg={len(neg)}")

    # Configs live in sweep_results/configs/, 4 levels deep — adjust accordingly.
    owl_for_conf = f"../../../../{args.owl}"

    keys = list(SWEEP_GRID.keys())
    combos = list(product(*[SWEEP_GRID[k] for k in keys]))
    print(f"Sweep size: {len(combos)} runs")

    rows = []
    for i, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))

        # Skip combos that DL-Learner 1.5 cannot handle (see INVALID_COMBOS).
        if (params["la.type"], params["la.accuracyMethod.type"]) in INVALID_COMBOS:
            continue

        tag = (f"{params['la.type']}_"
               f"{params['la.accuracyMethod.type']}_"
               f"t{params['la.maxExecutionTimeInSeconds']}_"
               f"n{params['la.noisePercentage']}")
        conf_path = configs_dir / f"sweep_{tag}.conf"
        conf_path.write_text(base_template(owl_for_conf, pos, neg, params), encoding="utf-8")

        print(f"[{i}/{len(combos)}] {tag}... ", end="", flush=True)
        ok, output = run_dllearner(conf_path, args.dllearner_jar,
                                    timeout=params["la.maxExecutionTimeInSeconds"] + 60)
        log_path = logs_dir / f"sweep_{tag}.log"
        log_path.write_text(output, encoding="utf-8")

        top = extract_top_solution(output)
        status = "OK" if ok and top["expression"] else "FAIL"
        print(status, "-", top.get("pred_acc", "?"), "/", top.get("f_measure", "?"))

        rows.append({
            "tag":        tag,
            "algorithm":  params["la.type"],
            "metric":     params["la.accuracyMethod.type"],
            "time_s":     params["la.maxExecutionTimeInSeconds"],
            "noise_pct":  params["la.noisePercentage"],
            "status":     status,
            "pred_acc":   top["pred_acc"],
            "f_measure":  top["f_measure"],
            "expression": top["expression"][:200],
        })

    csv_path = out_dir / f"sweep_{Path(args.base).stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults: {csv_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
