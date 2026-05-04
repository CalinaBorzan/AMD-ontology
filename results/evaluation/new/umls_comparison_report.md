# UMLS Validation — Method Comparison (Direct TUI vs NIH Semantic Groups)

Entities validated: 115

## Overview

| Method | MATCH | MISMATCH | Other | Precision |
|--------|------:|---------:|------:|----------:|
| **TUI-based** (30+ semantic type mappings, hand-curated) | 63 | 16 | 36 | **79.75%** |
| **Semantic Groups** (NIH official 15 groups; 7 classes × 1-3) | 76 | 26 | 13 | **74.51%** |

## Method Agreement

- Both methods MATCH: 63
- Both methods MISMATCH: 7
- Methods DISAGREE on evaluable entities: 9

### Entities where methods disagree

- `Zeaxanthin` (pipeline: Biomarker, UMLS CUI: C0078752)
    - TUI method: **MISMATCH** — semtypes ['T109', 'T121'] → ['Treatment']
    - Semantic Group method: **MATCH** — groups ['CHEM'] vs expected ['CHEM', 'GENE', 'PHYS']
- `Blindness` (pipeline: ClinicalOutcome, UMLS CUI: C0456909)
    - TUI method: **MISMATCH** — semtypes ['T047'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Endophthalmitis` (pipeline: ClinicalOutcome, UMLS CUI: C0014236)
    - TUI method: **MISMATCH** — semtypes ['T047'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Hypotony` (pipeline: ClinicalOutcome, UMLS CUI: C4760932)
    - TUI method: **MISMATCH** — semtypes ['T047'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Hemorrhage` (pipeline: ClinicalOutcome, UMLS CUI: C0019080)
    - TUI method: **MISMATCH** — semtypes ['T046'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Scarring` (pipeline: ClinicalOutcome, UMLS CUI: C2004491)
    - TUI method: **MISMATCH** — semtypes ['T046'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Depression` (pipeline: ClinicalOutcome, UMLS CUI: C0011570)
    - TUI method: **MISMATCH** — semtypes ['T048'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Dependence` (pipeline: ClinicalOutcome, UMLS CUI: C0439857)
    - TUI method: **MISMATCH** — semtypes ['T048'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `Conbercept` (pipeline: AntiVEGFTherapy, UMLS CUI: C5201155)
    - TUI method: **MISMATCH** — semtypes ['T116', 'T123'] → ['Biomarker']
    - Semantic Group method: **MATCH** — groups ['CHEM'] vs expected ['CHEM', 'PROC']

## Interpretation

- **TUI method** maps ~30 UMLS semantic type IDs directly to pipeline classes. Fast, simple, but requires maintaining a mapping table.
- **Semantic Group method** uses the 15 official UMLS Semantic Groups (fixed by NIH; TUI → Group mapping is authoritative and published at https://lhncbc.nlm.nih.gov/semanticnetwork/download/sg_v01.txt). Only 7 pipeline classes × 1-3 groups each are hand-mapped. No extra API calls — reuses the TUIs already fetched.
