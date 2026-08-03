# Version

**1.44.6** - 2026-08-03

**Cross-tabs render as a proper pivot grid, and Podman is a first-class
runtime.** Four presentation defects in the emitted crosstab are fixed
at the source: column groups no longer print their dimension name over
every value, a single measure no longer repeats under every column, the
row-area corner headers humanise and wrap instead of colliding (and
stay our text - the wizard metadata attribute had been letting the
engine swap labels back to raw field names), and every header and cell
carries the grid: thin borders, shaded bold headers, right-aligned
measures. Verified live through the real engine.

The dependency doctor now treats Podman as a first-class container
runtime alongside Docker - each CLI probed with its own info template
(docker's template is an error under podman even with the engine up),
three states with runtime-specific next steps, and Podman named as the
free option. The demo-box image is built and run-verified under Podman
6, with the compose files working as-is via `podman compose`.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects);
the agent stack (review + consultant reports) covers every family.
See [CHANGELOG.md](CHANGELOG.md) for history.
