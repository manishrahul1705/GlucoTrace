# Stage 3 Remediation Execution Record

## Execution Environment
- Operating System: Windows-11-10.0.26300-SP0
- Python: 3.12.3
- scikit-learn: 1.9.1
- numpy: 2.3.5
- pandas: 2.2.3
- scipy: 1.18.1
- matplotlib: 3.10.8
- Duration: 2944.19 seconds
- Total learned-estimator fits: 728 (672 inner selection + 56 outer refits)
- Execution Policy: Restart-only (non-resumable)
- Precision Policy: float64 full precision throughout selection and metrics

## Preflight Verification Status
- Verified Stage 2 Checkpoint: `029b530f7616c50fe634f1c695e25753b4041410ae611cfe7fd6019bc6c0147c`
- Verified Original Linux Checkpoint: `b871a7de0af394410c2a4484710f809c77e1be24c60291395de28f5fd7c1d8ce`
- Stage 2 Protocol SHA256: `2cb9be37042bbb6ea4b2a5d233c3d8f9f8bd89a0f11414bbf12b3ee200cd5abf`
- Split Manifest SHA256: `6fbc950407acf1f1a21f17f70ec4c497ac3a55c04805127e68e65a6c713321cd`
- Source Provenance SHA256: `b9006433b4386b2524e0c2d5b97bb6e1c6eb821013eacf63823145ad68c2da73`

## Budget Accounting
- Outer Folds: 14 planned / 14 executed
- Inner Folds: 3 per outer fold (42 fold evaluations)
- Candidate Grid: 4 per family/variant (16 candidate configurations per outer fold)
- Inner Fits: 672 planned / 672 executed
- Outer Refits: 56 planned / 56 executed
- Total Fits: 728 planned / 728 executed
- Missing or Failed Fits: 0
