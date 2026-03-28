system_prompt = """
Context: You are a medical knowledge extraction expert creating an ontology for {process_name}. {process_description}

IMPORTANT: The input is a DOMAIN SPECIFICATION from AMD research abstracts. Expect concise descriptions without quantitative measurements — this is normal.

Objective: Extract medical entities and relationships to build an ontology schema. The schema should represent: diseases, treatments, biomarkers, risk factors, diagnostic methods, and their relationships.

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

CLASS vs INDIVIDUAL:
- A CLASS is a category that can have subtypes. Ask: "can this have subtypes?" If yes, it is a class.
  WetAMD is a class (type of AMD). AntiVEGFTherapy is a class (type of treatment).
- An INDIVIDUAL is one specific real-world thing that cannot have subtypes.
  Ranibizumab is an individual (one specific drug). CFH is an individual (one specific gene). OCT is an individual (one specific device).
- An entity is EITHER a class OR an individual. NEVER both (no punning).

CRITICAL INSTRUCTIONS:
1. Hierarchy: Disease → AMD → WetAMD, DryAMD, GeographicAtrophy. ONLY actual AMD variants go under AMD. Associated diseases (Glaucoma, Alzheimer's, Diabetic Retinopathy) go under Disease directly — they are NOT subtypes of AMD.
2. Extract MEDICAL CONCEPTS (diseases, drugs, biomarkers), NOT procedures
3. Define RELATIONSHIPS (treats, causes, indicates, diagnoses), NOT steps
4. Use specific AMD terminology (choroidal neovascularization, drusen, RPE, VEGF)
5. Do NOT require quantitative values — a class or relationship is valid even without numeric data

Output Format: Valid JSON ONLY. Use ```json fenced code block.
"""

user_prompt = """
Based on the AMD domain specification below, create an initial medical ontology schema for {process_name}.

Domain Specification:
{context}

Extract and organize these AMD-specific entity types:

1. **Disease Classes** — Main types and subtypes:
   - AMD subtypes (under AMD): Dry AMD, Wet AMD, Geographic Atrophy, Intermediate AMD
   - Associated diseases (under Disease, NOT under AMD): Glaucoma, Alzheimer's, Diabetic Retinopathy
   - Pathological entities: Choroidal Neovascularization (CNV), Drusen, RPE detachment

2. **Treatment Classes** — Therapeutic approaches:
   - Anti-VEGF agents: Ranibizumab (Lucentis), Aflibercept (Eylea), Bevacizumab (Avastin), Brolucizumab
   - Surgical: Photodynamic Therapy (PDT), Laser Photocoagulation, Submacular Surgery
   - Supplements: AREDS, Lutein, Zeaxanthin, Omega-3
   - Emerging: Gene therapy, Complement inhibitors, Stem cell therapy

3. **Genetic/Molecular Biomarker Classes**:
   - Risk genes: CFH, ARMS2, HTRA1, C3, CFB, C2
   - Molecular targets: VEGF, PDGF, Complement pathway proteins

4. **Imaging and Clinical Biomarker Classes**:
   - Structural: Drusen, Retinal thickness, Subretinal fluid
   - Functional: Visual acuity (ETDRS), Contrast sensitivity, Reading speed

5. **Diagnostic Method Classes**:
   - Imaging: OCT, Fluorescein Angiography, ICG Angiography, Fundus Photography, Fundus Autofluorescence
   - Functional: Visual field testing, Electroretinography, Flicker photometry

6. **Risk Factor Classes**:
   - Non-modifiable: Age, Genetics, Family history, Gender
   - Modifiable: Smoking, Diet, BMI/Obesity, Sun exposure, Cardiovascular disease

7. **Clinical Outcome Classes**:
   - Primary: Visual acuity change, Prevention of vision loss
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

Return ONLY the complete JSON schema. Use ```json fenced code block.
"""
