system_prompt = """
Context: You are in the final validation stage of building a medical ontology for {process_name}. You have a comprehensive schema built from multiple AMD research abstracts. Your task is to validate and extend it using additional AMD abstracts.

IMPORTANT ABOUT INPUT: Each input is a research ABSTRACT (150-300 words). Abstracts do not contain full methodological detail or quantitative tables. Do NOT exclude a valid AMD entity simply because it lacks dosage, measurement units, or statistical values in this abstract.

Validation Focus:
1. **Completeness**: Does this abstract mention AMD entities or relationships not yet in the schema? If yes, ADD them.
2. **Consistency**: Do the findings align with existing schema structure? If a conflict exists, note it but keep the existing structure unless clearly wrong.
3. **Accuracy**: Do relationships make medical sense for AMD? (e.g., anti-VEGF treats Wet AMD is correct)
4. **Coverage Threshold**: A property or class should be RETAINED if it has appeared in at least 2 abstracts across the pipeline, even without quantitative support.

In this stage:
- ADD new AMD entities/relationships whenever they appear in the abstract — do not be overly conservative
- Do NOT add purely study-specific metadata (specific RCT enrollment numbers, researcher names, institution names)
- Maintain schema stability: do not restructure existing classes unless there is a clear medical error
- Focus on high-confidence AMD medical knowledge

AMD Entities to Check For in Every Abstract:
- New AMD subtypes, CNV variants, or pathological features not yet in schema
- New anti-VEGF agents, surgical techniques, or supplement formulations
- Genetic associations (CFH, ARMS2, HTRA1, C3, complement pathway genes)
- Imaging biomarkers (OCT findings, autofluorescence patterns, angiography findings)
- Treatment outcomes expressible as class properties (e.g., hasOutcome: VisualAcuityStabilization)
- Risk factor associations not yet captured

RETENTION RULE: Never remove an existing class, property, or individual from the schema at this stage. Only add.

Output: Complete, validated JSON schema in ```json fenced code block.
"""

user_prompt = """
Here is the current {process_name} ontology schema and a new AMD validation abstract. Validate completeness and add any missing AMD knowledge.

Current Ontology Schema:
{current_schema}

Validation Abstract:
{full_text}

Expert Validation Guidance:
{domain_expert_review}

Your validation task:
1. **Scan for missing AMD content**: Check the abstract for:
   - AMD disease subtypes or pathological entities not in schema
   - Treatments (anti-VEGF, PDT, laser, gene therapy, supplements) not in schema
   - Genetic markers or risk genes (CFH, ARMS2, HTRA1, VEGF, C3, ApoE) not in schema
   - Diagnostic methods (OCT, FA, ICG, fundus autofluorescence, perimetry) not in schema
   - Biomarkers (drusen type/size, retinal thickness, macular pigment, subretinal fluid) not in schema
   - Risk factors (age, smoking, genetics, diet, cardiovascular disease) not in schema
   - Clinical outcomes (visual acuity, lesion size, progression) not in schema
   - Relationships not yet in properties section

2. **Apply coverage threshold**: Add any entity or relationship that appears in this abstract, regardless of whether numeric details are provided. Abstracts routinely omit dosage and measurement details — this does NOT make the entity invalid.

3. **Verify relationship accuracy**: Ensure all AMD medical relationships in the existing schema are medically sound:
   - anti-VEGF agents should TREAT WetAMD (not DryAMD)
   - CFH gene variants should be ASSOCIATED_WITH AMD risk
   - OCT should DIAGNOSE retinal structural changes

4. **Return the COMPLETE validated and extended schema** in ```json format.

Also ensure the "individuals" section contains specific AMD instances:
- treatments: All specific drug/therapy names encountered (Ranibizumab, Aflibercept, Bevacizumab, Verteporfin, AREDS, Lutein, Zeaxanthin, etc.)
- diseases: All specific AMD subtypes/entities (WetAMD, DryAMD, GeographicAtrophy, CNV, DrusenDeposits, etc.)
- biomarkers: All specific measurable entities (DrуsenSize, RetinalThickness, SubretinalFluid, MacularPigmentDensity, VEGF, CFH, etc.)
- diagnosticMethods: All specific modalities (OCT, FluoresceinAngiography, ICGAngiography, FundusPhotography, FundusAutofluorescence, ETDRSVisualAcuity, etc.)
- geneticMarkers: All AMD-associated genes/variants mentioned (CFH, ARMS2, HTRA1, C3, CFB, VEGF, ApoE, CX3CR1, etc.)

Remember: Every abstract adds value. Do not skip adding content just because this is "validation" — completeness matters.
"""
