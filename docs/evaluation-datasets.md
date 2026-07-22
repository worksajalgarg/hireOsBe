# Evaluation datasets — Week 1 exit-gate dependency

The PRD's 12-week roadmap (Section 11) lists "evaluation datasets" as part of Week 1's build focus, and the quality evaluation gates (Section 9) depend on having real benchmark data before those gates can be measured:

- Resume extraction benchmark: ">=95% accuracy on critical fields; every key claim traceable to source" — requires a labelled resume set.
- Question quality: ">=90% reviewer acceptance after edits on pilot role set" — requires real role packs (see `docs/design-partners.md`).
- Speech robustness: "Accent/noise test set meets agreed transcript and completion thresholds" — requires an Indian-accent/noisy-environment audio benchmark (Section 11 "Critical dependencies": *"Quality benchmark dataset that includes Indian accents, noisy environments, varied resume formats and role seniority"*).

**This is a joint founder/business + engineering dependency**, distinct from the design-partner role packs: it also needs synthetic/supplementary data to cover edge cases design partners won't provide (accents, noise, adversarial resumes). Tracked here so it isn't silently dropped or assumed to already exist once agent implementation starts in Sprint 2+.

## What's needed
- [ ] Anonymised resume corpus (from design partners) plus synthetic resumes covering varied formats and role seniority.
- [ ] Golden-set rubric/evaluation benchmark for the Evaluation Agent (Sprint 7 dependency — PRD Section 6 "golden-set validation" appears at Sprint 12 in the technical roadmap, but a starter set is needed much earlier for iterative testing).
- [ ] Accent/noise audio test set for speech robustness benchmarking (Sprint 6+ voice runtime).
- [ ] A documented process for how synthetic data supplements — but does not replace — real design-partner data (PRD Section 13 risk: "Insufficient real-world evaluation data").

## Status
Not yet started — no datasets exist in this repository. Do not begin Sprint 2 rubric-generation benchmarking (PRD Section 11, Week 2/3 exit gates) without at least a starter resume set in place.
