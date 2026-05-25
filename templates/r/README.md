# R Templates

Drop-in scripts for an AEA-compliant R pipeline using the modern stack
(`fixest`, `did`, `modelsummary`).

## Files

| File | Purpose |
|---|---|
| `run_all.R` | Master script. Runs the full pipeline end-to-end. |
| `00_setup.R` | Paths, packages, seed, plot theme. |
| `03_main_did.R` | Callaway-Sant'Anna DiD + Bacon + Honest DiD. |
| `06_tables.R` | AER-style booktabs table via `fixest::etable`. |

## Conventions Enforced

- `set.seed(20260101)` in `00_setup.R`
- Relative paths via `PROJECT <- getwd()` and `file.path(...)`
- Output goes to `output/tables` and `output/figures`
- Optional `renv` lock for full package-version pinning
- `cairo_pdf` device for vector figures (publication-ready)

## How to Adapt

1. Copy `templates/r/` into your project
2. Open the project root in RStudio (so `getwd()` is correct)
3. `renv::restore()` if you maintain a lockfile
4. `source("run_all.R")`

## Package Stack

- **fixest** — `feols`, `etable`. AER-style tables out of the box.
- **did** — Callaway-Sant'Anna ATT(g,t), aggregations, event study
- **HonestDiD** — Rambachan-Roth pre-trends sensitivity
- **rdrobust** + **rddensity** — modern RDD
- **modelsummary** — flexible table backend (kableExtra / gt / LaTeX)
- **fwildclusterboot** — wild cluster bootstrap for few-cluster inference
