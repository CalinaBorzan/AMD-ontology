import argparse
import json
import os
import time
from pathlib import Path

import requests
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain.agents import create_react_agent, AgentExecutor

from pipeline.prompts.validation import PROMPT as AGENT_PROMPT
from schema_miner.config.envConfig import EnvConfig

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "results" / "amd" / "final" / "amd_ontology_final.json"


SCHEMA = {}
PROPOSED_FIXES = []

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "your.email@example.com")



@tool
def inspect_hierarchy(query: str = "none") -> str:
    """Inspect the class hierarchy of the ontology. Shows ALL classes with their subclasses and descriptions. Use this FIRST to understand the ontology structure."""
    classes = SCHEMA.get("classes", {})
    lines = [f"TOTAL CLASSES: {len(classes)}"]
    for class_name, data in classes.items():
        if not isinstance(data, dict):
            continue
        desc = data.get("description", "")
        subs = data.get("subclasses", [])
        instances = data.get("instances", [])
        line = f"{class_name}: {desc}"
        if subs:
            line += f"\n  subclasses ({len(subs)}): {subs}"
        if instances:
            line += f"\n  instances ({len(instances)}): {instances}"
        lines.append(line)
    return "\n".join(lines)


@tool
def inspect_relationships(query: str = "none") -> str:
    """Inspect all property definitions WITHOUT triples. Shows property name, domain, range, description, and the COUNT of triples for each. To see actual triples for a specific property, use list_triples."""
    props = SCHEMA.get("properties", {})
    if not props:
        return "No properties found."
    lines = [f"TOTAL PROPERTIES: {len(props)}"]
    for prop_name, prop_data in props.items():
        if not isinstance(prop_data, dict):
            continue
        domain = prop_data.get("domain", "?")
        range_ = prop_data.get("range", "?")
        desc = prop_data.get("description", "")
        ex_count = len(prop_data.get("examples", []))
        lines.append(f"\n{prop_name} (domain: {domain} → range: {range_}): {desc} [{ex_count} triples — use list_triples to see them]")
    return "\n".join(lines)


@tool
def list_triples(property_name: str) -> str:
    """List ALL triples (subject-predicate-object examples) for a specific property. Use this to scan for reversed-direction errors (e.g., 'Disease treats Drug' should be 'Drug treats Disease'), or wrong-domain entities. Input: the property name (e.g., 'treats', 'diagnosedBy')."""
    property_name = property_name.strip()
    props = SCHEMA.get("properties", {})
    if property_name not in props:
        return f"Property '{property_name}' not found. Available: {list(props.keys())}"
    prop_data = props[property_name]
    domain = prop_data.get("domain", "?")
    range_ = prop_data.get("range", "?")
    examples = prop_data.get("examples", [])
    if not examples:
        return f"Property '{property_name}' has no triples."
    lines = [f"Property '{property_name}' (domain: {domain} → range: {range_}) — {len(examples)} triples:"]
    for ex in examples:
        if len(ex) >= 3:
            lines.append(f"  {ex[0]}  --[{ex[1]}]-->  {ex[2]}")
    return "\n".join(lines)


@tool
def inspect_instances(query: str = "none") -> str:
    """Inspect all class-instance assignments — shows EVERY instance under EVERY class (no truncation). Use to find misclassified entities or instances under wrong parent."""
    classes = SCHEMA.get("classes", {})
    lines = []
    for class_name, data in classes.items():
        if not isinstance(data, dict):
            continue
        instances = data.get("instances", [])
        if instances:
            lines.append(f"{class_name} ({len(instances)}): {instances}")
    return "\n".join(lines) if lines else "No instances found in classes."


@tool
def check_punning(query: str = "none") -> str:
    """Check for punning violations — entities that are BOTH a class AND an individual. This is an OWL violation."""
    classes = SCHEMA.get("classes", {})
    all_individuals = set()

    for data in classes.values():
        if isinstance(data, dict):
            for inst in data.get("instances", []):
                all_individuals.add(inst)

    individuals = SCHEMA.get("individuals", {})
    for items in individuals.values():
        if isinstance(items, list):
            all_individuals.update(items)

    violations = sorted(set(classes.keys()) & all_individuals)
    if violations:
        return f"PUNNING VIOLATIONS FOUND: {violations}. These entities exist as both class and individual."
    return "No punning violations. ✓"


@tool
def check_dual_parents(query: str = "none") -> str:
    """Check for entities that are subclass of multiple parents. This can cause logical conflicts in OWL."""
    classes = SCHEMA.get("classes", {})
    child_to_parents = {}

    for parent_name, data in classes.items():
        if isinstance(data, dict):
            for sub in data.get("subclasses", []):
                child_to_parents.setdefault(sub, []).append(parent_name)

    dual = {k: v for k, v in child_to_parents.items() if len(v) > 1}
    if dual:
        lines = [f"DUAL-PARENT CONFLICTS:"]
        for child, parents in dual.items():
            lines.append(f"  '{child}' is subclass of: {parents}")
        return "\n".join(lines)
    return "No dual-parent conflicts. ✓"


@tool
def check_self_referential(query: str = "none") -> str:
    """Check for self-referential property examples where subject equals object (e.g., 'X causesOrIncreases X')"""
    issues = []
    for prop_name, prop_data in SCHEMA.get("properties", {}).items():
        if not isinstance(prop_data, dict):
            continue
        for example in prop_data.get("examples", []):
            if len(example) >= 3 and example[0] == example[2]:
                issues.append(f"  {example[0]} {example[1]} {example[2]}")

    if issues:
        return "SELF-REFERENTIAL PROPERTIES:\n" + "\n".join(issues)
    return "No self-referential properties. ✓"


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance. Small pure-python version."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def _normalize_name(n: str) -> str:
    """Normalize for fuzzy comparison: lowercase, strip whitespace/punctuation."""
    import re as _re
    return _re.sub(r"[\s\-_.,()]+", "", n.lower())


@tool
def find_spelling_duplicates(query: str = "none") -> str:
    """Detect near-duplicate instance names within the SAME class that differ
    only by spelling (e.g., 'Hemorrhage' vs 'Haemorrhage').
    Uses edit distance ≤ 2 on normalized names. """
    pairs = []
    for cls_name, cls_info in SCHEMA.get("classes", {}).items():
        if not isinstance(cls_info, dict):
            continue
        instances = cls_info.get("instances", [])
        seen = []
        for name in instances:
            norm = _normalize_name(name)
            for other, other_norm in seen:
                if norm == other_norm:
                    pairs.append(f"  {cls_name}: '{other}' ≡ '{name}' (identical after normalization)")
                elif abs(len(norm) - len(other_norm)) <= 2 and _levenshtein(norm, other_norm) <= 2:
                    pairs.append(f"  {cls_name}: '{other}' ≈ '{name}' (edit distance ≤ 2)")
            seen.append((name, norm))

    # Also check across classes (a class and instance with same normalized name)
    # e.g. AMRS2 instance in Gene but ARMS2 instance in Biomarker
    all_insts = []
    for cls_name, cls_info in SCHEMA.get("classes", {}).items():
        if not isinstance(cls_info, dict):
            continue
        for name in cls_info.get("instances", []):
            all_insts.append((cls_name, name, _normalize_name(name)))

    for i, (ca, na, norma) in enumerate(all_insts):
        for cb, nb, normb in all_insts[i + 1:]:
            if ca == cb:
                continue  # already covered above
            if norma == normb:
                pairs.append(f"  CROSS-CLASS: '{na}' ({ca}) ≡ '{nb}' ({cb})")
            elif abs(len(norma) - len(normb)) <= 2 and _levenshtein(norma, normb) <= 2:
                pairs.append(f"  CROSS-CLASS: '{na}' ({ca}) ≈ '{nb}' ({cb}) (edit distance ≤ 2)")

    if pairs:
        return "SPELLING DUPLICATES FOUND:\n" + "\n".join(pairs) + \
               "\n\nFor each pair, propose removing ONE (keep the more standard spelling — e.g. prefer American 'Hemorrhage' over 'Haemorrhage' for consistency; prefer correct 'ARMS2' over typo 'AMRS2')."
    return "No spelling duplicates detected. ✓"


# Heuristic patterns that commonly indicate a name is NOT a biomarker
# (biomarker = measurable quantity; these are cell types, structures, or supplements)
_CELL_TYPE_SUFFIXES = ("cyte", "cytes", "blast", "blasts", "phage", "phages")
_ANATOMY_KEYWORDS = {"photoreceptor", "plasma", "retina", "macula", "choroid",
                      "sclera", "cornea", "fovea", "lens", "iris", "pupil",
                      "vitreous", "aqueous"}
_SUPPLEMENT_NAMES = {"zinc", "copper", "iron", "magnesium", "selenium",
                     "calcium", "potassium", "saffron", "omega3", "omega6",
                     "curcumin", "resveratrol", "bilberry"}


@tool
def check_biomarker_semantics(query: str = "none") -> str:
    """Flag instances in the Biomarker class that are likely misclassified:
    cell types (Monocytes, Fibroblasts, Microglia), anatomical structures
    (Photoreceptor, Plasma, Retina), or supplements (Zinc, Copper, Saffron).
    A biomarker should be a measurable quantity or genetic variant."""
    biomarker = SCHEMA.get("classes", {}).get("Biomarker", {})
    if not isinstance(biomarker, dict):
        return "No Biomarker class in schema."

    issues = []
    for inst in biomarker.get("instances", []):
        lc = inst.lower()
        norm = _normalize_name(inst)
        if any(lc.endswith(suf) for suf in _CELL_TYPE_SUFFIXES):
            issues.append(f"  '{inst}' — looks like a CELL TYPE; should be removed or "
                          f"moved to a CellType class (not in current ontology).")
        elif norm in _ANATOMY_KEYWORDS or any(k in norm for k in _ANATOMY_KEYWORDS):
            issues.append(f"  '{inst}' — looks like ANATOMICAL STRUCTURE; should be "
                          f"removed (not a measurable biomarker).")
        elif norm in _SUPPLEMENT_NAMES:
            issues.append(f"  '{inst}' — looks like a SUPPLEMENT/MINERAL; should be "
                          f"MOVED to Treatment.")

    if issues:
        return ("LIKELY MISCLASSIFICATIONS IN BIOMARKER:\n" + "\n".join(issues) +
                "\n\nFor supplements/minerals use propose_fix with action='move'. "
                "For cell types/anatomy with no target class, use action='remove'.")
    return "No obvious misclassifications in Biomarker. ✓"


@tool
def check_domain_range_violations(query: str = "none") -> str:
    """Scan all triples for domain/range violations against the predicates'
    declared domain and range. E.g. 'Ranibizumab causesOrIncreases Glaucoma'
    violates because causesOrIncreases requires a RiskFactor subject, not a
    Treatment."""
    classes = SCHEMA.get("classes", {})
    props = SCHEMA.get("properties", {})

    # Walk up subclass chain to find the root class
    def root_of(name, seen=None):
        if seen is None:
            seen = set()
        if name in seen or name not in classes:
            return name
        seen.add(name)
        for p, pi in classes.items():
            if isinstance(pi, dict) and name in pi.get("subclasses", []):
                return root_of(p, seen)
        return name

    # Map every instance/class to its root
    entity_class = {}
    for cls_name, cls_info in classes.items():
        if not isinstance(cls_info, dict):
            continue
        root = root_of(cls_name)
        entity_class[cls_name] = root
        for inst in cls_info.get("instances", []):
            entity_class[inst] = root

    violations = []
    for pred_name, prop_data in props.items():
        if not isinstance(prop_data, dict):
            continue
        expected_domain = prop_data.get("domain")
        expected_range = prop_data.get("range")
        for ex in prop_data.get("examples", []):
            if not (isinstance(ex, list) and len(ex) >= 3):
                continue
            subj, _, obj = ex[0], ex[1], ex[2]
            s_root = entity_class.get(subj)
            o_root = entity_class.get(obj)
            if s_root and expected_domain and s_root != expected_domain:
                violations.append(
                    f"  {subj} {pred_name} {obj}: subject is {s_root}, "
                    f"but {pred_name} requires domain {expected_domain}"
                )
            if o_root and expected_range and o_root != expected_range:
                violations.append(
                    f"  {subj} {pred_name} {obj}: object is {o_root}, "
                    f"but {pred_name} requires range {expected_range}"
                )

    if not violations:
        return "No domain/range violations. ✓"

    # For each violation, enumerate MECHANICALLY-VALID fix candidates.
    # The LLM reviews and picks the medically correct one via propose_fix.
    def _enumerate_candidates(subj, pred_name, obj, expected_domain, expected_range):
        s_root = entity_class.get(subj)
        o_root = entity_class.get(obj)
        candidates = []

        # A) Swap — valid if (o_root, s_root) matches (domain, range)
        if o_root == expected_domain and s_root == expected_range:
            candidates.append(
                f"SWAP  → {obj} {pred_name} {subj}   "
                f"(direction reversed; now {o_root}→{s_root} matches {expected_domain}→{expected_range})"
            )
        # B) Change predicate — find another predicate whose domain/range matches
        for other_pred, other_info in props.items():
            if other_pred == pred_name or not isinstance(other_info, dict):
                continue
            od, orng = other_info.get("domain"), other_info.get("range")
            if s_root == od and o_root == orng:
                candidates.append(
                    f"CHANGE PREDICATE → {subj} {other_pred} {obj}   "
                    f"(matches {other_pred}'s domain={od} range={orng})"
                )
            # Also try swap + change predicate
            if o_root == od and s_root == orng:
                candidates.append(
                    f"SWAP + CHANGE PREDICATE → {obj} {other_pred} {subj}   "
                    f"(matches {other_pred}'s domain={od} range={orng})"
                )
        # C) Remove — always an option, marked as last resort
        candidates.append("REMOVE (last resort — loses information)")
        return candidates

    out = ["DOMAIN/RANGE VIOLATIONS — for each, pick the medically correct fix:"]
    # Re-walk violations and attach candidate fixes
    for pred_name, prop_data in props.items():
        if not isinstance(prop_data, dict):
            continue
        ed = prop_data.get("domain")
        er = prop_data.get("range")
        for ex in prop_data.get("examples", []):
            if not (isinstance(ex, list) and len(ex) >= 3):
                continue
            subj, _, obj = ex[0], ex[1], ex[2]
            s_root = entity_class.get(subj)
            o_root = entity_class.get(obj)
            if (s_root and ed and s_root != ed) or (o_root and er and o_root != er):
                out.append("")
                out.append(f"▸ VIOLATION: {subj} {pred_name} {obj}")
                out.append(f"    actual: subject={s_root} object={o_root}")
                out.append(f"    required: domain={ed} range={er}")
                cands = _enumerate_candidates(subj, pred_name, obj, ed, er)
                out.append("    candidate fixes (pick the medically correct one):")
                for c in cands:
                    out.append(f"      • {c}")

    out.append("")
    out.append("For EACH violation above, propose_fix with the fix you pick. "
               "Prefer SWAP or CHANGE PREDICATE over REMOVE when both are valid "
               "(preserves information).")
    return "\n".join(out)


@tool
def query_mesh(term: str) -> str:
    """Query MeSH (Medical Subject Headings) to verify if a biomedical concept exists in the standard terminology. Use this to check if a class or instance name is a real biomedical entity."""
    try:
        resp = requests.get(
            NCBI_ESEARCH,
            params={"db": "mesh", "term": term, "retmode": "json",
                    "retmax": 3, "email": NCBI_EMAIL},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json().get("esearchresult", {})
        count = result.get("count", "0")
        ids = result.get("idlist", [])
        if int(count) > 0:
            return f"MeSH found '{term}': {count} results, IDs: {ids}"
        return f"MeSH: '{term}' NOT found — may not be a standard biomedical term."
    except Exception as e:
        return f"MeSH query error: {e}"


@tool
def propose_fix(fix_spec: str) -> str:
    """Propose ONE structured fix for human review. Send a single JSON string:
      {"target_type": "...", "target": "...", "action": "...", "reason": "..."}

    target_type: "class" | "instance" | "triple"
    action:      "remove" | "swap" | "move" | "change_predicate" | "swap_and_change"

    target format:
      - class                    -> "ClassName"
      - instance + remove        -> "InstanceName | ParentClass"
      - instance + move          -> "InstanceName | FromClass -> ToClass"
      - triple + remove/swap     -> "subject | predicate | object"
      - triple + change_predicate or swap_and_change -> "subj | oldPred -> newPred | obj"

    Action restrictions:
      - swap, change_predicate, swap_and_change  -> only valid for triples
      - move                                     -> only valid for instances
    """
    # Parse the fix_spec — accept JSON, or fall back to kwargs-style parsing
    fix = None
    try:
        fix = json.loads(fix_spec)
    except (json.JSONDecodeError, TypeError):
        # Fallback: parse kwargs-style  target_type="x", target="y | z", action="w", reason="..."
        fix = {}
        import re as _re
        for m in _re.finditer(r'(\w+)\s*=\s*"([^"]*)"', fix_spec):
            fix[m.group(1)] = m.group(2)

    if not isinstance(fix, dict):
        return f"REJECTED: could not parse fix_spec. Use JSON: {{\"target_type\":\"...\",\"target\":\"...\",\"action\":\"...\",\"reason\":\"...\"}}"

    target_type = fix.get("target_type", "").strip().lower()
    target = fix.get("target", "").strip()
    action = fix.get("action", "").strip().lower()
    reason = fix.get("reason", "").strip()

    if not (target_type and target and action):
        return "REJECTED: missing required fields (target_type, target, action)."

    if target_type not in ("class", "instance", "triple"):
        return (f"REJECTED: target_type must be 'class', 'instance', or 'triple', "
                f"not '{target_type}'.")
    if action not in ("remove", "swap", "move", "change_predicate", "swap_and_change"):
        return (f"REJECTED: action must be 'remove', 'swap', 'move', "
                f"'change_predicate', or 'swap_and_change', not '{action}'.")
    if action == "swap" and target_type != "triple":
        return "REJECTED: 'swap' action is only valid for target_type='triple'."
    if action == "move" and target_type != "instance":
        return "REJECTED: 'move' action is only valid for target_type='instance'."
    if action in ("change_predicate", "swap_and_change") and target_type != "triple":
        return f"REJECTED: '{action}' action is only valid for target_type='triple'."

    # Validate the target against the live schema — reject hallucinations early
    classes = SCHEMA.get("classes", {})
    props = SCHEMA.get("properties", {})

    if target_type == "class":
        if target not in classes:
            return (f"REJECTED: class '{target}' does not exist in the ontology. "
                    f"Do not propose fixes for non-existent classes.")
    elif target_type == "instance":
        if "|" not in target:
            return ("REJECTED: instance target must be formatted "
                    "'InstanceName | ParentClass' (or 'InstanceName | From -> To' for move).")
        inst_name, rest = [s.strip() for s in target.split("|", 1)]
        if action == "move":
            if "->" not in rest:
                return ("REJECTED: move target must be formatted "
                        "'InstanceName | FromClass -> ToClass'.")
            from_cls, to_cls = [s.strip() for s in rest.split("->", 1)]
            if from_cls not in classes:
                return f"REJECTED: source class '{from_cls}' does not exist."
            if to_cls not in classes:
                return f"REJECTED: destination class '{to_cls}' does not exist."
            if inst_name not in classes[from_cls].get("instances", []):
                return (f"REJECTED: '{inst_name}' is not currently an instance of "
                        f"'{from_cls}'. Check inspect_instances for correct placement.")
            if from_cls == to_cls:
                return f"REJECTED: source and destination are both '{from_cls}'."
        else:
            parent = rest
            if parent not in classes:
                return f"REJECTED: class '{parent}' does not exist."
            if inst_name not in classes[parent].get("instances", []):
                return (f"REJECTED: '{inst_name}' is not an instance of '{parent}'. "
                        f"Check inspect_instances for correct placement.")
    elif target_type == "triple":
        parts = [s.strip() for s in target.split("|")]
        if len(parts) != 3:
            return ("REJECTED: triple target must be formatted "
                    "'subject | predicate | object' "
                    "(or 'subj | oldPred -> newPred | obj' for change_predicate/swap_and_change).")
        subj, pred_field, obj = parts
        # For change_predicate / swap_and_change, pred_field is "old -> new"
        if action in ("change_predicate", "swap_and_change"):
            if "->" not in pred_field:
                return (f"REJECTED: for '{action}', the middle component must be "
                        f"'oldPredicate -> newPredicate'.")
            old_pred, new_pred = [s.strip() for s in pred_field.split("->", 1)]
            if old_pred not in props:
                return f"REJECTED: source property '{old_pred}' does not exist."
            if new_pred not in props:
                return f"REJECTED: destination property '{new_pred}' does not exist."
            examples = props[old_pred].get("examples", [])
            if [subj, old_pred, obj] not in examples and \
               (subj, old_pred, obj) not in [tuple(e) for e in examples]:
                return (f"REJECTED: triple '{subj} {old_pred} {obj}' not found in "
                        f"'{old_pred}'. Use list_triples('{old_pred}') to check.")
        else:
            pred = pred_field
            if pred not in props:
                return f"REJECTED: property '{pred}' does not exist."
            examples = props[pred].get("examples", [])
            if [subj, pred, obj] not in examples and (subj, pred, obj) not in [tuple(e) for e in examples]:
                return (f"REJECTED: triple '{subj} {pred} {obj}' not found in property "
                        f"'{pred}'. Use list_triples('{pred}') to see actual triples.")

    # Build a canonical signature for dedupe
    sig = (target_type, target.lower().strip(), action)
    for f in PROPOSED_FIXES:
        existing_sig = (f["target_type"], f["target"].lower().strip(), f["action"])
        if existing_sig == sig:
            return (f"ALREADY PROPOSED: {target_type} '{target}'. "
                    f"Do NOT propose this again. Find a DIFFERENT issue.")

    fix = {
        "target_type": target_type,
        "target": target,
        "action": action,
        "reason": reason,
    }
    PROPOSED_FIXES.append(fix)
    return (f"Fix #{len(PROPOSED_FIXES)} recorded: {action} {target_type} '{target}'. "
            f"Now find a DIFFERENT issue.")


def _apply_fix(schema: dict, fix: dict) -> tuple[bool, str]:
    target_type = fix["target_type"]
    target = fix["target"]
    action = fix["action"]
    classes = schema.get("classes", {})
    props = schema.get("properties", {})

    if target_type == "class" and action == "remove":
        if target not in classes:
            return False, f"class '{target}' no longer exists (already removed?)"
        # Remove from any parent's subclasses list
        for cn, cd in classes.items():
            if isinstance(cd, dict) and target in cd.get("subclasses", []):
                cd["subclasses"] = [s for s in cd["subclasses"] if s != target]
        # Remove any triples that reference this class as subject or object
        for prop_data in props.values():
            if isinstance(prop_data, dict):
                prop_data["examples"] = [
                    ex for ex in prop_data.get("examples", [])
                    if not (len(ex) >= 3 and (ex[0] == target or ex[2] == target))
                ]
        del classes[target]
        return True, f"removed class '{target}' (plus subclass links and related triples)"

    if target_type == "instance" and action == "remove":
        inst_name, parent = [s.strip() for s in target.split("|", 1)]
        if parent not in classes:
            return False, f"parent class '{parent}' no longer exists"
        instances = classes[parent].get("instances", [])
        if inst_name not in instances:
            return False, f"instance '{inst_name}' no longer in '{parent}'"
        classes[parent]["instances"] = [i for i in instances if i != inst_name]
        # Remove any triples that reference this instance
        for prop_data in props.values():
            if isinstance(prop_data, dict):
                prop_data["examples"] = [
                    ex for ex in prop_data.get("examples", [])
                    if not (len(ex) >= 3 and (ex[0] == inst_name or ex[2] == inst_name))
                ]
        return True, f"removed instance '{inst_name}' from '{parent}' (plus related triples)"

    if target_type == "instance" and action == "move":
        inst_name, rest = [s.strip() for s in target.split("|", 1)]
        from_cls, to_cls = [s.strip() for s in rest.split("->", 1)]
        if from_cls not in classes:
            return False, f"source class '{from_cls}' no longer exists"
        if to_cls not in classes:
            return False, f"destination class '{to_cls}' no longer exists"
        src = classes[from_cls].get("instances", [])
        if inst_name not in src:
            return False, f"instance '{inst_name}' no longer in '{from_cls}'"
        classes[from_cls]["instances"] = [i for i in src if i != inst_name]
        dst = classes[to_cls].get("instances", [])
        if inst_name not in dst:
            dst.append(inst_name)
            classes[to_cls]["instances"] = dst
        # Triples referencing this instance are kept — only its class membership
        # changed; the facts still hold.
        return True, f"moved instance '{inst_name}' from '{from_cls}' to '{to_cls}'"

    if target_type == "triple":
        parts = [s.strip() for s in target.split("|")]
        if len(parts) != 3:
            return False, "malformed triple target"
        subj, pred_field, obj = parts

        if action in ("change_predicate", "swap_and_change"):
            if "->" not in pred_field:
                return False, "change_predicate needs 'oldPred -> newPred' format"
            old_pred, new_pred = [s.strip() for s in pred_field.split("->", 1)]
            if old_pred not in props or new_pred not in props:
                return False, f"predicate missing (old='{old_pred}' new='{new_pred}')"
            src = props[old_pred].get("examples", [])
            idx = None
            for i, ex in enumerate(src):
                if list(ex) == [subj, old_pred, obj]:
                    idx = i; break
            if idx is None:
                return False, f"triple '{subj} {old_pred} {obj}' no longer in '{old_pred}'"
            src.pop(idx)
            # Compute the new triple (swap subj/obj for swap_and_change)
            if action == "swap_and_change":
                new_triple = [obj, new_pred, subj]
            else:
                new_triple = [subj, new_pred, obj]
            dst = props[new_pred].get("examples", [])
            if new_triple not in dst:
                dst.append(new_triple)
                props[new_pred]["examples"] = dst
            return True, (f"moved triple '{subj} {old_pred} {obj}' → "
                          f"'{new_triple[0]} {new_pred} {new_triple[2]}'")

        # remove / swap
        pred = pred_field
        if pred not in props:
            return False, f"property '{pred}' no longer exists"
        examples = props[pred].get("examples", [])
        target_triple = [subj, pred, obj]
        idx = None
        for i, ex in enumerate(examples):
            if list(ex) == target_triple:
                idx = i; break
        if idx is None:
            return False, f"triple '{subj} {pred} {obj}' no longer in '{pred}'"
        if action == "remove":
            examples.pop(idx)
            return True, f"removed triple '{subj} {pred} {obj}'"
        if action == "swap":
            examples[idx] = [obj, pred, subj]
            return True, f"swapped triple to '{obj} {pred} {subj}'"

    return False, f"unsupported combination: {target_type} + {action}"


def present_fixes_to_human(schema: dict, fixes: list[dict], output_path: Path):
    """Present agent's proposed fixes for human approval and apply accepted ones."""
    if not fixes:
        print("\n  Agent found no issues!")
        return

    print(f"\n{'='*60}")
    print(f"  Agent proposed {len(fixes)} fixes — review each:")
    print(f"{'='*60}")

    applied = 0
    skipped = 0
    rejected = 0
    failed = 0

    for i, fix in enumerate(fixes, 1):
        print(f"\n── Fix {i}/{len(fixes)} ──")
        print(f"  Type    : {fix['target_type']}")
        print(f"  Target  : {fix['target']}")
        print(f"  Action  : {fix['action']}")
        print(f"  Reason  : {fix['reason']}")

        choice = input("  Accept? [y/n/skip/all]: ").strip().lower()
        if choice == "all":
            # Auto-accept this and all remaining fixes
            ok, msg = _apply_fix(schema, fix)
            print(f"  {'✓ Applied' if ok else '✗ Failed'}: {msg}")
            applied += 1 if ok else 0
            failed += 0 if ok else 1
            # Process remaining automatically
            for j, remaining_fix in enumerate(fixes[i:], i + 1):
                print(f"\n── Fix {j}/{len(fixes)} (auto) ──")
                print(f"  {remaining_fix['action']} {remaining_fix['target_type']} '{remaining_fix['target']}'")
                ok, msg = _apply_fix(schema, remaining_fix)
                print(f"  {'✓ Applied' if ok else '✗ Failed'}: {msg}")
                applied += 1 if ok else 0
                failed += 0 if ok else 1
            break
        if choice == "y":
            ok, msg = _apply_fix(schema, fix)
            print(f"  {'✓ Applied' if ok else '✗ Failed'}: {msg}")
            applied += 1 if ok else 0
            failed += 0 if ok else 1
        elif choice == "skip":
            print("  → skipped")
            skipped += 1
        else:
            print("  → rejected")
            rejected += 1

    # Save only if any fix was applied
    if applied > 0:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=4, ensure_ascii=False)
        print(f"\n  Saved to {output_path}")

    print(f"\n  Summary: {applied} applied, {failed} failed, {rejected} rejected, {skipped} skipped")


# ── Main ─────────────────────────────────────────────────────────────────────

def run(model: str, input_path: str, output_path: str, provider: str = "ollama",
        max_passes: int = 5):
    global SCHEMA, PROPOSED_FIXES
    PROPOSED_FIXES = []  # accumulates ACROSS passes; dedupe in propose_fix prevents repeats

    SCHEMA = json.loads(Path(input_path).read_text(encoding="utf-8"))
    classes = SCHEMA.get("classes", {})
    properties = SCHEMA.get("properties", {})

    print(f"\nLoaded: {input_path}")
    print(f"  Classes    : {len(classes)}")
    print(f"  Properties : {len(properties)}")
    print(f"  Model      : {model}")
    print(f"  Max passes : {max_passes}")

    # Create tools list
    tools = [
        inspect_hierarchy,
        inspect_relationships,
        list_triples,
        inspect_instances,
        check_punning,
        check_dual_parents,
        check_self_referential,
        find_spelling_duplicates,
        check_biomarker_semantics,
        check_domain_range_violations,
        query_mesh,
        propose_fix,
    ]

    # Create LLM — use Groq for cloud models, Ollama for local
    if provider == "groq":
        import os
        from dotenv import load_dotenv
        from langchain_groq import ChatGroq
        load_dotenv()
        llm = ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"), temperature=0)
        print(f"  Provider   : Groq (cloud)")
    else:
        llm = ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url, temperature=0)
        print(f"  Provider   : Ollama (local)")

    # Create ReAct agent
    print(f"\n{'='*60}")
    print("  Starting ReAct Validation Agent (auto-loop)")
    print(f"{'='*60}\n")

    agent = create_react_agent(llm, tools, AGENT_PROMPT)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=25,
        max_execution_time=600,
    )

    if provider == "groq":
        from langchain.callbacks.base import BaseCallbackHandler

        class RateLimitHandler(BaseCallbackHandler):
            def on_agent_action(self, action, **kwargs):
                time.sleep(5)
        agent_executor.callbacks = [RateLimitHandler()]

    try:
        for pass_num in range(1, max_passes + 1):
            before_count = len(PROPOSED_FIXES)
            print(f"\n{'─'*60}")
            print(f"  Pass {pass_num}/{max_passes}  (fixes so far: {before_count})")
            print(f"  Press Ctrl+C any time to stop early and jump to HITL review")
            print(f"{'─'*60}\n")

            try:
                result = agent_executor.invoke({
                    "input": (
                        "Validate the AMD ontology. Find DIFFERENT issues from the ones "
                        "already proposed (the propose_fix tool will reject duplicates). "
                        "Use ALL inspection tools systematically: inspect_hierarchy, "
                        "inspect_relationships, inspect_instances, check_punning, "
                        "check_dual_parents, check_self_referential."
                    )
                })
                print(f"\n  Pass {pass_num} final answer: {result.get('output', 'No output')[:200]}")
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"\n  Pass {pass_num} error: {e}")
                print("  Continuing to next pass...")

            new_fixes = len(PROPOSED_FIXES) - before_count
            print(f"\n  Pass {pass_num} added {new_fixes} new fix(es). Total: {len(PROPOSED_FIXES)}")

            if new_fixes == 0:
                print(f"\n  Convergence reached — no new issues found in pass {pass_num}. Stopping.")
                break
        else:
            print(f"\n  Hit max_passes ({max_passes}). Some issues may remain undiscovered.")
    except KeyboardInterrupt:
        print(f"\n\n  Interrupted by user. Jumping to HITL review with {len(PROPOSED_FIXES)} fix(es) collected so far.")

    # Present fixes for human approval
    print(f"\n{'='*60}")
    print(f"  Human Review (HITL) — {len(PROPOSED_FIXES)} total fixes across all passes")
    print(f"{'='*60}")

    present_fixes_to_human(SCHEMA, PROPOSED_FIXES, Path(output_path))

    print(f"\n{'='*60}")
    print(f"  Validation complete — {len(PROPOSED_FIXES)} issues found by agent")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Agentic Ontology Validation — LangChain ReAct Agent")
    parser.add_argument("--model", default="llama3.1:8b",
                        help="Model name (default: llama3.1:8b)")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "groq"],
                        help="LLM provider: ollama (local) or groq (cloud)")
    parser.add_argument("--input", default=str(DEFAULT_INPUT),
                        help="Input ontology JSON")
    parser.add_argument("--output", default=None,
                        help="Output path (default: overwrites input)")
    parser.add_argument("--max-passes", type=int, default=5,
                        help="Max validation passes (auto-stops on convergence)")
    args = parser.parse_args()
    run(args.model, args.input, args.output or args.input, args.provider,
        max_passes=args.max_passes)


if __name__ == "__main__":
    main()
