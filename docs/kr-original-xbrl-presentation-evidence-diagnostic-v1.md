# Original XBRL presentation-evidence diagnostic v1

An outcome-free source-structure diagnostic, not a validation version. v1 and v2
of `kr-original-xbrl-value-validation` are closed and untouched; this reruns
neither. v2 resolved the entity-scheme blocker and then stopped 60/60 at
`source presentation does not prove required financial statement` with empty
presentation evidence. Raw ZIPs were not retained, so the cause was unknown.

**Question.** Reader bug, source limitation, external-taxonomy dependency or mixed
structure?

**Design.** A deterministic 12-fact subset of the frozen 60 (4 families x 3 stages,
basis alternated, chosen by hash of frozen identity only; see the spec) is
downloaded, kept as a temporary Actions artifact (never committed), and
inventoried: files, roleTypes, refs, presentation networks, and for each fact the
chain element -> context -> expectation -> network, recording where the current
reader's chain first breaks. External taxonomy hrefs are documented, not fetched.
The report separates unique fact identification from statement-membership
corroboration and changes no contract. If a reader bug or an unsuitable gate is
found, only a separate, preregistered v3 may change anything.

Verdicts: `READER_BUG_CONFIRMED`, `SOURCE_PRESENTATION_INSUFFICIENT`,
`EXTERNAL_TAXONOMY_DEPENDENCY`, `MIXED_SOURCE_STRUCTURE`, `INCONCLUSIVE`.
No Alpha or outcome data is read.
