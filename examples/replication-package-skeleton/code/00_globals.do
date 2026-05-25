/*------------------------------------------------------------------
  00_globals.do
  Project-wide globals. Edit one line.
  See ../README.md for the full instructions to replicators.
-------------------------------------------------------------------*/

* ---- EDIT THIS LINE TO YOUR LOCAL PATH ---------------------------
global project "/path/to/replication-package"

* ---- Derived paths -----------------------------------------------
global data        "$project/data"
global raw         "$data/raw"
global intermediate "$data/intermediate"
global code        "$project/code"
global output      "$project/output"
global tables      "$output/tables"
global figures     "$output/figures"
global logs        "$project/logs"

* ---- Reproducibility ---------------------------------------------
set seed 20260101
