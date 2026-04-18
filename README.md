# Engineering an Ontology for Age-Related Macular Degeneration using Agentic AI and DL-Learner

This repository contains the implementation for the paper:

> **"Engineering an ontology for Age Related Macular Degeneration using Agentic AI and DL-Learner"**  
> Calina Annemary Borzan, Alexandru Lecu, George Muntean, Simona Delia Nicoara, Adrian Groza  
> Department of Computer Science, Technical University of Cluj-Napoca

## Overview

An automated pipeline for building an OWL ontology for AMD (Age-Related Macular Degeneration) from 100 clinical trial abstracts, using:
- **SCHEMA-MINERpro** (agentic LLM pipeline) for schema extraction
- **Qwen2.5:32B** via Ollama (local, no API costs)
- **rdflib** for OWL generation and semantic enrichment
- **DL-Learner 1.5.0** for automated class expression learning

## Pipeline (agentic delta-based, produces AMD3.owl)

```
abstracts_with_id.json
        │
        ▼
prepare_amd_simple.py                → organises abstracts into stage directories
        │
        ▼
run_schema_miner_agentic.py          → Stage 1: schema from domain spec
                                       Stage 2: refinement on curated abstracts
                                       Stage 3: extension on full corpus
                                       (delta-based propose_delta tool calls,
                                        class gate + hallucination guard)
        │
        ▼
run_validate_ontology_agent.py       → ReAct validation agent — inspects,
                                       proposes structured fixes, HITL approval
        │
        ▼
convert_to_owl.py                    → converts validated JSON → AMD3.owl
        │
        ▼
Protégé + HermiT reasoner            → domain/range inference validation
        │
        ▼
dl-learner/                          → 15 CELOE / ELTL experiments for
                                       axiom discovery and KG completion
```

## Results

| Metric | Value |
|--------|-------|
| Top-level classes | 7 |
| Total subclasses | 61 |
| Schema individuals | 261 |
| Object properties (schema) | 10 |
| Object properties (enrichment) | 6 |
| Enrichment triples | 401 |
| **Total RDF triples** | **1577** |

Key extracted relations: `Ranibizumab treats WetAMD`, `Bevacizumab inhibits VEGF`, `RetinalThickness measuredBy OCT`, `CFH associatedWith AMD`

## Installation

```bash
pip install -r requirements.txt
```

The final production run used **Groq cloud** with `llama-3.3-70b-versatile`.
Set your API key in `.env`:
```
GROQ_API_KEY=your_key_here
```

Local Ollama (`qwen2.5:32b`, `llama3.1:8b`) is also supported as a fallback.
Install Ollama and pull the model if using local inference:
```bash
ollama pull qwen2.5:32b
```

DL-Learner 1.5.0 and Java 8+ are required for the axiom-learning step.
Protégé 5.x + HermiT reasoner are required for OWL reasoner validation.

## Reproducing the thesis results

**Step 1 — Prepare data**
```bash
python prepare_amd_simple.py abstracts_with_id.json
```

**Step 2 — Run the agentic pipeline (all 3 stages)**
```bash
python run_schema_miner_agentic.py
```
Produces `results/amd/final/amd_ontology_final.json` — 12 classes, 100 instances, 112 triples.

**Step 3 — Run the validation agent (ReAct with 9 inspection tools)**
```bash
python run_validate_ontology_agent.py
```
Proposes structured fixes; human approves each one before it is applied.

**Step 4 — Convert to OWL**
```bash
python convert_to_owl.py results/amd/final/amd_ontology_final.json
```
Produces `AMD3.owl` and `AMD3.ttl`.

**Step 5 — Reasoner validation**
Open `AMD3.owl` in Protégé and run HermiT to detect domain/range violations.

**Step 6 — DL-Learner experiments**
```bash
# See dl-learner/README.md for the full experiment list
java -jar dllearner-1.5.0/bin/cli dl-learner/experiment6_vegf_inhibitors.conf
```
15 experiments cited in the thesis are in `dl-learner/` (experiments 3, 6, 8, 9, 10, 12, 15, 16, 17, 19, 21, 22, 23, 24, 25).

## Key Files

| File | Description |
|------|-------------|
| `AMD3.owl` / `AMD3.ttl` | Final OWL ontology (12 classes, 100 instances, 112 triples) |
| `results/amd/final/amd_ontology_final.json` | Final validated JSON schema |
| `abstracts_with_id.json` | Input: 100 AMD clinical trial abstracts with NCT IDs |
| `run_schema_miner_agentic.py` | Main agentic pipeline (delta-based, all 3 stages) |
| `run_validate_ontology_agent.py` | ReAct validation agent (9 inspection tools + HITL) |
| `convert_to_owl.py` | JSON schema → OWL/XML conversion |
| `prepare_amd_simple.py` | Data preparation and directory setup |
| `dl-learner/` | 15 DL-Learner CELOE/ELTL experiment configs |

## Model Comparison

| Aspect | Llama 3.1:8B | Qwen2.5:32B |
|--------|-------------|-------------|
| Classes | ~52 | 68 |
| Schema individuals | ~55 | 261 |
| Object properties | 44 (redundant) | 10 (reusable) |
| Ontological errors | High | Low |
| Runtime | ~5h | ~10h |

Llama 3.1:8B generated per-instance properties (`TREATS_WET_AMD_WITH_RANIBIZUMAB`) instead of reusable ones (`treats`), and exhibited class/individual punning. Qwen2.5:32B produced a correct, clean ontological structure.

## Citation

If you use this work, please cite:
```
@article{borzan2025amd,
  title={Engineering an ontology for Age Related Macular Degeneration using Agentic AI and DL-Learner},
  author={Borzan, Calina Annemary and Lecu, Alexandru and Muntean, George and Nicoara, Simona Delia and Groza, Adrian},
  year={2025}
}
```
