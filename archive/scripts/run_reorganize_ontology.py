"""
Phase 2 — Holistic Ontology Reorganization.

Takes the flat entity+triple pool from Phase 1 (run_agentic_harvest.py) and
reorganizes it into a coherent hierarchical OWL ontology via a SINGLE LLM
call. This is the "holistic output" phase that restores structural
coherence — per-entity agentic tool calls produce tag-cloud output; a single
whole-schema pass is what gives you clean hierarchies like
'Treatment → AntiVEGFTherapy → [Ranibizumab, Aflibercept, ...]'.

Memory is fine here: the input is just a few KB of names and triples
(not the full schema), and the output is the full schema — but we only
produce it ONCE, not per abstract.

Usage:
  python run_reorganize_ontology.py --provider groq --model llama-3.3-70b-versatile
  python run_reorganize_ontology.py --provider ollama --model qwen2.5:32b

Input : results/amd/pool/amd_pool.json
Output: results/amd/final/amd_ontology_final.json
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from schema_miner.config.envConfig import EnvConfig

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "reorganize_ontology.log"
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
POOL_FILE = PROJECT_ROOT / "results" / "amd" / "pool" / "amd_pool.json"
OUTPUT_DIR = PROJECT_ROOT / "results" / "amd" / "final"
OUTPUT_FILE = OUTPUT_DIR / "amd_ontology_final.json"


SYSTEM_PROMPT = """You are a biomedical ontology architect for Age-Related Macular Degeneration (AMD).

You will receive a FLAT POOL of medical entities and relationship triples that
were harvested from AMD research abstracts. Your job is to reorganize them
into a coherent hierarchical OWL ontology.

TARGET SHAPE (the structure your output MUST follow):

  Disease
    AMD                        (intermediate class)
      DryAMD, WetAMD, GeographicAtrophy, IntermediateAMD,
      NonExudativeAMD, ReticularPseudodrusen, ...
    Glaucoma, DiabeticRetinopathy, OcularHistoplasmosisSyndrome,
    PathologicMyopia, MacularEdema, ...   (related eye diseases, sibling of AMD)

  Treatment
    AntiVEGFTherapy             → instances: specific drugs (Ranibizumab, ...)
    SurgicalTherapy             → instances: specific procedures (PDT, LaserPhotocoagulation, ...)
    Supplements                 → instances: specific nutrients (Lutein, Zeaxanthin, AREDS, ...)
    CorticosteroidTherapy       → instances: specific corticosteroids
    EmergingTherapies           → instances: experimental treatments
    ... create other Treatment subclasses as the pool demands

  GeneticBiomarker              → instances: specific genes and SNPs (CFH, ARMS2, HTRA1, rs11200638, ...)
  MolecularTarget               → instances: VEGF, PDGF, ComplementPathwayProteins, ...
  ImmunologicalBiomarker        → instances: cytokines, immune markers
  ImagingBiomarker
    StructuralBiomarker         → instances: Drusen, RetinalThickness, SubretinalFluid, ...
    FunctionalBiomarker         → instances: VisualAcuity, ContrastSensitivity, ReadingSpeed, ...

  DiagnosticMethod
    ImagingMethod               → instances: OCT, FluoresceinAngiography, FundusPhotography, ...
    FunctionalMethod            → instances: VisualFieldTesting, Electroretinography, ETDRS, ...

  RiskFactor
    NonModifiableRiskFactor     → instances: Age, Genetics, FamilyHistory, ...
    ModifiableRiskFactor        → instances: Smoking, Diet, BMI, SunExposure, ...

  ClinicalOutcome
    PrimaryOutcome              → instances: VisualAcuityChange, PreventionOfVisionLoss, ...
    SecondaryOutcome            → instances: LesionSizeChange, CNVRegression, QualityOfLifeChange, ...

CLASS vs INSTANCE rule:
  - Subclasses are CATEGORIES that group 2+ siblings (WetAMD, AntiVEGFTherapy, StructuralBiomarker).
  - Instances are SPECIFIC named things that cannot meaningfully have subtypes
    (Ranibizumab, CFH, OCT, Drusen).
  - An entity is EITHER a class OR an instance, never both.

Rules for reorganization:
  1. Every entity in the pool MUST end up somewhere in the output —
     either as a class, a subclass, or an instance — UNLESS it is clearly
     non-medical noise (a person name, institution, country, study acronym).
     If noise, omit it silently.
  2. Use the entity's `hint` as a strong guide but feel free to
     reclassify it if you find a better parent (e.g., an entity hinted
     "other" may belong under Treatment).
  3. Preserve every triple whose subject AND object both end up in your
     output. If a triple references an entity you omitted, drop the triple.
  4. For triples, fix obvious direction errors. Example: if you see
     'AMD treats Aspirin', emit it as 'Aspirin treats AMD' in the output.
  5. Collapse casing/phrasing duplicates into ONE canonical name
     (AMD / age-related macular degeneration / ARMD → AMD).
  6. Every class MUST have a one-sentence description.

PROPERTIES (these 9, exactly):
  treats            : Treatment → Disease
  inhibits          : Treatment → MolecularTarget
  causesOrIncreases : RiskFactor → Disease
  indicates         : Biomarker → Disease
  diagnosedBy       : Disease → DiagnosticMethod
  hasSymptom        : Disease → ClinicalOutcome
  measuredBy        : Biomarker → DiagnosticMethod
  associatedWith    : GeneticBiomarker → Disease
  assessedBy        : ClinicalOutcome → DiagnosticMethod

Each property has a domain, range, description, and a list of example triples
(those that survive from the pool after fixing direction errors).

OUTPUT FORMAT — return ONLY a JSON object (no prose, no markdown code fences)
with EXACTLY this shape:

{
  "classes": {
    "ClassName": {
      "description": "one-sentence description",
      "subclasses": ["SubclassName", ...],
      "instances": ["InstanceName", ...]
    },
    ...
  },
  "properties": {
    "propertyName": {
      "domain": "ParentClass",
      "range": "ParentClass",
      "description": "one-sentence description",
      "examples": [
        ["subject", "propertyName", "object"],
        ...
      ]
    },
    ...
  }
}

Begin. Return ONLY the JSON object."""


def build_user_prompt(pool: dict) -> str:
    entities = pool.get("entities", {})
    triples = pool.get("triples", [])

    # Group entities by hint for readability
    by_hint = {}
    for name, data in entities.items():
        by_hint.setdefault(data.get("hint", "other"), []).append(name)

    lines = ["## ENTITY POOL (grouped by rough hint)\n"]
    for hint in sorted(by_hint):
        lines.append(f"### {hint} ({len(by_hint[hint])})")
        for n in sorted(by_hint[hint]):
            lines.append(f"  - {n}")
        lines.append("")

    lines.append(f"## TRIPLE POOL ({len(triples)} triples)\n")
    for t in triples:
        if len(t) >= 3:
            lines.append(f"  {t[0]} --[{t[1]}]--> {t[2]}")

    lines.append("\n## YOUR TASK")
    lines.append("Reorganize this pool into a coherent hierarchical ontology "
                 "using the target shape described in your system prompt. "
                 "Return ONLY the JSON object.")
    return "\n".join(lines)


def create_llm(model: str, provider: str):
    if provider == "groq":
        from dotenv import load_dotenv
        load_dotenv()
        return ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"),
                        temperature=0, max_tokens=8000)
    return ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url,
                      temperature=0, num_ctx=16384)


def extract_json(text: str) -> dict:
    """Extract a JSON object from the LLM response. Handles markdown fences
    and prose wrappers gracefully."""
    # Strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*\n(.+?)\n```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Find the first { and the matching last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response")
    candidate = text[start:end + 1]
    return json.loads(candidate)


def reorganize(model: str, provider: str):
    if not POOL_FILE.exists():
        logger.error(f"  Pool not found: {POOL_FILE}")
        logger.error("  Run run_agentic_harvest.py first to build the pool.")
        sys.exit(1)

    pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    entities = pool.get("entities", {})
    triples = pool.get("triples", [])

    logger.info("\n" + "=" * 60)
    logger.info("  PHASE 2 — Holistic Ontology Reorganization")
    logger.info("=" * 60)
    logger.info(f"  Pool     : {POOL_FILE}")
    logger.info(f"  Entities : {len(entities)}")
    logger.info(f"  Triples  : {len(triples)}")
    logger.info(f"  Model    : {model}")
    logger.info(f"  Provider : {provider}")
    logger.info("")

    llm = create_llm(model, provider)
    user_prompt = build_user_prompt(pool)

    # Rough token sanity check
    approx_tokens = (len(SYSTEM_PROMPT) + len(user_prompt)) // 4
    logger.info(f"  Input size: ~{approx_tokens} tokens")

    logger.info("\n  Calling LLM (single holistic pass)...")
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    raw = response.content if hasattr(response, "content") else str(response)
    logger.info(f"  LLM response length: {len(raw)} chars")

    # Save raw response in case parsing fails
    raw_file = PROJECT_ROOT / "results" / "amd" / "pool" / "reorganize_raw_response.txt"
    raw_file.write_text(raw, encoding="utf-8")
    logger.info(f"  Raw response saved to {raw_file}")

    try:
        ontology = extract_json(raw)
    except Exception as e:
        logger.error(f"\n  Failed to parse JSON: {e}")
        logger.error(f"  See raw response at {raw_file}")
        sys.exit(1)

    if "classes" not in ontology or "properties" not in ontology:
        logger.error(f"\n  Output missing required keys. Got: {list(ontology.keys())}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(ontology, f, indent=4, ensure_ascii=False)

    # Summary
    classes = ontology.get("classes", {})
    properties = ontology.get("properties", {})
    total_inst = sum(len(v.get("instances", [])) for v in classes.values()
                     if isinstance(v, dict))
    total_rel = sum(len(v.get("examples", [])) for v in properties.values()
                    if isinstance(v, dict))

    logger.info("\n" + "=" * 60)
    logger.info("  REORGANIZATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Classes       : {len(classes)}")
    logger.info(f"  Properties    : {len(properties)}")
    logger.info(f"  Instances     : {total_inst}")
    logger.info(f"  Relationships : {total_rel}")
    logger.info(f"  Saved to      : {OUTPUT_FILE}")
    logger.info("\n  Next: run run_validate_ontology_agent.py for the validation pass.\n")


def main():
    parser = argparse.ArgumentParser(description="Phase 2 — Holistic Reorganization")
    parser.add_argument("--model", default="llama-3.3-70b-versatile")
    parser.add_argument("--provider", default="groq", choices=["ollama", "groq"])
    args = parser.parse_args()
    reorganize(args.model, args.provider)


if __name__ == "__main__":
    main()
