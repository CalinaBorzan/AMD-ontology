"""
Validate pipeline ontology entity classifications against UMLS.

For each entity in the ontology (instance or class), query UMLS Metathesaurus
to retrieve its CUI and semantic types, then check whether the pipeline's
class assignment is consistent with UMLS semantic types.

Reads:
  .env → UMLS_API_KEY
  results/amd/final/amd_ontology_final.json

Writes:
  results/evaluation/umls_report.md  (human-readable summary)
  results/evaluation/umls_details.json  (per-entity CUI + semantic types)

Usage:
    python backend/tools/run_umls_validation.py
    python backend/tools/run_umls_validation.py --ontology ontology/AMD_v4.owl
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from collections import defaultdict

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("UMLS_API_KEY")
UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"
DEFAULT_INPUT = PROJECT_ROOT / "results" / "amd" / "final" / "amd_ontology_final.json"
OUTPUT_DIR = PROJECT_ROOT / "results" / "evaluation"

# Canonical root classes. Any class in the schema that is a subclass of one
# of these (directly or transitively) is normalized to that root for UMLS
# comparison. The seven roots are the same across all ontology versions.
CANONICAL_ROOTS = {"Disease", "Treatment", "Biomarker", "DiagnosticMethod",
                    "RiskFactor", "ClinicalOutcome", "MolecularTarget"}


def build_root_map(schema_classes: dict) -> dict:
    """Walk the `subclasses` structure of the schema to find each class's
    topmost ancestor that is a canonical root. Returns {class_name: root}.

    This replaces per-subclass hardcoded mappings (e.g. "Gene → Biomarker")
    with schema-driven normalization: any class the schema declares as a
    subclass of Biomarker is automatically normalized to Biomarker, even
    if we've never heard of it (SurgicalTherapy, GeneticBiomarker, etc.)."""
    parent_of = {}
    for pname, pinfo in schema_classes.items():
        if not isinstance(pinfo, dict):
            continue
        for child in pinfo.get("subclasses", []):
            parent_of[child] = pname

    def walk(name, seen=None):
        if seen is None:
            seen = set()
        if name in CANONICAL_ROOTS:
            return name
        if name in seen or name not in schema_classes:
            return name
        seen.add(name)
        parent = parent_of.get(name)
        if parent is None:
            return name  # top-level class that's not one of our canonical roots
        return walk(parent, seen)

    return {cname: walk(cname) for cname in schema_classes}


# Populated by main() after loading the schema; used inside resolve_entity.
ROOT_MAP: dict = {}


# ── UMLS Semantic Type → Pipeline Class mapping ────────────────────────────
# Source: https://www.nlm.nih.gov/research/umls/META3_current_semantic_types.html
# Each semantic type is grouped by our 7 root classes. Types not listed are
# unmapped (reported but not used for validation).
SEMTYPE_TO_CLASS = {
    # ---- Disease ----
    "T047": "Disease",  # Disease or Syndrome
    "T191": "Disease",  # Neoplastic Process
    "T046": "Disease",  # Pathologic Function
    "T049": "Disease",  # Cell or Molecular Dysfunction
    "T019": "Disease",  # Congenital Abnormality
    "T020": "Disease",  # Acquired Abnormality
    "T033": "Disease",  # Finding (sometimes disease)
    "T048": "Disease",  # Mental or Behavioral Dysfunction
    "T190": "Disease",  # Anatomical Abnormality
    "T037": "Disease",  # Injury or Poisoning

    # ---- Treatment ----
    "T121": "Treatment",  # Pharmacologic Substance
    "T200": "Treatment",  # Clinical Drug
    "T195": "Treatment",  # Antibiotic
    "T061": "Treatment",  # Therapeutic or Preventive Procedure
    "T129": "Treatment",  # Immunologic Factor (often therapeutic)
    "T131": "Treatment",  # Hazardous or Poisonous Substance (rare, context)

    # ---- Biomarker (includes Gene subclass) ----
    "T028": "Biomarker",  # Gene or Genome
    "T086": "Biomarker",  # Nucleotide Sequence
    "T085": "Biomarker",  # Molecular Sequence
    "T123": "Biomarker",  # Biologically Active Substance (can also be MolecularTarget)
    "T116": "Biomarker",  # Amino Acid, Peptide, or Protein (can also be MolecularTarget)
    "T114": "Biomarker",  # Nucleic Acid, Nucleoside, or Nucleotide
    "T125": "Biomarker",  # Hormone
    "T043": "Biomarker",  # Cell Function
    "T034": "Biomarker",  # Laboratory or Test Result

    # ---- DiagnosticMethod ----
    "T060": "DiagnosticMethod",  # Diagnostic Procedure
    "T059": "DiagnosticMethod",  # Laboratory Procedure
    "T130": "DiagnosticMethod",  # Indicator, Reagent, or Diagnostic Aid

    # ---- ClinicalOutcome ----
    "T184": "ClinicalOutcome",  # Sign or Symptom
    "T033_outcome": "ClinicalOutcome",  # Finding (context-dependent)
    "T046_outcome": "ClinicalOutcome",  # Pathologic Function as outcome
    "T169": "ClinicalOutcome",  # Functional Concept
    "T067": "ClinicalOutcome",  # Phenomenon or Process (rare)

    # ---- RiskFactor ----
    "T054": "RiskFactor",  # Social Behavior
    "T055": "RiskFactor",  # Individual Behavior
    "T098": "RiskFactor",  # Population Group
    "T094": "RiskFactor",  # Professional or Occupational Group (context)
    "T080": "RiskFactor",  # Qualitative Concept (sometimes)

    # ---- MolecularTarget (overlap with Biomarker — validated via predicate context) ----
    # Same UMLS types as Biomarker; distinguished by how the pipeline uses them.
}

# Semantic types we see but don't map (anatomical structures, mental objects, etc.)
UNMAPPED_SEMTYPES = {
    "T023": "Body Part, Organ, or Organ Component",
    "T024": "Tissue",
    "T025": "Cell",
    "T026": "Cell Component",
    "T029": "Body Location or Region",
    "T030": "Body Space or Junction",
    "T031": "Body Substance",
}


# ── Method 2: UMLS Semantic Groups ─────────────────────────────────────────
# UMLS Semantic Groups is an OFFICIAL NIH/NLM grouping of the 133 semantic
# types into 15 broad categories. Source:
#   https://lhncbc.nlm.nih.gov/semanticnetwork/download/sg_v01.txt
# The TUI → Group mapping is fixed by NIH. We only map our 7 pipeline
# classes to these official groups — much less hardcoding than TUI-based
# validation.
TUI_TO_GROUP = {
    # Activities & Behaviors
    "T052": "ACTI", "T053": "ACTI", "T054": "ACTI", "T055": "ACTI",
    "T056": "ACTI", "T064": "ACTI", "T065": "ACTI", "T066": "ACTI",
    "T057": "ACTI",
    # Anatomy
    "T017": "ANAT", "T029": "ANAT", "T023": "ANAT", "T030": "ANAT",
    "T031": "ANAT", "T022": "ANAT", "T025": "ANAT", "T026": "ANAT",
    "T018": "ANAT", "T021": "ANAT", "T024": "ANAT",
    # Chemicals & Drugs
    "T116": "CHEM", "T195": "CHEM", "T123": "CHEM", "T122": "CHEM",
    "T103": "CHEM", "T120": "CHEM", "T104": "CHEM", "T200": "CHEM",
    "T111": "CHEM", "T196": "CHEM", "T126": "CHEM", "T131": "CHEM",
    "T125": "CHEM", "T129": "CHEM", "T130": "CHEM", "T197": "CHEM",
    "T114": "CHEM", "T109": "CHEM", "T121": "CHEM", "T192": "CHEM",
    "T127": "CHEM",
    # Concepts & Ideas
    "T185": "CONC", "T077": "CONC", "T169": "CONC", "T102": "CONC",
    "T078": "CONC", "T170": "CONC", "T171": "CONC", "T080": "CONC",
    "T081": "CONC", "T089": "CONC", "T082": "CONC", "T079": "CONC",
    # Devices
    "T203": "DEVI", "T074": "DEVI", "T075": "DEVI",
    # Disorders
    "T020": "DISO", "T190": "DISO", "T049": "DISO", "T019": "DISO",
    "T047": "DISO", "T050": "DISO", "T033": "DISO", "T037": "DISO",
    "T048": "DISO", "T191": "DISO", "T046": "DISO", "T184": "DISO",
    # Genes & Molecular Sequences
    "T087": "GENE", "T088": "GENE", "T028": "GENE", "T085": "GENE",
    "T086": "GENE",
    # Geographic Areas
    "T083": "GEOG",
    # Living Beings
    "T100": "LIVB", "T011": "LIVB", "T008": "LIVB", "T194": "LIVB",
    "T007": "LIVB", "T012": "LIVB", "T204": "LIVB", "T099": "LIVB",
    "T013": "LIVB", "T004": "LIVB", "T096": "LIVB", "T016": "LIVB",
    "T015": "LIVB", "T001": "LIVB", "T101": "LIVB", "T002": "LIVB",
    "T098": "LIVB", "T097": "LIVB", "T014": "LIVB", "T010": "LIVB",
    "T005": "LIVB", "T168": "LIVB",
    # Objects
    "T071": "OBJC", "T073": "OBJC", "T072": "OBJC", "T167": "OBJC",
    # Occupations
    "T091": "OCCU", "T090": "OCCU",
    # Organizations
    "T093": "ORGA", "T092": "ORGA", "T094": "ORGA", "T095": "ORGA",
    # Phenomena
    "T038": "PHEN", "T069": "PHEN", "T068": "PHEN", "T034": "PHEN",
    "T070": "PHEN", "T067": "PHEN",
    # Physiology
    "T043": "PHYS", "T201": "PHYS", "T045": "PHYS", "T041": "PHYS",
    "T044": "PHYS", "T032": "PHYS", "T040": "PHYS", "T042": "PHYS",
    "T039": "PHYS",
    # Procedures
    "T060": "PROC", "T058": "PROC", "T059": "PROC", "T063": "PROC",
    "T062": "PROC", "T061": "PROC",
}

# Our 7 pipeline classes → expected UMLS Semantic Groups.
# The only hand-curated mapping: 7 classes × 1-3 groups each.
CLASS_TO_GROUPS = {
    "Disease":          {"DISO"},
    "Treatment":        {"CHEM", "PROC"},
    "Biomarker":        {"GENE", "CHEM", "PHYS"},
    "DiagnosticMethod": {"PROC", "DEVI"},
    "RiskFactor":       {"ACTI", "LIVB"},
    "ClinicalOutcome":  {"DISO", "PHEN"},
    "MolecularTarget":  {"CHEM", "GENE"},
}


# ── UMLS REST client ────────────────────────────────────────────────────────

def umls_search(term: str, api_key: str, search_type: str = "words") -> list[dict]:
    """Search UMLS for a term, return top CUI matches."""
    url = f"{UMLS_BASE}/search/current"
    params = {
        "apiKey": api_key,
        "string": term,
        "searchType": search_type,
        "pageSize": 5,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("result", {}).get("results", [])
    except Exception:
        return []


def umls_cui_details(cui: str, api_key: str) -> dict:
    """Fetch CUI details including semantic types."""
    url = f"{UMLS_BASE}/content/current/CUI/{cui}"
    params = {"apiKey": api_key}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return {}
        return resp.json().get("result", {})
    except Exception:
        return {}


def get_semantic_types(cui: str, api_key: str) -> list[str]:
    """Get the TUI (semantic type IDs) for a CUI."""
    details = umls_cui_details(cui, api_key)
    if not details:
        return []
    semtypes = details.get("semanticTypes", [])
    tuis = []
    for st in semtypes:
        # semanticType URI like .../semantic-network/current/TUI/T121
        uri = st.get("uri", "")
        if "/TUI/" in uri:
            tui = uri.split("/TUI/")[-1]
            tuis.append(tui)
    return tuis


def classify_by_semgroups(tuis: list, pipeline_class: str) -> dict:
    """Classify an entity using UMLS official Semantic Groups.
    Looks up each TUI → Semantic Group, then checks whether any group
    matches the set declared in CLASS_TO_GROUPS[pipeline_class].
    No additional API calls needed — reuses TUIs retrieved earlier."""
    # Map each TUI to its official UMLS Semantic Group
    groups = sorted({TUI_TO_GROUP[t] for t in tuis if t in TUI_TO_GROUP})

    # Normalize pipeline class to its canonical root via the schema's own
    # subclasses hierarchy (ROOT_MAP built once from the loaded schema).
    compare_cls = ROOT_MAP.get(pipeline_class, pipeline_class)

    expected = CLASS_TO_GROUPS.get(compare_cls, set())

    if not groups:
        verdict = "NO_GROUP"  # entity has no TUI that maps to a semantic group
    elif set(groups) & expected:
        verdict = "MATCH"
    else:
        verdict = "MISMATCH"

    return {"method": "semgroup", "groups": groups,
            "expected_groups": sorted(expected),
            "mapped_classes": [compare_cls] if verdict == "MATCH" else [],
            "verdict": verdict}


# ── Validation logic ────────────────────────────────────────────────────────

def resolve_entity(name: str, pipeline_class: str, api_key: str,
                    method: str = "tui") -> dict:
    """Look up an entity in UMLS and return classification verdict(s).
    method = 'tui' | 'semgroup' | 'both'
    """
    # Try exact match first, then word search
    results = umls_search(name, api_key, search_type="exact")
    if not results or results[0].get("ui") == "NONE":
        results = umls_search(name, api_key, search_type="words")

    # Fallback: if name contains CamelCase (e.g. "DryAMD"), try splitting
    # into separate words ("Dry AMD") — UMLS indexes terms with spaces.
    if not results or results[0].get("ui") == "NONE":
        import re as _re
        # Insert a space before any uppercase letter that follows a lowercase
        # letter or an uppercase sequence of 2+ letters: "DryAMD" -> "Dry AMD"
        split_name = _re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
        split_name = _re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", split_name)
        if split_name != name:
            results = umls_search(split_name, api_key, search_type="words")

    if not results or results[0].get("ui") == "NONE":
        base = {"name": name, "pipeline_class": pipeline_class,
                "cui": None, "umls_name": None}
        empty_tui  = {"semtypes": [], "mapped_classes": [], "verdict": "NOT_FOUND"}
        empty_grp  = {"groups": [], "expected_groups": [],
                      "mapped_classes": [], "verdict": "NOT_FOUND"}
        if method == "both":
            return {**base, "tui_result": empty_tui, "semgroup_result": empty_grp}
        return {**base, **(empty_grp if method == "semgroup" else empty_tui)}


    candidates = sorted(
        [r for r in results if r.get("ui") and r.get("ui") != "NONE"],
        key=lambda r: r.get("ui", "")
    )

    all_cuis: list[str] = []
    all_umls_names: list[str] = []
    tuis_set: set[str] = set()
    for cand in candidates:
        cand_cui = cand.get("ui")
        all_cuis.append(cand_cui)
        all_umls_names.append(cand.get("name", ""))
        tuis_set.update(get_semantic_types(cand_cui, api_key))

    tuis = sorted(tuis_set)

    cui = ",".join(all_cuis) if len(all_cuis) > 1 else (all_cuis[0] if all_cuis else None)
    umls_name = " | ".join(all_umls_names) if len(all_umls_names) > 1 else (all_umls_names[0] if all_umls_names else None)

    base = {"name": name, "pipeline_class": pipeline_class,
            "cui": cui, "umls_name": umls_name,
            "candidate_cuis": all_cuis}

    def _tui_verdict():
        mapped = sorted({SEMTYPE_TO_CLASS[t] for t in tuis if t in SEMTYPE_TO_CLASS})
        # Normalize via schema-derived root map (auto-walk subclasses)
        compare_cls = ROOT_MAP.get(pipeline_class, pipeline_class)
        # MolecularTarget shares UMLS semantic types with Biomarker in the
        # TUI mapping, so we treat them as equivalent for TUI validation.
        if compare_cls == "MolecularTarget":
            compare_cls = "Biomarker"
        if not mapped:
            verdict = "UMLS_UNMAPPED"
        elif compare_cls in mapped:
            verdict = "MATCH"
        else:
            verdict = "MISMATCH"
        return {"semtypes": tuis, "mapped_classes": mapped, "verdict": verdict}

    def _semgroup_verdict():
        return classify_by_semgroups(tuis, pipeline_class)

    if method == "tui":
        return {**base, **_tui_verdict()}
    elif method == "semgroup":
        r = _semgroup_verdict()
        r["semtypes"] = tuis  # keep TUIs for the report
        return {**base, **r}
    else:  # both
        return {**base,
                "tui_result":      _tui_verdict(),
                "semgroup_result": _semgroup_verdict()}


def collect_all_entities(schema: dict) -> list[tuple[str, str]]:
    """Return [(entity_name, pipeline_class), ...] for every class/instance in the ontology."""
    entities = []
    seen = set()
    for cls_name, cls_info in schema.get("classes", {}).items():
        if cls_name not in seen:
            entities.append((cls_name, cls_name))
            seen.add(cls_name)
        for inst in cls_info.get("instances", []):
            if inst not in seen:
                entities.append((inst, cls_name))
                seen.add(inst)
    return entities


# ── Reporting ───────────────────────────────────────────────────────────────

def _verdict_summary(results, key=None):
    """Aggregate verdict counts. If key is given, look in results[i][key]['verdict']."""
    counts = {"MATCH": 0, "MISMATCH": 0, "UMLS_UNMAPPED": 0, "NOT_FOUND": 0, "NO_ANCHOR": 0}
    mismatches, unmapped, notfound = [], [], []
    for r in results:
        v = r[key]["verdict"] if key else r.get("verdict", "?")
        counts[v] = counts.get(v, 0) + 1
        if v == "MISMATCH":
            mismatches.append(r)
        elif v in ("UMLS_UNMAPPED", "NO_ANCHOR"):
            unmapped.append(r)
        elif v == "NOT_FOUND":
            notfound.append(r)
    n_match = counts.get("MATCH", 0)
    n_mm    = counts.get("MISMATCH", 0)
    n_eval  = n_match + n_mm
    precision = n_match / n_eval if n_eval else 0.0
    return counts, precision, mismatches, unmapped, notfound


def render_report(results: list[dict]) -> str:
    total = len(results)
    by_verdict = defaultdict(list)
    for r in results:
        by_verdict[r["verdict"]].append(r)

    n_match = len(by_verdict.get("MATCH", []))
    n_mismatch = len(by_verdict.get("MISMATCH", []))
    n_unmapped = len(by_verdict.get("UMLS_UNMAPPED", []))
    n_notfound = len(by_verdict.get("NOT_FOUND", []))
    n_evaluable = n_match + n_mismatch
    precision = n_match / n_evaluable if n_evaluable else 0.0

    lines = [
        "# UMLS Semantic Type Validation",
        "",
        f"Entities validated: {total}",
        "",
        f"- **MATCH** (pipeline class consistent with UMLS): {n_match}",
        f"- **MISMATCH** (pipeline class differs from UMLS): {n_mismatch}",
        f"- **UMLS_UNMAPPED** (found in UMLS but semantic type outside our mapping): {n_unmapped}",
        f"- **NOT_FOUND** (not in UMLS / Metathesaurus): {n_notfound}",
        "",
        f"**Classification precision** (MATCH / (MATCH + MISMATCH)) = "
        f"**{precision:.2%}** ({n_match}/{n_evaluable})",
        "",
    ]

    # Per-class breakdown
    lines.append("## Precision per pipeline class")
    lines.append("")
    lines.append("| Class | Match | Mismatch | Precision |")
    lines.append("|-------|------:|---------:|----------:|")
    per_class = defaultdict(lambda: {"match": 0, "mismatch": 0})
    for r in results:
        if r["verdict"] in ("MATCH", "MISMATCH"):
            per_class[r["pipeline_class"]][r["verdict"].lower()] += 1
    for cls in sorted(per_class):
        m = per_class[cls]["match"]
        mm = per_class[cls]["mismatch"]
        p = m / (m + mm) if (m + mm) else 0.0
        lines.append(f"| {cls} | {m} | {mm} | {p:.2%} |")
    lines.append("")

    # Mismatches (likely pipeline errors worth reviewing)
    lines.append("## Mismatches — pipeline class differs from UMLS")
    lines.append("")
    if not by_verdict.get("MISMATCH"):
        lines.append("_none_")
    else:
        for r in by_verdict["MISMATCH"]:
            lines.append(f"- **{r['name']}** → pipeline says `{r['pipeline_class']}`, "
                         f"UMLS semantic types {r['semtypes']} map to {r['mapped_classes']} "
                         f"(CUI: {r['cui']})")
    lines.append("")

    # Not found
    lines.append("## Not in UMLS")
    lines.append("")
    if not by_verdict.get("NOT_FOUND"):
        lines.append("_all entities found_")
    else:
        for r in by_verdict["NOT_FOUND"]:
            lines.append(f"- `{r['name']}` (pipeline class: {r['pipeline_class']})")
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append("- Queried UMLS Metathesaurus REST API for each class and instance in the ontology.")
    lines.append("- For each entity, retrieved the best-match CUI and its semantic type(s) (TUI).")
    lines.append("- Mapped UMLS semantic types to pipeline classes using a manually-curated table "
                 "(see SEMTYPE_TO_CLASS in `backend/tools/run_umls_validation.py`). The mapping covers "
                 "~30 semantic types across 7 pipeline classes; mappings follow standard biomedical "
                 "ontology conventions.")
    lines.append("- Pipeline subclasses are aggregated to their root for comparison "
                 "(AntiVEGFTherapy → Treatment, Gene → Biomarker, AMD subtypes → Disease, "
                 "MolecularTarget treated as Biomarker-equivalent).")
    lines.append("")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def render_comparison_report(results: list[dict]) -> str:
    """Report comparing TUI-based vs Semantic Group methods side-by-side."""
    tui_counts, tui_p, tui_mm, _, _ = _verdict_summary(results, key="tui_result")
    sg_counts,  sg_p,  sg_mm,  _, _ = _verdict_summary(results, key="semgroup_result")

    lines = [
        "# UMLS Validation — Method Comparison (Direct TUI vs NIH Semantic Groups)",
        "",
        f"Entities validated: {len(results)}",
        "",
        "## Overview",
        "",
        "| Method | MATCH | MISMATCH | Other | Precision |",
        "|--------|------:|---------:|------:|----------:|",
    ]
    def _other(counts):
        return sum(counts.get(k, 0) for k in
                   ("UMLS_UNMAPPED", "NO_GROUP", "NO_ANCHOR", "NOT_FOUND"))
    lines.append(f"| **TUI-based** (30+ semantic type mappings, hand-curated) | "
                 f"{tui_counts['MATCH']} | {tui_counts['MISMATCH']} | "
                 f"{_other(tui_counts)} | **{tui_p:.2%}** |")
    lines.append(f"| **Semantic Groups** (NIH official 15 groups; 7 classes × 1-3) | "
                 f"{sg_counts['MATCH']} | {sg_counts['MISMATCH']} | "
                 f"{_other(sg_counts)} | **{sg_p:.2%}** |")
    lines.append("")

    # Agreement / disagreement matrix
    both_match = sum(1 for r in results
                     if r["tui_result"]["verdict"] == "MATCH"
                     and r["semgroup_result"]["verdict"] == "MATCH")
    both_mismatch = sum(1 for r in results
                        if r["tui_result"]["verdict"] == "MISMATCH"
                        and r["semgroup_result"]["verdict"] == "MISMATCH")
    disagree = [r for r in results
                if r["tui_result"]["verdict"] != r["semgroup_result"]["verdict"]
                and r["tui_result"]["verdict"] in ("MATCH", "MISMATCH")
                and r["semgroup_result"]["verdict"] in ("MATCH", "MISMATCH")]

    lines.append("## Method Agreement")
    lines.append("")
    lines.append(f"- Both methods MATCH: {both_match}")
    lines.append(f"- Both methods MISMATCH: {both_mismatch}")
    lines.append(f"- Methods DISAGREE on evaluable entities: {len(disagree)}")
    lines.append("")

    if disagree:
        lines.append("### Entities where methods disagree")
        lines.append("")
        for r in disagree[:30]:
            tv = r["tui_result"]["verdict"]
            av = r["semgroup_result"]["verdict"]
            lines.append(f"- `{r['name']}` (pipeline: {r['pipeline_class']}, "
                         f"UMLS CUI: {r['cui']})")
            lines.append(f"    - TUI method: **{tv}** — semtypes "
                         f"{r['tui_result']['semtypes']} → "
                         f"{r['tui_result']['mapped_classes']}")
            lines.append(f"    - Semantic Group method: **{av}** — groups "
                         f"{r['semgroup_result'].get('groups', [])} vs expected "
                         f"{r['semgroup_result'].get('expected_groups', [])}")
        if len(disagree) > 30:
            lines.append(f"- ... and {len(disagree) - 30} more")
        lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append("- **TUI method** maps ~30 UMLS semantic type IDs directly to pipeline "
                 "classes. Fast, simple, but requires maintaining a mapping table.")
    lines.append("- **Semantic Group method** uses the 15 official UMLS Semantic "
                 "Groups (fixed by NIH; TUI → Group mapping is authoritative and "
                 "published at https://lhncbc.nlm.nih.gov/semanticnetwork/download/sg_v01.txt). "
                 "Only 7 pipeline classes × 1-3 groups each are hand-mapped. "
                 "No extra API calls — reuses the TUIs already fetched.")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology", default=str(DEFAULT_INPUT),
                        help="Path to ontology JSON")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--sleep", type=float, default=0.1,
                        help="Sleep between UMLS calls (seconds) to avoid rate limit")
    parser.add_argument("--method", choices=["tui", "semgroup", "both"],
                        default="tui",
                        help="Classification method: tui (direct semantic-type "
                             "mapping, 30+ hand-curated entries), semgroup "
                             "(NIH official UMLS Semantic Groups, 7 classes "
                             "× 1-3 groups), or both (writes comparison report)")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: UMLS_API_KEY not found in .env file.")
        print("Get one at https://uts.nlm.nih.gov/uts/signup-login and add to .env:")
        print("  UMLS_API_KEY=your-key-here")
        sys.exit(1)

    print(f"Loading ontology from {args.ontology}")
    with open(args.ontology, encoding="utf-8") as f:
        schema = json.load(f)

    # Build the schema-driven root map (no hardcoded subclass mappings)
    global ROOT_MAP
    ROOT_MAP = build_root_map(schema.get("classes", {}))
    non_canonical = [k for k, v in ROOT_MAP.items() if v == k and k not in CANONICAL_ROOTS]
    normalized = [k for k, v in ROOT_MAP.items() if v != k]
    print(f"  Root map built: {len(ROOT_MAP)} classes, "
          f"{len(normalized)} normalized to a canonical root, "
          f"{len(non_canonical)} unmapped top-level (e.g. {non_canonical[:3]})")

    entities = collect_all_entities(schema)
    print(f"  {len(entities)} entities to validate")
    print()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, (name, cls) in enumerate(entities, 1):
        print(f"[{i}/{len(entities)}] {name} ({cls})...", end=" ", flush=True)
        res = resolve_entity(name, cls, API_KEY, method=args.method)
        results.append(res)
        if args.method == "both":
            print(f"TUI={res['tui_result']['verdict']} "
                  f"SEMGROUP={res['semgroup_result']['verdict']}")
        else:
            print(res["verdict"],
                  f"CUI={res['cui']}" if res["cui"] else "",
                  f"→ {res['mapped_classes']}" if res.get("mapped_classes") else "")
        time.sleep(args.sleep)

    # Save — reports depend on method
    suffix = f"_{args.method}" if args.method != "tui" else ""
    details_path = output_dir / f"umls_details{suffix}.json"
    details_path.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    if args.method == "both":
        report_path = output_dir / "umls_comparison_report.md"
        report_path.write_text(render_comparison_report(results), encoding="utf-8")
    else:
        report_path = output_dir / f"umls_report{suffix}.md"
        report_path.write_text(render_report(results), encoding="utf-8")

    # Summary
    print()
    print("=" * 60)
    print(f"Report:  {report_path}")
    print(f"Details: {details_path}")
    print()

    if args.method == "both":
        tui_c, tui_p, _, _, _ = _verdict_summary(results, key="tui_result")
        sg_c, sg_p, _, _, _ = _verdict_summary(results, key="semgroup_result")
        print("Method          | MATCH | MISMATCH | Precision")
        print(f"TUI-based       | {tui_c['MATCH']:>5} | {tui_c['MISMATCH']:>8} | {tui_p:.2%}")
        print(f"Semantic Groups | {sg_c['MATCH']:>5} | {sg_c['MISMATCH']:>8} | {sg_p:.2%}")
    else:
        counts, p, _, _, _ = _verdict_summary(results)
        print(f"MATCH:      {counts['MATCH']}")
        print(f"MISMATCH:   {counts['MISMATCH']}")
        if args.method == "semgroup":
            print(f"NO_GROUP:   {counts.get('NO_GROUP', 0)}")
        else:
            print(f"UMLS_UNMAPPED: {counts.get('UMLS_UNMAPPED', 0)}")
        print(f"NOT_FOUND:  {counts.get('NOT_FOUND', 0)}")
        print(f"\nClassification precision: {p:.2%}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
