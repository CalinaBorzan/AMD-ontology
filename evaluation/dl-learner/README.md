# DL-Learner Experiments for AMD Ontology

## What DL-Learner does

DL-Learner learns **OWL class expressions** (axioms) from your data.
Given positive and negative examples, it finds patterns that describe
the positive examples and exclude the negative ones.

It does NOT:
- Add new instances
- Create new classes
- Extract from text

It DOES:
- Learn definitions like: `AntiVEGFTherapy ≡ Treatment AND inhibits SOME {VEGF}`
- Discover patterns: "WetAMD treatments all inhibit VEGF"
- Validate structure: if DL-Learner can learn correct definitions, your ontology is well-structured

## Setup

1. Install Java 11+
2. Download DL-Learner: https://github.com/SmartDataAnalytics/DL-Learner/releases
3. Unzip to a folder (e.g., `dl-learner-1.5.0/`)
4. Make sure `AMD.owl` is in the parent directory (or adjust `ks.fileName` in .conf files)

## Running experiments

```bash
# From the dl-learner directory:
path/to/dl-learner-1.5.0/bin/cli experiment1_antivegf.conf
path/to/dl-learner-1.5.0/bin/cli experiment2_wetamd_treatments.conf
path/to/dl-learner-1.5.0/bin/cli experiment3_amd_genes.conf
```

## Experiments

### Experiment 1: What defines an AntiVEGF drug?
- **Positive**: Ranibizumab, Aflibercept, Bevacizumab, Lucentis, Eylea, Conbercept, Avastin
- **Negative**: Verteporfin, Celecoxib, Aspirin, Copaxone, Sirolimus, PDT, Vitrectomy
- **Expected result**: `Treatment AND inhibits SOME {VEGF}`
- **Thesis value**: Validates that the ontology correctly captures the VEGF-inhibition relationship

### Experiment 2: WetAMD treatments vs DryAMD treatments
- **Positive**: Drugs that treat WetAMD
- **Negative**: Drugs that treat DryAMD or general AMD
- **Expected result**: Pattern involving VEGF inhibition or WetAMD-specific triples
- **Thesis value**: Discovers treatment differentiation patterns from extracted data

### Experiment 3: AMD-associated genes
- **Positive**: Genes with associatedWith AMD (CFH, ARMS2, HTRA1, C3, CFB, C2, etc.)
- **Negative**: Genes without AMD association + non-gene biomarkers
- **Expected result**: Pattern involving associatedWith AMD relationship
- **Thesis value**: Validates genetic biomarker extraction quality

## Interpreting output

DL-Learner outputs ranked class expressions:
```
1. (Treatment AND inhibits SOME {VEGF})  (pred.acc.: 95.2%, F-measure: 0.93)
2. (AntiVEGFTherapy)                      (pred.acc.: 91.0%, F-measure: 0.88)
```

- **pred.acc.** = predictive accuracy (how well the expression separates pos from neg)
- **F-measure** = harmonic mean of precision and recall
- Higher-ranked = better description of your positive examples

## Common issues

- IRIs must match exactly — check namespace in AMD.owl
- Use "closed world reasoner" (not open world) for small ontologies
- If DL-Learner returns only `owl:Thing`, your positive/negative sets are too similar
- Minimum ~5 positive and ~5 negative examples for meaningful results
