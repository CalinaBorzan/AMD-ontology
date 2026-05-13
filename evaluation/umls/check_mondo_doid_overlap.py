import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("UMLS_API_KEY")
UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"
OLS_BASE = "https://www.ebi.ac.uk/ols4/api"


def get_atoms(cui: str) -> list[dict]:
    url = f"{UMLS_BASE}/content/current/CUI/{cui}/atoms"
    try:
        resp = requests.get(url, params={"apiKey": API_KEY, "pageSize": 100}, timeout=15)
        if resp.status_code != 200:
            return []
        return resp.json().get("result", []) or []
    except Exception:
        return []


def find_codes(cui: str, target_sources: list[str]) -> dict[str, list[str]]:
    atoms = get_atoms(cui)
    found: dict[str, list[str]] = {src: [] for src in target_sources}
    for atom in atoms:
        root_src = atom.get("rootSource", "")
        if root_src in target_sources:
            code = atom.get("code", "")
            if code and code not in found[root_src]:
                found[root_src].append(code.split("/")[-1])
    return found


MONDO_DOID_EXPECTED_CLASSES = {"Disease", "AMD", "ChoroidalNeovascularization"}
HPO_EXPECTED_CLASSES = {"ClinicalOutcome"}


def find_in_ols(term: str, ontologies: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {ont.upper(): [] for ont in ontologies}
    try:
        resp = requests.get(
            f"{OLS_BASE}/search",
            params={
                "q": term,
                "ontology": ",".join(ontologies),
                "exact": "false",
                "rows": 5,
                "fieldList": "iri,label,ontology_name,short_form",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return found
        docs = resp.json().get("response", {}).get("docs", [])
    except Exception:
        return found

    term_lower = term.lower().replace(" ", "").replace("-", "")
    for d in docs:
        ont = d.get("ontology_name", "").upper()
        label = d.get("label", "")
        short = d.get("short_form", "")
        if ont not in found:
            continue
        label_norm = label.lower().replace(" ", "").replace("-", "")
        if term_lower in label_norm or label_norm in term_lower:
            if short and short not in found[ont]:
                found[ont].append(short)
    return found


def check_class_match(name: str, pipeline_class: str,
                       external_codes: dict[str, list[str]]) -> dict[str, str]:
    verdict: dict[str, str] = {}

    in_mondo = bool(external_codes.get("MONDO"))
    in_doid = bool(external_codes.get("DOID"))
    in_hpo = bool(external_codes.get("HPO"))
    in_msh = bool(external_codes.get("MSH"))

    if in_mondo:
        verdict["MONDO_class_match"] = (
            "MATCH" if pipeline_class in MONDO_DOID_EXPECTED_CLASSES else "MISMATCH"
        )
    if in_doid:
        verdict["DOID_class_match"] = (
            "MATCH" if pipeline_class in MONDO_DOID_EXPECTED_CLASSES else "MISMATCH"
        )
    if in_hpo:
        verdict["HPO_class_match"] = (
            "MATCH" if pipeline_class in HPO_EXPECTED_CLASSES else "MISMATCH"
        )
    if in_msh:
        verdict["MSH_present"] = "MATCH"
    return verdict


def main():
    p = argparse.ArgumentParser(
        description="Check overlap of our AMD ontology with MONDO + DOID via UMLS atoms.")
    p.add_argument("--input",
                    default=str(PROJECT_ROOT / "results" / "evaluation" / "after_demote" / "umls_details_both.json"))
    p.add_argument("--output",
                    default=str(PROJECT_ROOT / "results" / "evaluation" / "mondo_doid_overlap.json"))
    p.add_argument("--sources", default="HPO,MSH",
                    help="UMLS source vocabularies to check via UMLS atoms")
    p.add_argument("--ols-ontologies", default="mondo,doid",
                    help="OBO ontologies to check via OLS API")
    p.add_argument("--sleep", type=float, default=0.1)
    args = p.parse_args()

    if not API_KEY:
        print("ERROR: UMLS_API_KEY not set in .env")
        sys.exit(1)

    sources = [s.strip() for s in args.sources.split(",")]
    ols_ontologies = [s.strip() for s in args.ols_ontologies.split(",") if s.strip()]
    all_keys = sources + [o.upper() for o in ols_ontologies]

    entities = json.loads(Path(args.input).read_text(encoding="utf-8"))
    entities = [e for e in entities if e.get("cui")]
    print(f"Checking {len(entities)} entities — UMLS: {sources}, OLS: {ols_ontologies}")

    results = []
    for i, e in enumerate(entities, 1):
        cuis = e["cui"].split(",") if isinstance(e["cui"], str) else [e["cui"]]
        merged: dict[str, list[str]] = {k: [] for k in all_keys}

        for cui in cuis:
            cui = cui.strip()
            if not cui:
                continue
            codes = find_codes(cui, sources)
            for src, vals in codes.items():
                for v in vals:
                    if v not in merged[src]:
                        merged[src].append(v)
            if args.sleep:
                time.sleep(args.sleep)

        if ols_ontologies:
            ols_codes = find_in_ols(e["name"], ols_ontologies)
            for src, vals in ols_codes.items():
                for v in vals:
                    if v not in merged[src]:
                        merged[src].append(v)
            if args.sleep:
                time.sleep(args.sleep)

        any_match = any(len(v) > 0 for v in merged.values())
        class_verdicts = check_class_match(e["name"], e.get("pipeline_class", ""), merged)
        results.append({
            "name": e["name"],
            "pipeline_class": e.get("pipeline_class"),
            "cuis": cuis,
            "external_codes": merged,
            "in_external_kg": any_match,
            "class_match": class_verdicts,
        })
        flag = "[+]" if any_match else "[-]"
        cv_str = " | ".join(f"{k}={v}" for k, v in class_verdicts.items())
        print(f"[{i}/{len(entities)}] {flag} {e['name']} ({e.get('pipeline_class')}): " +
              ", ".join(f"{src}={len(v)}" for src, v in merged.items() if v) +
              (f"   {cv_str}" if cv_str else ""))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    summary: dict[str, int] = {k: 0 for k in all_keys}
    for r in results:
        for src, codes in r["external_codes"].items():
            if codes:
                summary[src] += 1
    total = len(results)
    in_any = sum(1 for r in results if r["in_external_kg"])

    print(f"\n=== OVERLAP SUMMARY (existence) ===")
    print(f"  Total entities: {total}")
    for src in all_keys:
        n = summary[src]
        print(f"  {src:8s} : {n:3d} ({n / total:.0%})")
    print(f"  In ANY: {in_any} ({in_any / total:.0%})")
    print(f"  Not in any external KG: {total - in_any}")

    print(f"\n=== CLASS MATCH SUMMARY ===")
    for kg in ["MONDO", "DOID", "HPO"]:
        key = f"{kg}_class_match"
        match = sum(1 for r in results if r["class_match"].get(key) == "MATCH")
        mismatch = sum(1 for r in results if r["class_match"].get(key) == "MISMATCH")
        present = match + mismatch
        if present:
            print(f"  {kg:6s}: {match}/{present} class-match ({match / present:.0%}) "
                    f"of those present in {kg}")

    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
