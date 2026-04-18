"""
SCHEMA-MINERpro — Agentic 3-stage schema mining with delta-based updates.

This preserves:
  * The schema-miner 3-stage refinement principle (Stage 1 → Stage 2 → Stage 3
    with HITL checkpoints between stages).
  * The supervisor-approved architecture: ontology lives in a Python dict,
    LLM sees only a compact summary in system prompt + the abstract in user
    prompt, LLM uses tools to modify the dict, LLM never sees or reproduces
    the full JSON.

Key difference from run_agentic_extraction.py:
  * Instead of many per-entity tool calls (check_exists, add_class,
    add_instance, add_relationship) per abstract, the agent makes ONE
    `propose_delta` call per abstract. The delta is a structured JSON
    describing all the changes the abstract suggests.
  * This forces HOLISTIC per-abstract reasoning (the LLM must compose a
    coherent delta in one shot), which is what restores the structural
    coherence that fragmented tool calls destroy.

Usage:
  python run_schema_miner_agentic.py --provider groq --model llama-3.3-70b-versatile
  python run_schema_miner_agentic.py --provider ollama --model qwen2.5:32b
  python run_schema_miner_agentic.py --stage 3 --resume results/amd/stage-2/AMD/agentic_schema.json
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

from schema_miner.config.envConfig import EnvConfig
from schema_miner.config.processConfig import ProcessConfig
from schema_miner.prompts.schema_extraction import (
    prompt_template1,
    prompt_template2,
    prompt_template3,
)

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "schema_miner_agentic.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
DOMAIN_SPEC_PATH = PROJECT_ROOT / "data" / "stage-1" / "AMD" / "amd_domain_spec.txt"
STAGE2_ABSTRACTS_DIR = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "abstracts"
STAGE3_ABSTRACTS_DIR = PROJECT_ROOT / "data" / "stage-3" / "AMD" / "abstracts"
RESULTS_DIR = PROJECT_ROOT / "results" / "amd"

# ── The schema (lives entirely in Python) ───────────────────────────────────

SCHEMA = {
    "classes": {},
    "properties": {},
}

CURRENT_ABSTRACT = ""

_VALID_PREDICATES = {
    "treats", "inhibits", "causesOrIncreases", "diagnosedBy", "associatedWith",
    "measuredBy", "hasSymptom", "assessedBy", "indicates",
}

# Fixed property schema — domain/range definitions so deltas can add triples
# without needing to redefine properties each call.
PROPERTY_DEFINITIONS = {
    "treats":             ("Treatment",        "Disease",          "A treatment that manages a disease"),
    "inhibits":           ("Treatment",        "MolecularTarget",  "A treatment that inhibits a molecular target"),
    "causesOrIncreases":  ("RiskFactor",       "Disease",          "A risk factor that causes or increases a disease"),
    "indicates":          ("Biomarker",        "Disease",          "A biomarker that indicates a disease"),
    "diagnosedBy":        ("Disease",          "DiagnosticMethod", "A disease diagnosed via a method"),
    "hasSymptom":         ("Disease",          "ClinicalOutcome",  "A disease has a clinical symptom"),
    "measuredBy":         ("Biomarker",        "DiagnosticMethod", "A biomarker measured by a method"),
    "associatedWith":     ("GeneticBiomarker", "Disease",          "A gene associated with a disease"),
    "assessedBy":         ("ClinicalOutcome",  "DiagnosticMethod", "A clinical outcome assessed by a method"),
}


def _ensure_properties():
    """Initialize the 9 properties in the schema if missing."""
    for name, (domain, range_, desc) in PROPERTY_DEFINITIONS.items():
        if name not in SCHEMA["properties"]:
            SCHEMA["properties"][name] = {
                "domain": domain,
                "range": range_,
                "description": desc,
                "examples": [],
            }


# Root classes that the schema-miner target shape always contains.
# Pre-populated so children can always find their parent at add-time.
_CANONICAL_ROOTS = [
    ("Disease", "A medical condition affecting the human body"),
    ("Treatment", "A medical intervention used to manage or cure a disease"),
    ("Biomarker", "A measurable indicator of a biological state or condition"),
    ("DiagnosticMethod", "A procedure or test used to diagnose a disease"),
    ("RiskFactor", "A factor that increases the likelihood of developing a disease"),
    ("ClinicalOutcome", "A measurable result of a treatment or disease progression"),
]


def _ensure_root_classes():
    """Pre-populate the canonical root classes so that children added in any
    delta can always find their parent. These are the structural scaffolding
    that the schema-miner target shape specifies — not domain hardcoding,
    just the contract the prompts rely on."""
    for name, desc in _CANONICAL_ROOTS:
        if name not in SCHEMA["classes"]:
            SCHEMA["classes"][name] = {
                "description": desc,
                "subclasses": [],
                "instances": [],
            }


def _normalize(name: str) -> str:
    return name.lower().strip().replace("-", "").replace(" ", "").replace("_", "")


def _find_class(name: str) -> str | None:
    """Return the canonical class name if one matches (fuzzy)."""
    norm = _normalize(name)
    for cn in SCHEMA["classes"]:
        if _normalize(cn) == norm:
            return cn
    return None


def _find_instance(name: str) -> tuple[str, str] | None:
    """Return (class_name, instance_name) if the instance exists (fuzzy)."""
    norm = _normalize(name)
    for cn, cd in SCHEMA["classes"].items():
        if isinstance(cd, dict):
            for inst in cd.get("instances", []):
                if _normalize(inst) == norm:
                    return (cn, inst)
    return None


def _heal_orphan_parents() -> list[str]:
    """Walk every class that has a _pending_parent field and try to link it
    to its parent now that more classes may exist. Returns a list of
    "child -> parent" strings for the links that were successfully healed."""
    healed = []
    for cn, cd in list(SCHEMA["classes"].items()):
        if not isinstance(cd, dict):
            continue
        pending = cd.get("_pending_parent")
        if not pending:
            continue
        parent_canonical = _find_class(pending)
        if not parent_canonical or parent_canonical == cn:
            continue
        subs = SCHEMA["classes"][parent_canonical].get("subclasses", [])
        if cn not in subs:
            subs.append(cn)
        SCHEMA["classes"][parent_canonical]["subclasses"] = subs
        # Remove the pending marker — this class is now properly linked
        del cd["_pending_parent"]
        healed.append(f"{cn} -> {parent_canonical}")
    return healed


def compact_summary() -> str:
    """Regenerate the compact summary shown to the LLM."""
    classes = SCHEMA.get("classes", {})
    props = SCHEMA.get("properties", {})
    if not classes and not props:
        return "SCHEMA IS EMPTY. This is Stage 1 — build the initial structure."

    lines = []

    # Hierarchy: roots first, then subclasses indented
    all_subs = set()
    for v in classes.values():
        if isinstance(v, dict):
            for s in v.get("subclasses", []):
                all_subs.add(s)
    roots = [c for c in classes if c not in all_subs]

    lines.append("CLASSES:")

    def show(name, depth=1):
        data = classes.get(name, {})
        if not isinstance(data, dict):
            return
        prefix = "  " * depth
        insts = data.get("instances", [])
        inst_str = f" [{', '.join(insts)}]" if insts else ""
        lines.append(f"{prefix}{name}{inst_str}")
        for s in data.get("subclasses", []):
            show(s, depth + 1)

    for r in roots:
        show(r)

    if props:
        lines.append("\nPROPERTIES (9 fixed, do not add new ones):")
        for pn, pd in props.items():
            ex_count = len(pd.get("examples", [])) if isinstance(pd, dict) else 0
            domain = pd.get("domain", "?") if isinstance(pd, dict) else "?"
            range_ = pd.get("range", "?") if isinstance(pd, dict) else "?"
            lines.append(f"  {pn}: {domain} -> {range_} ({ex_count} examples)")

    total_inst = sum(len(v.get("instances", [])) for v in classes.values() if isinstance(v, dict))
    total_rel = sum(len(v.get("examples", [])) for v in props.values() if isinstance(v, dict))
    lines.append(f"\nSTATS: {len(classes)} classes, {total_inst} instances, {total_rel} relationships")
    return "\n".join(lines)


def save_schema(stage: str):
    stage_dir = RESULTS_DIR / stage / "AMD"
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_file = stage_dir / "agentic_schema.json"
    with open(stage_file, "w", encoding="utf-8") as f:
        json.dump(SCHEMA, f, indent=4, ensure_ascii=False)

    final_dir = RESULTS_DIR / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_file = final_dir / "amd_ontology_final.json"
    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(SCHEMA, f, indent=4, ensure_ascii=False)

    logger.info(f"  Saved to {stage_file}")


# ── THE tool: a single delta-based update per abstract ──────────────────────

@tool
def propose_delta(
    add_classes: list = None,
    add_instances: list = None,
    add_triples: list = None,
) -> str:
    """Propose a STRUCTURED delta — ALL changes this abstract suggests.

    MOST ABSTRACTS NEED ZERO NEW CLASSES. Add entities as INSTANCES.
    New classes without 2+ instances will be REJECTED.

    RELATIONSHIPS ARE THE MOST VALUABLE PART. For every entity in the
    abstract, extract ALL relationships it participates in. A good delta
    has MORE triples than instances. Use all 9 predicates:
      treats:            Drug/therapy → Disease it treats
      inhibits:          Drug → Molecular target it blocks (e.g., VEGF)
      causesOrIncreases: Risk factor → Disease it increases risk of
      indicates:         Biomarker → Disease it signals
      diagnosedBy:       Disease → Diagnostic method used to detect it
      hasSymptom:        Disease → Clinical outcome/symptom
      measuredBy:        Biomarker → Diagnostic method that measures it
      associatedWith:    Gene → Disease it is linked to
      assessedBy:        Clinical outcome → Diagnostic method that assesses it

    EXAMPLE — a GOOD delta (rich in triples):
      add_classes: []
      add_instances: [
        {"name": "Faricimab", "class": "AntiVEGFTherapy"}
      ]
      add_triples: [
        {"subject": "Faricimab", "predicate": "treats", "object": "WetAMD"},
        {"subject": "Faricimab", "predicate": "inhibits", "object": "VEGF"},
        {"subject": "WetAMD", "predicate": "diagnosedBy", "object": "OCT"},
        {"subject": "Drusen", "predicate": "indicates", "object": "DryAMD"},
        {"subject": "CFH", "predicate": "associatedWith", "object": "AMD"},
        {"subject": "Drusen", "predicate": "measuredBy", "object": "OCT"},
        {"subject": "AMD", "predicate": "hasSymptom", "object": "Endophthalmitis"},
        {"subject": "Smoking", "predicate": "causesOrIncreases", "object": "AMD"}
      ]

    Notice: 1 instance but 8 triples. Extract EVERY relationship the
    abstract mentions, even for entities already in the schema. Triples
    about existing entities are just as valuable as new instances.

    Parameters:
      add_classes: list of {"name", "parent_class", "description"} — RARE.
      add_instances: list of {"name", "class"} — entities go here.
      add_triples: list of {"subject", "predicate", "object"} — THE MOST
        IMPORTANT PART. Extract every relationship. Use all 9 predicates.
    """
    add_classes = add_classes or []
    add_instances = add_instances or []
    add_triples = add_triples or []

    if not (add_classes or add_instances or add_triples):
        return "REJECTED: delta is empty. Include at least one change."

    results = {"classes_added": [], "instances_added": [], "triples_added": [],
               "rejected": [], "healed": []}

    # ── Defensive: make sure canonical root classes and properties exist ─
    # even if the caller forgot to initialize them. This is idempotent.
    _ensure_properties()
    _ensure_root_classes()

    # ── Pre-pass: heal any orphan classes whose parents may now exist ────
    # This catches cases where an earlier delta added a child class whose
    # parent didn't exist yet, and a later delta (or this one) introduces
    # the parent.
    pre_healed = _heal_orphan_parents()
    results["healed"].extend(pre_healed)

    # ── GATE: enforce 2-child minimum for new classes (Stages 2/3 only) ──
    # In Stage 1 (schema is nearly empty), allow class creation freely —
    # the LLM is building the initial hierarchy.
    # In Stages 2/3, require that each new class has 2+ children
    # (instances OR subclasses) in the same delta.
    schema_has_content = len(SCHEMA.get("classes", {})) > len(_CANONICAL_ROOTS) + 2

    if schema_has_content and add_classes:
        # Count instances per class in this delta
        _inst_per_class = {}
        for inst in (add_instances or []):
            if isinstance(inst, dict):
                cls_name = str(inst.get("class", "")).strip()
                _inst_per_class[cls_name] = _inst_per_class.get(cls_name, 0) + 1

        # Count subclasses per parent in this delta
        _subs_per_parent = {}
        for cl in (add_classes or []):
            if isinstance(cl, dict):
                p = str(cl.get("parent_class", "")).strip()
                if p:
                    _subs_per_parent[p] = _subs_per_parent.get(p, 0) + 1

        gated_classes = []
        for c in add_classes:
            if not isinstance(c, dict):
                results["rejected"].append(f"class entry not a dict: {c}")
                continue
            cname = str(c.get("name", "")).strip()

            # Count children: instances + subclasses targeting this class
            n_children = _inst_per_class.get(cname, 0) + _subs_per_parent.get(cname, 0)
            # Also check fuzzy match
            for k, v in _inst_per_class.items():
                if _normalize(k) == _normalize(cname):
                    n_children = max(n_children, v + _subs_per_parent.get(cname, 0))

            if n_children < 2 and not _is_root_marker(c.get("parent_class")):
                results["rejected"].append(
                    f"class '{cname}' rejected: needs 2+ children (instances or "
                    f"subclasses) in the same delta, got {n_children}. "
                    f"Auto-converting to instance of parent."
                )
                # Auto-convert: add it as an instance of its parent
                parent = str(c.get("parent_class", "")).strip()
                if parent and cname:
                    add_instances.append({"name": cname, "class": parent})
                continue
            gated_classes.append(c)
        add_classes = gated_classes

    # ── Apply classes: TWO-PASS so order within the delta doesn't matter ──
    # Pass 1: add every new class as a node (no parent linking yet).
    #         This lets children reference parents that come later in the list.
    new_class_names = []
    class_by_name = {}  # name -> {parent_raw, desc}

    def _is_root_marker(v) -> bool:
        if v is None:
            return True
        return str(v).strip().lower() in ("", "none", "null", "root")

    for c in add_classes:
        if not isinstance(c, dict):
            results["rejected"].append(f"class entry not a dict: {c}")
            continue
        name = str(c.get("name", "")).strip()
        desc = str(c.get("description", "")).strip()
        parent_raw = c.get("parent_class")

        if len(name) < 2:
            results["rejected"].append(f"class name too short: '{name}'")
            continue

        existing = _find_class(name)
        if existing:
            results["rejected"].append(f"class '{name}' already exists as '{existing}'")
            continue

        # Add as a bare node; parent is resolved in pass 2
        SCHEMA["classes"][name] = {
            "description": desc,
            "subclasses": [],
            "instances": [],
        }
        new_class_names.append(name)
        class_by_name[name] = parent_raw

    # Pass 2: resolve parent edges now that all new classes exist as nodes.
    for name in new_class_names:
        parent_raw = class_by_name[name]
        if _is_root_marker(parent_raw):
            # explicit root class — no parent linking
            results["classes_added"].append(name)
            continue
        parent = str(parent_raw).strip()
        parent_canonical = _find_class(parent)
        if not parent_canonical:
            # Parent doesn't exist YET — store the intended parent in the
            # class data so we can heal the link when the parent is added
            # in a later delta.
            SCHEMA["classes"][name]["_pending_parent"] = parent
            results["rejected"].append(
                f"class '{name}' parent '{parent}' not found — stored as "
                f"pending, will re-link when parent is added")
            results["classes_added"].append(name)
            continue
        if parent_canonical == name:
            results["rejected"].append(f"class '{name}' cannot be its own parent")
            continue
        subs = SCHEMA["classes"][parent_canonical].get("subclasses", [])
        if name not in subs:
            subs.append(name)
        SCHEMA["classes"][parent_canonical]["subclasses"] = subs
        results["classes_added"].append(name)

    # ── Post-pass: heal orphan links again after this delta's classes ────
    # This catches the case where a class added earlier in this same delta
    # listed a parent that was added later in the same delta but pass 2
    # (which iterates in original order) may have already marked it pending.
    post_healed = _heal_orphan_parents()
    results["healed"].extend(post_healed)

    # ── Apply instances ───────────────────────────────────────────────────
    for inst in add_instances:
        if not isinstance(inst, dict):
            results["rejected"].append(f"instance entry not a dict: {inst}")
            continue
        name = str(inst.get("name", "")).strip()
        cls = str(inst.get("class", "")).strip()

        if len(name) < 2:
            results["rejected"].append(f"instance name too short: '{name}'")
            continue

        # Hallucination guard — must be in the abstract text
        if CURRENT_ABSTRACT and name.lower() not in CURRENT_ABSTRACT.lower():
            results["rejected"].append(f"instance '{name}' not in abstract text")
            continue

        # Block obvious person names
        lc = name.lower()
        if any(lc.startswith(p) for p in ("mr ", "mrs ", "dr ", "prof ", "professor ")):
            results["rejected"].append(f"'{name}' looks like a person, not medical")
            continue

        # Fuzzy dedupe against existing instances AND classes
        existing_inst = _find_instance(name)
        if existing_inst:
            results["rejected"].append(
                f"instance '{name}' already exists as '{existing_inst[1]}' in '{existing_inst[0]}'")
            continue
        if _find_class(name):
            results["rejected"].append(
                f"'{name}' already exists as a CLASS (cannot also be an instance)")
            continue

        # Class must exist (canonicalize via fuzzy match)
        cls_canonical = _find_class(cls)
        if not cls_canonical:
            results["rejected"].append(
                f"instance '{name}' → unknown class '{cls}'")
            continue

        insts = SCHEMA["classes"][cls_canonical].get("instances", [])
        if name not in insts:
            insts.append(name)
        SCHEMA["classes"][cls_canonical]["instances"] = insts
        results["instances_added"].append(f"{name} → {cls_canonical}")

    # ── Apply triples ─────────────────────────────────────────────────────
    for t in add_triples:
        if not isinstance(t, dict):
            results["rejected"].append(f"triple entry not a dict: {t}")
            continue
        pred = str(t.get("property", "") or t.get("predicate", "")).strip()
        subj = str(t.get("subject", "")).strip()
        obj = str(t.get("object", "")).strip()

        if pred not in _VALID_PREDICATES:
            results["rejected"].append(
                f"triple has invalid predicate '{pred}' "
                f"(valid: {sorted(_VALID_PREDICATES)})")
            continue

        # Canonicalize subject/object via fuzzy match (instances or classes)
        def canonical(n):
            found = _find_instance(n)
            if found:
                return found[1]
            c = _find_class(n)
            if c:
                return c
            return None

        subj_c = canonical(subj)
        obj_c = canonical(obj)
        if not subj_c:
            results["rejected"].append(f"triple subject '{subj}' not in schema")
            continue
        if not obj_c:
            results["rejected"].append(f"triple object '{obj}' not in schema")
            continue

        examples = SCHEMA["properties"][pred]["examples"]
        triple = [subj_c, pred, obj_c]
        if triple in examples:
            results["rejected"].append(f"triple already exists: {subj_c} {pred} {obj_c}")
            continue
        examples.append(triple)
        results["triples_added"].append(f"{subj_c} {pred} {obj_c}")

    # ── Log and return summary ───────────────────────────────────────────
    logger.info(f"  Delta applied: "
                f"+{len(results['classes_added'])} classes, "
                f"+{len(results['instances_added'])} instances, "
                f"+{len(results['triples_added'])} triples, "
                f"{len(results['healed'])} orphan links healed, "
                f"{len(results['rejected'])} rejected")

    summary = [
        f"DELTA APPLIED:",
        f"  classes: +{len(results['classes_added'])} ({', '.join(results['classes_added'][:6])}{'...' if len(results['classes_added'])>6 else ''})",
        f"  instances: +{len(results['instances_added'])}",
        f"  triples: +{len(results['triples_added'])}",
        f"  healed orphan links: {len(results['healed'])}",
    ]
    if results["rejected"]:
        summary.append(f"  rejected: {len(results['rejected'])}")
        for r in results["rejected"][:5]:
            summary.append(f"    - {r}")
    summary.append("")
    summary.append("TASK COMPLETE. Do NOT call propose_delta again. "
                   "Do NOT call any tool. Emit your Final Answer now with "
                   "a one-sentence summary of what you added.")
    return "\n".join(summary)


@tool
def get_class_details(class_name: str) -> str:
    """Look up details of a specific class in the current schema.
    Use this when you need to check what instances already exist under
    a class BEFORE composing your delta. Optional — most abstracts can
    be handled from the compact summary alone."""
    canonical = _find_class(class_name)
    if not canonical:
        return f"Class '{class_name}' not found."
    data = SCHEMA["classes"][canonical]
    subs = data.get("subclasses", [])
    instances = data.get("instances", [])
    return (f"Class: {canonical}\n"
            f"  description: {data.get('description', '')}\n"
            f"  subclasses ({len(subs)}): {subs}\n"
            f"  instances ({len(instances)}): {instances}")


# ── Prompts ──────────────────────────────────────────────────────────────────

_AGENTIC_TOOL_TAIL = """

═══════════════════════════════════════════════════════════════════════
AGENTIC OUTPUT FORMAT — IMPORTANT
═══════════════════════════════════════════════════════════════════════

You are NOT writing JSON directly. Instead, you call the propose_delta
tool ONCE with all the new classes, individuals/instances, and triples
the text implies. The tool receives three lists:
  - add_classes  : [{"name": "X", "parent_class": "Y", "description": "..."}]
  - add_instances: [{"name": "X", "class": "Y"}]  ← this is how you add INDIVIDUALS
  - add_triples  : [{"subject": "X", "predicate": "Y", "object": "Z"}]

IMPORTANT: "add_instances" is the tool's name for adding INDIVIDUALS.
Every entity the prompt calls an "individual" goes in add_instances.
  - Specific drugs (Ranibizumab, Aflibercept) → add_instances
  - Specific genes (CFH, ARMS2, HTRA1) → add_instances
  - Specific devices/tests (OCT, FundusPhotography) → add_instances
  - Specific risk factors (Smoking, Age) → add_instances
Only CATEGORIES with subtypes go in add_classes.

Do NOT emit a JSON schema. Do NOT use markdown code fences. Call
propose_delta EXACTLY ONCE per abstract with all changes bundled.

═══════════════════════════════════════════════════════════════════════
INSTANCE-FIRST RULE (most important)
═══════════════════════════════════════════════════════════════════════

The schema already has classes for most entity types. For EVERY entity
you find in the abstract, your FIRST action should be: find the existing
class it belongs to and add it as an INSTANCE. The existing classes are
a CLOSED vocabulary — use them.

ONLY create a new class if ALL of these are true:
  (a) NO existing class fits the entity
  (b) You have 2+ concrete instances for the new class IN THIS abstract
  (c) The new class represents a category, not a specific named thing

Most abstracts need ZERO new classes. If you find yourself adding more
than 1 new class per abstract, you are almost certainly wrong — those
entities should be instances.

═══════════════════════════════════════════════════════════════════════
RELATIONSHIP EXTRACTION (equally important as instances)
═══════════════════════════════════════════════════════════════════════

For EVERY entity (new or existing), extract ALL relationships the
abstract mentions. A good delta has MORE triples than instances.
Even if an entity already exists in the schema, add new triples about
it. Use ALL 9 predicates — not just treats and associatedWith:
  - treats: which drug treats which disease?
  - inhibits: which drug inhibits which molecular target?
  - diagnosedBy: which disease is diagnosed by which method?
  - indicates: which biomarker indicates which disease?
  - measuredBy: which biomarker is measured by which method?
  - hasSymptom: which disease has which clinical outcome?
  - causesOrIncreases: which risk factor causes which disease?
  - associatedWith: which gene is associated with which disease?
  - assessedBy: which outcome is assessed by which method?

═══════════════════════════════════════════════════════════════════════
ADDITIONAL STRUCTURAL GUARDRAILS
═══════════════════════════════════════════════════════════════════════

1. ONE-MEMBER RULE: enforced by the tool — new classes with fewer than
   2 instances in the same delta will be AUTO-REJECTED and converted to
   instances. Don't waste your delta on classes you can't populate.

2. NAMING FORMAT: All entity names MUST be CamelCase with NO spaces,
   NO parentheses, NO slashes, NO dashes. Valid: "NuclearCataract",
   "AgeRelatedMaculopathy", "ChoroidalNeovascularization". Invalid:
   "Nuclear Cataract", "Age-related Maculopathy", "ARMS2/HTRA1".

3. CANONICALIZATION: For any concept with synonyms, abbreviations,
   spelling variants (British vs American), or expanded forms, pick
   ONE canonical name and use it everywhere. Do NOT emit near-
   duplicates like "ChoroidalNeovascularization" AND
   "ChoroidalNeovascularisation" as separate entities.

4. NO STUDY METADATA: Do NOT add people, institutions, places,
   populations/demographics, p-values, or study names. Anything ending
   in "Study", "Trial", "Survey", "Group", "Community", "Registry",
   "Cohort" is study metadata, not a medical entity — skip it. Cell
   types (fibroblasts, monocytes) are also not medical entities for
   this ontology — skip them.

5. NO PUNNING: Brand names and generic names of the same drug are the
   SAME entity — pick one canonical name and make it a single instance.
   Never create a class + brand-instance pair for the same drug (e.g.
   class "Celecoxib" with instance "Celebrex" is WRONG — just use
   "Celecoxib" as one instance).
"""


def _build_stage1_prompt() -> ChatPromptTemplate:
    """Use the original schema-miner Stage 1 prompt, adapted for agentic tool calls."""
    system_text = prompt_template1.system_prompt.format(
        process_name=ProcessConfig.Process_name,
        process_description=ProcessConfig.Process_description,
    ) + _AGENTIC_TOOL_TAIL
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=system_text),
        HumanMessagePromptTemplate.from_template("{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])


def _build_abstract_prompt(summary: str, stage_name: str) -> ChatPromptTemplate:
    """Use the original schema-miner Stage 2/3 prompt with the compact summary
    injected in place of {current_schema}."""
    template = prompt_template2 if stage_name == "Stage 2" else prompt_template3
    system_text = template.system_prompt.format(
        process_name=ProcessConfig.Process_name,
    )
    # Prepend the compact schema summary (our agentic equivalent of current_schema)
    system_text = (
        f"CURRENT SCHEMA (compact summary — full schema lives in the tool, "
        f"you never see it):\n{summary}\n\n" + system_text + _AGENTIC_TOOL_TAIL
    )
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=system_text),
        HumanMessagePromptTemplate.from_template("{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])


# ── Runners ──────────────────────────────────────────────────────────────────

TOOLS = [propose_delta, get_class_details]


def create_llm(model: str, provider: str):
    if provider == "groq":
        from langchain_groq import ChatGroq
        from dotenv import load_dotenv
        load_dotenv()
        return ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"),
                        temperature=0)
    return ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url,
                      temperature=0, num_ctx=16384)


def create_executor(llm, prompt, max_iter: int = 3):
    agent = create_tool_calling_agent(llm, TOOLS, prompt)
    return AgentExecutor(
        agent=agent, tools=TOOLS, verbose=True,
        handle_parsing_errors=True,
        max_iterations=max_iter, max_execution_time=600,
    )


def human_checkpoint(stage_label: str):
    """HITL pause between stages — matches schema-miner convention."""
    print(f"\n{'='*60}")
    print(f"  HITL CHECKPOINT — {stage_label}")
    print(f"{'='*60}")
    print(compact_summary())
    print("\n  Press ENTER to continue (or Ctrl+C to stop)...")
    try:
        input()
    except EOFError:
        pass


def run_stage1(llm, hitl: bool):
    logger.info("\n" + "=" * 60)
    logger.info("  STAGE 1: Build Initial Schema from Domain Specification")
    logger.info("=" * 60)

    _ensure_properties()
    _ensure_root_classes()
    spec = DOMAIN_SPEC_PATH.read_text(encoding="utf-8")
    if len(spec) > 8000:
        spec = spec[:8000]

    global CURRENT_ABSTRACT
    CURRENT_ABSTRACT = spec

    executor = create_executor(llm, _build_stage1_prompt(), max_iter=5)
    try:
        result = executor.invoke({
            "input": f"AMD domain specification:\n\n{spec}\n\nEmit one propose_delta call with the full initial structure."
        })
        logger.info(f"\n  Stage 1 result: {result.get('output', 'Done')[:300]}")
    except Exception as e:
        logger.error(f"  Stage 1 error: {e}")

    save_schema("stage-1")
    logger.info(f"\n  After Stage 1: {compact_summary()}")

    if hitl:
        human_checkpoint("After Stage 1")


def run_stage_abstracts(llm, stage_label: str, directory: Path,
                         max_abstracts: int, provider: str, hitl: bool):
    logger.info("\n" + "=" * 60)
    logger.info(f"  {stage_label}: Refine with abstracts in {directory.name}")
    logger.info("=" * 60)

    _ensure_properties()
    _ensure_root_classes()
    files = sorted(directory.glob("*.txt"))
    if max_abstracts:
        files = files[:max_abstracts]
    if not files:
        logger.info(f"  No abstracts in {directory}")
        return

    logger.info(f"  Processing {len(files)} abstracts\n")

    for i, f in enumerate(files):
        text = f.read_text(encoding="utf-8")
        logger.info(f"\n  --- [{i+1}/{len(files)}] {f.name} ---")

        global CURRENT_ABSTRACT
        CURRENT_ABSTRACT = text

        summary = compact_summary()
        prompt = _build_abstract_prompt(summary, stage_label)
        executor = create_executor(llm, prompt, max_iter=5)

        if provider == "groq":
            time.sleep(4)

        for attempt in range(3):
            try:
                result = executor.invoke({"input": f"Abstract:\n\n{text}"})
                logger.info(f"  Result: {result.get('output', 'Done')[:200]}")
                break
            except Exception as e:
                if attempt < 2:
                    logger.info(f"  Attempt {attempt+1} failed: {e}. Retrying in 10s...")
                    time.sleep(10)
                else:
                    logger.error(f"  Error after 3 attempts: {e}. Skipping abstract.")

        if (i + 1) % 10 == 0:
            save_schema(stage_label.lower().replace(" ", "-"))

    save_schema(stage_label.lower().replace(" ", "-"))
    logger.info(f"\n  After {stage_label}: {compact_summary()}")

    if hitl:
        human_checkpoint(f"After {stage_label}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agentic SCHEMA-MINERpro — 3-stage delta-based refinement")
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    parser.add_argument("--provider", default="groq", choices=["ollama", "groq"])
    parser.add_argument("--stage", type=int, default=None)
    parser.add_argument("--max-abstracts", type=int, default=None)
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume from a saved schema JSON")
    parser.add_argument("--no-hitl", action="store_true",
                        help="Skip the HITL checkpoints between stages")
    args = parser.parse_args()

    logger.info("\n" + "=" * 60)
    logger.info("  SCHEMA-MINERpro — Agentic delta-based refinement")
    logger.info("=" * 60)
    logger.info(f"  Model    : {args.model}")
    logger.info(f"  Provider : {args.provider}")
    logger.info(f"  HITL     : {'off' if args.no_hitl else 'on'}")

    llm = create_llm(args.model, args.provider)

    if args.resume:
        global SCHEMA
        SCHEMA = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        _ensure_properties()
        logger.info(f"  Resumed from: {args.resume}")
        logger.info(f"\n{compact_summary()}")

    hitl = not args.no_hitl

    if args.stage == 1 or args.stage is None:
        run_stage1(llm, hitl)

    if args.stage == 2 or (args.stage is None and not args.resume):
        run_stage_abstracts(llm, "Stage 2", STAGE2_ABSTRACTS_DIR,
                             args.max_abstracts, args.provider, hitl)
    elif args.stage == 2:
        run_stage_abstracts(llm, "Stage 2", STAGE2_ABSTRACTS_DIR,
                             args.max_abstracts, args.provider, hitl)

    if args.stage == 3 or (args.stage is None and not args.resume):
        run_stage_abstracts(llm, "Stage 3", STAGE3_ABSTRACTS_DIR,
                             args.max_abstracts, args.provider, hitl)
    elif args.stage == 3:
        run_stage_abstracts(llm, "Stage 3", STAGE3_ABSTRACTS_DIR,
                             args.max_abstracts, args.provider, hitl)

    save_schema("final")

    logger.info("\n" + "=" * 60)
    logger.info("  PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info(compact_summary())
    logger.info("\n  Next: python run_validate_ontology_agent.py --provider groq --model llama-3.3-70b-versatile\n")


if __name__ == "__main__":
    main()
