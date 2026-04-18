"""
Agentic Ontology Validation — LangChain ReAct Agent with Tools.

A LangChain agent that AUTONOMOUSLY decides which validation tools to use,
reasons about the ontology, and proposes fixes.

The agent has access to tools:
  - inspect_hierarchy: see class-subclass structure
  - inspect_relationships: see property definitions and examples
  - inspect_instances: see class-instance assignments
  - check_punning: detect class/individual conflicts
  - check_dual_parents: detect entities under multiple parents
  - check_self_referential: detect subject==object in properties
  - query_mesh: look up a concept in MeSH to verify it exists
  - propose_fix: record a proposed fix for human review

The agent reasons in a ReAct loop (Thought → Action → Observation → ...)
and decides what to check based on what it finds.

Usage:
    python run_validate_ontology_agent.py
    python run_validate_ontology_agent.py --model qwen2.5:32b
    python run_validate_ontology_agent.py --input results/amd/final/amd_ontology_final.json
"""

import argparse
import json
import time
from pathlib import Path

import requests
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain.agents import create_react_agent, AgentExecutor

from schema_miner.config.envConfig import EnvConfig

PROJECT_ROOT = Path(__file__).parent
DEFAULT_INPUT = PROJECT_ROOT / "results" / "amd" / "final" / "amd_ontology_final.json"

# ── Global state — loaded schema and collected fixes ─────────────────────────

SCHEMA = {}
PROPOSED_FIXES = []

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EMAIL = "calina.borzan18@yahoo.com"


# ── Tools for the agent ──────────────────────────────────────────────────────

@tool
def inspect_hierarchy(query: str = "none") -> str:
    """Inspect the class hierarchy of the ontology. Shows ALL classes with their subclasses and descriptions. Use this FIRST to understand the ontology structure. Action Input should be: none"""
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
    """Inspect all property definitions WITHOUT triples. Shows property name, domain, range, description, and the COUNT of triples for each. To see actual triples for a specific property, use list_triples. Action Input should be: none"""
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
    """Inspect all class-instance assignments — shows EVERY instance under EVERY class (no truncation). Use to find misclassified entities or instances under wrong parent. Action Input should be: none"""
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
    """Check for punning violations — entities that are BOTH a class AND an individual. This is an OWL violation. Action Input should be: none"""
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
    """Check for entities that are subclass of multiple parents. This can cause logical conflicts in OWL. Action Input should be: none"""
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
    """Check for self-referential property examples where subject equals object (e.g., 'X causesOrIncreases X'). Action Input should be: none"""
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
    """Propose a STRUCTURED fix that can be applied deterministically.

    Input is ONE string in JSON format with these fields:
    {"target_type": "...", "target": "...", "action": "...", "reason": "..."}

    target_type MUST be one of:
      - "class"    : remove a whole class from the ontology
      - "instance" : remove one specific instance from a class
      - "triple"   : remove OR swap a specific (subject, predicate, object) triple

    target MUST be formatted based on target_type:
      - class    : the class name only, e.g. "StudyDesign"
      - instance : "InstanceName | ParentClass", e.g. "Steve Jennings | Treatment"
      - triple   : "subject | predicate | object", e.g. "AMD | treats | Aspirin"

    action MUST be one of:
      - "remove" : delete the class/instance/triple  (valid for all target_types)
      - "swap"   : swap subject and object of a triple  (ONLY valid for target_type=triple)

    reason: short human-readable justification (one sentence).

    Example JSON input:
      {"target_type": "triple", "target": "AMD | treats | Aspirin",
       "action": "swap", "reason": "Aspirin treats AMD, not vice versa"}
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
    if action not in ("remove", "swap"):
        return f"REJECTED: action must be 'remove' or 'swap', not '{action}'."
    if action == "swap" and target_type != "triple":
        return "REJECTED: 'swap' action is only valid for target_type='triple'."

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
                    "'InstanceName | ParentClass'.")
        inst_name, parent = [s.strip() for s in target.split("|", 1)]
        if parent not in classes:
            return f"REJECTED: class '{parent}' does not exist."
        if inst_name not in classes[parent].get("instances", []):
            return (f"REJECTED: '{inst_name}' is not an instance of '{parent}'. "
                    f"Check inspect_instances for correct placement.")
    elif target_type == "triple":
        parts = [s.strip() for s in target.split("|")]
        if len(parts) != 3:
            return ("REJECTED: triple target must be formatted "
                    "'subject | predicate | object'.")
        subj, pred, obj = parts
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


# ── Agent prompt ─────────────────────────────────────────────────────────────

AGENT_PROMPT = PromptTemplate.from_template("""You are a biomedical ontology validation agent for an Age-Related Macular Degeneration (AMD) ontology.

Your job is to systematically validate the ontology by using your tools to inspect the structure, find issues, and propose fixes.

SCOPE RULES — READ CAREFULLY BEFORE PROPOSING ANY FIXES:

1. This is an AMD-CENTERED ontology, NOT an AMD-only ontology. Adjacent and
   co-morbid eye diseases (Glaucoma, Cataract, DiabeticRetinopathy,
   ProliferativeDiabeticRetinopathy, MacularEdema, RetinalVeinOcclusion,
   OcularHistoplasmosisSyndrome, NeurodegenerativeDisease, etc.) are IN SCOPE.
   Do NOT propose removing them. They are legitimately related to AMD research.

2. DO NOT swap a triple's direction unless you are CERTAIN the original is
   medically wrong. A correctly directed triple like "Aspirin treats AMD"
   (Treatment → Disease) or "Phenylephrine treats ArterialHypotension"
   (Treatment → Disease) must NOT be reversed. Check the domain/range of the
   property: if the subject matches the domain and the object matches the
   range, the direction is CORRECT — do not swap.

3. Only propose removing entities that are genuinely non-medical: study names,
   populations/demographics (e.g., AmishCommunity), biological processes
   (WoundRepair, CellInjury, CellDeath), or cell types used as classes.

4. Do NOT remove a class just because it has few or zero instances. Empty
   classes may be valid structural categories.

Follow this validation plan — be THOROUGH, check EVERY instance:

1. Use inspect_hierarchy to see EVERY class with EVERY instance.
2. Use inspect_instances to see every (class, instances) pair in full.
3. Now go through EACH class's instance list one by one and ask:
   - Is this a study name or acronym? (e.g., PrONTO, GARM, LUCAS, APGS are
     study names, not clinical outcomes)
   - Is this an anatomical structure rather than a biomarker? (e.g., Fovea,
     Photoreceptors are anatomy, not biomarkers)
   - Is this a non-disease listed under Disease? (e.g., normal states like
     Emmetropes, or findings like CNV that belong elsewhere)
   - Is this a chemical compound misplaced as a risk factor? (e.g.,
     Phenylthiocarbamide is a taste compound used in genetics research)
   - Use query_mesh on ANY instance you are unsure about.
   - Propose a fix IMMEDIATELY for each issue found.
4. Use check_punning, check_dual_parents, check_self_referential.
5. Use list_triples on EACH property that has triples — check direction
   errors (but VERIFY against domain/range before proposing a swap).
6. Check if any class is an orphan (not linked to any parent) — propose
   fixes for orphan classes that should be subclasses of a root.

CRITICAL:
- Be EXHAUSTIVE. Check every single instance in every class. Do not stop
  after finding 2-3 issues — there may be 10+.
- Only report issues you can SEE in the tool output.
- Every issue must reference a specific class, instance, or triple.
- Do NOT call the same tool twice with the same input.

Types of issues to look for:
- Study names/acronyms as instances (they are NOT medical entities)
- Anatomical structures listed as biomarkers (Fovea, Photoreceptors)
- Non-diseases under Disease (normal states, findings, processes)
- Non-risk-factors under RiskFactor (chemicals, foods, places)
- Orphan classes not linked to any root class
- Duplicate entities (brand name + generic name as separate instances)

You have access to the following tools:

{tools}

IMPORTANT: Use EXACTLY this format (no parentheses on Action, no extra text on Action Input):

Thought: I need to inspect the hierarchy first
Action: inspect_hierarchy
Action Input: none
Observation: the result of the action

Thought: Now I need to check for punning
Action: check_punning
Action Input: none
Observation: the result of the action

Thought: Let me verify a concept in MeSH
Action: query_mesh
Action Input: Ranibizumab
Observation: the result of the action

Thought: I found a reversed triple, let me propose a fix
Action: propose_fix
Action Input: {{"target_type": "triple", "target": "AMD | treats | Aspirin", "action": "swap", "reason": "Aspirin treats AMD, not the other way around"}}
Observation: Fix recorded

Thought: I found a non-medical instance, let me propose removing it
Action: propose_fix
Action Input: {{"target_type": "instance", "target": "Steve Jennings | Treatment", "action": "remove", "reason": "Person name, not a medical treatment"}}
Observation: Fix recorded

Thought: I found a noise class, let me propose removing it
Action: propose_fix
Action Input: {{"target_type": "class", "target": "StudyDesign", "action": "remove", "reason": "Study metadata, not a medical category"}}
Observation: Fix recorded

When you are done with all checks, end with EXACTLY this format.
Use the literal string "Final Answer:" — do NOT use LaTeX, do NOT use
markdown, do NOT use boxed{{}} notation, do NOT write "The final answer is":

Thought: I have completed my validation
Final Answer: Summary of all issues found and fixes proposed

Available tools: [{tool_names}]

Begin validation now!

{agent_scratchpad}""")


# ── HITL: Present fixes for human approval ───────────────────────────────────

def _apply_fix(schema: dict, fix: dict) -> tuple[bool, str]:
    """Deterministically apply one structured fix to the schema dict.
    Returns (success, message)."""
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

    if target_type == "triple":
        subj, pred, obj = [s.strip() for s in target.split("|")]
        if pred not in props:
            return False, f"property '{pred}' no longer exists"
        examples = props[pred].get("examples", [])
        target_triple = [subj, pred, obj]
        # Match either list or tuple form
        idx = None
        for i, ex in enumerate(examples):
            if list(ex) == target_triple:
                idx = i
                break
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

    # Add rate limit handling for Groq
    if provider == "groq":
        from langchain.callbacks.base import BaseCallbackHandler

        class RateLimitHandler(BaseCallbackHandler):
            def on_agent_action(self, action, **kwargs):
                time.sleep(5)  # 5 second pause between tool calls to avoid rate limit

        agent_executor.callbacks = [RateLimitHandler()]

    # ── Auto-loop: keep running until a pass produces zero new fixes ──────────
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
