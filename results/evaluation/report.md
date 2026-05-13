# Pipeline Evaluation vs. Reference Annotations

Evaluated against 32 unique human-annotated abstracts from Stage 3 corpus.

## Entities (per class)

| Class | TP | FP | FN | Precision | Recall | F1 |
|-------|---:|---:|---:|----------:|-------:|---:|
| Biomarker | 7 | 13 | 13 | 35.00% | 35.00% | 35.00% |
| ClinicalOutcome | 3 | 5 | 10 | 37.50% | 23.08% | 28.57% |
| DiagnosticMethod | 0 | 8 | 1 | 0.00% | 0.00% | 0.00% |
| Disease | 4 | 4 | 9 | 50.00% | 30.77% | 38.10% |
| MolecularTarget | 0 | 2 | 0 | 0.00% | 0.00% | 0.00% |
| RiskFactor | 0 | 5 | 2 | 0.00% | 0.00% | 0.00% |
| Treatment | 14 | 8 | 16 | 63.64% | 46.67% | 53.85% |
| **OVERALL** | 28 | 45 | 51 | **38.36%** | **35.44%** | **36.84%** |

## Relations (per predicate)

| Predicate | TP | FP | FN | Precision | Recall | F1 |
|-----------|---:|---:|---:|----------:|-------:|---:|
| associatedWith | 0 | 8 | 0 | 0.00% | 0.00% | 0.00% |
| causesOrIncreases | 0 | 8 | 14 | 0.00% | 0.00% | 0.00% |
| hasSymptom | 1 | 0 | 4 | 100.00% | 20.00% | 33.33% |
| indicates | 0 | 3 | 0 | 0.00% | 0.00% | 0.00% |
| inhibits | 0 | 5 | 2 | 0.00% | 0.00% | 0.00% |
| treats | 2 | 1 | 24 | 66.67% | 7.69% | 13.79% |
| **OVERALL** | 3 | 25 | 44 | **10.71%** | **6.38%** | **8.00%** |

## False negatives — entities pipeline missed (up to 20)

- `vision loss` should have been **ClinicalOutcome** (abstract #0)
- `choroidal neovascular membrane formation (CNVM)` should have been **Biomarker** (abstract #0)
- `laser photocoagulation` should have been **Treatment** (abstract #0)
- `fundus autofluorescence changes` should have been **DiagnosticMethod** (abstract #1)
- `Lutein [wrong class: got Biomarker]` should have been **Treatment** (abstract #3)
- `vitamin C` should have been **Treatment** (abstract #3)
- `vitamin E` should have been **Treatment** (abstract #3)
- `beta-carotene` should have been **Treatment** (abstract #3)
- `photodynamic therapy to transpupillary thermotherapy` should have been **Treatment** (abstract #4)
- `choroidal neovascularization` should have been **ClinicalOutcome** (abstract #4)
- `Photodynamic therapy ( PDT)` should have been **Treatment** (abstract #4)
- `Transpupillary thermotherapy ( TTT)` should have been **Treatment** (abstract #4)
- `polymorphisms (small gene variances)` should have been **Biomarker** (abstract #5)
- `visual impairment` should have been **ClinicalOutcome** (abstract #6)
- `recurrent subfoveal CNV` should have been **Disease** (abstract #8)
- `CNV` should have been **Disease** (abstract #8)
- `submacular surgery` should have been **Treatment** (abstract #8)
- `breakdown of the macular pigment (MP)` should have been **Biomarker** (abstract #10)
- `fluocinolone implant` should have been **Treatment** (abstract #12)
- `CNVM` should have been **Disease** (abstract #12)
- … and 31 more

## False positives — entities pipeline invented (up to 20)

- `Glaucoma` labeled **Disease**
- `Cataract` labeled **Disease**
- `Retinopathy` labeled **Disease**
- `Uveitis` labeled **Disease**
- `Verteporfin` labeled **Treatment**
- `Macuvite` labeled **Treatment**
- `Tropicamide` labeled **Treatment**
- `Copaxone` labeled **Treatment**
- `iSONEP` labeled **Treatment**
- `Sonepcizumab` labeled **Treatment**
- `Remicade` labeled **Treatment**
- `Drusen` labeled **Biomarker**
- `C2` labeled **Biomarker**
- `Photoreceptors` labeled **Biomarker**
- `Zeaxanthin` labeled **Biomarker**
- `Monocytes` labeled **Biomarker**
- `Lipofuscin` labeled **Biomarker**
- `Microglia` labeled **Biomarker**
- `PRLs` labeled **Biomarker**
- `rs11200638` labeled **Biomarker**
- … and 21 more

## False negatives — triples pipeline missed (up to 20)

- `choroidal neovascular membrane formation (CNVM)` —**causesOrIncreases**→ `vision loss` (abstract #0)
- `corticosteroid injection around the eye` —**inhibits**→ `severe vision loss` (abstract #0)
- `age-related macular degeneration` —**hasSymptom**→ `severe vision loss` (abstract #0)
- `hereditary` —**causesOrIncreases**→ `Age-related macular degeneration (AMD)` (abstract #2)
- `environmental` —**causesOrIncreases**→ `Age-related macular degeneration (AMD)` (abstract #2)
- `Lutein` —**treats**→ `age-related macular degeneration` (abstract #3)
- `vitamin C` —**treats**→ `age-related macular degeneration` (abstract #3)
- `vitamin E` —**treats**→ `age-related macular degeneration` (abstract #3)
- `beta-carotene` —**treats**→ `age-related macular degeneration` (abstract #3)
- `photodynamic therapy to transpupillary thermotherapy` —**treats**→ `choroidal neovascularization` (abstract #4)
- `Photodynamic therapy ( PDT)` —**treats**→ `neovascular membranes` (abstract #4)
- `Transpupillary thermotherapy ( TTT)` —**treats**→ `choroidal neovascularization` (abstract #4)
- `significant genetic component` —**causesOrIncreases**→ `AMD` (abstract #5)
- `Age-related macular degeneration (AMD)` —**hasSymptom**→ `visual impairment` (abstract #6)
- `potential environmental influences` —**causesOrIncreases**→ `AMD` (abstract #6)
- `AMD` —**causesOrIncreases**→ `Amish individuals` (abstract #6)
- `laser treatment` —**treats**→ `recurrent subfoveal CNV` (abstract #8)
- `photodynamic therapy with verteporfin` —**treats**→ `moderate and server loss of vision` (abstract #8)
- `submacular surgery` —**treats**→ `CNV` (abstract #8)
- `photodynamic therapy` —**treats**→ `age-related macular degeneration (AMD)` (abstract #9)
- … and 24 more

## False positives — triples pipeline invented (up to 20)

- `Smoking` —**causesOrIncreases**→ `ARMD`
- `rs11200638` —**associatedWith**→ `ARMD`
- `Bevacizumab` —**inhibits**→ `VEGF`
- `Avastin` —**causesOrIncreases**→ `Endophthalmitis`
- `Occupation` —**causesOrIncreases**→ `ARMD`
- `Macuvite` —**treats**→ `ARMD`
- `iSONEP` —**inhibits**→ `S1P`
- `Lutein` —**associatedWith**→ `ARMD`
- `Lutein` —**indicates**→ `ARMD`
- `CFH` —**associatedWith**→ `ARMD`
- `Zeaxanthin` —**associatedWith**→ `ARMD`
- `HTRA1` —**associatedWith**→ `ARMD`
- `rs1061170` —**associatedWith**→ `ARMD`
- `Age` —**causesOrIncreases**→ `ARMD`
- `Age` —**causesOrIncreases**→ `Retinopathy`
- `Lipofuscin` —**indicates**→ `ARMD`
- `C2` —**associatedWith**→ `ARMD`
- `Zeaxanthin` —**indicates**→ `ARMD`
- `Avastin` —**inhibits**→ `VEGF`
- `Ranibizumab` —**inhibits**→ `VEGF`
- … and 5 more

## Filtering applied

- Non-entity phrases skipped from entity evaluation: 23
- Triples skipped because head/child was a descriptive phrase: 17

## Methodology notes

- Reference labels **BODY PART** and **PROGRESSION** are not mapped to pipeline classes (no direct equivalent). Entities with these labels are excluded.
- Reference relations **AFFECT**, **PRESENT**, **IMPROVE** are not mapped (too generic or semantically divergent).
- Predicate mapping is **direction-aware**: reference `CAUSE` maps to `hasSymptom` for Disease→Symptom but `causesOrIncreases` for RiskFactor→Disease. This reflects the pipeline's finer-grained predicates.
- Entity matching is fuzzy: lowercase, punctuation/whitespace stripped. Parenthesized acronyms are extracted as candidate matches, and substring matching is applied so that pipeline entity `'AMD'` matches the reference span `'Age-Related Macular Degeneration (AMD)'`.
- Descriptive phrases (>4 words containing verbs like *impair, cause, present, develop*, or >8 words total) are filtered from evaluation because they are not atomic ontology entities.
- False positives at the set level: a pipeline entity counts as FP only if it literally appears in a reference abstract text but is not in any reference annotation. Entities the pipeline extracted from abstracts outside the reference set are not counted as FPs.
