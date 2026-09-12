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

## Phase 3 questions

**Q: Which edges actually exist in the graph, and why not more (e.g. LOCATED_IN for persons)?**
A: The graph only contains edges backed by a real structural link in the
relational schema: `WORKS_FOR` (from `persons.organization_id`),
`OCCURRED_AT` (from `events.location_id`), one edge per row in
`relationships` (using its `relationship_type`), and `TRANSFERRED_TO`
(one per row in `transactions`). A `LOCATED_IN` edge from a person to a
location was deliberately left out: `persons.city`/`country` are free-text
strings, not foreign keys into `locations`, so matching them would mean
string-matching two independently generated fields with no guarantee they
refer to the same real-world place -- exactly the kind of unreliable
inference the entity-resolution phase (Phase 4) is meant to handle
carefully, not something to bake into the graph silently.

**Q: Why is the graph a MultiDiGraph instead of a simple Graph?**
A: Two reasons. It needs to be directed because some relationships have a
real direction (`WORKS_FOR`, `TRANSFERRED_TO`). It needs to allow multiple
edges between the same pair of nodes because two entities can be connected
in more than one way at once -- e.g. two people who both `KNOWS` each other
*and* have a `TRANSFERRED_TO` transaction between them. A simple `DiGraph`
would silently collapse those into one edge and lose information.

**Q: Betweenness centrality is exact for small graphs but "approximated" above 3,000 nodes -- what does that actually mean, and is it defensible?**
A: Exact betweenness centrality requires computing shortest paths between
every pair of nodes, which costs O(V x E) -- infeasible on an 8 GB CPU
laptop once V reaches the tens of thousands. Above the threshold, ATLAS
uses NetworkX's sampled betweenness: instead of using every node as a
shortest-path source, it uses a fixed-size random sample (`k=500`, seeded
for reproducibility) and scales the result. This is a standard, published
approximation technique (Brandes' algorithm with sampling), not an ad hoc
shortcut, and the UI explicitly labels the result as approximated rather
than presenting it as exact.

**Q: Why cap the Graph Explorer's visualization to a bounded neighborhood instead of showing the whole graph?**
A: A dataset can have up to 100,000 entities. Rendering all of them in a
single interactive vis.js graph would both exhaust available memory and
be visually meaningless -- nobody can read a 100,000-node hairball. Instead,
exploration always starts from a specific entity (found via search) and
expands outward a bounded number of hops (`get_neighborhood`), capped at a
maximum node count regardless of how many hops were requested. This
mirrors how real investigative tools handle scale: start from something
specific, expand deliberately.

**Q: Why does community detection just return `None` on large graphs instead of also approximating?**
A: Unlike betweenness centrality, there isn't a similarly standard,
well-understood sampling approximation for modularity-based community
detection that would fit cleanly into this project's scope. Rather than
implementing a home-grown approximation whose accuracy couldn't be
argued for confidently in a defense, the honest choice is to skip it
above the size threshold and say so, rather than return a number that
looks precise but wasn't validated.

**Q: Why is `search_entities` a SQL query but `search_nodes` iterates the in-memory graph -- isn't that inconsistent?**
A: They serve different situations. `EntityRepository.search_entities`
runs a `LIKE` query directly against the database, which uses the indexed
`name` columns and scales to 100,000 rows without loading anything into
Python first -- this is what the dashboard actually uses. `search_nodes` in
`app/graph/queries.py` operates on a graph already sitting in memory (e.g.
during testing, or if a caller already has the graph loaded for another
reason) and avoids a redundant database round-trip in that case. Having
both isn't inconsistency; it's picking the right tool depending on
whether the data is already in memory.

---

## Phase 4 questions

**Q: Why does ATLAS never say two records "are" the same entity, only that they're a "potential match"?**
A: Entity resolution is a similarity estimate, not ground truth verification.
Two different people can have identical names; the same person can be
written many different ways. Claiming certainty where there is only
statistical similarity would be actively misleading in an analytical tool
-- exactly the kind of overclaiming the project brief explicitly warns
against. `confidence_label()` uses hedged language ("potential", "possible",
"weak possible") at every band, and there is no band that says "confirmed"
or "same".

**Q: What is blocking, and why is it necessary?**
A: Comparing every person against every other person is O(n^2) -- at
100,000 records that's 5 billion pairs, infeasible on a laptop. Blocking
groups records by a cheap key first (here: first character of the
normalized name, and the last token) and only compares records that share
at least one key. This trades a small amount of recall (a true duplicate
pair that shares neither key is never even compared) for turning the
problem from O(n^2) into something close to O(n) in practice. It's a
standard, well-documented technique in the entity-resolution literature,
not an ad hoc shortcut.

**Q: Why these two blocking keys specifically?**
A: They were chosen to survive the kinds of variation the synthetic
generator actually injects (initials, honorifics, dropped middle names,
single-character typos) -- see `_blocking_keys`'s docstring for the
worked-through cases. The known failure mode is a variant that changes
both the first character and the last token (e.g. a typo hitting the very
first or very last character) which no two-key blocking scheme can fully
avoid; a production system would add more blocking passes (e.g. phonetic
keys like Soundex) to reduce that risk further.

**Q: Explain the multi-feature score: why these three features and these weights?**
A: Levenshtein ratio (weight 0.4) catches character-level typos and small
edits. Token (word-set) Jaccard similarity (weight 0.3) catches
word-reordering and dropped/added words (e.g. honorifics) that Levenshtein
alone penalizes harshly. Character n-gram TF-IDF cosine similarity (weight
0.3) catches partial/abbreviated tokens (e.g. an initial) that pure token
overlap would miss entirely, since "M" and "Muhammad" share zero whole
tokens but overlapping character n-grams. Levenshtein gets the largest
weight because it's the most broadly reliable signal for short strings;
the other two compensate for its specific blind spots. As with the Data
Quality Engine's weights (Phase 2), this is a documented judgement call,
not a fitted parameter.

**Q: Your baseline-vs-improved evaluation showed low precision at threshold 0.55 (F1 ~0.02-0.10) but much better at 0.70 (F1 ~0.07 baseline vs ~0.69 multi-feature). What does that tell you?**
A: Two things. First, the similarity threshold matters enormously --
0.55 is too permissive for this dataset (many unrelated people who
happen to share a first letter and have moderately similar names cross
that bar), while 0.70 is a much better precision/recall trade-off here.
Second, and more importantly for the research question, the *gap between
methods widens sharply* at the higher threshold: multi-feature clearly
outperforms the single-feature baseline once the threshold is high enough
to separate signal from noise. That is itself a finding worth reporting in
Phase 8, not just an implementation detail -- it shows the extra features
earn their computational cost primarily when precision matters, not
uniformly everywhere.

**Q: Why is `evaluate_against_ground_truth` in Phase 4 instead of waiting for Phase 8?**
A: The synthetic generator (Phase 1) already injects known duplicate pairs
specifically so entity resolution could be validated as soon as it existed
-- leaving that unused until Phase 8 would mean shipping an unvalidated
algorithm for three phases. This function is a *development-time* check
(does this dataset's specific run look reasonable?); Phase 8's job is the
full study across multiple dataset sizes with proper experimental write-up.

---

## Phase 5 questions

**Q: Why does ATLAS only say "potential anomaly," never "fraud"?**
A: An anomaly score is a statement about how unusual a transaction looks
relative to the rest of the dataset -- it says nothing about intent, and
plenty of statistically unusual transactions are entirely legitimate (a
one-off large purchase, a rare but valid transfer). Calling something
"fraud" would be a claim this system has no evidence to support. This
mirrors the same "confidence, not certainty" principle behind entity
resolution's "potential match" language in Phase 4.

**Q: Why does the statistical method use median/MAD instead of mean/standard deviation?**
A: The whole point of anomaly detection here is that the data being scored
already contains the outliers being searched for. A handful of extreme
values pulls the mean up and inflates the standard deviation enough that
the z-score of the very outliers you're trying to catch can shrink below
threshold -- the outliers mask themselves. The median and median absolute
deviation (MAD) barely move when a few values are extreme, which is
exactly the property ("robustness") needed here. The 1.4826 scaling
constant is the standard value that makes MAD comparable to a standard
deviation under a normal distribution, not something invented for this
project.

**Q: Your own results show the "baseline" statistical method (F1=1.0) actually beat Isolation Forest (F1=0.75) on the synthetic dataset -- doesn't that undercut the "multi-feature/improved method is better" narrative from Phase 4?**
A: No -- it's a genuinely useful finding, and reporting it honestly is
more defensible than hiding it. The synthetic generator injects outliers
as pure amount extremes (one feature, no interaction effects), which is
exactly the setting a univariate robust z-score is designed for.
Isolation Forest is built to find outliers in multivariate feature spaces
where no single feature alone reveals the anomaly (its advantage would
show up if features like transaction frequency, time-of-day, or
sender/receiver degree were added). At default contamination, it also
flagged a handful of unusually *small* transactions as outliers, which
technically are statistical outliers but weren't the injected anomalies
-- a reminder that "contamination" is a rate you're asking the model to
find, not a rate it discovers on its own. The lesson for Phase 8: which
method wins depends on the anomaly's shape, and a fair comparison needs
to say so rather than assume the more sophisticated method always wins.

**Q: How would you extend this to catch more realistic (non-univariate) anomalies?**
A: Add more features to the Isolation Forest input beyond raw amount --
e.g. transaction frequency per sender, time since the sender's previous
transaction, or the sender/receiver's graph degree from Phase 3. Isolation
Forest's actual advantage over a simple z-score is multivariate
interaction effects (e.g. "unremarkable amount, but this pair of entities
has never transacted before and it's 3am"), which a single-feature
z-score structurally cannot detect. That's a natural Phase 8 extension,
not a Phase 5 requirement, since it needs its own injected ground truth to
evaluate fairly.

**Q: Why is `contamination` (Isolation Forest) exposed as a slider instead of a fixed value?**
A: `contamination` tells the model what fraction of the data to treat as
outliers -- it isn't learned, it's asserted. Fixing it silently would hide
that this is a real, consequential choice: too low and real anomalies get
missed, too high and normal transactions get flagged. Exposing it as a
parameter (mirroring the entity resolution threshold slider in Phase 4)
keeps that trade-off visible to whoever is using the tool, rather than
baking in one number and hiding the trade-off it implies.

---

*(Further questions will be appended as Phases 6–9 are implemented.)*
