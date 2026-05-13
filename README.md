---
title: AMD Ontology
emoji: 👁️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Agentic ontology engineering for AMD
---

# AMD Ontology — Agentic Schema Mining + DL-Learner

Automated pipeline to build an OWL ontology for Age-Related Macular Degeneration from clinical trial abstracts.

> **"Engineering an ontology for Age Related Macular Degeneration using Agentic AI and DL-Learner"**
> Calina Annemary Borzan, Alexandru Lecu, George Muntean, Simona Delia Nicoara, Adrian Groza
> Department of Computer Science, Technical University of Cluj-Napoca

## Stack

- **SCHEMA-MINERpro** agentic LLM pipeline (3 stages: domain spec → curated abstracts → full corpus)
- **Qwen2.5:32B** via Ollama or **Llama-3.3-70B** via Groq
- **rdflib** for OWL/XML and Turtle serialization
- **DL-Learner 1.5.0** for class expression learning

## Install

```bash
pip install -r backend/requirements.txt
```

For Groq: set `GROQ_API_KEY` in `.env`. For local Ollama: `ollama pull qwen2.5:32b`.
DL-Learner experiments need Java 8+ and DL-Learner 1.5.0.

## Run

```bash
# 1. Prepare abstracts
python backend/tools/prepare_amd_simple.py data/abstracts_with_id.json

# 2. Agentic schema mining (Stages 1–3)
python backend/pipeline/run_schema_miner_agentic.py

# 3. Validation agent (ReAct + HITL)
python backend/pipeline/run_validate_ontology_agent.py

# 4. JSON → OWL
python backend/pipeline/convert_to_owl.py results/amd/final/amd_ontology_final.json

# 5. DL-Learner
java -jar dllearner-1.5.0/bin/cli evaluation/dl-learner/experiment6_vegf_inhibitors.conf
```

## Layout

| Path | Purpose |
|------|---------|
| `backend/pipeline/` | Pipeline scripts (mining, validation, OWL conversion) |
| `backend/schema_miner/` | Stage prompts and config |
| `backend/tools/` | Data preparation utilities |
| `data/` | Input abstracts and reference annotations |
| `results/amd/final/` | Final JSON schema |
| `ontology/` | Generated OWL/TTL |
| `evaluation/dl-learner/` | DL-Learner experiment configs |

## Citation

```
@article{borzan2025amd,
  title={Engineering an ontology for Age Related Macular Degeneration using Agentic AI and DL-Learner},
  author={Borzan, Calina Annemary and Lecu, Alexandru and Muntean, George and Nicoara, Simona Delia and Groza, Adrian},
  year={2025}
}
```
