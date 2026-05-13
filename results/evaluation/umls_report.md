# UMLS Semantic Type Validation

Entities validated: 115

- **MATCH** (pipeline class consistent with UMLS): 63
- **MISMATCH** (pipeline class differs from UMLS): 16
- **UMLS_UNMAPPED** (found in UMLS but semantic type outside our mapping): 23
- **NOT_FOUND** (not in UMLS / Metathesaurus): 13

**Classification precision** (MATCH / (MATCH + MISMATCH)) = **79.75%** (63/79)

## Precision per pipeline class

| Class | Match | Mismatch | Precision |
|-------|------:|---------:|----------:|
| AMD | 1 | 0 | 100.00% |
| AntiVEGFTherapy | 6 | 1 | 85.71% |
| Biomarker | 8 | 2 | 80.00% |
| ClinicalOutcome | 0 | 8 | 0.00% |
| DiagnosticMethod | 3 | 2 | 60.00% |
| Disease | 5 | 0 | 100.00% |
| Gene | 9 | 0 | 100.00% |
| MolecularTarget | 9 | 1 | 90.00% |
| RiskFactor | 1 | 2 | 33.33% |
| Treatment | 21 | 0 | 100.00% |

## Mismatches — pipeline class differs from UMLS

- **Drusen** → pipeline says `Biomarker`, UMLS semantic types ['T047'] map to ['Disease'] (CUI: C1260959)
- **Zeaxanthin** → pipeline says `Biomarker`, UMLS semantic types ['T109', 'T121'] map to ['Treatment'] (CUI: C0078752)
- **OCT** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T116', 'T126'] map to ['Biomarker'] (CUI: C0029279)
- **Ultrasound** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T169'] map to ['ClinicalOutcome'] (CUI: C0220934)
- **Oxygen** → pipeline says `RiskFactor`, UMLS semantic types ['T121', 'T123', 'T196'] map to ['Biomarker', 'Treatment'] (CUI: C0030054)
- **Hypoxia** → pipeline says `RiskFactor`, UMLS semantic types ['T033'] map to ['Disease'] (CUI: C1963140)
- **Blindness** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T047'] map to ['Disease'] (CUI: C0456909)
- **Endophthalmitis** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T047'] map to ['Disease'] (CUI: C0014236)
- **Hypotony** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T047'] map to ['Disease'] (CUI: C4760932)
- **Hemorrhage** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T046'] map to ['Disease'] (CUI: C0019080)
- **Scarring** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T046'] map to ['Disease'] (CUI: C2004491)
- **Depression** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T048'] map to ['Disease'] (CUI: C0011570)
- **Dependence** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T048'] map to ['Disease'] (CUI: C0439857)
- **PED** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T028'] map to ['Biomarker'] (CUI: C1417925)
- **Inflammation** → pipeline says `MolecularTarget`, UMLS semantic types ['T046'] map to ['Disease'] (CUI: C0021368)
- **Conbercept** → pipeline says `AntiVEGFTherapy`, UMLS semantic types ['T116', 'T123'] map to ['Biomarker'] (CUI: C5201155)

## Not in UMLS

- `Rheohemapheresis` (pipeline class: Treatment)
- `Rheopheresis` (pipeline class: Treatment)
- `DiagnosticMethod` (pipeline class: DiagnosticMethod)
- `Maculometer` (pipeline class: DiagnosticMethod)
- `NEI VFQ-25` (pipeline class: DiagnosticMethod)
- `RiskFactor` (pipeline class: RiskFactor)
- `ClinicalOutcome` (pipeline class: ClinicalOutcome)
- `MolecularTarget` (pipeline class: MolecularTarget)
- `DryAMD` (pipeline class: DryAMD)
- `WetAMD` (pipeline class: WetAMD)
- `GeographicAtrophy` (pipeline class: GeographicAtrophy)
- `ChoroidalNeovascularization` (pipeline class: ChoroidalNeovascularization)
- `AntiVEGFTherapy` (pipeline class: AntiVEGFTherapy)

## Methodology

- Queried UMLS Metathesaurus REST API for each class and instance in the ontology.
- For each entity, retrieved the best-match CUI and its semantic type(s) (TUI).
- Mapped UMLS semantic types to pipeline classes using a manually-curated table (see SEMTYPE_TO_CLASS in `backend/tools/run_umls_validation.py`). The mapping covers ~30 semantic types across 7 pipeline classes; mappings follow standard biomedical ontology conventions.
- Pipeline subclasses are aggregated to their root for comparison (AntiVEGFTherapy → Treatment, Gene → Biomarker, AMD subtypes → Disease, MolecularTarget treated as Biomarker-equivalent).
