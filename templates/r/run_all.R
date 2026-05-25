# ============================================================
# run_all.R
# Master script -- AER-compliant R pipeline.
#
# Author      : <your name>
# Paper       : <short title>
# Last update : <YYYY-MM-DD>
# R           : 4.4.1 or later
#
# Reproducibility contract:
#   1. Open this project via the .Rproj file (so getwd() is correct).
#   2. Run renv::restore() if not already activated.
#   3. source("run_all.R") from the project root.
#   4. All output is written to output/. No file outside the project
#      directory is read or written.
#
# Approximate runtime: 25 minutes on a 2024-class laptop.
# ============================================================

# ---- 1. Environment lock --------------------------------------
# Recommended: use renv to pin packages.
# renv::init()  # first time only
# renv::snapshot()  # to update the lock file

suppressPackageStartupMessages({
  source("code/00_setup.R")
})

# ---- 2. Pipeline ----------------------------------------------
log_path <- file.path("logs", paste0("run_all_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".log"))
con <- file(log_path, open = "wt")
sink(con, split = TRUE, type = "output")
sink(con, type = "message")

source("code/01_clean.R")        # raw -> intermediate analytic file
source("code/02_descriptives.R") # summary stats + balance
source("code/03_main_did.R")     # main DiD specification
source("code/04_robustness.R")
source("code/05_heterogeneity.R")
source("code/06_tables.R")       # publication-ready .tex tables
source("code/07_figures.R")      # publication-ready .pdf figures

sink(type = "message")
sink()
close(con)

cat("=================================================\n")
cat("  Pipeline complete. Outputs in: output/\n")
cat("=================================================\n")
