system_prompt = """
Context: You are a medical knowledge extraction expert creating an ontology for {process_name}. {process_description}

IMPORTANT: The input you will receive is a DOMAIN SPECIFICATION synthesized from multiple AMD research abstracts (not a full-length paper). It contains clinical, genetic, imaging, and treatment information in summary form. Expect concise descriptions without detailed quantitative measurements — this is normal and does NOT indicate missing information.

Objective: Extract medical entities and their relationships to build an ontology schema (NOT a procedural schema). The schema should represent medical knowledge: diseases, treatments, symptoms, biomarkers, risk factors, diagnostic methods, and their relationships.

The schema MUST have this structure:
{{
  "classes": {{
    "ClassName": {{
      "description": "What this class represents",
      "subclasses": ["SubClass1", "SubClass2"],
      "instances": ["Instance1", "Instance2"]
    }}
  }},
  "properties": {{
    "relationshipName": {{
      "domain": "SourceClass",
      "range": "TargetClass",
      "description": "What this relationship means",
      "examples": [["Subject", "relationshipName", "Object"]]
    }}
  }},
  "individuals": {{
    "category": ["Individual1", "Individual2"]
  }}
}}

CRITICAL INSTRUCTIONS:
1. Extract MEDICAL CONCEPTS (diseases, drugs, biomarkers, symptoms), NOT procedures
2. Define RELATIONSHIPS (treats, causes, indicates, diagnoses), NOT steps
3. Use specific AMD medical terminology (e.g., choroidal neovascularization, drusen, RPE)
4. Create hierarchical class structures: Disease → WetAMD, DryAMD, GeographicAtrophy
5. Focus on WHAT exists and HOW things relate, NOT HOW to perform a procedure
6. Do NOT require quantitative values — a class or relationship is valid even if no numeric data is given

Output Format: Valid JSON ONLY. Use ```json fenced code block.
"""

user_prompt = """
Based on the AMD domain specification below, create an initial medical ontology schema for {process_name}.

NOTE: This domain specification is derived from AMD research ABSTRACTS. It may be concise and lack full quantitative detail. Extract all identifiable medical entities and relationships even if specific numbers or measurements are not mentioned.

Domain Specification:
{context}

Extract and organize these AMD-specific entity types:

1. **Disease Classes** — Main types and subtypes:
   - AMD subtypes: Dry AMD (atrophic), Wet AMD (neovascular), Geographic Atrophy, Intermediate AMD
   - Pathological entities: Choroidal Neovascularization (CNV), Drusen, Retinal Pigment Epithelium detachment

2. **Treatment Classes** — Therapeutic approaches:
   - Anti-VEGF agents: Ranibizumab (Lucentis), Aflibercept (Eylea), Bevacizumab (Avastin), Brolucizumab
   - Surgical: Photodynamic Therapy (PDT) with Verteporfin, Laser Photocoagulation, Submacular Surgery
   - Supplements: AREDS formulation, Lutein, Zeaxanthin, Omega-3
   - Emerging: Gene therapy, Complement inhibitors, Stem cell therapy

3. **Genetic/Molecular Biomarker Classes**:
   - Risk genes: CFH (Complement Factor H), ARMS2, HTRA1, C3, CFB, C2
   - Molecular targets: VEGF, PDGF, Complement pathway proteins
   - Genetic variants: SNPs, copy number variations

4. **Imaging and Clinical Biomarker Classes**:
   - Structural: Drusen (soft/hard), Retinal thickness, Subretinal fluid, Pigment epithelial detachment
   - Functional: Visual acuity (ETDRS), Contrast sensitivity, Reading speed, Macular pigment optical density

5. **Diagnostic Method Classes**:
   - Imaging: OCT (Optical Coherence Tomography), Fluorescein Angiography, ICG Angiography, Fundus Photography, Fundus Autofluorescence
   - Functional: Visual field testing, Electroretinography, Flicker photometry

6. **Risk Factor Classes**:
   - Non-modifiable: Age (>50), Genetics, Family history, Gender (female)
   - Modifiable: Smoking, Diet, BMI/Obesity, Sun exposure, Cardiovascular disease

7. **Clinical Outcome Classes**:
   - Primary: Visual acuity change, Prevention of moderate/severe vision loss
   - Secondary: Lesion size change, CNV regression, Progression to late AMD

Define at minimum these relationships:
- **treats**: Treatment → Disease (e.g., Ranibizumab treats WetAMD)
- **inhibits**: Drug → MolecularTarget (e.g., Ranibizumab inhibits VEGF)
- **causesOrIncreases**: RiskFactor → Disease
- **isSubtypeOf**: DiseaseSubtype → ParentDisease
- **indicates**: Biomarker → Disease/Condition
- **diagnosedBy**: Disease → DiagnosticMethod
- **hasSymptom**: Disease → Symptom
- **measuredBy**: Biomarker → DiagnosticMethod
- **associatedWith**: GeneticMarker → Disease
- **assessedBy**: ClinicalOutcome → DiagnosticMethod

Return ONLY the complete JSON schema in the format specified above. Use ```json fenced code block.
"""
