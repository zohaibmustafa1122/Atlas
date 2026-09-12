# ATLAS — FYP Defense Preparation

This file accumulates likely defense questions and technically accurate
answers as the project grows. Update it every phase.

---

## Phase 1 questions

**Q: Why did you design ATLAS in phases instead of building everything at once?**
A: A phased build keeps the system runnable and demonstrable at every stage,
mirrors real data-engineering practice (incremental delivery), and lets each
phase be evaluated/tested independently before the next is layered on top —
which also makes the eventual research evaluation (Phase 8) cleaner, since
each capability was validated when it was introduced.

**Q: Why SQLite instead of PostgreSQL for development?**
A: SQLite requires no server process or setup, which matters on a personal
laptop with limited resources, and it is sufficient for single-user
development and for datasets up to ~100,000 rows. Because the schema is
defined through SQLAlchemy's ORM rather than raw SQL, switching to
PostgreSQL later only requires changing the `DATABASE_URL` environment
variable and installing a PostgreSQL driver — no application code changes.

**Q: Why not use Neo4j from the start if the project is graph-heavy?**
A: Neo4j requires running a separate database server, which adds setup
complexity and memory overhead that isn't justified for graphs of the size
ATLAS targets on this hardware (thousands to low tens-of-thousands of
nodes). NetworkX runs in-process in pure Python and is more than capable at
that scale. The graph-builder module is written behind a narrow interface
so a Neo4j-backed implementation could be substituted later without
touching the analytics or visualization code.

**Q: Why Streamlit instead of a React frontend?**
A: The project's core contribution is the data science and data engineering
pipeline, not frontend engineering. Streamlit produces an interactive,
usable UI in a fraction of the time a custom frontend would take, which
keeps effort concentrated on entity resolution, graph analytics, and anomaly
detection — the parts that are actually being evaluated academically. A
React frontend consuming the FastAPI backend remains a documented future
extension.

**Q: Why generate synthetic data instead of using a real dataset immediately?**
A: Using synthetic data avoids any ethical or legal concern about profiling
real individuals, lets the dataset size be controlled precisely (1,000 /
10,000 / 100,000 records) for the performance and scalability experiments
planned in Phase 8, and lets ground truth be known (e.g. which records were
generated as duplicates of the same person) so entity-resolution precision
and recall can actually be measured.

**Q: Why Pandas instead of Polars for Phase 1, when the brief says "prefer Polars"?**
A: Pandas has broader documentation and is the more familiar starting point,
which reduces risk while the ingestion module's behavior and API are still
being defined. Because ingestion functions take a file path and return a
DataFrame/records at their boundary, the internal implementation can be
swapped to Polars later for performance-critical paths (e.g. cleaning
100,000-row files) without changing any calling code.

**Q: How does the relational schema represent that a "relationship" can
connect either two people, two organizations, or one of each?**
A: `relationships.source_entity` and `target_entity` store an id string that
may belong to either the `persons` or `organizations` table — a polymorphic
association. This is deliberately not enforced as a database-level foreign
key (a single column cannot reference two different tables in standard SQL);
integrity is instead enforced in the repository layer and checked by tests.
This is a standard, documented pattern for polymorphic relationships in
relational schemas.

**Q: What would you change if this dataset needed to scale to millions of rows?**
A: Move from SQLite to PostgreSQL, introduce chunked/streaming ingestion
instead of loading a full file into memory, move the graph backend to
Neo4j, and introduce pagination/sampling everywhere in the UI more
aggressively than the current 100k-row target already requires. The
architecture is intentionally organized so each of those is a swap, not a
rewrite.

---

## Phase 2 questions

**Q: How is the Data Quality Score calculated?**
A: It's a weighted average of four sub-metrics, each in [0, 100]:
completeness (share of non-missing cells), uniqueness (share of
non-duplicate rows), validity (share of type-checked values that parse as
their declared type), and consistency (share of columns that don't mix
numeric-looking and non-numeric-looking values). The weights (40/25/20/15)
are a documented judgement call, not a fitted parameter — there's no
"ground truth" quality score to fit against for an arbitrary dataset. The
weighting reflects that missing data is usually the most damaging issue
for downstream analysis, followed by duplication, then validity and
formatting consistency.

**Q: How do you detect "invalid values" in a column without knowing its schema in advance?**
A: By design, ATLAS doesn't guess a schema for an arbitrary uploaded file.
Instead, `detect_invalid_values` takes an optional `column_rules` mapping
(column name -> "numeric" or "date") that the caller supplies when the
expected type of specific columns is known (e.g. the synthetic dataset's
`amount`, `confidence`, `timestamp` columns). Without rules, no values are
flagged as invalid — validity defaults to 100%, which is the honest answer
when nothing is known about what "valid" means for that column.

**Q: What counts as a "consistent" column, and why use that heuristic?**
A: A column is flagged as inconsistent if some (but not all) of its
non-null values parse as numbers — e.g. a column mixing "30" and "thirty".
That's a proxy, not a guarantee of consistency, because there's no schema
to check against. It's deliberately conservative: a column that's
entirely numeric-as-text, or entirely free text, is never flagged, only
columns that visibly mix representations.

**Q: Why does the cleaning step only remove exact duplicates and normalize whitespace, instead of doing more (e.g. filling missing values, fixing typos)?**
A: Anything beyond that would be guessing at the data's meaning without
domain knowledge — e.g. filling a missing age with a mean/median silently
invents a value that was never observed, and "fixing" typos is exactly
the fuzzy-matching problem that entity resolution (Phase 4) is designed to
solve deliberately, with a similarity score and human-reviewable
confidence, not silently during ingestion. Phase 2 only removes noise that
is unambiguous: exact duplicate rows and stray whitespace.

**Q: Why is `quality_score` computed on the persons table alone for the synthetic dataset, rather than across all six tables?**
A: For Phase 2, the quality engine operates on a single tabular dataset,
matching the "upload one file, get one score" flow. The synthetic dataset
is really six related tables; persons is used as the representative table
because it's the one most analogous to what a real single-file upload
looks like. Extending the quality score to multi-table datasets (e.g. a
weighted combination across tables) is a natural Phase 3+ extension once
the graph layer makes cross-table relationships first-class.

---

*(Further questions will be appended as Phases 3–9 are implemented.)*
