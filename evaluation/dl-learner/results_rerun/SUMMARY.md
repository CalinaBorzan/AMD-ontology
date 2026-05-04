# DL-Learner rerun summary
OWL: ontology/AMD_final_clean.owl
Experiments: 15

## experiment3_amd_genes.conf

Status: OK

```
1: Treatment or ((associatedWith some Disease) and (indicates only RiskFactor)) (pred. acc.: 90.00%, F-measure: 91.67%)
2: DiagnosticMethod or ((associatedWith some Disease) and (indicates only RiskFactor)) (pred. acc.: 90.00%, F-measure: 91.67%)
3: ClinicalOutcome or ((associatedWith some Disease) and (indicates only RiskFactor)) (pred. acc.: 90.00%, F-measure: 91.67%)
4: (Treatment or (indicates only RiskFactor)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)
5: (Gene or (indicates only Nothing)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)
6: (Gene or (indicates only RiskFactor)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)
7: (DiagnosticMethod or (indicates only Nothing)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)
8: (DiagnosticMethod or (indicates only RiskFactor)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)
9: (ClinicalOutcome or (indicates only Nothing)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)
10: (ClinicalOutcome or (indicates only RiskFactor)) and (associatedWith some Disease) (pred. acc.: 90.00%, F-measure: 91.67%)


--- STDERR ---
```

## experiment6_vegf_inhibitors.conf

Status: OK

```
1: inhibits some (not (RiskFactor)) (pred. acc.: 95.00%, F-measure: 94.74%)
2: inhibits some (not (Biomarker)) (pred. acc.: 95.00%, F-measure: 94.74%)
3: inhibits some (causesOrIncreases only Nothing) (pred. acc.: 95.00%, F-measure: 94.74%)
4: inhibits some (causesOrIncreases only RiskFactor) (pred. acc.: 95.00%, F-measure: 94.74%)
5: inhibits some (associatedWith only Nothing) (pred. acc.: 95.00%, F-measure: 94.74%)
6: inhibits some (associatedWith only RiskFactor) (pred. acc.: 95.00%, F-measure: 94.74%)
7: inhibits some (Gene or (not (RiskFactor))) (pred. acc.: 95.00%, F-measure: 94.74%)
8: RiskFactor or (inhibits some (not (RiskFactor))) (pred. acc.: 95.00%, F-measure: 94.74%)
9: RiskFactor or (inhibits some (not (Biomarker))) (pred. acc.: 95.00%, F-measure: 94.74%)
10: MolecularTarget or (inhibits some (not (Biomarker))) (pred. acc.: 95.00%, F-measure: 94.74%)


--- STDERR ---
```

## experiment8_wetamd_drugs.conf

Status: OK

```
1: AntiVEGFTherapy or (treats min 3 Thing) (pred. acc.: 94.74%, F-measure: 94.12%)
2: AntiVEGFTherapy or (treats min 2 Thing) (pred. acc.: 94.74%, F-measure: 94.12%)
3: AntiVEGFTherapy or (treats min 3 (not (RiskFactor))) (pred. acc.: 94.74%, F-measure: 94.12%)
4: AntiVEGFTherapy or (treats min 2 (not (RiskFactor))) (pred. acc.: 94.74%, F-measure: 94.12%)
5: AntiVEGFTherapy or (treats min 3 (causesOrIncreases only Nothing)) (pred. acc.: 94.74%, F-measure: 94.12%)
6: AntiVEGFTherapy or (treats min 3 (causesOrIncreases only RiskFactor)) (pred. acc.: 94.74%, F-measure: 94.12%)
7: AntiVEGFTherapy or (treats min 2 (causesOrIncreases only Nothing)) (pred. acc.: 94.74%, F-measure: 94.12%)
8: AntiVEGFTherapy or (treats min 2 (causesOrIncreases only RiskFactor)) (pred. acc.: 94.74%, F-measure: 94.12%)
9: AntiVEGFTherapy or (treats min 2 (hasSymptom some Thing)) (pred. acc.: 94.74%, F-measure: 94.12%)
10: AntiVEGFTherapy or (treats min 2 (diagnosedBy some Thing)) (pred. acc.: 94.74%, F-measure: 94.12%)


--- STDERR ---
```

## experiment9_amd_biomarkers.conf

Status: OK

```
1: Biomarker (pred. acc.: 83.33%, F-measure: 83.33%)
2: not (MolecularTarget) (pred. acc.: 83.33%, F-measure: 83.33%)
3: Biomarker or WetAMD (pred. acc.: 83.33%, F-measure: 83.33%)
4: Biomarker or Treatment (pred. acc.: 83.33%, F-measure: 83.33%)
5: Biomarker or DryAMD (pred. acc.: 83.33%, F-measure: 83.33%)
6: Biomarker or Disease (pred. acc.: 83.33%, F-measure: 83.33%)
7: Biomarker or DiagnosticMethod (pred. acc.: 83.33%, F-measure: 83.33%)
8: Biomarker or ClinicalOutcome (pred. acc.: 83.33%, F-measure: 83.33%)
9: AntiVEGFTherapy or Biomarker (pred. acc.: 83.33%, F-measure: 83.33%)
10: AMD or Biomarker (pred. acc.: 83.33%, F-measure: 83.33%)


--- STDERR ---
```

## experiment10_risk_factors.conf

Status: OK

```
1: RiskFactor (pred. acc.: 100.00%, F-measure: 100.00%)
2: Gene or RiskFactor (pred. acc.: 100.00%, F-measure: 100.00%)
3: Disease or RiskFactor (pred. acc.: 100.00%, F-measure: 100.00%)
4: DiagnosticMethod or RiskFactor (pred. acc.: 100.00%, F-measure: 100.00%)
5: ClinicalOutcome or RiskFactor (pred. acc.: 100.00%, F-measure: 100.00%)
6: RiskFactor and (not (Treatment)) (pred. acc.: 100.00%, F-measure: 100.00%)
7: RiskFactor and (not (Disease)) (pred. acc.: 100.00%, F-measure: 100.00%)
8: RiskFactor and (not (DiagnosticMethod)) (pred. acc.: 100.00%, F-measure: 100.00%)
9: RiskFactor and (not (ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
10: RiskFactor and (not (AntiVEGFTherapy)) (pred. acc.: 100.00%, F-measure: 100.00%)


--- STDERR ---
```

## experiment12_vegf_ELTL.conf

Status: OK

```
1: inhibits some MolecularTarget (pred. acc.: 90.00%, F-measure: 90.00%)
2: (inhibits some MolecularTarget) and (treats some Disease) (pred. acc.: 90.00%, F-measure: 90.00%)
3: (inhibits some MolecularTarget) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 90.00%, F-measure: 90.00%)
4: (inhibits some MolecularTarget) and (treats some (diagnosedBy some DiagnosticMethod)) (pred. acc.: 90.00%, F-measure: 90.00%)
5: (inhibits some MolecularTarget) and (treats some ((diagnosedBy some DiagnosticMethod) and (hasSymptom some ClinicalOutcome))) (pred. acc.: 90.00%, F-measure: 90.00%)
6: (inhibits some MolecularTarget) and (treats some (diagnosedBy some DiagnosticMethod)) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 90.00%, F-measure: 90.00%)
7: treats some Disease (pred. acc.: 70.00%, F-measure: 75.00%)
8: treats some (hasSymptom some ClinicalOutcome) (pred. acc.: 70.00%, F-measure: 75.00%)
9: treats some (diagnosedBy some DiagnosticMethod) (pred. acc.: 70.00%, F-measure: 75.00%)
10: (treats some (diagnosedBy some DiagnosticMethod)) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 70.00%, F-measure: 75.00%)
```

## experiment15_dryamd_treatments.conf

Status: OK

```
1: (not (AntiVEGFTherapy)) and (treats max 1 Thing) (pred. acc.: 100.00%, F-measure: 100.00%)
2: (not (AntiVEGFTherapy)) and (treats max 1 (not (RiskFactor))) (pred. acc.: 100.00%, F-measure: 100.00%)
3: RiskFactor or ((not (AntiVEGFTherapy)) and (treats max 1 Thing)) (pred. acc.: 100.00%, F-measure: 100.00%)
4: MolecularTarget or ((not (AntiVEGFTherapy)) and (treats max 1 Thing)) (pred. acc.: 100.00%, F-measure: 100.00%)
5: Gene or ((not (AntiVEGFTherapy)) and (treats max 1 Thing)) (pred. acc.: 100.00%, F-measure: 100.00%)
6: Biomarker or ((not (AntiVEGFTherapy)) and (treats max 1 Thing)) (pred. acc.: 100.00%, F-measure: 100.00%)
7: (RiskFactor or (treats max 1 Thing)) and (not (AntiVEGFTherapy)) (pred. acc.: 100.00%, F-measure: 100.00%)
8: (RiskFactor or (not (AntiVEGFTherapy))) and (treats max 1 Thing) (pred. acc.: 100.00%, F-measure: 100.00%)
9: (MolecularTarget or (treats max 1 Thing)) and (not (AntiVEGFTherapy)) (pred. acc.: 100.00%, F-measure: 100.00%)
10: (AntiVEGFTherapy or (treats max 1 Thing)) and (not (AntiVEGFTherapy)) (pred. acc.: 100.00%, F-measure: 100.00%)


--- STDERR ---
```

## experiment16_diagnosable_diseases.conf

Status: OK

```
1: (not (RiskFactor)) and (hasSymptom some ClinicalOutcome) (pred. acc.: 100.00%, F-measure: 100.00%)
2: (not (RiskFactor)) and (diagnosedBy some DiagnosticMethod) (pred. acc.: 100.00%, F-measure: 100.00%)
3: (Treatment or (not (RiskFactor))) and (diagnosedBy some DiagnosticMethod) (pred. acc.: 100.00%, F-measure: 100.00%)
4: (MolecularTarget or (not (RiskFactor))) and (diagnosedBy some DiagnosticMethod) (pred. acc.: 100.00%, F-measure: 100.00%)
5: (DiagnosticMethod or (not (RiskFactor))) and (hasSymptom some ClinicalOutcome) (pred. acc.: 100.00%, F-measure: 100.00%)
6: (DiagnosticMethod or (not (RiskFactor))) and (diagnosedBy some DiagnosticMethod) (pred. acc.: 100.00%, F-measure: 100.00%)
7: (ClinicalOutcome or (not (RiskFactor))) and (hasSymptom some ClinicalOutcome) (pred. acc.: 100.00%, F-measure: 100.00%)
8: (ClinicalOutcome or (not (RiskFactor))) and (diagnosedBy some DiagnosticMethod) (pred. acc.: 100.00%, F-measure: 100.00%)
9: (Biomarker or (not (RiskFactor))) and (hasSymptom some ClinicalOutcome) (pred. acc.: 100.00%, F-measure: 100.00%)
10: (Biomarker or (not (RiskFactor))) and (diagnosedBy some DiagnosticMethod) (pred. acc.: 100.00%, F-measure: 100.00%)


--- STDERR ---
```

## experiment17_targeted_vs_general.conf

Status: OK

```
1: (inhibits some MolecularTarget) or (treats only Nothing) (pred. acc.: 72.00%, F-measure: 77.42%)
2: (inhibits some MolecularTarget) or (treats only RiskFactor) (pred. acc.: 72.00%, F-measure: 78.79%)
3: (Treatment and (treats only RiskFactor)) or (inhibits some MolecularTarget) (pred. acc.: 72.00%, F-measure: 78.79%)
4: Treatment and ((inhibits some MolecularTarget) or (treats only Nothing)) (pred. acc.: 72.00%, F-measure: 77.42%)
5: Treatment and ((inhibits some MolecularTarget) or (treats only RiskFactor)) (pred. acc.: 72.00%, F-measure: 78.79%)
6: ((inhibits some MolecularTarget) or (treats only RiskFactor)) and (not (Gene)) (pred. acc.: 72.00%, F-measure: 78.79%)
7: ((inhibits some MolecularTarget) or (treats only RiskFactor)) and (not (DiagnosticMethod)) (pred. acc.: 72.00%, F-measure: 78.79%)
8: ((inhibits some MolecularTarget) or (treats only RiskFactor)) and (not (ClinicalOutcome)) (pred. acc.: 72.00%, F-measure: 78.79%)
9: ((inhibits some MolecularTarget) or (treats only RiskFactor)) and (not (ChoroidalNeovascularization)) (pred. acc.: 72.00%, F-measure: 78.79%)
10: Treatment and (treats some Thing) and (treats only (not (RiskFactor))) (pred. acc.: 72.00%, F-measure: 74.07%)


--- STDERR ---
```

## experiment19_dual_mechanism_ELTL.conf

Status: OK

```
1: AntiVEGFTherapy and (treats some Disease) (pred. acc.: 100.00%, F-measure: 100.00%)
2: AntiVEGFTherapy and (inhibits some MolecularTarget) (pred. acc.: 100.00%, F-measure: 100.00%)
3: AntiVEGFTherapy and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
4: AntiVEGFTherapy and (treats some (diagnosedBy some DiagnosticMethod)) (pred. acc.: 100.00%, F-measure: 100.00%)
5: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some Disease) (pred. acc.: 100.00%, F-measure: 100.00%)
6: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
7: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some (diagnosedBy some DiagnosticMethod)) (pred. acc.: 100.00%, F-measure: 100.00%)
8: AntiVEGFTherapy and (treats some (diagnosedBy some DiagnosticMethod)) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
9: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some ((diagnosedBy some DiagnosticMethod) and (hasSymptom some ClinicalOutcome))) (pred. acc.: 100.00%, F-measure: 100.00%)
10: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some (diagnosedBy some DiagnosticMethod)) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
```

## experiment21_classlearn_Treatment.conf

Status: OK

```
1: Treatment (pred. acc.: 92.68%, F-measure: 93.88%)
2: Treatment (pred. acc.: 92.68%, F-measure: 93.88%)
3: Treatment (pred. acc.: 92.68%, F-measure: 93.88%)
4: Gene or Treatment (pred. acc.: 92.68%, F-measure: 93.88%)
5: Treatment and (not (RiskFactor)) (pred. acc.: 92.68%, F-measure: 93.88%)
6: Treatment and (not (MolecularTarget)) (pred. acc.: 92.68%, F-measure: 93.88%)
7: Treatment and (not (Gene)) (pred. acc.: 92.68%, F-measure: 93.88%)
8: Treatment and (not (Biomarker)) (pred. acc.: 92.68%, F-measure: 93.88%)
9: Treatment or (Gene and RiskFactor) (pred. acc.: 92.68%, F-measure: 93.88%)
10: Treatment or (Gene and MolecularTarget) (pred. acc.: 92.68%, F-measure: 93.88%)


--- STDERR ---
```

## experiment22_classlearn_Gene.conf

Status: OK

```
1: Biomarker and (Treatment or (indicates only Nothing)) (pred. acc.: 96.15%, F-measure: 96.00%)
2: Biomarker and (Treatment or (indicates only RiskFactor)) (pred. acc.: 96.15%, F-measure: 96.00%)
3: Biomarker and (RiskFactor or (indicates only Nothing)) (pred. acc.: 96.15%, F-measure: 96.00%)
4: Biomarker and (RiskFactor or (indicates only RiskFactor)) (pred. acc.: 96.15%, F-measure: 96.00%)
5: Biomarker and (MolecularTarget or (indicates only Nothing)) (pred. acc.: 96.15%, F-measure: 96.00%)
6: Biomarker and (MolecularTarget or (indicates only RiskFactor)) (pred. acc.: 96.15%, F-measure: 96.00%)
7: Biomarker and (Disease or (indicates only RiskFactor)) (pred. acc.: 96.15%, F-measure: 96.00%)
8: Biomarker and (AntiVEGFTherapy or (indicates only Nothing)) (pred. acc.: 96.15%, F-measure: 96.00%)
9: Biomarker and (AntiVEGFTherapy or (indicates only RiskFactor)) (pred. acc.: 96.15%, F-measure: 96.00%)
10: Biomarker and (AMD or (indicates only RiskFactor)) (pred. acc.: 96.15%, F-measure: 96.00%)


--- STDERR ---
```

## experiment23_posonly_antivegf.conf

Status: OK

```
1: AntiVEGFTherapy and (treats some Disease) (pred. acc.: 100.00%, F-measure: 100.00%)
2: AntiVEGFTherapy and (inhibits some MolecularTarget) (pred. acc.: 100.00%, F-measure: 100.00%)
3: AntiVEGFTherapy and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
4: AntiVEGFTherapy and (treats some (diagnosedBy some DiagnosticMethod)) (pred. acc.: 100.00%, F-measure: 100.00%)
5: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some Disease) (pred. acc.: 100.00%, F-measure: 100.00%)
6: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
7: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some (diagnosedBy some DiagnosticMethod)) (pred. acc.: 100.00%, F-measure: 100.00%)
8: AntiVEGFTherapy and (treats some (diagnosedBy some DiagnosticMethod)) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
9: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some ((diagnosedBy some DiagnosticMethod) and (hasSymptom some ClinicalOutcome))) (pred. acc.: 100.00%, F-measure: 100.00%)
10: AntiVEGFTherapy and (inhibits some MolecularTarget) and (treats some (diagnosedBy some DiagnosticMethod)) and (treats some (hasSymptom some ClinicalOutcome)) (pred. acc.: 100.00%, F-measure: 100.00%)
```

## experiment24_missing_inhibits.conf

Status: OK

```
1: (inhibits some MolecularTarget) or (treats some RiskFactor) (pred. acc.: 80.77%, F-measure: 81.48%)
2: (inhibits some MolecularTarget) or (treats some (causesOrIncreases some Disease)) (pred. acc.: 80.77%, F-measure: 81.48%)
3: ((not (RiskFactor)) and (inhibits some MolecularTarget)) or (treats some RiskFactor) (pred. acc.: 80.77%, F-measure: 81.48%)
4: ((not (MolecularTarget)) and (treats some RiskFactor)) or (inhibits some MolecularTarget) (pred. acc.: 80.77%, F-measure: 81.48%)
5: ((not (MolecularTarget)) and (inhibits some MolecularTarget)) or (treats some RiskFactor) (pred. acc.: 80.77%, F-measure: 81.48%)
6: ((not (Gene)) and (treats some RiskFactor)) or (inhibits some MolecularTarget) (pred. acc.: 80.77%, F-measure: 81.48%)
7: ((not (Gene)) and (inhibits some MolecularTarget)) or (treats some RiskFactor) (pred. acc.: 80.77%, F-measure: 81.48%)
8: ((not (AntiVEGFTherapy)) and (treats some RiskFactor)) or (inhibits some MolecularTarget) (pred. acc.: 80.77%, F-measure: 81.48%)
9: ((inhibits some MolecularTarget) or (treats some RiskFactor)) and (not (RiskFactor)) (pred. acc.: 80.77%, F-measure: 81.48%)
10: ((inhibits some MolecularTarget) or (treats some RiskFactor)) and (not (MolecularTarget)) (pred. acc.: 80.77%, F-measure: 81.48%)


--- STDERR ---
```

## experiment25_missing_assoc.conf

Status: OK

```
1: associatedWith some Disease (pred. acc.: 82.61%, F-measure: 84.62%)
2: associatedWith some (hasSymptom some ClinicalOutcome) (pred. acc.: 82.61%, F-measure: 84.62%)
3: associatedWith some (diagnosedBy some DiagnosticMethod) (pred. acc.: 82.61%, F-measure: 84.62%)
4: associatedWith some ((diagnosedBy some DiagnosticMethod) and (hasSymptom some ClinicalOutcome)) (pred. acc.: 82.61%, F-measure: 84.62%)
5: (associatedWith some (diagnosedBy some DiagnosticMethod)) and (associatedWith some (hasSymptom some ClinicalOutcome)) (pred. acc.: 82.61%, F-measure: 84.62%)
6: Biomarker (pred. acc.: 69.57%, F-measure: 75.86%)
7: Thing (pred. acc.: 56.52%, F-measure: 68.75%)
```
