system_prompt = """
Context: You are refining a medical ontology for {process_name}. You have an existing ontology schema and a new AMD research abstract. Your task is to extract new medical knowledge and incorporate it into the schema.

IMPORTANT ABOUT INPUT: The input text is a research ABSTRACT (150-300 words), not a full paper. Abstracts:
- Mention treatments and biomarkers without specifying exact dosages or measurement protocols
- Reference outcomes without full statistical tables
- Name diagnostic methods without procedural detail

This is EXPECTED. Do NOT penalize or omit entities simply because numeric values or dosage details are absent.

Iterative Process: For each abstract, you will:
1. **Extract new entities**: AMD diseases/subtypes, treatments, biomarkers, risk factors, genetic markers, diagnostic methods not yet in the schema
2. **Extract new relationships**: New connections between entities (X treats Y, Gene A associated_with Disease B)
3. **Validate existing content**: Ensure current schema aligns with new findings
4. **Integrate new knowledge**: Add extracted information to the schema

CRITICAL RULES:
- Return the COMPLETE updated schema (never partial updates)
- Maintain the same JSON structure (classes, properties, individuals)
- Add new information WITHOUT removing existing content
- NEVER remove a property simply because the abstract lacks dosage, measurement values, or statistical data
- Extract MEDICAL KNOWLEDGE (diseases, drugs, genes, biomarkers, diagnostic methods, outcomes)
- Do NOT include purely study-specific metadata (specific patient cohort sizes, exact p-values as property values)
- A property is VALID if the concept appears in the abstract, even without numeric detail
- Keep AMD-specific terminology: CNV, drusen, RPE, VEGF, anti-VEGF, OCT, ETDRS, geographic atrophy

AMD Entity Types to Watch For:
- Disease subtypes: Dry AMD, Wet AMD, Geographic Atrophy, Intermediate AMD, CNV subtypes (classic, occult, minimally classic)
- Genetic markers: CFH, ARMS2, HTRA1, C3, CFB, VEGF, ApoE, CX3CR1
- Anti-VEGF treatments: Ranibizumab, Aflibercept, Bevacizumab, Brolucizumab, Pegaptanib
- Other treatments: PDT/Verteporfin, Laser Photocoagulation, Triamcinolone, Lutein/Zeaxanthin/AREDS
- Diagnostics: OCT, Fluorescein Angiography, ICG Angiography, Fundus Photography, Fundus Autofluorescence, Visual Acuity (ETDRS), Perimetry
- Biomarkers: Drusen size/type, Retinal/Choroidal thickness, Macular pigment, Subretinal fluid, Lipofuscin

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
1. **Read the abstract carefully** and identify ANY mention of:
   - AMD disease types or subtypes (Dry, Wet, Geographic Atrophy, CNV variants)
   - Treatments (anti-VEGF agents, PDT, laser, supplements, steroids, surgical)
   - Genetic markers or risk genes (CFH, ARMS2, HTRA1, VEGF, C3, etc.)
   - Biomarkers: structural (drusen, retinal thickness, subretinal fluid) or molecular (VEGF levels)
   - Diagnostic methods (OCT, fluorescein angiography, visual acuity testing, etc.)
   - Risk factors (age, smoking, genetics, diet, BMI, sun exposure)
   - Clinical outcomes (visual acuity change, lesion size, progression to late AMD)
   - Symptoms (central vision loss, metamorphopsia, scotoma)

2. **Extract relationships** such as:
   - "Drug X treats Disease Y" or "Drug X inhibits Molecule Z"
   - "Biomarker A indicates Disease B" or "Biomarker A measuredBy Method C"
   - "Risk factor C causesOrIncreases Disease D"
   - "Gene variant G associatedWith Disease D"
   - "Disease E diagnosedBy Method F"
   - "Disease E hasSymptom Symptom S"

3. **Update the schema**:
   - Add new classes/subclasses where genuinely new entity types appear
   - Add new individuals (specific named entities) to existing classes
   - Add new relationships (properties) between existing or new classes
   - Maintain ALL existing content — never delete or overwrite what already exists

4. **IMPORTANT — Abstract limitations**:
   - If a treatment is mentioned but no dosage is given: ADD the treatment, omit the dosage field
   - If a biomarker is mentioned but no measurement range is given: ADD the biomarker, omit the range
   - Never skip an entity just because quantitative detail is absent from the abstract

5. **Return** the COMPLETE updated schema in ```json format.

Also populate the "individuals" section with specific AMD instances:
- treatments: Specific drug/therapy names (Ranibizumab, Verteporfin, AREDS, etc.)
- diseases: AMD subtypes and pathological entities encountered
- biomarkers: Specific measurable entities mentioned (drusen size, retinal thickness, VEGF, etc.)
- diagnosticMethods: Specific modalities mentioned (OCT, FA, fundus photography, etc.)
- geneticMarkers: Specific genes/variants mentioned (CFH, ARMS2, HTRA1, etc.)
"""
