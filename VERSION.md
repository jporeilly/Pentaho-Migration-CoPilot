# Version

**1.33.0** — 2026-07-25

**Phase 1 COMPLETE** — Informatica PowerCenter, SAP Crystal Reports, and
Talend. This round: **Talend rules v4** (190+ components) from the gap
analysis of the 150-job corpus — database families completed, big data and
object storage mapped through PDI's own mechanisms (Hive over JDBC, HDFS
and S3/Azure over VFS) rather than invented steps, corpus manual steps
293 → 167 — and an **honesty contract**: every unmapped component now
carries its reason, with Camel/ESB routes flagged as a different artifact
kind and in-house custom components named as such.
SSIS has been dropped from the roadmap; Phase 2 is IBM DataStage.
See [CHANGELOG.md](CHANGELOG.md) for history.
