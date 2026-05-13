"""
Phase 1 — Agentic Harvest (entity + triple pool).

Memory-safe agentic extraction. The LLM never sees the full ontology — only
a compact summary of what's been harvested so far, plus one abstract. It
records what it finds into a flat POOL via two simple tools:

  - record_entity(name, category_hint)
  - record_triple(subject, predicate, object_entity)

No hierarchy decisions are made during harvesting. That is done holistically
in Phase 2 (run_reorganize_ontology.py) on the full pool.

Stages are unchanged:
  Stage 1: domain specification
  Stage 2: curated abstracts (stage-2/AMD/abstracts)
  Stage 3: full corpus   (stage-3/AMD/abstracts)

Usage:
  python run_agentic_harvest.py --provider groq --model llama-3.3-70b-versatile
  python run_agentic_harvest.py --provider groq --model llama-3.3-70b-versatile --stage 2 --resume results/amd/pool/amd_pool.json
  python run_agentic_harvest.py --provider ollama --model qwen2.5:32b --stage 3 --max-abstracts 10

Output: results/amd/pool/amd_pool.json
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
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

from schema_miner.config.envConfig import EnvConfig

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "agentic_harvest.log"
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
POOL_DIR = PROJECT_ROOT / "results" / "amd" / "pool"
POOL_FILE = POOL_DIR / "amd_pool.json"

# ── The flat pool ────────────────────────────────────────────────────────────

POOL = {
    "entities": {},   # name -> {"hint": str, "mentions": int}
    "triples": [],    # list of [subject, predicate, object]
}

CURRENT_ABSTRACT = ""
_VALID_HINTS = {
    "drug", "gene", "diagnostic", "disease", "outcome", "risk_factor",
    "biomarker", "treatment", "anatomy", "molecular_target", "other",
}
_VALID_PREDICATES = {
    "treats", "inhibits", "causesOrIncreases", "diagnosedBy", "associatedWith",
    "measuredBy", "hasSymptom", "assessedBy", "indicates",
}


def _normalize(name: str) -> str:
    return name.lower().strip().replace("-", "").replace(" ", "").replace("_", "")


def save_pool():
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(POOL, f, indent=2, ensure_ascii=False)
    logger.info(f"  Pool saved to {POOL_FILE}")


def compact_summary() -> str:
    ents = POOL["entities"]
    if not ents:
        return "POOL IS EMPTY."
    by_hint = {}
    for n, d in ents.items():
        by_hint.setdefault(d["hint"], []).append(n)
    lines = [f"POOL: {len(ents)} entities, {len(POOL['triples'])} triples"]
    for hint in sorted(by_hint):
        names = by_hint[hint]
        shown = names[:6]
        suffix = f"...(+{len(names)-6})" if len(names) > 6 else ""
        lines.append(f"  {hint} ({len(names)}): {', '.join(shown)}{suffix}")
    return "\n".join(lines)


# ── Tools ────────────────────────────────────────────────────────────────────

@tool
def record_entity(name: str, category_hint: str) -> str:
    """Record a medical entity you found in the abstract.

    name: the entity as it appears (e.g., "Ranibizumab", "CFH", "OCT",
          "WetAMD", "Choroidal Neovascularization").
    category_hint: your best guess at the rough type. Must be one of:
      drug, gene, diagnostic, disease, outcome, risk_factor,
      biomarker, treatment, anatomy, molecular_target, other.
      (Hierarchy decisions are made later — you only give a rough hint.)
    """
    name = name.strip()
    hint = category_hint.strip().lower()

    if len(name) < 3:
        return f"REJECTED: '{name}' is too short."
    if hint not in _VALID_HINTS:
        return (f"REJECTED: hint '{hint}' not in {sorted(_VALID_HINTS)}. "
                f"Use 'other' if unsure.")

    # Hallucination guard: must appear in the abstract text
    if CURRENT_ABSTRACT and name.lower() not in CURRENT_ABSTRACT.lower():
        return (f"REJECTED: '{name}' not found in the abstract text. "
                f"Only record entities that actually appear in the text.")

    # Non-medical filter: the LLM itself decides via the hint system,
    # but we still block obvious person-name patterns (Mr/Dr/Professor etc.)
    lc = name.lower()
    if any(lc.startswith(p) for p in ("mr ", "mrs ", "dr ", "prof ", "professor ")):
        return (f"REJECTED: '{name}' looks like a person name, not a medical entity. "
                f"Do not record people, institutions, or study names.")

    # Fuzzy dedupe
    norm = _normalize(name)
    for existing in POOL["entities"]:
        if _normalize(existing) == norm:
            POOL["entities"][existing]["mentions"] += 1
            return (f"ALREADY RECORDED: '{name}' matches existing '{existing}'. "
                    f"Move on to a DIFFERENT entity.")

    POOL["entities"][name] = {"hint": hint, "mentions": 1}
    logger.info(f"  RECORDED: {name}  [{hint}]")
    return f"RECORDED: '{name}' ({hint}). Move on to the NEXT entity."


@tool
def record_triple(subject: str, predicate: str, object_entity: str) -> str:
    """Record a medical relationship triple found in the abstract.

    predicate MUST be one of:
      treats, inhibits, causesOrIncreases, diagnosedBy, associatedWith,
      measuredBy, hasSymptom, assessedBy, indicates.

    Direction matters: for "treats", the subject is the Treatment and the
    object is the Disease (e.g., 'Ranibizumab treats WetAMD'). For
    "diagnosedBy", the subject is the Disease (e.g., 'AMD diagnosedBy OCT').
    """
    subj = subject.strip()
    pred = predicate.strip()
    obj = object_entity.strip()

    if pred not in _VALID_PREDICATES:
        return f"REJECTED: predicate must be one of {sorted(_VALID_PREDICATES)}."

    triple = [subj, pred, obj]
    # Fuzzy dedupe
    norm_triple = (_normalize(subj), pred, _normalize(obj))
    for ex in POOL["triples"]:
        if (_normalize(ex[0]), ex[1], _normalize(ex[2])) == norm_triple:
            return f"ALREADY RECORDED: {subj} {pred} {obj}. Move on."

    POOL["triples"].append(triple)
    logger.info(f"  RECORDED TRIPLE: {subj} {pred} {obj}")
    return f"RECORDED: '{subj} {pred} {obj}'. Move on to NEXT relationship."


@tool
def list_entities_by_hint(hint: str = "all") -> str:
    """List entities already recorded. Pass 'all' or a specific hint
    (drug, gene, diagnostic, etc.) to filter."""
    hint = hint.strip().lower()
    ents = POOL["entities"]
    if hint != "all":
        ents = {n: d for n, d in ents.items() if d["hint"] == hint}
    if not ents:
        return "No entities found."
    return ", ".join(sorted(ents.keys()))


# ── Prompts ──────────────────────────────────────────────────────────────────

STAGE1_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a biomedical entity harvester for Age-Related Macular Degeneration (AMD).

Read the domain specification below and record every medical entity and every
medical relationship triple you find using your tools.

DO NOT worry about class hierarchy, parent classes, or ontology structure —
that is handled in a later phase. Your ONLY job is:

  1. Call record_entity for every medical entity, with a rough category_hint.
  2. Call record_triple for every relationship you can express using one of
     the allowed predicates.

Valid category hints: drug, gene, diagnostic, disease, outcome, risk_factor,
biomarker, treatment, anatomy, molecular_target, other.

Valid predicates: treats, inhibits, causesOrIncreases, diagnosedBy,
associatedWith, measuredBy, hasSymptom, assessedBy, indicates.

DO NOT record: people, institutions, funders, study names/acronyms,
patient cohort sizes, p-values, geographic locations, populations, time
periods, study designs. These are study metadata, not entities.

Be thorough. Missed entities cannot be added later."""),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])


def make_abstract_prompt(summary: str, task: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", f"""You are a biomedical entity harvester for AMD.

CURRENT POOL:
{summary}

Task: Read the abstract and {task}.

Record each medical entity with record_entity (give a category_hint).
Record each relationship with record_triple (pick the correct predicate
and direction).

Valid hints: drug, gene, diagnostic, disease, outcome, risk_factor,
biomarker, treatment, anatomy, molecular_target, other.

Valid predicates: treats, inhibits, causesOrIncreases, diagnosedBy,
associatedWith, measuredBy, hasSymptom, assessedBy, indicates.

DO NOT record people, institutions, study names, places, time periods,
or study designs. DO NOT worry about class hierarchy — that is decided
in a later phase.

If an entity or triple is already in the pool, the tool will tell you
and you should move on. Be systematic, not exhaustive in any one area —
cover the full abstract."""),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])


# ── Runners ──────────────────────────────────────────────────────────────────

ALL_TOOLS = [record_entity, record_triple, list_entities_by_hint]


def create_llm(model: str, provider: str):
    if provider == "groq":
        from dotenv import load_dotenv
        load_dotenv()
        return ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"), temperature=0)
    return ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url, temperature=0)


def create_executor(llm, prompt, max_iter: int = 25):
    agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)
    return AgentExecutor(
        agent=agent, tools=ALL_TOOLS, verbose=True,
        handle_parsing_errors=True,
        max_iterations=max_iter, max_execution_time=600,
    )


def run_stage1(llm):
    logger.info("\n" + "=" * 60)
    logger.info("  STAGE 1: Harvest from domain specification")
    logger.info("=" * 60)

    spec = DOMAIN_SPEC_PATH.read_text(encoding="utf-8")
    if len(spec) > 8000:
        logger.info(f"  Domain spec: {len(spec)} chars — truncating to 8000")
        spec = spec[:8000]

    global CURRENT_ABSTRACT
    CURRENT_ABSTRACT = spec

    executor = create_executor(llm, STAGE1_PROMPT, max_iter=40)
    try:
        result = executor.invoke({
            "input": f"Harvest all medical entities and relationships from this AMD domain specification:\n\n{spec}"
        })
        logger.info(f"\n  Stage 1 result: {result.get('output', 'Done')[:300]}")
    except Exception as e:
        logger.info(f"\n  Stage 1 error: {e}")

    save_pool()
    logger.info(f"\n  After Stage 1: {len(POOL['entities'])} entities, {len(POOL['triples'])} triples")


def run_abstracts(llm, stage_name: str, directory: Path, max_abstracts: int = None,
                   provider: str = "ollama"):
    logger.info("\n" + "=" * 60)
    logger.info(f"  {stage_name}: Harvest from {directory.name}")
    logger.info("=" * 60)

    all_files = sorted(directory.glob("*.txt"))
    files = all_files[:max_abstracts] if max_abstracts else all_files
    if not files:
        logger.info(f"  No abstracts in {directory}")
        return

    logger.info(f"  Processing {len(files)} abstracts")

    for i, f in enumerate(files):
        text = f.read_text(encoding="utf-8")
        logger.info(f"\n  --- [{i+1}/{len(files)}] {f.name} ---")

        global CURRENT_ABSTRACT
        CURRENT_ABSTRACT = text

        summary = compact_summary()
        task = "harvest new entities and relationships"
        prompt = make_abstract_prompt(summary, task)
        executor = create_executor(llm, prompt, max_iter=20)

        if provider == "groq":
            time.sleep(5)

        for attempt in range(3):
            try:
                result = executor.invoke({
                    "input": f"Abstract:\n\n{text}"
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
            save_pool()
            logger.info(f"  Progress: {len(POOL['entities'])} entities, {len(POOL['triples'])} triples")

    save_pool()
    logger.info(f"\n  After {stage_name}: {len(POOL['entities'])} entities, {len(POOL['triples'])} triples")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agentic Harvest (Phase 1)")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "groq"])
    parser.add_argument("--stage", type=int, default=None,
                        help="Run only a specific stage (1, 2, or 3)")
    parser.add_argument("--max-abstracts", type=int, default=None)
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume from a previously saved pool JSON")
    args = parser.parse_args()

    logger.info("\n" + "=" * 60)
    logger.info("  SCHEMA-MINERpro — Phase 1 (Agentic Harvest)")
    logger.info("=" * 60)
    logger.info(f"  Model    : {args.model}")
    logger.info(f"  Provider : {args.provider}")

    llm = create_llm(args.model, args.provider)

    if args.resume:
        global POOL
        POOL = json.loads(Path(args.resume).read_text(encoding="utf-8"))
        logger.info(f"  Resumed from: {args.resume}")
        logger.info(f"\n{compact_summary()}")

    if args.stage == 1 or args.stage is None:
        run_stage1(llm)

    if args.stage == 2 or (args.stage is None and not args.resume):
        run_abstracts(llm, "STAGE 2", STAGE2_ABSTRACTS_DIR, args.max_abstracts, args.provider)
    elif args.stage == 2:
        run_abstracts(llm, "STAGE 2", STAGE2_ABSTRACTS_DIR, args.max_abstracts, args.provider)

    if args.stage == 3 or (args.stage is None and not args.resume):
        run_abstracts(llm, "STAGE 3", STAGE3_ABSTRACTS_DIR, args.max_abstracts, args.provider)
    elif args.stage == 3:
        run_abstracts(llm, "STAGE 3", STAGE3_ABSTRACTS_DIR, args.max_abstracts, args.provider)

    save_pool()
    logger.info("\n" + "=" * 60)
    logger.info("  HARVEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Entities  : {len(POOL['entities'])}")
    logger.info(f"  Triples   : {len(POOL['triples'])}")
    logger.info(f"  Saved to  : {POOL_FILE}")
    logger.info(f"\n{compact_summary()}")
    logger.info("\n  Next: run run_reorganize_ontology.py to build the structured ontology.\n")


if __name__ == "__main__":
    main()
