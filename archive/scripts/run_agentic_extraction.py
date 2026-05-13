"""
Agentic Schema Extraction — LangChain Tool-Calling Agent.

Uses create_tool_calling_agent (native function calling) instead of
create_react_agent (text parsing) to avoid looping issues.

The agent:
  - Has the ontology summary + abstract in the prompt
  - Uses tools with proper parameter signatures (not JSON strings)
  - Groq handles tool calls natively — no text parsing

Stages:
  Stage 1: Domain spec → agent builds initial ontology
  Stage 2: Curated abstracts → agent adds new entities
  Stage 3: Full corpus → agent validates and extends

Usage:
    python run_agentic_extraction.py --provider groq --model llama-3.3-70b-versatile --stage 1
    python run_agentic_extraction.py --provider groq --model llama-3.3-70b-versatile --stage 2 --resume results/amd/stage-1/AMD/ontology_agentic.json
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

from schema_miner.config.envConfig import EnvConfig

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "agentic_extraction.log"
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

# ── Ontology Store ───────────────────────────────────────────────────────────

ONTOLOGY = {
    "classes": {},
    "properties": {},
    "individuals": {},
}

CURRENT_ABSTRACT = ""


def generate_compact_summary() -> str:
    """Generate compact text summary of the ontology."""
    lines = []
    classes = ONTOLOGY.get("classes", {})
    properties = ONTOLOGY.get("properties", {})

    if not classes and not properties:
        return "ONTOLOGY IS EMPTY."

    lines.append("CLASSES:")
    all_subclasses = set()
    for data in classes.values():
        if isinstance(data, dict):
            for sub in data.get("subclasses", []):
                all_subclasses.add(sub)

    roots = [name for name in classes if name not in all_subclasses]

    def format_class(name, indent=1):
        data = classes.get(name, {})
        if not isinstance(data, dict):
            return
        prefix = "  " * indent
        instances = data.get("instances", [])
        subs = data.get("subclasses", [])
        # Show first 5 instances only to keep summary compact
        if instances:
            shown = instances[:5]
            inst_str = f" [{', '.join(shown)}{'...(+' + str(len(instances)-5) + ')' if len(instances) > 5 else ''}]"
        else:
            inst_str = ""
        lines.append(f"{prefix}{name}{inst_str}")
        for sub in subs:
            format_class(sub, indent + 1)

    for root in roots:
        format_class(root)

    if properties:
        lines.append("\nPROPERTIES:")
        for prop_name, prop_data in properties.items():
            if isinstance(prop_data, dict):
                domain = prop_data.get("domain", "?")
                range_ = prop_data.get("range", "?")
                examples = prop_data.get("examples", [])
                lines.append(f"  {prop_name}: {domain} -> {range_} ({len(examples)} examples)")

    total_instances = sum(
        len(d.get("instances", []))
        for d in classes.values() if isinstance(d, dict)
    )
    lines.append(f"\nSTATS: {len(classes)} classes, {len(properties)} properties, {total_instances} instances")
    return "\n".join(lines)


def save_ontology(stage: str):
    output_dir = RESULTS_DIR / "final"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "amd_ontology_final.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(ONTOLOGY, f, indent=4, ensure_ascii=False)
    logger.info(f"Ontology saved to {output_file}")

    stage_dir = RESULTS_DIR / stage / "AMD"
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_file = stage_dir / "ontology_agentic.json"
    with open(stage_file, "w", encoding="utf-8") as f:
        json.dump(ONTOLOGY, f, indent=4, ensure_ascii=False)


# ── Tools (proper parameter signatures for native function calling) ──────────

_checked_cache = set()


def _normalize(name: str) -> str:
    """Normalize entity name for fuzzy matching: lowercase, remove hyphens/spaces."""
    return name.lower().replace("-", "").replace(" ", "").replace("_", "")


def _find_similar(entity_name: str) -> str | None:
    """Check if a similar entity already exists (fuzzy match)."""
    norm = _normalize(entity_name)
    classes = ONTOLOGY.get("classes", {})

    # Check class names
    for cn in classes:
        if _normalize(cn) == norm:
            return f"class:{cn}"

    # Check all instances
    for cn, data in classes.items():
        if isinstance(data, dict):
            for inst in data.get("instances", []):
                if _normalize(inst) == norm:
                    return f"instance:{inst} in {cn}"

    return None


@tool
def check_exists(entity_name: str) -> str:
    """Check if an entity already exists in the ontology.
    Call this ONCE per entity before adding. If NOT FOUND, proceed to add_class or add_instance."""
    entity_name = entity_name.strip()

    # Dedup: if already checked, tell agent to move on
    if entity_name in _checked_cache:
        return f"ALREADY CHECKED: '{entity_name}'. Do not re-check. Proceed to add or move to next entity."
    _checked_cache.add(entity_name)

    classes = ONTOLOGY.get("classes", {})
    properties = ONTOLOGY.get("properties", {})

    # Exact match
    if entity_name in classes:
        return f"FOUND: '{entity_name}' exists as a CLASS."

    for class_name, data in classes.items():
        if isinstance(data, dict) and entity_name in data.get("instances", []):
            return f"FOUND: '{entity_name}' exists as an INSTANCE of {class_name}."

    if entity_name in properties:
        return f"FOUND: '{entity_name}' exists as a PROPERTY."

    # Fuzzy match — catches "WetAMD" vs "Wet AMD" vs "Wet Age-related macular degeneration"
    similar = _find_similar(entity_name)
    if similar:
        return f"FOUND (similar): '{entity_name}' matches existing {similar}. Skip — do not add duplicate."

    return f"NOT FOUND: '{entity_name}' does not exist. Add it using add_class or add_instance."


@tool
def list_classes(query: str = "all") -> str:
    """List all classes in the ontology with their hierarchy and instances."""
    return generate_compact_summary()


@tool
def get_class(class_name: str) -> str:
    """Get details of a specific class: description, subclasses, and instances."""
    class_name = class_name.strip()
    classes = ONTOLOGY.get("classes", {})
    if class_name not in classes:
        return f"Class '{class_name}' not found."
    data = classes[class_name]
    desc = data.get("description", "")
    subs = data.get("subclasses", [])
    instances = data.get("instances", [])
    return f"Class: {class_name}\n  Description: {desc}\n  Subclasses: {subs}\n  Instances: {instances}"


@tool
def add_class(class_name: str, description: str, parent_class: str = "") -> str:
    """Add a new OWL class to the ontology. Call AFTER check_exists returned NOT FOUND.
    If parent_class is specified, the new class becomes a subclass of it."""
    class_name = class_name.strip()
    parent_class = parent_class.strip()
    classes = ONTOLOGY["classes"]

    if class_name in classes:
        return f"'{class_name}' already exists as a class. Move to next entity."

    # Fuzzy duplicate check for classes
    similar = _find_similar(class_name)
    if similar:
        return f"REJECTED: '{class_name}' is a duplicate of existing {similar}. Skip it."

    classes[class_name] = {
        "description": description,
        "subclasses": [],
        "instances": [],
    }

    if parent_class and parent_class in classes:
        if class_name not in classes[parent_class].get("subclasses", []):
            classes[parent_class]["subclasses"].append(class_name)

    logger.info(f"  ADDED CLASS: {class_name}" + (f" under {parent_class}" if parent_class else ""))
    return f"ADDED CLASS: '{class_name}'" + (f" as subclass of '{parent_class}'" if parent_class else "")


@tool
def add_instance(instance_name: str, class_name: str) -> str:
    """Add an individual (instance) to an existing OWL class. Call AFTER check_exists returned NOT FOUND.
    The class_name must already exist in the ontology."""
    instance_name = instance_name.strip()
    class_name = class_name.strip()
    classes = ONTOLOGY["classes"]

    if class_name not in classes:
        available = list(classes.keys())
        return f"Error: class '{class_name}' not found. Available classes: {available}"

    instances = classes[class_name].get("instances", [])
    if instance_name in instances:
        return f"'{instance_name}' already exists in {class_name}. Move to next entity."

    # Hallucination guard — entity must appear in abstract text
    if CURRENT_ABSTRACT and instance_name.lower() not in CURRENT_ABSTRACT.lower():
        return f"REJECTED: '{instance_name}' not found in abstract text. Only add entities from the abstract."

    # Reject very short names (not real entities)
    if len(instance_name) < 3:
        return f"REJECTED: '{instance_name}' is too short to be a medical entity. Skip it."

    # Fuzzy duplicate check — catches "WetAMD" vs "Wet AMD"
    similar = _find_similar(instance_name)
    if similar:
        return f"REJECTED: '{instance_name}' is a duplicate of existing {similar}. Skip it."

    instances.append(instance_name)
    classes[class_name]["instances"] = instances
    logger.info(f"  ADDED INSTANCE: {instance_name} -> {class_name}")
    return f"ADDED INSTANCE: '{instance_name}' to '{class_name}'"


@tool
def add_property(property_name: str, domain: str, range_class: str, description: str) -> str:
    """Add a new object property (relationship type) to the ontology."""
    property_name = property_name.strip()
    properties = ONTOLOGY["properties"]

    if property_name in properties:
        return f"Property '{property_name}' already exists. Move to next."

    properties[property_name] = {
        "domain": domain.strip(),
        "range": range_class.strip(),
        "description": description,
        "examples": [],
    }
    logger.info(f"  ADDED PROPERTY: {property_name} ({domain} -> {range_class})")
    return f"ADDED PROPERTY: '{property_name}' ({domain} -> {range_class})"


@tool
def add_relationship(subject: str, predicate: str, object_entity: str) -> str:
    """Add a relationship triple to an existing property.
    Example: subject='Ranibizumab', predicate='treats', object_entity='WetAMD'"""
    subject = subject.strip()
    predicate = predicate.strip()
    object_entity = object_entity.strip()

    properties = ONTOLOGY["properties"]
    if predicate not in properties:
        return f"Error: property '{predicate}' not found. Use existing: {list(properties.keys())}"

    # Block new property creation through relationships
    prop_data = properties[predicate]

    # Check for reversed relationships (e.g., "OCT diagnosedBy AMD" should be "AMD diagnosedBy OCT")
    domain_class = prop_data.get("domain", "")
    range_class = prop_data.get("range", "")
    classes = ONTOLOGY.get("classes", {})

    def _find_class_of(entity):
        if entity in classes:
            return entity
        for cn, cd in classes.items():
            if isinstance(cd, dict) and entity in cd.get("instances", []):
                return cn
            for sub in cd.get("subclasses", []) if isinstance(cd, dict) else []:
                if entity == sub:
                    return cn
        return None

    subject_class = _find_class_of(subject)
    object_class = _find_class_of(object_entity)

    # If subject matches range and object matches domain, it's reversed
    if subject_class and object_class:
        if subject_class == range_class and object_class == domain_class:
            subject, object_entity = object_entity, subject
            logger.info(f"  AUTO-CORRECTED reversed relationship: {subject} {predicate} {object_entity}")

    triple = [subject, predicate, object_entity]
    examples = properties[predicate].get("examples", [])
    if triple in examples:
        return f"Relationship '{subject} {predicate} {object_entity}' already exists."

    examples.append(triple)
    properties[predicate]["examples"] = examples
    logger.info(f"  ADDED RELATIONSHIP: {subject} {predicate} {object_entity}")
    return f"ADDED: '{subject} {predicate} {object_entity}'"


@tool
def get_relationships(entity_name: str) -> str:
    """Get all relationships involving a specific entity."""
    entity_name = entity_name.strip()
    results = []
    for prop_name, prop_data in ONTOLOGY.get("properties", {}).items():
        if not isinstance(prop_data, dict):
            continue
        for ex in prop_data.get("examples", []):
            if len(ex) >= 3 and (ex[0] == entity_name or ex[2] == entity_name):
                results.append(f"  {ex[0]} {ex[1]} {ex[2]}")
    if results:
        return f"Relationships for '{entity_name}':\n" + "\n".join(results)
    return f"No relationships found for '{entity_name}'."


# ── Prompts ──────────────────────────────────────────────────────────────────

STAGE1_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a biomedical ontology extraction agent for Age-Related Macular Degeneration (AMD).

Read the domain specification and BUILD the ontology using your tools.

VALID ENTITY TEST: a valid entity is something a clinician would record in
a patient chart, a pharmacist would dispense, a geneticist would map, a
radiologist would order, or a researcher would measure as a clinical outcome.
People, institutions, funders, study names, registries, source organisms, and
geographic locations are study metadata, NOT entities — skip them.

For every term that passes the valid entity test, ask:

(a) Is this a SPECIFIC named thing — a drug name, a gene symbol, a device,
    a measurement, a clinical outcome metric? → INSTANCE.
(b) Is this a GENERAL CATEGORY that groups 2 or more sibling things
    you can name from the text or medical knowledge? → CLASS.
(c) Cannot decide, or you cannot name 2+ members? → SKIP it.

Class hierarchy rules:
- Try to fit every new class as a SUBCLASS of an existing class first.
- Only create a new ROOT class if no existing root fits AND you can name
  3+ sibling categories of the same kind that need this root.
- A new root class is the LAST resort, not the first.

Properties (relationships) come from the text — define them as you find
relations expressed in the spec (treats, inhibits, causesOrIncreases,
indicates, diagnosedBy, associatedWith, measuredBy, hasSymptom, ...).

Use canonical names: collapse "anti-VEGF therapy" / "anti-VEGF agents" /
"VEGF inhibitors" to ONE entity. Prefer the shortest scientifically
standard form.

Use check_exists before adding. Never repeat a tool call with the same input."""),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])


def make_stage_prompt(ontology_summary: str, stage_name: str) -> ChatPromptTemplate:
    """Create stage 2/3 prompt with ontology summary in system message."""
    task = "extract new entities and relationships" if stage_name == "Stage 2" else "validate and extend"

    return ChatPromptTemplate.from_messages([
        ("system", f"""You are refining a medical ontology for AMD.

CURRENT ONTOLOGY:
{ontology_summary}

Task: Read the abstract and {task}.

VALID ENTITY TEST (apply BEFORE extracting): a valid entity is something a clinician would record in a patient chart, a pharmacist would dispense, a geneticist would map, a radiologist would order, or a researcher would measure as a clinical outcome. People, institutions, funders, study names, registries, source organisms, and geographic locations are study metadata, NOT entities — skip them.

WORKFLOW: Find sentences expressing a medical relationship (X treats Y, X causes Y, X diagnoses Y, X inhibits Y, X is associated with Y). The X and Y must pass the valid entity test. Anything else is NOT extracted.

For each entity: check_exists, then add_instance (specific named thing: drug, gene, device) or add_class (category that groups 2+ siblings). If you can't name 2+ siblings, it is NOT a class. Skip anything that fails both tests.

NEW CLASSES: try to fit as a subclass of an existing class first. Only create a new root class if no root fits AND you can name 3+ sibling categories needing it. An entity is EITHER class OR instance, never both.

CANONICAL NAMES: collapse synonyms to one entity (anti-VEGF therapy / VEGF inhibitors → AntiVEGFTherapy; wet AMD / neovascular AMD → WetAMD). Use the shortest standard form.

Never repeat check_exists for the same entity. After adding, move on."""),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])


# ── Stage Runners ────────────────────────────────────────────────────────────

ALL_TOOLS = None

def get_tools():
    global ALL_TOOLS
    if ALL_TOOLS is None:
        ALL_TOOLS = [check_exists, list_classes, get_class, add_class,
                     add_instance, add_property, add_relationship, get_relationships]
    return ALL_TOOLS


def create_llm(model: str, provider: str):
    if provider == "groq":
        from dotenv import load_dotenv
        load_dotenv()
        return ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"), temperature=0)
    return ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url, temperature=0)


def create_executor(llm, prompt, provider: str, max_iter: int = 30):
    tools = get_tools()
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True,
        handle_parsing_errors=True,
        max_iterations=max_iter, max_execution_time=600,
    )
    return executor


def run_stage1(llm, provider: str):
    logger.info("\n" + "=" * 60)
    logger.info("  STAGE 1: Build Initial Ontology from Domain Specification")
    logger.info("=" * 60)

    domain_spec = DOMAIN_SPEC_PATH.read_text(encoding="utf-8")
    if len(domain_spec) > 8000:
        logger.info(f"  Domain spec: {len(domain_spec)} chars — truncating to 8000")
        domain_spec = domain_spec[:8000]

    executor = create_executor(llm, STAGE1_PROMPT, provider, max_iter=50)

    try:
        result = executor.invoke({
            "input": f"Build an AMD ontology from this domain specification:\n\n{domain_spec}"
        })
        logger.info(f"\n  Stage 1 result: {result.get('output', 'Done')[:300]}")
    except Exception as e:
        logger.info(f"\n  Stage 1 error: {e}")

    save_ontology("stage-1")
    classes = ONTOLOGY.get("classes", {})
    total_instances = sum(len(d.get("instances", [])) for d in classes.values() if isinstance(d, dict))
    logger.info(f"\n  After Stage 1: {len(classes)} classes, {len(ONTOLOGY.get('properties', {}))} properties, {total_instances} instances")


def run_stage2(llm, provider: str, max_abstracts: int = None):
    logger.info("\n" + "=" * 60)
    logger.info("  STAGE 2: Refine with Curated Abstracts")
    logger.info("=" * 60)

    all_abstracts = sorted(STAGE2_ABSTRACTS_DIR.glob("*.txt"))
    abstracts = all_abstracts[:max_abstracts] if max_abstracts else all_abstracts
    if not abstracts:
        logger.info(f"  No abstracts in {STAGE2_ABSTRACTS_DIR}")
        return

    logger.info(f"  Processing {len(abstracts)} curated abstracts\n")

    for i, abstract_file in enumerate(abstracts):
        abstract_text = abstract_file.read_text(encoding="utf-8")
        logger.info(f"\n  --- [{i+1}/{len(abstracts)}] {abstract_file.name} ---")

        global CURRENT_ABSTRACT, _checked_cache
        CURRENT_ABSTRACT = abstract_text
        _checked_cache = set()  # Reset per abstract

        summary = generate_compact_summary()
        prompt = make_stage_prompt(summary, "Stage 2")
        executor = create_executor(llm, prompt, provider, max_iter=20)

        if provider == "groq":
            time.sleep(5)

        for attempt in range(3):
            try:
                result = executor.invoke({
                    "input": f"Extract new AMD entities from this abstract:\n\n{abstract_text}"
                })
                logger.info(f"  Result: {result.get('output', 'Done')[:200]}")
                break
            except Exception as e:
                if attempt < 2:
                    logger.info(f"  Attempt {attempt+1} failed: {e}. Retrying in 10s...")
                    time.sleep(10)
                else:
                    logger.info(f"  Error after 3 attempts: {e}. Skipping abstract.")

    save_ontology("stage-2")
    classes = ONTOLOGY.get("classes", {})
    total_instances = sum(len(d.get("instances", [])) for d in classes.values() if isinstance(d, dict))
    logger.info(f"\n  After Stage 2: {len(classes)} classes, {len(ONTOLOGY.get('properties', {}))} properties, {total_instances} instances")


def run_stage3(llm, provider: str, max_abstracts: int = None):
    logger.info("\n" + "=" * 60)
    logger.info("  STAGE 3: Validate and Extend with Full Corpus")
    logger.info("=" * 60)

    all_abstracts = sorted(STAGE3_ABSTRACTS_DIR.glob("*.txt"))
    abstracts = all_abstracts[:max_abstracts] if max_abstracts else all_abstracts
    if not abstracts:
        logger.info(f"  No abstracts in {STAGE3_ABSTRACTS_DIR}")
        return

    logger.info(f"  Processing {len(abstracts)} abstracts\n")

    for i, abstract_file in enumerate(abstracts):
        abstract_text = abstract_file.read_text(encoding="utf-8")
        logger.info(f"\n  --- [{i+1}/{len(abstracts)}] {abstract_file.name} ---")

        global CURRENT_ABSTRACT, _checked_cache
        CURRENT_ABSTRACT = abstract_text
        _checked_cache = set()

        summary = generate_compact_summary()
        prompt = make_stage_prompt(summary, "Stage 3")
        executor = create_executor(llm, prompt, provider, max_iter=15)

        if provider == "groq":
            time.sleep(5)

        # Retry up to 2 times on API errors
        for attempt in range(3):
            try:
                result = executor.invoke({
                    "input": f"Validate and extend from this abstract:\n\n{abstract_text}"
                })
                logger.info(f"  Result: {result.get('output', 'Done')[:200]}")
                break
            except Exception as e:
                if attempt < 2:
                    logger.info(f"  Attempt {attempt+1} failed: {e}. Retrying in 10s...")
                    time.sleep(10)
                else:
                    logger.info(f"  Error after 3 attempts: {e}. Skipping abstract.")

        if (i + 1) % 10 == 0:
            save_ontology("stage-3")
            classes = ONTOLOGY.get("classes", {})
            total_instances = sum(len(d.get("instances", [])) for d in classes.values() if isinstance(d, dict))
            logger.info(f"\n  Progress: {len(classes)} classes, {total_instances} instances")

    save_ontology("stage-3")
    classes = ONTOLOGY.get("classes", {})
    total_instances = sum(len(d.get("instances", [])) for d in classes.values() if isinstance(d, dict))
    logger.info(f"\n  After Stage 3: {len(classes)} classes, {len(ONTOLOGY.get('properties', {}))} properties, {total_instances} instances")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agentic Schema Extraction")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "groq"])
    parser.add_argument("--stage", type=int, default=None)
    parser.add_argument("--max-abstracts", type=int, default=None)
    parser.add_argument("--resume", type=str, default=None)
    args = parser.parse_args()

    logger.info("\n" + "=" * 60)
    logger.info("  SCHEMA-MINERpro — Agentic Extraction")
    logger.info("=" * 60)
    logger.info(f"  Model    : {args.model}")
    logger.info(f"  Provider : {args.provider}")

    llm = create_llm(args.model, args.provider)

    if args.resume:
        global ONTOLOGY
        ONTOLOGY = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        logger.info(f"  Resumed from: {args.resume}")
        logger.info(f"\n{generate_compact_summary()}")

    if args.stage == 1 or args.stage is None:
        run_stage1(llm, args.provider)

    if args.stage == 2 or (args.stage is None and args.resume is None):
        run_stage2(llm, args.provider, args.max_abstracts)
    elif args.stage == 2:
        run_stage2(llm, args.provider, args.max_abstracts)

    if args.stage == 3 or (args.stage is None and args.resume is None):
        run_stage3(llm, args.provider, args.max_abstracts)
    elif args.stage == 3:
        run_stage3(llm, args.provider, args.max_abstracts)

    save_ontology("final")

    classes = ONTOLOGY.get("classes", {})
    properties = ONTOLOGY.get("properties", {})
    total_instances = sum(
        len(d.get("instances", []))
        for d in classes.values() if isinstance(d, dict)
    )

    logger.info("\n" + "=" * 60)
    logger.info("  EXTRACTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Classes     : {len(classes)}")
    logger.info(f"  Properties  : {len(properties)}")
    logger.info(f"  Instances   : {total_instances}")
    logger.info(f"\n{generate_compact_summary()}")
    logger.info("=" * 60 + "\n")


if __name__ == "__main__":
    main()
