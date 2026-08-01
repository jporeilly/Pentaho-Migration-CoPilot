# Version

**1.44.4** - 2026-08-01

**The doctor knows every moving part.** `pentaho-migrate doctor` prints
one readiness table across the whole estate of dependencies - the
Pentaho suite, the SAP Crystal runtime and its tools, LLM providers,
Docker Desktop (told apart from installed-but-not-running), Airflow and
Marquez, the sample databases - each row with what it is needed for and
the exact next step. Both installer modes end with it, so Complete
stays zero-prompt and a fresh box finishes with its own readiness
report. The policy it encodes: install only what the product owns
(venv, package, UI build, SHA-verified JDBC jars); check and report
licensed or system-level third parties rather than accepting their
licences on your behalf; offer exactly one assisted install where the
path is clean (Ollama via winget, explicit opt-in in Custom mode).

Also in this release: a render queue caps concurrent JVM/viewer
renders so bursts stop thrashing demo laptops, background-job messages
own the server-restart story, the demo-box image carries every extra
and the curated demo samples with a persistent /data volume plus a
root docker-compose with the optional Xtreme MySQL profile, and the
solution-zip and estate upload paths passed a path-traversal audit.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects);
the agent stack (review + consultant reports) covers every family.
See [CHANGELOG.md](CHANGELOG.md) for history.
