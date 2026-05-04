"""
Rerun the 15 DL-Learner experiments cited in the thesis against the current
ontology.

Updates each .conf file's ks.fileName to point to the target OWL, runs
DL-Learner CLI, and collects the output in results_rerun/.

Usage:
    python dl-learner/run_cited_experiments.py \\
        --owl ontology/AMD_20260419_163840.owl \\
        --dllearner-jar <path/to/dllearner-cli.jar>
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# The 15 experiments that produced property-based axioms in the thesis
CITED_EXPERIMENTS = [
    "experiment3_amd_genes.conf",
    "experiment6_vegf_inhibitors.conf",
    "experiment8_wetamd_drugs.conf",
    "experiment9_amd_biomarkers.conf",
    "experiment10_risk_factors.conf",
    "experiment12_vegf_ELTL.conf",
    "experiment15_dryamd_treatments.conf",
    "experiment16_diagnosable_diseases.conf",
    "experiment17_targeted_vs_general.conf",
    "experiment19_dual_mechanism_ELTL.conf",
    "experiment21_classlearn_Treatment.conf",
    "experiment22_classlearn_Gene.conf",
    "experiment23_posonly_antivegf.conf",
    "experiment24_missing_inhibits.conf",
    "experiment25_missing_assoc.conf",
]


def patch_conf(conf_path: Path, new_owl: str) -> Path:
    """Copy conf file into a _rerun version with ks.fileName updated."""
    out_dir = conf_path.parent / "rerun_configs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / conf_path.name

    content = conf_path.read_text(encoding="utf-8")
    # Replace existing ks.fileName = "..." with the new path
    patched = re.sub(
        r'ks\.fileName\s*=\s*"[^"]*"',
        f'ks.fileName = "{new_owl}"',
        content,
    )
    out_path.write_text(patched, encoding="utf-8")
    return out_path


def run_one(conf_path: Path, jar: str, output_dir: Path) -> tuple[bool, str]:
    """Run DL-Learner on one patched config; capture stdout+stderr.
    `jar` may be either a real jar path or a CLI launcher (cli.bat / cli)."""
    log_path = output_dir / f"{conf_path.stem}.log"
    # If the launcher ends with .bat or has no extension (unix cli wrapper),
    # call it directly; otherwise call as `java -jar`.
    jar_str = str(jar)
    if jar_str.lower().endswith(".bat") or jar_str.lower().endswith(".sh") \
            or (not jar_str.lower().endswith(".jar")):
        cmd = [jar_str, str(conf_path)]
        use_shell = jar_str.lower().endswith(".bat")
    else:
        cmd = ["java", "-jar", jar_str, str(conf_path)]
        use_shell = False

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, shell=use_shell,
        )
        output = result.stdout + "\n--- STDERR ---\n" + result.stderr
        log_path.write_text(output, encoding="utf-8")
        # Extract the solutions section — everything from "solutions:" until
        # the first empty line or "--- STDERR ---" marker.
        match = re.search(r"solutions:\s*\n(.*?)(?=\n\n|--- STDERR|\Z)",
                           output, re.DOTALL)
        if not match:
            # Fallback: "more accurate" lines are what DL-Learner logs
            # during search, they often contain the best result.
            lines = re.findall(r"more accurate .*?class expression found.*?:\s*.*",
                                output)
            summary = "\n".join(lines[-5:]) if lines else "(no solutions found)"
        else:
            summary = match.group(1).strip()
        return True, summary[:2000]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (>300s)"
    except Exception as e:
        return False, f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owl", required=True,
                        help="Path to the target OWL file (relative to project root)")
    parser.add_argument("--dllearner-jar", default="dllearner-1.5.0/bin/cli",
                        help="Path to the DL-Learner CLI jar/script")
    parser.add_argument("--output-dir", default="evaluation/dl-learner/results_rerun",
                        help="Where to save logs and summary")
    parser.add_argument("--conf-dir", default="evaluation/dl-learner",
                        help="Directory containing the .conf files")
    args = parser.parse_args()

    conf_dir = Path(args.conf_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # DL-Learner reads ks.fileName relative to the .conf location, so we
    # need a path that is correct from evaluation/dl-learner/rerun_configs/
    owl_path_for_conf = f"../../../{args.owl}"

    summary_lines = [
        "# DL-Learner rerun summary",
        f"OWL: {args.owl}",
        f"Experiments: {len(CITED_EXPERIMENTS)}",
        "",
    ]

    for name in CITED_EXPERIMENTS:
        src = conf_dir / name
        if not src.exists():
            print(f"[SKIP] {name} not found")
            summary_lines.append(f"## {name}\n\nSKIPPED: file missing\n")
            continue

        patched = patch_conf(src, owl_path_for_conf)
        print(f"[RUN] {name}... ", end="", flush=True)
        ok, summary = run_one(patched, args.dllearner_jar, output_dir)
        status = "OK" if ok else "FAIL"
        print(status)
        summary_lines.append(f"## {name}\n\nStatus: {status}\n\n```\n{summary}\n```\n")

    (output_dir / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"\nSummary: {output_dir / 'SUMMARY.md'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
