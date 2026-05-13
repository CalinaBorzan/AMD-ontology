# UMLS Validation — Method Comparison (Direct TUI vs NIH Semantic Groups)

Entities validated: 161

## Overview

| Method | MATCH | MISMATCH | Other | Precision |
|--------|------:|---------:|------:|----------:|
| **TUI-based** (30+ semantic type mappings, hand-curated) | 64 | 48 | 49 | **57.14%** |
| **Semantic Groups** (NIH official 15 groups; 7 classes × 1-3) | 72 | 47 | 42 | **60.50%** |

## Method Agreement

- Both methods MATCH: 62
- Both methods MISMATCH: 38
- Methods DISAGREE on evaluable entities: 12

### Entities where methods disagree

- `Conbercept` (pipeline: AntiVEGFTherapy, UMLS CUI: C5201155)
    - TUI method: **MISMATCH** — semtypes ['T116', 'T123'] → ['Biomarker']
    - Semantic Group method: **MATCH** — groups ['CHEM'] vs expected ['CHEM', 'PROC']
- `MolecularTarget` (pipeline: MolecularTarget, UMLS CUI: C1513403,C1513404,C1579409,C5419559,C5984809)
    - TUI method: **MISMATCH** — semtypes ['T064', 'T104', 'T121', 'T170'] → ['Treatment']
    - Semantic Group method: **MATCH** — groups ['ACTI', 'CHEM', 'CONC'] vs expected ['CHEM', 'GENE']
- `ImagingMethod` (pipeline: ImagingMethod, UMLS CUI: C1275506,C6024199,C6024200,C6024202,C6024204)
    - TUI method: **MISMATCH** — semtypes ['T061', 'T169'] → ['ClinicalOutcome', 'Treatment']
    - Semantic Group method: **MATCH** — groups ['CONC', 'PROC'] vs expected ['DEVI', 'PROC']
- `HRT` (pipeline: ImagingMethod, UMLS CUI: C0282402,C5848651,C5848652)
    - TUI method: **MISMATCH** — semtypes ['T061', 'T201'] → ['Treatment']
    - Semantic Group method: **MATCH** — groups ['PHYS', 'PROC'] vs expected ['DEVI', 'PROC']
- `ETDRS` (pipeline: FunctionalMethod, UMLS CUI: C1275992,C3174563,C3899277,C5939077,C5942789)
    - TUI method: **MISMATCH** — semtypes ['T033', 'T058', 'T074', 'T170', 'T201'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['CONC', 'DEVI', 'DISO', 'PHYS', 'PROC'] vs expected ['DEVI', 'PROC']
- `RiskFactor` (pipeline: RiskFactor, UMLS CUI: C0035648,C0686731,C0686732,C0850664,C3538984)
    - TUI method: **MATCH** — semtypes ['T033', 'T080', 'T201'] → ['Disease', 'RiskFactor']
    - Semantic Group method: **MISMATCH** — groups ['CONC', 'DISO', 'PHYS'] vs expected ['ACTI', 'LIVB']
- `ModifiableRiskFactor` (pipeline: ModifiableRiskFactor, UMLS CUI: C0814292,C4710207,C4717889)
    - TUI method: **MATCH** — semtypes ['T033', 'T058', 'T080'] → ['Disease', 'RiskFactor']
    - Semantic Group method: **MISMATCH** — groups ['CONC', 'DISO', 'PROC'] vs expected ['ACTI', 'LIVB']
- `Diet` (pipeline: ModifiableRiskFactor, UMLS CUI: C0012155,C0012159,C1549512,C3668949)
    - TUI method: **MISMATCH** — semtypes ['T058', 'T168', 'T169'] → ['ClinicalOutcome']
    - Semantic Group method: **MATCH** — groups ['CONC', 'LIVB', 'PROC'] vs expected ['ACTI', 'LIVB']
- `ClinicalOutcome` (pipeline: ClinicalOutcome, UMLS CUI: C1333602,C1519790,C4553328,C4684667,C4744956)
    - TUI method: **MISMATCH** — semtypes ['T033', 'T064', 'T081', 'T170'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['ACTI', 'CONC', 'DISO'] vs expected ['DISO', 'PHEN']
- `DarkAdaptationChange` (pipeline: PrimaryOutcome, UMLS CUI: C1839366)
    - TUI method: **MISMATCH** — semtypes ['T033'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `LesionSizeChange` (pipeline: SecondaryOutcome, UMLS CUI: C2168373)
    - TUI method: **MISMATCH** — semtypes ['T033'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['DISO'] vs expected ['DISO', 'PHEN']
- `QualityOfLifeChange` (pipeline: SecondaryOutcome, UMLS CUI: C2058097,C4068028,C4070167,C4070172,C4086679)
    - TUI method: **MISMATCH** — semtypes ['T033', 'T170', 'T201'] → ['Disease']
    - Semantic Group method: **MATCH** — groups ['CONC', 'DISO', 'PHYS'] vs expected ['DISO', 'PHEN']

## Interpretation

- **TUI method** maps ~30 UMLS semantic type IDs directly to pipeline classes. Fast, simple, but requires maintaining a mapping table.
- **Semantic Group method** uses the 15 official UMLS Semantic Groups (fixed by NIH; TUI → Group mapping is authoritative and published at https://lhncbc.nlm.nih.gov/semanticnetwork/download/sg_v01.txt). Only 7 pipeline classes × 1-3 groups each are hand-mapped. No extra API calls — reuses the TUIs already fetched.
