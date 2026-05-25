/*------------------------------------------------------------------
  run_all.do
  Master script — AER-compliant Stata pipeline

  Author      : <your name>
  Paper       : <short title>
  Last update : <YYYY-MM-DD>
  Stata       : 18.0 MP

  Reproducibility contract:
    1. Edit `globals.do` so $project points to this directory.
    2. Run `do run_all.do` from any working directory.
    3. All output is written to `output/`. No file outside the project
       directory is read or written.

  Approximate runtime: 25 minutes on a 2024-class laptop.
-------------------------------------------------------------------*/

version 18.0
clear all
set more off
set varabbrev off
set linesize 100
cap log close

* ---- 1. Globals & package install --------------------------------
do "code/00_globals.do"
do "code/00_install_packages.do"

* ---- 2. Pipeline --------------------------------------------------
log using "logs/run_all.log", replace text

do "code/01_clean.do"        // raw -> intermediate analytic file
do "code/02_descriptives.do" // summary stats + balance tables
do "code/03_main.do"         // main regression specifications
do "code/04_robustness.do"   // referee-anticipating checks
do "code/05_heterogeneity.do"
do "code/06_tables.do"       // emit publication-ready .tex tables
do "code/07_figures.do"      // emit publication-ready .pdf figures

log close

display as result "================================================="
display as result "  Pipeline complete. Outputs in: $project/output/"
display as result "================================================="
