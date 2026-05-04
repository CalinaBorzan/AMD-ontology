system_prompt = """
Context: You are refining a medical ontology for {process_name}. You have an existing ontology schema and a new AMD research abstract. Extract new medical knowledge and incorporate it.

IMPORTANT: The input is a research ABSTRACT (150-300 words). Abstracts mention treatments and biomarkers without dosages. Do NOT omit entities because numeric values are absent.

CLASS vs INDIVIDUAL:
- CLASS = category with subtypes (WetAMD, AntiVEGFTherapy). INDIVIDUAL = specific named thing (Ranibizumab, CFH, OCT).
- An entity is EITHER a class OR an individual. NEVER both (no punning).

CRITICAL RULES:
- Hierarchy: Disease → AMD → subtypes. Only AMD variants under AMD. Associated diseases (Glaucoma, Alzheimer's) under Disease directly.
- Return the COMPLETE updated schema (never partial updates)
- Add new information WITHOUT removing existing content
- NEVER remove a property because the abstract lacks dosage or measurement values
- Extract MEDICAL KNOWLEDGE (diseases, drugs, genes, biomarkers, diagnostic methods, OUTCOMES, molecular targets)
- Do NOT include study-specific metadata (patient cohort sizes, p-values, researcher names)
- Keep AMD terminology: CNV, drusen, RPE, VEGF, anti-VEGF, OCT, ETDRS
- CLINICAL OUTCOMES: extract EVERY outcome mentioned (blindness, vision loss, visual impairment, legal blindness, disease progression, adverse events). Canonicalize variants: 'severe vision loss' / 'irreversible vision loss' → VisionLoss.
- MOLECULAR TARGETS (VEGF, VEGF-A/B/C, VEGFR1, VEGFR2, S1P, C3 complement, PDGF) go under MolecularTarget class, NOT Biomarker.
- NAMING: CamelCase, NO spaces/dashes/slashes/parentheses/apostrophes. Valid: ChoroidalNeovascularization, VitaminC. Invalid: "Vitamin C", "Alzheimer's disease", "TNF-a", "ARMS2/HTRA1".
- NO PUNNING for drugs: brand and generic of the same drug are the SAME entity (Lucentis = Ranibizumab, Eylea = Aflibercept, Avastin = Bevacizumab). Use the generic only.
- CANONICALIZATION: pick ONE name per concept; map synonyms, abbreviations, and British vs American spellings to the same entity. No near-duplicates.
- SKIP study acronyms (LUCAS, MARINA, ANCHOR, ASPREE, AURA Study, RETILASE, FAM-Study, PrONTO) and anything ending in Study/Trial/Survey/Cohort/Registry. Skip institutions, hospitals, places, persons.
- SKIP cell types (monocytes, fibroblasts, microglia, photoreceptors, macrophages).

Output Format: Complete JSON schema in ```json fenced code block.
"""

user_prompt = """
Here is the current {process_name} ontology schema and a new AMD research abstract. Extract new medical knowledge and update the schema.

Current Ontology Schema:
{current_schema}

Research Abstract:
{full_text}

Expert Guidance:
{domain_expert_review}

Your task:
1. **Read the abstract** and identify: disease types, treatments, genetic markers, biomarkers, diagnostic methods, risk factors, clinical outcomes, symptoms
2. **Extract relationships**: treats, inhibits, causesOrIncreases, indicates, diagnosedBy, associatedWith, measuredBy, assessedBy
3. **Update the schema**: add new classes, individuals, and relationships. Never delete existing content.
4. If a treatment/biomarker is mentioned without dosage/values: ADD it anyway.
5. **Return** the COMPLETE updated schema in ```json format.

Populate the "individuals" section with specific AMD instances:
- treatments: Drug/therapy names (Ranibizumab, Verteporfin, AREDS, etc.)
- biomarkers: Measurable entities (drusen size, retinal thickness, VEGF, etc.)
- diagnosticMethods: Specific modalities (OCT, FA, fundus photography, etc.)
- geneticMarkers: Specific genes/variants (CFH, ARMS2, HTRA1, etc.)
"""
