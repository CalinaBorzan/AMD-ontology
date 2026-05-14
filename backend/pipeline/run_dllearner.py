import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DLLEARNER_DIR = PROJECT_ROOT / "dllearner-1.5.0"
CONFIGS_DIR = PROJECT_ROOT / "evaluation" / "dl-learner"


def list_experiments() -> list[dict]:
    out = []
    for p in sorted(CONFIGS_DIR.glob("experiment*.conf")):
        if "rerun_configs" in str(p):
            continue
        text = p.read_text(encoding="utf-8")
        m = re.search(r"\*\s*(?:DL-Learner\s+)?Experiment\s+\d+:\s*(.+?)\n", text)
        title = m.group(1).strip() if m else p.stem
        out.append({"name": p.stem, "title": title, "path": str(p)})
    return out


def run_experiment(experiment_name: str, owl_path: str | None = None,
                    timeout: int = 180) -> dict:
    src_conf = CONFIGS_DIR / f"{experiment_name}.conf"
    if not src_conf.exists():
        return {"error": f"experiment '{experiment_name}' not found"}

    if owl_path:
        rel_owl = f"../../../{owl_path}"
        rerun_dir = CONFIGS_DIR / "rerun_configs"
        rerun_dir.mkdir(exist_ok=True)
        out_conf = rerun_dir / f"{experiment_name}.conf"
        text = src_conf.read_text(encoding="utf-8")
        text = re.sub(r'ks\.fileName\s*=\s*"[^"]*"',
                       f'ks.fileName = "{rel_owl}"', text)
        out_conf.write_text(text, encoding="utf-8")
        conf_path = out_conf
    else:
        conf_path = src_conf

    import sys as _sys
    cli = DLLEARNER_DIR / "bin" / ("cli.bat" if _sys.platform == "win32" else "cli")
    if not cli.exists():
        return {"error": f"DL-Learner CLI not found at {cli}"}

    try:
        r = subprocess.run(
            [str(cli), str(conf_path)],
            capture_output=True, text=True, timeout=timeout,
            shell=(_sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s", "experiment": experiment_name}
    except Exception as e:
        return {"error": str(e), "experiment": experiment_name}

    output = (r.stdout or "") + "\n---STDERR---\n" + (r.stderr or "")

    solutions = []
    sols_match = re.search(r"solutions:\s*\n(.+?)(?=\n\n|\Z|---STDERR)",
                            output, re.DOTALL)
    if sols_match:
        for line in sols_match.group(1).splitlines():
            sm = re.match(r"\s*\d+:\s*(.+?)\s*\(.*?(?:pred\.\s*acc\.?:\s*([\d.]+%))?.*?(?:F-measure:\s*([\d.]+%))?",
                           line)
            if sm:
                expr = sm.group(1).strip()
                solutions.append({
                    "expression": expr,
                    "pred_acc": sm.group(2) or "",
                    "f_measure": sm.group(3) or "",
                })

    return {
        "experiment": experiment_name,
        "owl_path": owl_path,
        "solutions": solutions[:10],
        "raw_output": output[-3000:],
        "error": None if solutions else "no solutions parsed",
    }
