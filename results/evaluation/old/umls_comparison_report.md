# UMLS Validation — Method Comparison (Direct TUI vs NIH Semantic Groups)

Entities validated: 161

## Overview

| Method | MATCH | MISMATCH | Other | Precision |
|--------|------:|---------:|------:|----------:|
| **TUI-based** (30+ semantic type mappings, hand-curated) | 27 | 25 | 109 | **51.92%** |
| **Semantic Groups** (NIH official 15 groups; 7 classes × 1-3) | 31 | 29 | 101 | **51.67%** |

## Method Agreement

- Both methods MATCH: 27
- Both methods MISMATCH: 23
- Methods DISAGREE on evaluable entities: 2

### Entities where methods disagree

- `Conbercept` (pipeline: AntiVEGFTherapy, UMLS CUI: C5201155)
    - TUI method: **MISMATCH** — semtypes ['T116', 'T123'] → ['Biomarker']
    - Semantic Group method: **MATCH** — groups ['CHEM'] vs expected ['CHEM', 'PROC']
- `HRT` (pipeline: ImagingMethod, UMLS CUI: C0282402)
    - TUI method: **MISMATCH** — semtypes ['T061'] → ['Treatment']
    - Semantic Group method: **MATCH** — groups ['PROC'] vs expected ['DEVI', 'PROC']

## Interpretation

- **TUI method** maps ~30 UMLS semantic type IDs directly to pipeline classes. Fast, simple, but requires maintaining a mapping table.
- **Semantic Group method** uses the 15 official UMLS Semantic Groups (fixed by NIH; TUI → Group mapping is authoritative and published at https://lhncbc.nlm.nih.gov/semanticnetwork/download/sg_v01.txt). Only 7 pipeline classes × 1-3 groups each are hand-mapped. No extra API calls — reuses the TUIs already fetched.
