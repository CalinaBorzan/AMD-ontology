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

## Pipeline

```
abstracts_with_id.json
        │
        ▼
prepare_amd_simple.py       → organises abstracts into stage directories
        │
        ▼
run_amd_hitl.py             → Stage 1: schema from domain spec
                              Stage 2: refinement on 20 abstracts
                              Stage 3: validation on 100 abstracts
                              (Human-in-the-Loop corrections between stages)
        │
        ▼
convert_to_owl.py           → converts final JSON schema to AMD.owl
        │
        ▼
enrich_owl.py               → links 100 abstract individuals to schema
                              entities via 6 enrichment properties
                              (+401 RDF triples)
        │
        ▼
dl_learner/                 → OWL class expression learning experiments
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
# Install Ollama and pull model
ollama pull qwen2.5:32b
```

## Usage

**Step 1 — Prepare data**
```bash
python prepare_amd_simple.py abstracts_with_id.json
```

**Step 2 — Run pipeline (Human-in-the-Loop)**
```bash
python run_amd_hitl.py
```

**Step 3 — Convert to OWL**
```bash
python convert_to_owl.py results/amd/final/<model>.json
```

**Step 4 — Enrich ontology**
```bash
python enrich_owl.py
```

**Step 5 — DL-Learner experiments**
```bash
# See dl_learner/README.md
java -jar dllearner-1.5.0/bin/cli dl_learner/dl_learner_mechanistic.conf
```

## Key Files

| File | Description |
|------|-------------|
| `AMD.owl` | Final enriched OWL ontology |
| `AMD.ttl` | Same ontology in Turtle format |
| `abstracts_with_id.json` | Input: 100 AMD clinical trial abstracts with NCT IDs |
| `run_amd_hitl.py` | Main pipeline script with Human-in-the-Loop |
| `convert_to_owl.py` | JSON schema → OWL/XML conversion |
| `enrich_owl.py` | Semantic enrichment of abstract individuals |
| `prepare_amd_simple.py` | Data preparation and directory setup |
| `Dockerfile` | Docker environment for DL-Learner |
| `dl_learner/` | DL-Learner configuration files and results |

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
