# UMLS Validation — Method Comparison (Direct TUI vs NIH Semantic Groups)

Entities validated: 115

## Overview

| Method | MATCH | MISMATCH | Other | Precision |
|--------|------:|---------:|------:|----------:|
| **TUI-based** (30+ semantic type mappings, hand-curated) | 73 | 21 | 21 | **77.66%** |
| **Semantic Groups** (NIH official 15 groups; 7 classes × 1-3) | 89 | 20 | 6 | **81.65%** |

## Method Agreement

- Both methods MATCH: 72
- Both methods MISMATCH: 7
- Methods DISAGREE on evaluable entities: 15

### Entities where methods disagree

- `Zeaxanthin` (pipeline: Biomarker, UMLS CUI: C0078752)
    - TUI method: **MISMATCH** — semtypes ['T109', 'T121'] → ['Treatment']
    - Semantic Group method: **MATCH** — groups ['CHEM'] vs expected ['CHEM', 'GENE', 'PHYS']
- `ETDRS` (pipeline: DiagnosticMethod, UMLS CUI: C1275992,C3174563,C3899277,C5939077,C5942789)
    - TUI method: **MISMATCH** — semtypes ['T033', 'T058', 'T074', 'T170', 'T201'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['CONC', 'DEVI', 'DISO', 'PHYS', 'PROC'] vs expected ['DEVI', 'PROC']
- `RiskFactor` (pipeline: RiskFactor, UMLS CUI: C0035648,C0686731,C0686732,C0850664,C3538984)
    - TUI method: **MATCH** — semtypes ['T033', 'T080', 'T201'] → ['Disease', 'RiskFactor']
    - Semantic Group method: **MISMATCH** — groups ['CONC', 'DISO', 'PHYS'] vs expected ['ACTI', 'LIVB']
- `Diet` (pipeline: RiskFactor, UMLS CUI: C0012155,C0012159,C1549512,C3668949)
    - TUI method: **MISMATCH** — semtypes ['T058', 'T168', 'T169'] → ['ClinicalOutcome']
    - Semantic Group method: **MATCH** — groups ['CONC', 'LIVB', 'PROC'] vs expected ['ACTI', 'LIVB']
- `ClinicalOutcome` (pipeline: ClinicalOutcome, UMLS CUI: C1333602,C1519790,C4553328,C4744955,C4744957)
    - TUI method: **MISMATCH** — semtypes ['T033', 'T081', 'T170'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['CONC', 'DISO'] vs expected ['DISO', 'PHEN']
- `Blindness` (pipeline: ClinicalOutcome, UMLS CUI: C0456909)
    - TUI method: **MISMATCH** — semtypes ['T047'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Endophthalmitis` (pipeline: ClinicalOutcome, UMLS CUI: C0014236)
    - TUI method: **MISMATCH** — semtypes ['T047'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Hypotony` (pipeline: ClinicalOutcome, UMLS CUI: C0026827,C0028841,C0154782,C1393640,C4760932)
    - TUI method: **MISMATCH** — semtypes ['T033', 'T047'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Hemorrhage` (pipeline: ClinicalOutcome, UMLS CUI: C0019080)
    - TUI method: **MISMATCH** — semtypes ['T046'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Edema` (pipeline: ClinicalOutcome, UMLS CUI: C0013604,C1717255)
    - TUI method: **MISMATCH** — semtypes ['T046', 'T201'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO', 'PHYS'] vs expected ['DISO', 'PHEN']
- `Scarring` (pipeline: ClinicalOutcome, UMLS CUI: C0008767,C2004491)
    - TUI method: **MISMATCH** — semtypes ['T046'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Dependence` (pipeline: ClinicalOutcome, UMLS CUI: C0011546,C0439857)
    - TUI method: **MISMATCH** — semtypes ['T048', 'T055'] → ['Disease', 'RiskFactor']
    - Semantic Group method: **MATCH** — groups ['ACTI', 'DISO'] vs expected ['DISO', 'PHEN']
- `PED` (pipeline: ClinicalOutcome, UMLS CUI: C1417925,C1418449,C1842534,C2698187,C2698689)
    - TUI method: **MISMATCH** — semtypes ['T028', 'T047', 'T123'] → ['Biomarker', 'Disease']
    - Semantic Group method: **MATCH** — groups ['CHEM', 'DISO', 'GENE'] vs expected ['DISO', 'PHEN']
- `MolecularTarget` (pipeline: MolecularTarget, UMLS CUI: C1513403,C1513404,C1579409,C5419559,C5984809)
    - TUI method: **MISMATCH** — semtypes ['T064', 'T104', 'T121', 'T170'] → ['Treatment']
    - Semantic Group method: **MATCH** — groups ['ACTI', 'CHEM', 'CONC'] vs expected ['CHEM', 'GENE']
- `Conbercept` (pipeline: AntiVEGFTherapy, UMLS CUI: C5201155)
    - TUI method: **MISMATCH** — semtypes ['T116', 'T123'] → ['Biomarker']
    - Semantic Group method: **MATCH** — groups ['CHEM'] vs expected ['CHEM', 'PROC']

## Interpretation

- **TUI method** maps ~30 UMLS semantic type IDs directly to pipeline classes. Fast, simple, but requires maintaining a mapping table.
- **Semantic Group method** uses the 15 official UMLS Semantic Groups (fixed by NIH; TUI → Group mapping is authoritative and published at https://lhncbc.nlm.nih.gov/semanticnetwork/download/sg_v01.txt). Only 7 pipeline classes × 1-3 groups each are hand-mapped. No extra API calls — reuses the TUIs already fetched.
