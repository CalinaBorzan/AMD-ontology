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
2. Create subclasses only when they are ONTOLOGICALLY CORRECT — a genuine category with 3+ distinct sibling members. Don't create decorative classes that just group 1-2 instances; keep those as instances. There is no fixed class count cap — add classes when they're justified, skip when they're not.
3. NEVER create a 'Gene' class — genes are instances of Biomarker (the `associatedWith` relationship links Biomarker genes to Disease).
4. MolecularTarget (VEGF, VEGF-A/B/C, VEGFR1/2, S1P, complement C3, PDGF) is a ROOT class, NOT a subclass of Biomarker. Its INSTANCES are the specific target names.
5. Extract MEDICAL CONCEPTS (diseases, drugs, biomarkers, outcomes, targets), NOT procedures or study metadata.
6. Define RELATIONSHIPS using ONLY the 9 predicates listed below.
7. CLINICAL OUTCOMES: extract every outcome mentioned (blindness, vision loss, visual impairment, endophthalmitis, ...) as INSTANCES of ClinicalOutcome. Canonicalize variants: 'severe vision loss' / 'irreversible vision loss' / 'permanent vision loss' → ONE instance `VisionLoss`.
8. Do NOT require quantitative values — a class, instance, or relationship is valid even without numeric data.
9. NAMING: CamelCase, NO spaces/dashes/slashes/parentheses/apostrophes. Valid: ChoroidalNeovascularization, AgeRelatedMaculopathy, VitaminC. Invalid: "Vitamin C", "Alzheimer's disease", "TNF-a", "ARMS2/HTRA1", "OCT 3".
10. NO PUNNING for drugs: brand and generic name of the same drug are the SAME entity. Use the generic only — do NOT add both Lucentis AND Ranibizumab, both Eylea AND Aflibercept, both Avastin AND Bevacizumab.
11. CANONICALIZATION (general): pick ONE name per concept; map synonyms, abbreviations, and British vs American spellings to the same entity. No near-duplicates.
12. SKIP study acronyms (LUCAS, MARINA, ANCHOR, ASPREE, AURA Study, RETILASE, FAM-Study, PrONTO) and anything ending in Study/Trial/Survey/Cohort/Registry/Group. Skip institutions, hospitals, clinics, places, persons.
13. SKIP cell types (monocytes, fibroblasts, microglia, photoreceptors, macrophages, pericytes).

Output Format: Valid JSON ONLY. Use ```json fenced code block.
"""

user_prompt = """
Based on the AMD domain specification below, create an initial medical ontology schema for {process_name}.

Domain Specification:
{context}

ROOT CLASSES (use EXACTLY these — do NOT invent new roots):
  Disease, Treatment, Biomarker, DiagnosticMethod, RiskFactor,
  ClinicalOutcome, MolecularTarget

Create a subclass ONLY when it represents a genuine medical category with
multiple distinct members (ontologically justified), not just as a
grouping tag for one or two instances. There is no fixed limit on class
count — add classes when they are CORRECT, skip them when they are
decorative. A class with one or zero instances should be an instance of
its would-be parent instead.

Standard subclasses in AMD:
  - Under Disease:   AMD → DryAMD, WetAMD, GeographicAtrophy (well-established)
  - Under Treatment: AntiVEGFTherapy (well-established sibling of other
                     therapy modalities). Other Treatment subclasses are
                     acceptable only if they genuinely group 3+ distinct
                     members in the domain (e.g., PhotodynamicTherapy
                     would be a subclass only if you can name 3+ different
                     PDT protocols; otherwise it is an INSTANCE).

EVERYTHING ELSE IS AN INSTANCE under a root, including:
  - Specific drugs (Ranibizumab, Aflibercept, Bevacizumab, Verteporfin,
    AREDS, AREDS2, Lutein, Zeaxanthin, triamcinolone, ...) → Treatment
    or AntiVEGFTherapy instances
  - Procedures (PhotodynamicTherapy, LaserPhotocoagulation, Submacular
    Surgery) → Treatment instances
  - Specific genes (CFH, ARMS2, HTRA1, C3, CFB, C2, ApoE, CX3CR1, ...)
    → Biomarker instances (NOT a separate 'Gene' class)
  - Molecular targets (VEGF, VEGF-A, VEGF-B, VEGF-C, VEGFR1, VEGFR2,
    S1P, PDGF, Complement C3) → MolecularTarget instances
  - Structural biomarkers (Drusen, RetinalThickness, SubretinalFluid)
    → Biomarker instances
  - Imaging devices (OCT, FluoresceinAngiography, ICG, FundusPhotography,
    Electroretinography) → DiagnosticMethod instances
  - Risk factors (Smoking, Age, FamilyHistory, Obesity, SunExposure)
    → RiskFactor instances
  - Clinical outcomes (Blindness, VisionLoss, LegalBlindness,
    VisualImpairment, Endophthalmitis, RetinalDetachment) → ClinicalOutcome
    instances. Canonicalize variants: 'severe vision loss' / 'irreversible
    vision loss' / 'permanent vision loss' → ONE instance `VisionLoss`.

RELATIONSHIPS to define (these 9 properties are the vocabulary):
- **treats**: Treatment → Disease (e.g., Ranibizumab treats WetAMD)
- **inhibits**: Treatment → MolecularTarget (e.g., Ranibizumab inhibits VEGF)
- **causesOrIncreases**: RiskFactor → Disease
- **indicates**: Biomarker → Disease
- **diagnosedBy**: Disease → DiagnosticMethod
- **hasSymptom**: Disease → ClinicalOutcome
- **measuredBy**: Biomarker → DiagnosticMethod
- **associatedWith**: Biomarker → Disease (for genes: CFH associatedWith AMD)
- **assessedBy**: ClinicalOutcome → DiagnosticMethod

Return ONLY the complete JSON schema. Use ```json fenced code block.
"""
