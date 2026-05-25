# Stata Templates

Drop-in scripts for an AEA-compliant Stata pipeline.

## Files

| File | Purpose |
|---|---|
| `run_all.do` | Master script. Runs the full pipeline end-to-end. |
| `00_globals.do` | Project paths, seed, display options. Edit one line. |
| `00_install_packages.do` | Pin every user-written package. Run once. |
| `03_main_did.do` | Staggered DiD with Callaway-Sant'Anna + diagnostics. |
| `06_tables.do` | AER-style 5-column main results table via `esttab`. |

## Conventions Enforced

- `version 18.0` at the top of every file
- Relative paths via `$project` global
- `set seed 20260101` before any stochastic procedure
- Output goes to `$tables` and `$figures` — never to the project root
- Logs to `$logs/run_all.log` for reproducibility traceability

## How to Adapt to Your Project

1. Copy `templates/stata/` into your replication package
2. Edit `00_globals.do` line 8 to point `$project` at your directory
3. Replace `outcome`, `treat`, `$controls`, `unit_id`, `year`, `iv`, `endog`
   with your variable names
4. Run `do run_all.do`

## Dependencies

See `00_install_packages.do`. Core: `reghdfe`, `csdid`, `ivreg2`, `weakivtest`,
`rdrobust`, `estout`, `coefplot`, `bacondecomp`, `honestdid`, `boottest`.
