"""Sort conversion notes into what a consultant must actually do.

Everything the pipeline learns lands in one list of notes, and that list reads
as a wall of manual work — which is wrong twice over. It overstates the job
(most entries are repairs the layout agent already applied and is telling you
about), and it buries the few entries that genuinely need a decision.

Three kinds:

* **applied**  - the pipeline changed something and wants it verified. Nothing
  to do unless the verification fails.
* **manual**   - a Crystal behaviour with no PRD equivalent, or one we refuse
  to guess at. This is the real backlog.
* **info**     - provenance and context; no action either way.

Classification is deterministic and prefix-driven, because a consultant's
estimate should not move because a model felt differently today.
"""

import re

APPLIED = "applied"
MANUAL = "manual"
INFO = "info"

# Ordered: first match wins. Patterns are unanchored on purpose — the same
# note reaches us bare from model.issues and prefixed with its band
# ("`PageHeader`: ...") from the markdown report.
_RULES = (
    (APPLIED, re.compile(r"\blayout auto-fit:", re.I)),
    (APPLIED, re.compile(r"\bnudged apart\b|\bgrown to fit\b|\bscaled by\b", re.I)),
    (APPLIED, re.compile(r"\brecovered\b.*\brpt-rs\b", re.I)),
    # "conditional EnableSuppress converted to a 'visible' style expression -
    # verify against Crystal", "cross-tab converted to a nested PRD crosstab
    # sub-report", "subreport 'x' converted as a nested PRD sub-report". The
    # pipeline did the work; the sentence is telling you what it chose.
    (APPLIED, re.compile(r"\bconverted (?:to|as|into)\b", re.I)),
    (APPLIED, re.compile(r"\bapplied to the\b", re.I)),
    (APPLIED, re.compile(r"\bresolved to column\b", re.I)),
    # "summary 'StdDev of APR' has no PRD report function - computed as a
    # windowed SQL column (STDDEV_SAMP ... OVER ...)". The workaround shipped;
    # the sentence names it. Without this the note reads as a rebuild.
    (APPLIED, re.compile(r"\bcomputed as a\b|\brewritten as a\b|\bemitted as a "
                         r"PRD\b|\bgenerated in the bundle\b", re.I)),
    (INFO, re.compile(r"\bimage carved from the \.rpt", re.I)),
    (INFO, re.compile(r"\bchart migrated as a PRD legacy chart", re.I)),
    (MANUAL, re.compile(r"\bnot carried\b|\brebuild by hand\b|\bby hand\b"
                        r"|\bhand-add\b|\bno PRD\b|\bunresolved\b", re.I)),
)


def classify_todo(note: str) -> str:
    """One of APPLIED / MANUAL / INFO. Unknown notes default to MANUAL — an
    unclassified note is more safely over-reported than quietly dropped."""
    for kind, pattern in _RULES:
        if pattern.search(note or ""):
            return kind
    return MANUAL


def split_todos(notes):
    """{applied: [...], manual: [...], info: [...]}, order preserved."""
    out = {APPLIED: [], MANUAL: [], INFO: []}
    for note in notes:
        out[classify_todo(note)].append(note)
    return out
