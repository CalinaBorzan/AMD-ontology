# UMLS Semantic Type Validation

Entities validated: 115

- **MATCH** (pipeline class consistent with UMLS): 76
- **MISMATCH** (pipeline class differs from UMLS): 26
- **UMLS_UNMAPPED** (found in UMLS but semantic type outside our mapping): 0
- **NOT_FOUND** (not in UMLS / Metathesaurus): 13

**Classification precision** (MATCH / (MATCH + MISMATCH)) = **74.51%** (76/102)

## Precision per pipeline class

| Class | Match | Mismatch | Precision |
|-------|------:|---------:|----------:|
| AMD | 1 | 0 | 100.00% |
| AntiVEGFTherapy | 7 | 0 | 100.00% |
| Biomarker | 10 | 6 | 62.50% |
| ClinicalOutcome | 7 | 2 | 77.78% |
| DiagnosticMethod | 5 | 8 | 38.46% |
| Disease | 5 | 0 | 100.00% |
| Gene | 9 | 1 | 90.00% |
| MolecularTarget | 9 | 2 | 81.82% |
| RiskFactor | 2 | 5 | 28.57% |
| Treatment | 21 | 2 | 91.30% |

## Mismatches — pipeline class differs from UMLS

- **Treatment** → pipeline says `Treatment`, UMLS semantic types ['T077'] map to [] (CUI: C1705169)
- **Saffron** → pipeline says `Treatment`, UMLS semantic types ['T002'] map to [] (CUI: C0376238)
- **Drusen** → pipeline says `Biomarker`, UMLS semantic types ['T047'] map to [] (CUI: C1260959)
- **Monocytes** → pipeline says `Biomarker`, UMLS semantic types ['T025'] map to [] (CUI: C0026473)
- **Fibroblasts** → pipeline says `Biomarker`, UMLS semantic types ['T025'] map to [] (CUI: C0016030)
- **Microglia** → pipeline says `Biomarker`, UMLS semantic types ['T025'] map to [] (CUI: C0206116)
- **Plasma** → pipeline says `Biomarker`, UMLS semantic types ['T031'] map to [] (CUI: C1609077)
- **Photoreceptor** → pipeline says `Biomarker`, UMLS semantic types ['T025'] map to [] (CUI: C0031760)
- **OCT** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T116', 'T126'] map to [] (CUI: C0029279)
- **MOS SF-36** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T170'] map to [] (CUI: C4481637)
- **ICG** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T026'] map to [] (CUI: C0230547)
- **Ultrasound** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T169'] map to [] (CUI: C0220934)
- **MAIA** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T204'] map to [] (CUI: C0323300)
- **IReST** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T170'] map to [] (CUI: C5557500)
- **ERG** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T081'] map to [] (CUI: C1551083)
- **PAECT** → pipeline says `DiagnosticMethod`, UMLS semantic types ['T204'] map to [] (CUI: C1083883)
- **Age** → pipeline says `RiskFactor`, UMLS semantic types ['T201'] map to [] (CUI: C1114365)
- **Sunlight** → pipeline says `RiskFactor`, UMLS semantic types ['T070'] map to [] (CUI: C0038817)
- **Occupation** → pipeline says `RiskFactor`, UMLS semantic types ['T090'] map to [] (CUI: C0028811)
- **Oxygen** → pipeline says `RiskFactor`, UMLS semantic types ['T121', 'T123', 'T196'] map to [] (CUI: C0030054)
- **Hypoxia** → pipeline says `RiskFactor`, UMLS semantic types ['T033'] map to [] (CUI: C1963140)
- **Edema** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T201'] map to [] (CUI: C1717255)
- **PED** → pipeline says `ClinicalOutcome`, UMLS semantic types ['T028'] map to [] (CUI: C1417925)
- **Inflammation** → pipeline says `MolecularTarget`, UMLS semantic types ['T046'] map to [] (CUI: C0021368)
- **Ab** → pipeline says `MolecularTarget`, UMLS semantic types ['T170'] map to [] (CUI: C0580927)
- **LOC** → pipeline says `Gene`, UMLS semantic types ['T078'] map to [] (CUI: C0021783)

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
