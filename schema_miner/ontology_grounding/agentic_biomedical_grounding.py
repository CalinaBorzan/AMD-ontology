"""
Stage 4 — Biomedical Ontology Grounding (AMD)

Replaces the original QUDT grounding (OpenAI + units-only) with a free,
local, biomedical grounding pipeline:

  APIs used (all free, no API key required):
    - OLS4  (EBI Ontology Lookup Service) — searches SNOMED CT, GO, ChEBI, HPO simultaneously
    - MeSH  (NCBI)                        — medical subject headings fallback

  LLM used:
    - Ollama (local) via LangChain ChatOllama — no OpenAI dependency

  Ontologies covered:
    SNOMED CT  clinical concepts, diseases, procedures, anatomy
    ChEBI      drugs, chemical compounds, biologics
    GO         genes, proteins, biological processes
    HPO        phenotypes, symptoms, observable characteristics
    MeSH       general medical terms (fallback)
"""

import json
import logging
import time
from pathlib import Path

import requests
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from schema_miner.config.envConfig import EnvConfig
from schema_miner.config.processConfig import ProcessConfig
from schema_miner.prompts.ontology_grounding import agent_biomedical_prompt1, agent_biomedical_prompt2
from schema_miner.utils.dictionary_utils import get_schema_leaf_keys
from schema_miner.utils.file_utils import load_json_input, save_json_file

logger = logging.getLogger(__name__)

# ── API config ────────────────────────────────────────────────────────────────

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
MESH_SEARCH_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"

OLS4_ONTOLOGIES  = "snomed,chebi,go,hp"   # HPO prefix in OLS4 is "hp"
OLS4_ROWS        = 5
MESH_LIMIT       = 3
REQUEST_TIMEOUT  = 10   # seconds per API call
RETRY_DELAY      = 1.0  # seconds between retries


# ── API helpers ───────────────────────────────────────────────────────────────

def _query_ols4(term: str) -> list[dict]:
    """
    Query OLS4 for a term across SNOMED CT, ChEBI, GO, and HPO.
    Returns a list of candidate dicts with ontology, id, uri, label.
    """
    try:
        resp = requests.get(
            OLS4_SEARCH_URL,
            params={"q": term, "ontology": OLS4_ONTOLOGIES, "rows": OLS4_ROWS, "exact": "false"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
    except Exception as e:
        logger.warning(f"OLS4 query failed for '{term}': {e}")
        return []

    candidates = []
    for doc in docs:
        ontology_raw = doc.get("ontology_name", "").upper()
        ontology = {
            "SNOMED": "SNOMED", "CHEBI": "ChEBI",
            "GO": "GO", "HP": "HPO",
        }.get(ontology_raw, ontology_raw)

        candidates.append({
            "ontology": ontology,
            "id":       doc.get("obo_id") or doc.get("short_form", ""),
            "uri":      doc.get("iri", ""),
            "label":    doc.get("label", ""),
            "description": (doc.get("description") or [""])[0][:200],
        })
    return candidates


def _query_mesh(term: str) -> list[dict]:
    """
    Query NCBI MeSH for a term.
    Returns a list of candidate dicts.
    """
    try:
        resp = requests.get(
            MESH_SEARCH_URL,
            params={"label": term, "match": "contains", "limit": MESH_LIMIT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as e:
        logger.warning(f"MeSH query failed for '{term}': {e}")
        return []

    candidates = []
    for item in results:
        candidates.append({
            "ontology":    "MeSH",
            "id":          item.get("ui", ""),
            "uri":         f"https://id.nlm.nih.gov/mesh/{item.get('ui', '')}",
            "label":       item.get("label", ""),
            "description": "",
        })
    return candidates


def _format_candidates(candidates: list[dict]) -> str:
    """Format candidates as a numbered list for the LLM prompt."""
    if not candidates:
        return "No candidates found."
    lines = []
    for i, c in enumerate(candidates, 1):
        desc = f" — {c['description']}" if c.get("description") else ""
        lines.append(f"{i}. [{c['ontology']}] {c['label']} (ID: {c['id']}){desc}")
    return "\n".join(lines)


# ── LLM grounding ─────────────────────────────────────────────────────────────

def _ground_concept_with_llm(
    llm: ChatOllama,
    concept_name: str,
    concept_description: str,
    candidates: list[dict],
) -> dict:
    """
    Use Ollama to select the best ontology matches from the candidates.
    Returns a grounding dict: {grounded, concept_type, matches}.
    """
    candidates_text = _format_candidates(candidates)

    # Step 1: classify + reason (prompt 1)
    step1_messages = [
        SystemMessage(content=agent_biomedical_prompt1.system_prompt),
        HumanMessage(content=agent_biomedical_prompt1.user_prompt.format(
            concept_name=concept_name,
            concept_description=concept_description or "No description available.",
            candidates=candidates_text,
        )),
    ]
    step1_response = llm.invoke(step1_messages)
    concept_type_hint = step1_response.content.strip()

    # Step 2: produce structured JSON (prompt 2)
    step2_messages = [
        SystemMessage(content=agent_biomedical_prompt2.system_prompt),
        HumanMessage(content=agent_biomedical_prompt2.user_prompt.format(
            concept_name=concept_name,
            concept_description=concept_description or "No description available.",
            concept_type=concept_type_hint[:100],
            candidates=candidates_text,
        )),
    ]
    step2_response = llm.invoke(step2_messages)

    # Parse JSON from LLM response
    raw = step2_response.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError:
        logger.warning(f"LLM returned invalid JSON for '{concept_name}': {raw[:200]}")
        result = {"grounded": False, "concept_type": "other", "matches": []}

    return result


# ── Schema injection ──────────────────────────────────────────────────────────

def _inject_biomedical_grounding(schema: dict, key_path: list[str], grounding: dict) -> None:
    """
    Inject the biomedical grounding result into the schema at the location
    defined by key_path, adding an 'ontology_grounding' field.
    """
    target = schema["properties"]
    for key in key_path[:-1]:
        if key in target and "properties" in target[key]:
            target = target[key]["properties"]
        elif key in target:
            target = target[key]

    leaf_key = key_path[-1]
    if leaf_key in target:
        target[leaf_key]["ontology_grounding"] = {
            "grounded":     grounding.get("grounded", False),
            "concept_type": grounding.get("concept_type", "other"),
            "matches":      grounding.get("matches", []),
        }


# ── Main function ─────────────────────────────────────────────────────────────

def agentic_biomedical_grounding(
    llm_model_name: str,
    process_schema: dict | Path,
    result_file_path: str,
    save_schema: bool = False,
) -> dict | None:
    """
    Ground an AMD process schema to standard biomedical ontologies using
    free REST APIs (OLS4, MeSH) and a local Ollama LLM.

    Replaces the original agentic_qudt_grounding() which required OpenAI.

    :param str llm_model_name: Ollama model name (e.g. 'llama3.1:8b')
    :param dict | Path process_schema: Path to or dict of the JSON schema to ground
    :param str result_file_path: Directory to save results if save_schema=True
    :param bool save_schema: Whether to save the grounded schema to disk
    :returns dict | None: The grounded schema, or None on failure
    """
    logger.info(
        f"\nBiomedical Ontology Grounding for {ProcessConfig.Process_name} "
        f"using Ollama ({llm_model_name}) + OLS4/MeSH APIs"
    )

    # Load schema
    schema = load_json_input(process_schema)
    if not schema:
        raise ValueError("Unable to load JSON schema for biomedical grounding.")

    # Initialize local Ollama LLM
    llm = ChatOllama(
        model=llm_model_name,
        base_url=EnvConfig.OLLAMA_base_url,
        temperature=0,
    )

    # Extract all leaf properties from the schema
    schema_properties = get_schema_leaf_keys(schema["properties"])
    total = len(schema_properties)
    logger.info(f"Grounding {total} schema concept(s)...")

    grounded_count = 0
    failed_count   = 0

    for i, (key_path, description) in enumerate(schema_properties, 1):
        concept_name = key_path.split(" ")[-1]  # use the leaf key as concept name
        logger.info(f"[{i}/{total}] Grounding: '{concept_name}'")

        # Query APIs
        ols4_candidates  = _query_ols4(concept_name)
        time.sleep(0.2)  # be polite to EBI servers
        mesh_candidates  = _query_mesh(concept_name)
        all_candidates   = ols4_candidates + mesh_candidates

        if not all_candidates:
            logger.warning(f"  No API candidates found for '{concept_name}' — skipping.")
            failed_count += 1
            continue

        # Ground with LLM
        grounding = _ground_concept_with_llm(llm, concept_name, description, all_candidates)

        # Inject into schema
        _inject_biomedical_grounding(schema, key_path.split(" "), grounding)

        if grounding.get("grounded"):
            grounded_count += 1
            matches_summary = ", ".join(
                f"{m['ontology']}:{m['id']}" for m in grounding.get("matches", [])[:2]
            )
            logger.info(f"  Grounded → {matches_summary}")
        else:
            failed_count += 1
            logger.info(f"  No suitable ontology match found.")

    logger.info(
        f"\nGrounding complete: {grounded_count}/{total} concepts grounded, "
        f"{failed_count} ungrounded."
    )

    # Optionally save
    if save_schema:
        saved = save_json_file(result_file_path, f"{llm_model_name}_biomedical_grounded.json", schema)
        if saved:
            logger.info(f"Grounded schema saved to: {result_file_path}")

    return schema
