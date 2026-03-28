system_prompt = """
Context: You are in the final validation stage of building a medical ontology for {process_name}. Validate and extend using additional AMD abstracts.

IMPORTANT: Each input is a research ABSTRACT (150-300 words). Do NOT exclude entities because they lack dosage or measurement values.

CLASS vs INDIVIDUAL:
- CLASS = category with subtypes (WetAMD, AntiVEGFTherapy). INDIVIDUAL = specific named thing (Ranibizumab, CFH, OCT).
- An entity is EITHER a class OR an individual. NEVER both (no punning). If found, keep as class if it has subtypes, otherwise keep as individual.

Validation Focus:
1. **Completeness**: Add AMD entities or relationships not yet in schema.
2. **Consistency**: Keep existing structure unless clearly wrong.
3. **Accuracy**: anti-VEGF treats WetAMD (not DryAMD). CFH associatedWith AMD risk.
4. **Hierarchy**: Disease → AMD → subtypes. Associated diseases (Glaucoma, Alzheimer's) under Disease directly — NOT under AMD.

RETENTION RULE: Never remove an existing class, property, or individual. Only add.

Output: Complete, validated JSON schema in ```json fenced code block.
"""

user_prompt = """
Here is the current {process_name} ontology schema and a new AMD validation abstract. Validate completeness and add any missing knowledge.

Current Ontology Schema:
{current_schema}

Validation Abstract:
{full_text}

Expert Validation Guidance:
{domain_expert_review}

Your validation task:
1. **Scan for missing content**: disease subtypes, treatments, genetic markers, diagnostics, biomarkers, risk factors, outcomes, relationships
2. **Add** any entity or relationship from this abstract, even without numeric details.
3. **Verify relationship accuracy**: anti-VEGF → WetAMD, CFH → AMD risk, OCT → diagnoses.
4. **Return the COMPLETE validated and extended schema** in ```json format.

Ensure the "individuals" section contains specific AMD instances:
- treatments: Drug/therapy names (Ranibizumab, Aflibercept, Verteporfin, AREDS, Lutein, etc.)
- biomarkers: Measurable entities (DrusenSize, RetinalThickness, SubretinalFluid, VEGF, etc.)
- diagnosticMethods: Modalities (OCT, FluoresceinAngiography, FundusAutofluorescence, etc.)
- geneticMarkers: Genes/variants (CFH, ARMS2, HTRA1, C3, CFB, ApoE, CX3CR1, etc.)
"""
