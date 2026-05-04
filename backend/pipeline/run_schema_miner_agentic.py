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

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_FILE = PROJECT_ROOT / "logs" / "schema_miner_agentic.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

DOMAIN_SPEC_PATH = PROJECT_ROOT / "data" / "stage-1" / "AMD" / "amd_domain_spec.txt"
STAGE2_ABSTRACTS_DIR = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "abstracts"
STAGE3_ABSTRACTS_DIR = PROJECT_ROOT / "data" / "stage-3" / "AMD" / "abstracts"
RESULTS_DIR = PROJECT_ROOT / "results" / "amd"

SCHEMA = {
    "classes": {},
    "properties": {},
    "disjoint_groups": [
        ["Disease", "Treatment", "DiagnosticMethod", "ClinicalOutcome"],
    ],
}

CURRENT_ABSTRACT = ""

# Queue for classes proposed with one child; promoted when a second child arrives later.
PENDING_CLASSES: dict = {}

BUILTIN_PROPERTY_DEFINITIONS = {
    "treats":             ("Treatment",        "Disease",          "A treatment that manages a disease"),
    "inhibits":           ("Treatment",        "MolecularTarget",  "A treatment that inhibits a molecular target"),
    "causesOrIncreases":  ("RiskFactor",       "Disease",          "A risk factor that causes or increases a disease"),
    "indicates":          ("Biomarker",        "Disease",          "A biomarker that indicates a disease"),
    "diagnosedBy":        ("Disease",          "DiagnosticMethod", "A disease diagnosed via a method"),
    "hasSymptom":         ("Disease",          "ClinicalOutcome",  "A disease has a clinical symptom"),
    "measuredBy":         ("Biomarker",        "DiagnosticMethod", "A biomarker measured by a method"),
    "associatedWith":     ("Biomarker",        "Disease",          "A biomarker (typically a gene) associated with a disease"),
    "assessedBy":         ("ClinicalOutcome",  "DiagnosticMethod", "A clinical outcome assessed by a method"),
}


def _ensure_properties():
    """Seed missing built-in predicates; preserve any already present."""
    for name, (domain, range_, desc) in BUILTIN_PROPERTY_DEFINITIONS.items():
        if name not in SCHEMA["properties"]:
            SCHEMA["properties"][name] = {
                "domain": domain,
                "range": range_,
                "description": desc,
                "examples": [],
            }


def _valid_predicates() -> set[str]:
    """Return predicate names declared in the schema (extensible at runtime)."""
    return set(SCHEMA.get("properties", {}).keys())


_CANONICAL_ROOTS = [
    ("Disease", "A medical condition affecting the human body"),
    ("Treatment", "A medical intervention used to manage or cure a disease"),
    ("Biomarker", "A measurable indicator of a biological state or condition"),
    ("DiagnosticMethod", "A procedure or test used to diagnose a disease"),
    ("RiskFactor", "A factor that increases the likelihood of developing a disease"),
    ("ClinicalOutcome", "A measurable result of a treatment or disease progression, "
                         "including visual impairments (blindness, vision loss, visual "
                         "acuity decline), adverse events, and disease progressions"),
    ("MolecularTarget", "A molecular entity (protein, receptor, pathway component) "
                        "that a treatment inhibits or modulates (e.g., VEGF, VEGFR, "
                        "complement C3, S1P)"),
]


def _ensure_root_classes():
    """Pre-populate the canonical root classes so children can always find a parent."""
    for name, desc in _CANONICAL_ROOTS:
        if name not in SCHEMA["classes"]:
            SCHEMA["classes"][name] = {
                "description": desc,
                "subclasses": [],
                "instances": [],
            }


def _normalize(name: str) -> str:
    return name.lower().strip().replace("-", "").replace(" ", "").replace("_", "")


def _root_of(class_name: str, _seen=None) -> str | None:
    """Topmost ancestor via the subclass chain."""
    if _seen is None:
        _seen = set()
    if class_name in _seen or class_name not in SCHEMA.get("classes", {}):
        return class_name if class_name in SCHEMA.get("classes", {}) else None
    _seen.add(class_name)
    for parent, parent_info in SCHEMA["classes"].items():
        if class_name in parent_info.get("subclasses", []):
            return _root_of(parent, _seen)
    return class_name


def _disjoint_partners(class_name: str) -> set[str]:
    """Classes declared disjoint with this class (resolved via its root)."""
    root = _root_of(class_name)
    partners: set[str] = set()
    for group in SCHEMA.get("disjoint_groups", []):
        if root in group:
            partners.update(c for c in group if c != root)
    return partners


def _find_class(name: str) -> str | None:
    """Fuzzy lookup: canonical class name if one matches."""
    norm = _normalize(name)
    for cn in SCHEMA["classes"]:
        if _normalize(cn) == norm:
            return cn
    return None


def _find_instance(name: str) -> tuple[str, str] | None:
    """Fuzzy lookup: (class_name, instance_name) if present."""
    norm = _normalize(name)
    for cn, cd in SCHEMA["classes"].items():
        if isinstance(cd, dict):
            for inst in cd.get("instances", []):
                if _normalize(inst) == norm:
                    return (cn, inst)
    return None


def _heal_orphan_parents() -> list[str]:
    """Link any class carrying a _pending_parent marker to its now-existing parent."""
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
        lines.append(f"\nPROPERTIES ({len(props)} declared in schema — "
                     f"use these predicates when extracting triples):")
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

    # Persist pending-class queue so it survives across runs
    pending_file = stage_dir / "pending_classes.json"
    with open(pending_file, "w", encoding="utf-8") as f:
        json.dump(
            {k: {"parent": v["parent"], "desc": v["desc"],
                 "children": sorted(v["children"])}
             for k, v in PENDING_CLASSES.items()},
            f, indent=4, ensure_ascii=False,
        )

    logger.info(f"  Saved to {stage_file}")


@tool
def propose_delta(
    add_classes: list = None,
    add_instances: list = None,
    add_triples: list = None,
) -> str:
    """Submit all schema changes from one abstract in a single call.

    Parameters:
      add_classes:   list of {"name", "parent_class", "description"} — rare; needs 2+ siblings.
      add_instances: list of {"name", "class"} — most entities go here.
      add_triples:   list of {"subject", "predicate", "object"} — extract every relationship.
    """
    add_classes = add_classes or []
    add_instances = add_instances or []
    add_triples = add_triples or []

    if not (add_classes or add_instances or add_triples):
        return "REJECTED: delta is empty. Include at least one change."

    results = {"classes_added": [], "instances_added": [], "triples_added": [],
               "rejected": [], "healed": []}

    # Idempotent: make sure roots and properties exist even on a fresh run.
    _ensure_properties()
    _ensure_root_classes()

    pre_healed = _heal_orphan_parents()
    results["healed"].extend(pre_healed)

    def _is_root_marker(v) -> bool:
        if v is None:
            return True
        return str(v).strip().lower() in ("", "none", "null", "root")

    # Class gate: require 2+ children per new class in Stages 2/3 only.
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
                parent = str(c.get("parent_class", "")).strip()
                desc = str(c.get("description", "")).strip()

                # Collect children proposed for this class in the current delta
                cur_children = {
                    str(inst.get("name", "")).strip()
                    for inst in (add_instances or [])
                    if isinstance(inst, dict)
                    and _normalize(inst.get("class", "")) == _normalize(cname)
                }

                # Stash in the pending queue
                pending = PENDING_CLASSES.setdefault(
                    cname, {"parent": parent, "desc": desc, "children": set()}
                )
                pending["children"].update(cur_children)

                if len(pending["children"]) >= 2:
                    # Promote the pending class now: 2+ children accumulated
                    # across abstracts. Fall through to normal class creation.
                    results["healed"].append(
                        f"pending class '{cname}' promoted: accumulated "
                        f"{len(pending['children'])} children across abstracts"
                    )
                    gated_classes.append(c)
                    # Move any already-demoted children from parent.instances
                    # into this new class when the instance loop runs below.
                    continue

                results["rejected"].append(
                    f"class '{cname}' pending: has {n_children} child(ren) "
                    f"in this delta, needs 2+. Held in queue; will promote "
                    f"when another abstract contributes a sibling."
                )
                # Auto-convert: add it as an instance of its parent (safe fallback)
                if parent and cname:
                    add_instances.append({"name": cname, "class": parent})
                continue
            gated_classes.append(c)
        add_classes = gated_classes

    # Two-pass apply so a child can reference a parent added later in the same delta.
    new_class_names = []
    class_by_name = {}  # name -> {parent_raw, desc}

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

        # If this class was promoted from the pending queue, reclaim any
        # children that were previously demoted into the parent's instances.
        pending_info = PENDING_CLASSES.pop(name, None)
        if pending_info:
            parent_insts = SCHEMA["classes"][parent_canonical].get("instances", [])
            new_insts = SCHEMA["classes"][name].get("instances", [])
            for child in pending_info["children"]:
                if child in parent_insts:
                    parent_insts.remove(child)
                if child not in new_insts:
                    new_insts.append(child)
                    results["healed"].append(
                        f"reassigned '{child}' from '{parent_canonical}' to "
                        f"promoted class '{name}'"
                    )
            SCHEMA["classes"][parent_canonical]["instances"] = parent_insts
            SCHEMA["classes"][name]["instances"] = new_insts

    # Re-run healing: parents added later in this delta may now resolve pending links.
    post_healed = _heal_orphan_parents()
    results["healed"].extend(post_healed)

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

        # Disjointness check — data-driven from SCHEMA['disjoint_groups'].
        # Reject if the instance already lives in a class declared disjoint
        # with the target (via its root).
        disjoint_with_target = _disjoint_partners(cls_canonical)
        violated = False
        for other_cls, other_info in SCHEMA["classes"].items():
            if name in other_info.get("instances", []):
                other_root = _root_of(other_cls)
                if other_root in disjoint_with_target:
                    results["rejected"].append(
                        f"disjointness violation: '{name}' already in "
                        f"'{other_cls}' (root '{other_root}'), cannot also "
                        f"be in '{cls_canonical}'"
                    )
                    violated = True
                    break
        if violated:
            continue

        insts = SCHEMA["classes"][cls_canonical].get("instances", [])
        if name not in insts:
            insts.append(name)
        SCHEMA["classes"][cls_canonical]["instances"] = insts
        results["instances_added"].append(f"{name} → {cls_canonical}")

    for t in add_triples:
        if not isinstance(t, dict):
            results["rejected"].append(f"triple entry not a dict: {t}")
            continue
        pred = str(t.get("property", "") or t.get("predicate", "")).strip()
        subj = str(t.get("subject", "")).strip()
        obj = str(t.get("object", "")).strip()

        valid = _valid_predicates()
        if pred not in valid:
            results["rejected"].append(
                f"triple has invalid predicate '{pred}' "
                f"(valid: {sorted(valid)})")
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


_AGENTIC_TOOL_TAIL = """

AGENTIC OUTPUT FORMAT
Call propose_delta ONCE with three lists. Do NOT emit JSON. Do NOT use markdown code fences.
  - add_classes  : [{"name": "X", "parent_class": "Y", "description": "..."}]
  - add_instances: [{"name": "X", "class": "Y"}]   ← INDIVIDUALS go here
  - add_triples  : [{"subject": "X", "predicate": "Y", "object": "Z"}]

Existing classes are a CLOSED vocabulary — prefer adding instances over new classes.
For EVERY entity (new or existing), extract ALL relationships the abstract mentions. Use all 9 predicates. A good delta has MORE triples than instances.
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
    parser.add_argument("--stage3-dir", type=str, default=None,
                        help="Override Stage 3 abstracts directory (for evaluation subsets)")
    parser.add_argument("--results-dir", type=str, default=None,
                        help="Override output results directory (to avoid overwriting the main run)")
    args = parser.parse_args()

    # Override path globals if requested
    global STAGE3_ABSTRACTS_DIR, RESULTS_DIR
    if args.stage3_dir:
        STAGE3_ABSTRACTS_DIR = Path(args.stage3_dir)
        logger.info(f"  Stage3   : {STAGE3_ABSTRACTS_DIR} (override)")
    if args.results_dir:
        RESULTS_DIR = Path(args.results_dir)
        logger.info(f"  Results  : {RESULTS_DIR} (override)")

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
