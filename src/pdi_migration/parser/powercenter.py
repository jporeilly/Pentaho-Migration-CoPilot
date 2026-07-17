"""Deterministic parser for Informatica PowerCenter XML exports (Stage 1: PARSE).

PowerCenter exports are structured XML (POWERMART > REPOSITORY > FOLDER >
MAPPING), so no AI is involved here — real parsing only, per the design
principle that accuracy in this stage is non-negotiable.
"""

from pathlib import Path
from xml.etree import ElementTree

from pdi_migration.ir import (
    Confidence,
    Expression,
    FieldDef,
    Hop,
    Job,
    JobEntry,
    JobHop,
    Pipeline,
    SourceInfo,
    SourceTool,
    Step,
)

# REPOSITORY_VERSION attribute -> PowerCenter product release.
REPOSITORY_VERSIONS = {
    "177.85": "8.1",
    "178.87": "8.5",
    "181.90": "8.6",
    "179.88": "9.0/9.1",
    "182.91": "9.6",
    "184.93": "10.1",
    "186.95": "10.2",
    "187.96": "10.4.0",
    "188.97": "10.4.1",
    "189.98": "10.5",
}


class PowerCenterParseError(Exception):
    pass


class PowerCenterParser:
    def parse_file(self, path: str | Path) -> list[Pipeline]:
        return [self._parse_mapping(m) for m in self._root(path).iter("MAPPING")]

    def parse_workflows(self, path: str | Path) -> list[Job]:
        """WORKFLOW elements -> Job IR (orchestration layer, ≈ PDI .kjb)."""
        root = self._root(path)
        # session name -> mapping name, defined at folder or workflow level
        session_mappings = {
            s.get("NAME", ""): s.get("MAPPINGNAME")
            for s in root.iter("SESSION")
        }
        jobs = []
        for workflow in root.iter("WORKFLOW"):
            job = Job(name=workflow.get("NAME", "unnamed_workflow"))
            for task in workflow.iter("TASKINSTANCE"):
                name = task.get("NAME", "unnamed")
                task_type = task.get("TASKTYPE", "Unknown")
                entry = JobEntry(name=name, task_type=task_type)
                if task_type == "Session":
                    entry.mapping = session_mappings.get(task.get("TASKNAME", name))
                job.entries.append(entry)
            for link in workflow.iter("WORKFLOWLINK"):
                job.hops.append(JobHop(
                    from_entry=link.get("FROMTASK", ""),
                    to_entry=link.get("TOTASK", ""),
                    condition=link.get("CONDITION") or None,
                ))
            jobs.append(job)
        return jobs

    def analyze_export(self, path: str | Path) -> SourceInfo:
        """Export-level facts: tool version, repository, object counts."""
        root = self._root(path)
        repository = root.find("REPOSITORY")
        repo_version = root.get("REPOSITORY_VERSION")
        return SourceInfo(
            repository_version=repo_version,
            product_version=REPOSITORY_VERSIONS.get(repo_version or ""),
            repository_name=repository.get("NAME") if repository is not None else None,
            database_type=repository.get("DATABASETYPE") if repository is not None else None,
            codepage=repository.get("CODEPAGE") if repository is not None else None,
            creation_date=root.get("CREATION_DATE"),
            folders=[f.get("NAME", "") for f in root.iter("FOLDER")],
            mappings=sum(1 for _ in root.iter("MAPPING")),
            workflows=sum(1 for _ in root.iter("WORKFLOW")),
            sessions=sum(1 for _ in root.iter("SESSION")),
            mapplets=sum(1 for _ in root.iter("MAPPLET")),
        )

    def _root(self, path: str | Path) -> ElementTree.Element:
        root = ElementTree.parse(path).getroot()
        if root.tag != "POWERMART":
            raise PowerCenterParseError(
                f"{path}: expected a PowerCenter export (root POWERMART), got <{root.tag}>"
            )
        return root

    def _parse_mapping(self, mapping: ElementTree.Element) -> Pipeline:
        pipeline = Pipeline(
            name=mapping.get("NAME", "unnamed_mapping"),
            source_tool=SourceTool.POWERCENTER,
            metadata={"isvalid": mapping.get("ISVALID", "")},
        )

        for xform in mapping.iter("TRANSFORMATION"):
            pipeline.steps.append(self._parse_transformation(xform))

        # Source/target instances appear as INSTANCE elements, not TRANSFORMATION.
        for instance in mapping.iter("INSTANCE"):
            if instance.get("TYPE") in ("SOURCE", "TARGET") and not pipeline.step(
                instance.get("NAME", "")
            ):
                pipeline.steps.append(
                    Step(
                        name=instance.get("NAME", "unnamed"),
                        source_type=instance.get("TYPE", "").title(),
                    )
                )

        seen: set[tuple[str, str]] = set()
        for conn in mapping.iter("CONNECTOR"):
            edge = (conn.get("FROMINSTANCE", ""), conn.get("TOINSTANCE", ""))
            if all(edge) and edge not in seen:
                seen.add(edge)
                pipeline.hops.append(Hop(from_step=edge[0], to_step=edge[1]))

        return pipeline

    def _parse_transformation(self, xform: ElementTree.Element) -> Step:
        step = Step(
            name=xform.get("NAME", "unnamed"),
            source_type=xform.get("TYPE", "Unknown"),
        )
        for field in xform.iter("TRANSFORMFIELD"):
            name = field.get("NAME", "")
            attrs = {
                key: value
                for key in ("PORTTYPE", "EXPRESSIONTYPE")
                if (value := field.get(key))
            }
            step.fields.append(
                FieldDef(
                    name=name,
                    datatype=field.get("DATATYPE", "string"),
                    precision=_to_int(field.get("PRECISION")),
                    scale=_to_int(field.get("SCALE")),
                    attrs=attrs,
                )
            )
            raw_expr = field.get("EXPRESSION")
            # Passthrough ports repeat the field name as their expression; only
            # real derivations need translation.
            if raw_expr and raw_expr != name:
                step.expressions.append(
                    Expression(field=name, raw=raw_expr, confidence=Confidence.MANUAL)
                )
        for attr in xform.iter("TABLEATTRIBUTE"):
            step.properties[attr.get("NAME", "")] = attr.get("VALUE", "")
        return step


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None
