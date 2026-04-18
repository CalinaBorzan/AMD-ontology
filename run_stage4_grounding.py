"""
Stage 4 — Biomedical Ontology Grounding on the final AMD ontology.

Fixes applied:
  1. Use inner 'name' field (not abstract key) as the concept to search
  2. Expanded SYNONYMS — AMD subtypes, brand names, treatments, diagnostics
  3. detect_concept_type no longer misclassifies AMD diseases as "gene"
  4. NCBI Gene: normalize hyphens (VEGF-A → VEGFA) and try both forms
  5. Fallback: if routed API returns nothing, retry with all-ontology OLS4 + MeSH
  6. SKIP_CLASSES: study acronyms (DSGA, FAM) that have no ontology entry

Reads:  results/amd/final/amd_ontology_final.json
Writes: results/amd/stage-4/AMD/amd_ontology_grounded.json

Run:
    python run_stage4_grounding.py
    python run_stage4_grounding.py --model qwen2.5:32b
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

import requests
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from schema_miner.config.envConfig import EnvConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent
INPUT_SCHEMA = PROJECT_ROOT / "results" / "amd" / "final" / "amd_ontology_final.json"
OUTPUT_DIR   = PROJECT_ROOT / "results" / "amd" / "stage-4" / "AMD"

# ── Skip list ─────────────────────────────────────────────────────────────────
# Study acronyms and chemical formulas that have no meaningful ontology entry.

SKIP_CLASSES = {"DSGA", "FAM", "C3F8"}

# ── Synonym map ───────────────────────────────────────────────────────────────
# Maps concept names that APIs won't find directly to searchable terms.

SYNONYMS = {
    # ── AMD subtypes ──────────────────────────────────────────────────────────
    "AMD":                             "age-related macular degeneration",
    "AgeRelatedMacularDegeneration":   "age-related macular degeneration",
    "DryAMD":                          "dry age-related macular degeneration",
    "WetAMD":                          "wet age-related macular degeneration",
    "NeovascularAMD":                  "neovascular age-related macular degeneration",
    "ExudativeAMD":                    "exudative age-related macular degeneration",
    "NonExsudativeAMD":                "non-exudative age-related macular degeneration",
    "LateAMD":                         "late age-related macular degeneration",
    "EarlyAMD":                        "early age-related macular degeneration",
    "IntermediateAMD":                 "intermediate age-related macular degeneration",
    "AtrophicMacularDegeneration":     "geographic atrophy macular degeneration",
    "GeographicAtrophy":               "geographic atrophy",
    "MinimallyClassicCNV":             "minimally classic choroidal neovascularization",
    "OccultCNV":                       "occult choroidal neovascularization",
    # ── Specific pathologies ──────────────────────────────────────────────────
    "ChoroidalNeovascularMembrane":    "choroidal neovascularization",
    "IllDefinedCNV":                   "choroidal neovascularization",
    "PolypoidalChoroidalVasculopathy": "polypoidal choroidal vasculopathy",
    "PigmentEpithelialDetachment":     "retinal pigment epithelial detachment",
    "ReticularPseudodrusen":           "reticular pseudodrusen",
    "PosteriorVitreoMacularAdhesion":  "vitreoretinal adhesion",
    "OcularHistoplasmosisSyndrome":    "ocular histoplasmosis syndrome",
    "PseudoxanthomaElasticum":         "pseudoxanthoma elasticum",
    "ImmunologicalMechanism":          "complement system macular degeneration",
    "GutMicrobiotaAlteration":         "gut microbiota",
    "DarkAdaptationDeficiency":        "dark adaptation",
    "FeederVessels":                   "feeder vessels choroidal neovascularization",
    "DepressiveDisorder":              "depression",
    "DrusenDeposits":                  "drusen deposits",
    "MacularPigment":                  "macular pigment",
    "SubmacularHemorrhage":            "submacular hemorrhage",
    "AmyloidBeta":                     "amyloid beta peptides",
    "SubretinalFluid":                 "subretinal fluid",
    "DrusenSize":                      "drusen size macular degeneration",
    "LipofuscinAccumulation":          "lipofuscin",
    # ── Abstract ontology categories → MeSH/SNOMED headings ──────────────────
    "Disease":                         "macular degeneration",
    "DiseaseSubtype":                  "macular degeneration subtype",
    "Treatment":                       "macular degeneration therapy",
    "DiagnosticMethod":                "diagnostic imaging ophthalmology",
    "RiskFactor":                      "risk factors macular degeneration",
    "GeneticMarker":                   "genetic markers",
    "GeneticVariant":                  "genetic variation",
    "GeneticVariants":                 "genetic variation",
    "Biomarker":                       "biomarkers",
    "PathologicalEntity":              "pathologic processes",
    "ClinicalOutcome":                 "treatment outcome",
    "PrimaryOutcomes":                 "primary outcome",
    "SecondaryOutcomes":               "secondary outcome",
    "RiskGenes":                       "susceptibility genes macular degeneration",
    "MolecularTargets":                "molecular targeted therapy",
    "GeneticMolecularBiomarker":       "biomarkers genetic macular degeneration",
    "ImagingClinicalBiomarker":        "biomarkers imaging retinal",
    "StructuralBiomarkers":            "structural biomarkers retina",
    "FunctionalBiomarkers":            "biomarkers functional vision",
    "ImagingMethods":                  "retinal imaging",
    "FunctionalMethods":               "visual function tests",
    "NonModifiableRiskFactors":        "risk factors age macular degeneration",
    "ModifiableRiskFactors":           "lifestyle risk factors macular degeneration",
    "TreatmentApproach":               "macular degeneration treatment approach",
    # ── Specific treatments ───────────────────────────────────────────────────
    "AntiVEGFTherapy":                 "anti-VEGF therapy intravitreal",
    "AntiVEGF":                        "anti-vascular endothelial growth factor",
    "SurgicalTherapy":                 "vitreoretinal surgery",
    "SupplementTherapy":               "AREDS dietary supplement macular degeneration",
    "EmergingTherapy":                 "macular degeneration emerging treatment",
    "SteroidTherapy":                  "corticosteroids ophthalmic",
    "PhotodynamicTherapy":             "photodynamic therapy verteporfin",
    "TranspupillaryThermotherapy":     "transpupillary thermotherapy",
    "Ellex2RTLaser":                   "subthreshold retinal laser treatment",
    "StereotacticRadiosurgery":        "stereotactic radiosurgery",
    "StereotacticRadiotherapy":        "stereotactic radiotherapy",
    "NightTimeLightTherapy":           "light therapy",
    "IntraocularLensImplantation":     "intraocular lens implantation",
    "PulseDiodeLaserPhotocoagulation": "laser photocoagulation retinal",
    "OculomotorTraining":              "oculomotor rehabilitation",
    "Rheohemapheresis":                "rheopheresis",
    "CNTFImplantTherapy":              "ciliary neurotrophic factor",
    "CopaxoneTherapy":                 "glatiramer acetate",
    "ISONEPTherapy":                   "sphingomab anti-S1P antibody",
    "AntiTNFTherapy":                  "tumor necrosis factor inhibitor",
    "LowVisionRehabilitation":         "low vision rehabilitation",
    "PreferredRetinalLocusTraining":   "preferred retinal locus training",
    "EccentricViewingTraining":        "eccentric viewing training",
    "TrainedRetinalLocusTraining":     "preferred retinal locus training",
    "EyeMovementReadingTraining":      "eye movement reading rehabilitation",
    "ClosedCircuitTelevision":         "low vision aids electronic magnification",
    "UltrasoundEvaluation":            "ocular ultrasonography",
    "IntravitrealInjection":           "intravitreal injections",
    "LaserSurgery":                    "laser photocoagulation",
    "SqualamineLactate":               "squalamine",
    # ── Diagnostics ───────────────────────────────────────────────────────────
    "OCT":                             "optical coherence tomography",
    "FluoresceinAngiography":          "fluorescein angiography",
    "FundusAutofluorescence":          "fundus autofluorescence",
    "ICGAngiography":                  "indocyanine green angiography",
    "FundusPhotography":               "fundus photography",
    "ETDRSVisualAcuity":               "ETDRS visual acuity",
    "VisualAcuity":                    "visual acuity",
    # ── Brand names → INN ─────────────────────────────────────────────────────
    "Avastin":                         "bevacizumab",
    "Lucentis":                        "ranibizumab",
    "Remicade":                        "infliximab",
    "Eylea":                           "aflibercept",
    "Beovu":                           "brolucizumab",
    "Vabysmo":                         "faricimab",
    "Visudyne":                        "verteporfin",
    # ── Gene full names for OLS4/MeSH ─────────────────────────────────────────
    "CFH":                             "complement factor H",
    "CFB":                             "complement factor B",
    "ARMS2":                           "age-related maculopathy susceptibility 2",
    "ApoE":                            "apolipoprotein E",
    "HTRA-1":                          "HTRA1 serine peptidase",
    "PlekhA1":                         "PLEKHA1 pleckstrin homology domain",
    "TNF-alpha":                       "tumor necrosis factor alpha",
    "VEGF-A":                          "vascular endothelial growth factor A",
    "VEGF-B":                          "vascular endothelial growth factor B",
    "VEGFR":                           "vascular endothelial growth factor receptor",
    "Perfluoropropane":                "perfluoropropane gas",
    "TissuePlasminogenActivator":      "tissue plasminogen activator",
    "Genetics":                        "genetics macular degeneration risk",
}

# Gene symbols that should be searched in NCBI Gene API.
GENE_SYMBOLS = {
    "VEGF", "VEGFA", "VEGF-A", "VEGF-B", "VEGFB", "VEGFR", "KDR",
    "CFH", "CFB", "ARMS2", "HTRA1", "HTRA-1",
    "C3", "C2", "ApoE", "APOE", "PlekhA1", "PLEKHA1",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def split_camel_case(name: str) -> str:
    """Split CamelCase into space-separated words, keeping known acronyms intact."""
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', s)
    return s.strip()


def normalize_gene_symbol(symbol: str) -> str:
    """Remove hyphens for NCBI Gene queries: VEGF-A → VEGFA, HTRA-1 → HTRA1."""
    return symbol.replace("-", "")


def resolve_search_term(concept_name: str) -> str:
    """Return the best API search term for a concept name."""
    if concept_name in SYNONYMS:
        return SYNONYMS[concept_name]
    return split_camel_case(concept_name)


def detect_concept_type(concept_name: str, description: str) -> str:
    """
    Determine concept type for API routing.
    Only routes to 'gene' if the concept_name is a known gene symbol.
    Description-based gene keywords are NOT enough — prevents AMD disease
    classes from being misclassified when their description mentions genetics.
    """
    # Gene: only if explicitly in GENE_SYMBOLS set
    if concept_name in GENE_SYMBOLS:
        return "gene"

    desc = description.lower()

    if any(k in desc for k in ["treatment", "drug", "therapy", "injection",
                                "activator", "inhibitor", "supplement"]):
        return "drug"
    if any(k in desc for k in ["disease", "subtype", "disorder", "syndrome",
                                "macular degeneration", "condition", "atrophy",
                                "neovascular", "retinopathy"]):
        return "clinical"
    if any(k in desc for k in ["diagnostic", "imaging", "angiography",
                                "tomography", "autofluorescence", "photography",
                                "ultrasound"]):
        return "diagnostic"
    if any(k in desc for k in ["biomarker", "thickness", "measurement", "acuity"]):
        return "measurement"
    if any(k in desc for k in ["phenotype", "symptom", "sign",
                                "hemorrhage", "fluid", "drusen"]):
        return "phenotype"
    return "other"


def label_similarity(search_term: str, label: str) -> float:
    """Word-overlap score — filters obviously unrelated candidates before LLM."""
    stop = {"of", "the", "a", "an", "and", "or", "in", "for", "with",
            "to", "by", "type", "related", "associated"}
    term_words  = set(search_term.lower().split()) - stop
    label_words = set(label.lower().split()) - stop
    if not term_words:
        return 0.0
    return len(term_words & label_words) / len(term_words)


def filter_candidates(search_term: str, candidates: list[dict],
                      min_score: float = 0.15) -> list[dict]:
    """Keep candidates with sufficient word overlap; fall back to top-2 if none pass."""
    scored = [(label_similarity(search_term, c.get("label", "")), c) for c in candidates]
    filtered = [c for score, c in scored if score >= min_score]
    if not filtered and scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        filtered = [c for _, c in scored[:2]]
    return filtered


# ── API functions ─────────────────────────────────────────────────────────────

OLS4_URL      = "https://www.ebi.ac.uk/ols4/api/search"
NCBI_ESEARCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
NCBI_EMAIL    = "calina.borzan18@yahoo.com"


def query_ols4(term: str, ontologies: str = "snomed,chebi,go,hp") -> list[dict]:
    """Query EBI OLS4 across the specified ontologies."""
    try:
        resp = requests.get(
            OLS4_URL,
            params={"q": term, "ontology": ontologies, "rows": 5, "exact": "false"},
            timeout=10,
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
    except Exception as e:
        logger.warning(f"  OLS4 error: {e}")
        return []

    ont_map = {"SNOMED": "SNOMED", "CHEBI": "ChEBI", "GO": "GO", "HP": "HPO"}
    return [{
        "ontology":    ont_map.get(d.get("ontology_name", "").upper(), d.get("ontology_name", "")),
        "id":          d.get("obo_id") or d.get("short_form", ""),
        "uri":         d.get("iri", ""),
        "label":       d.get("label", ""),
        "description": (d.get("description") or [""])[0][:200],
    } for d in docs]


def query_mesh_eutils(term: str) -> list[dict]:
    """Query MeSH via NCBI E-utilities — returns real MeSH UIDs."""
    try:
        search_resp = requests.get(
            NCBI_ESEARCH,
            params={"db": "mesh", "term": term, "retmode": "json",
                    "retmax": 5, "email": NCBI_EMAIL},
            timeout=10,
        )
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        time.sleep(0.3)

        summary_resp = requests.get(
            NCBI_ESUMMARY,
            params={"db": "mesh", "id": ",".join(ids), "retmode": "json",
                    "email": NCBI_EMAIL},
            timeout=10,
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})

    except Exception as e:
        logger.warning(f"  MeSH eutils error: {e}")
        return []

    candidates = []
    for uid in ids:
        entry    = result.get(uid, {})
        mesh_ui  = entry.get("ds_meshui", uid)
        terms    = entry.get("ds_meshterms", [uid])
        label    = terms[0] if isinstance(terms, list) and terms else str(terms)
        candidates.append({
            "ontology":    "MeSH",
            "id":          mesh_ui,
            "uri":         f"https://id.nlm.nih.gov/mesh/{mesh_ui}",
            "label":       label,
            "description": "",
        })
    return candidates


def query_ncbi_gene(symbol: str) -> list[dict]:
    """Query NCBI Gene for a gene symbol (human genes only)."""
    try:
        search_resp = requests.get(
            NCBI_ESEARCH,
            params={
                "db": "gene",
                "term": f"{symbol}[gene] AND Homo sapiens[organism]",
                "retmode": "json", "retmax": 3, "email": NCBI_EMAIL,
            },
            timeout=10,
        )
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        time.sleep(0.3)

        summary_resp = requests.get(
            NCBI_ESUMMARY,
            params={"db": "gene", "id": ",".join(ids), "retmode": "json",
                    "email": NCBI_EMAIL},
            timeout=10,
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})

    except Exception as e:
        logger.warning(f"  NCBI Gene error: {e}")
        return []

    candidates = []
    for gene_id in ids:
        entry  = result.get(gene_id, {})
        sym    = entry.get("name", symbol)
        name   = entry.get("description", "")
        candidates.append({
            "ontology":    "NCBI Gene",
            "id":          f"NCBIGene:{gene_id}",
            "uri":         f"https://www.ncbi.nlm.nih.gov/gene/{gene_id}",
            "label":       f"{sym} — {name}" if name else sym,
            "description": entry.get("summary", "")[:200],
        })
    return candidates


def gather_candidates(concept_name: str, concept_type: str,
                      search_term: str) -> list[dict]:
    """Route to the right APIs, with a full-ontology fallback if routing fails."""
    candidates = []

    if concept_type == "gene" or concept_name in GENE_SYMBOLS:
        # Try original symbol, then hyphen-normalized form
        candidates += query_ncbi_gene(concept_name)
        normalized = normalize_gene_symbol(concept_name)
        if normalized != concept_name and not candidates:
            candidates += query_ncbi_gene(normalized)
        candidates += query_ols4(search_term, ontologies="go,chebi")

    elif concept_type == "drug":
        candidates += query_ols4(search_term, ontologies="chebi")
        candidates += query_mesh_eutils(search_term)

    elif concept_type in ("clinical", "phenotype"):
        candidates += query_ols4(search_term, ontologies="snomed,hp")
        candidates += query_mesh_eutils(search_term)

    elif concept_type == "diagnostic":
        candidates += query_mesh_eutils(search_term)
        candidates += query_ols4(search_term, ontologies="snomed")

    elif concept_type == "measurement":
        candidates += query_mesh_eutils(search_term)
        candidates += query_ols4(search_term, ontologies="snomed,hp")

    else:
        candidates += query_ols4(search_term)
        candidates += query_mesh_eutils(search_term)

    # Fallback: if routing gave nothing, try all ontologies
    if not candidates:
        logger.warning(f"  Routing returned nothing — falling back to all-ontology search")
        candidates += query_ols4(search_term)
        candidates += query_mesh_eutils(search_term)

    return filter_candidates(search_term, candidates, min_score=0.15)


# ── LLM grounding ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a biomedical ontology expert for Age-Related Macular Degeneration (AMD).

Your task: given an AMD concept and a list of API-retrieved ontology candidates,
select matches that genuinely correspond to the same or closely related biological concept.

RULES:
1. Only use IDs and URIs that appear EXACTLY in the candidates list. Never invent IDs.
2. A match is valid if the candidate label refers to the SAME or PARENT biological entity.
   VALID matches:
   - "Complement Factor H" matches "CFH" ✓
   - "Choroidal Neovascularization" matches "ChoroidalNeovascularMembrane" ✓
   - "Macular Degeneration" matches "DryAMD" ✓ (parent concept, medium confidence)
   - "Bevacizumab" matches "Avastin" ✓ (same drug, different name)
   - "Anti-VEGF therapy" matches "AntiVEGFTherapy" ✓
   INVALID matches:
   - "cyclopropane ring" does NOT match "C3 gene variant" ✗
   - "L-glutamic acid" does NOT match "ApoE gene" ✗
   - "Principal" does NOT match "PrimaryOutcome" ✗ (unrelated concept)
3. Single generic words like "Imaging", "Secondary", "Principal" alone are NOT valid.
4. If no candidate is a genuine match, set grounded=false with empty matches.
5. Confidence levels:
   - high   : label is essentially the same concept (e.g. "Ranibizumab" = "Ranibizumab")
   - medium : label is the direct parent or broader category (e.g. "Macular Degeneration" for "DryAMD")
   - low    : label is related but not directly the same or parent

Output format (valid JSON only, no explanatory text):
{
  "grounded": true | false,
  "concept_type": "clinical | drug | gene | phenotype | diagnostic | measurement | other",
  "matches": [
    {
      "ontology": "<ontology name>",
      "id": "<exact ID from candidates>",
      "uri": "<exact URI from candidates>",
      "label": "<exact label from candidates>",
      "confidence": "high | medium | low"
    }
  ]
}"""

USER_PROMPT = """AMD concept to ground:
  Name       : {concept_name}
  Description: {concept_description}

API candidates (these are the ONLY valid options):
{candidates}

Return JSON only."""


def format_candidates(candidates: list[dict]) -> str:
    if not candidates:
        return "No candidates found."
    lines = []
    for i, c in enumerate(candidates, 1):
        desc = f"\n     Description: {c['description']}" if c.get("description") else ""
        lines.append(
            f"{i}. [{c['ontology']}] {c['label']}\n"
            f"     ID : {c['id']}\n"
            f"     URI: {c['uri']}{desc}"
        )
    return "\n".join(lines)


def ground_concept(llm: ChatOllama, concept_name: str, description: str,
                   candidates: list[dict]) -> dict:
    valid_ids    = {c["id"] for c in candidates if c.get("id")}
    valid_labels = {c["label"].lower() for c in candidates if c.get("label")}

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT.format(
            concept_name=concept_name,
            concept_description=description or "No description available.",
            candidates=format_candidates(candidates),
        )),
    ])

    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError:
        return {"grounded": False, "concept_type": "other", "matches": []}

    # Hard validation: strip any hallucinated IDs
    if result.get("matches"):
        result["matches"] = [
            m for m in result["matches"]
            if m.get("id") in valid_ids or m.get("label", "").lower() in valid_labels
        ]
        if not result["matches"]:
            result["grounded"] = False

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def collect_all_entities(schema: dict) -> list[tuple[str, str, str]]:
    """
    Collect ALL unique entities to ground: classes + individuals.
    Returns list of (entity_name, description, source) tuples.
    """
    entities = {}  # name → (description, source)
    classes = schema.get("classes", {})

    # 1. Classes
    for class_key, class_data in classes.items():
        if not isinstance(class_data, dict):
            continue
        concept_name = class_data.get("name", class_key)
        desc = class_data.get("description", "")
        entities[concept_name] = (desc, f"class:{class_key}")

    # 2. Individuals from class instances
    for class_key, class_data in classes.items():
        if not isinstance(class_data, dict):
            continue
        for inst in class_data.get("instances", []):
            if inst not in entities:
                entities[inst] = (
                    f"Instance of {class_key}: {class_data.get('description', '')}",
                    f"instance:{class_key}",
                )

    # 3. Individuals from individuals section
    individuals = schema.get("individuals", {})
    for group_name, items in individuals.items():
        if isinstance(items, list):
            for item in items:
                if item not in entities:
                    entities[item] = (f"Individual in {group_name}", f"individual:{group_name}")

    return [(name, desc, source) for name, (desc, source) in entities.items()]


def run(model: str):
    with open(INPUT_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)

    all_entities = collect_all_entities(schema)
    total = len(all_entities)
    print(f"\nLoaded schema from {INPUT_SCHEMA.name}")
    print(f"  Classes    : {len(schema.get('classes', {}))}")
    print(f"  Unique entities to ground: {total}")
    print(f"  Model      : {model}\n")

    llm = ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url, temperature=0)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Store all grounding results in one place
    grounded_entities = {}
    grounded_count = 0

    for i, (entity_name, description, source) in enumerate(all_entities, 1):
        # Skip study acronyms
        if entity_name in SKIP_CLASSES:
            print(f"[{i}/{total}] {entity_name} → skipped")
            grounded_entities[entity_name] = {
                "grounded": False, "concept_type": "other", "matches": [],
                "source": source, "note": "Skipped",
            }
            continue

        search_term  = resolve_search_term(entity_name)
        concept_type = detect_concept_type(entity_name, description)

        label = f"[{i}/{total}] {entity_name}"
        if search_term != entity_name:
            label += f" → '{search_term}'"
        label += f" [{concept_type}] ({source})"
        print(label)

        candidates = gather_candidates(entity_name, concept_type, search_term)
        time.sleep(0.2)

        if not candidates:
            print(f"  ✗ No candidates")
            grounded_entities[entity_name] = {
                "grounded": False, "concept_type": concept_type,
                "matches": [], "source": source,
            }
            continue

        grounding = ground_concept(llm, entity_name, description, candidates)
        grounding["source"] = source
        grounded_entities[entity_name] = grounding

        if grounding.get("grounded"):
            grounded_count += 1
            for m in grounding.get("matches", [])[:2]:
                print(f"  ✓ [{m['ontology']}] {m['label']} ({m['id']}) [{m['confidence']}]")
        else:
            print(f"  ✗ No valid match")

    # Save grounded results into schema
    schema["grounded_entities"] = grounded_entities

    # Also annotate classes with their grounding (for convenience)
    classes = schema.get("classes", {})
    for class_key, class_data in classes.items():
        if not isinstance(class_data, dict):
            continue
        concept_name = class_data.get("name", class_key)
        if concept_name in grounded_entities:
            class_data["ontology_grounding"] = grounded_entities[concept_name]

    output_file = OUTPUT_DIR / "amd_ontology_grounded.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"Grounded : {grounded_count}/{total} entities")
    print(f"  Classes    : {sum(1 for e in grounded_entities.values() if e.get('grounded') and e.get('source','').startswith('class'))}")
    print(f"  Individuals: {sum(1 for e in grounded_entities.values() if e.get('grounded') and not e.get('source','').startswith('class'))}")
    print(f"Saved to : {output_file}")
    print(f"{'='*55}")


def main():
    parser = argparse.ArgumentParser(description="Stage 4 — AMD Biomedical Ontology Grounding")
    parser.add_argument("--model", default="llama3.1:8b",
                        help="Ollama model to use (default: llama3.1:8b)")
    args = parser.parse_args()
    run(args.model)


if __name__ == "__main__":
    main()
