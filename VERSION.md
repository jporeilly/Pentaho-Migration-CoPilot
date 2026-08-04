# Version

**1.44.7** - 2026-08-04

**The demo statement's "missing beige panel" was never a defect - and
the evidence says so.** The letter image inside the `.rpt` is pure
white-backed, and two independent decoders agree exactly: our OLE carve
and rpt-rs's decode of the picture record both read 227,093 pixels of
white and 17,078 of tyre-track tan. The SAP viewer's PDF export
quantises that image into a 256-colour indexed palette and lands its
background on `#fffdfa` - the reference PDF's own embedded copy carries
225,936 pixels of `#fffdfa` and no pure white at all. Our bundle embeds
the picture losslessly, so white stays white: the conversion is the
faithful one. The coverage notes, the demo walkthrough and the
appearance check's tolerance comment are corrected accordingly - the
demo no longer concedes a fidelity gap that does not exist, and the
tolerance is documented as sitting deliberately above palette noise so
a reference artifact cannot masquerade as a finding.

**rpt-rs v0.4.0.** Upstream shipped our Windows fix natively and retired
the `xml-dump` subcommand cross-tab recovery depended on; the adapter
now reads the `json-dump` model, with recovered definitions identical
across all 155 demo and corpus reports. Saved-data values arrive
un-scaled from the tool, so the decoder drops its own correction. The
locally-patched build is retired in favour of the verified release
binaries.

Also: crosstab cells gain padding so text clears the grid, and postcss
moves to 8.5.25, clearing the last open Dependabot alert.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal
Reports, Talend, and Pentaho Xactions (all three definition dialects);
the agent stack (review + consultant reports) covers every family.
See [CHANGELOG.md](CHANGELOG.md) for history.
