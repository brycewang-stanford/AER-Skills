# Workflow Map

The intended journey through the AER-skills stack.

## Linear Default

```
┌─────────────────────┐
│  aer-topic-selection│   Topic + venue routing (AER / Insights / AEJ)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  aer-identification │   Design-based identification, modern estimators
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   aer-robustness    │   Heterogeneity, mechanism, placebo, anticipation
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  aer-introduction   │   Five-paragraph intro + 100-word abstract
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ aer-tables-figures  │   Booktabs, regression tables, figure notes
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   aer-replication   │   AEA Data and Code Availability deposit
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   aer-submission    │   Format preflight, cover letter, conflicts
└──────────┬──────────┘
           │
           ▼ (after decision)
┌─────────────────────┐
│    aer-rebuttal     │   R&R response letter + aligned manuscript edits
└─────────────────────┘
```

## When to Loop

- **Identification rebuild** triggered by an R&R targeting the design → loop back to `aer-identification` then forward
- **Format-only revisions** → skip back only to `aer-tables-figures` or `aer-submission`
- **Venue change** after rejection → `aer-topic-selection` again, then `aer-introduction` for re-framing

## Cross-Cutting Checks

- Run [`desk-rejection-audit`](./desk-rejection-audit.md) before submission or
  after a rejection to find the first failure point in framing, identification,
  robustness, exhibits, or policy compliance.
- Use [`methods-reference`](./methods-reference.md) whenever
  `aer-identification` or `aer-robustness` asks for an estimator, diagnostic,
  package call, or primary citation.
- Check [`source-register`](./source-register.md) before changing journal
  policy, AEA replication, or submission-limit language.

## The Router

`aer-workflow` is the entry point when the user is unsure where they are. It does not perform work — it picks the next skill.
