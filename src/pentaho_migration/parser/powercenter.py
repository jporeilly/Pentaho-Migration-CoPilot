"""Deterministic parser for Informatica PowerCenter XML exports (Stage 1: PARSE).

PowerCenter exports are structured XML (POWERMART > REPOSITORY > FOLDER >
MAPPING), so no AI is involved here — real parsing only, per the design
principle that accuracy in this stage is non-negotiable.
"""

from pathlib import Path
from xml.etree import ElementTree

from pentaho_migration.ir import (
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


from pentaho_migration.parser.errors import ParseError


class PowerCenterParseError(ParseError):
    pass


class PowerCenterParser:
    def parse_file(self, path: str | Path) -> list[Pipeline]:
        root = self._root(path)
        targets = self._parse_target_defs(root)
        mapplets = self._parse_mapplet_defs(root)
        return [self._parse_mapping(m, targets, mapplets) for m in root.iter("MAPPING")]

    def _parse_mapplet_defs(self, root: ElementTree.Element) -> dict[str, dict]:
        """Folder-level <MAPPLET> definitions -> {name: {steps, hops, inputs,
        outputs}}. A mapplet is a reusable sub-mapping; expanding it inline
        preserves its Expression/Filter/etc. transformations (and their
        translatable expressions) instead of dropping the instance."""
        defs: dict[str, dict] = {}
        for mapplet in root.iter("MAPPLET"):
            name = mapplet.get("NAME", "")
            if not name:
                continue
            steps = [self._parse_transformation(x) for x in mapplet.iter("TRANSFORMATION")]
            hops = []
            seen: set[tuple[str, str]] = set()
            for conn in mapplet.iter("CONNECTOR"):
                edge = (conn.get("FROMINSTANCE", ""), conn.get("TOINSTANCE", ""))
                if all(edge) and edge not in seen and edge[0] != edge[1]:
                    seen.add(edge)
                    hops.append(edge)
            inputs = [s.name for s in steps if s.source_type == "Input Transformation"]
            outputs = [s.name for s in steps if s.source_type == "Output Transformation"]
            defs[name] = {"steps": steps, "hops": hops,
                          "inputs": inputs, "outputs": outputs}
        return defs

    def _parse_target_defs(self, root: ElementTree.Element) -> dict[str, list[FieldDef]]:
        """Folder-level <TARGET> definitions, keyed by name. Their <TARGETFIELD>
        elements carry KEYTYPE (PRIMARY KEY / FOREIGN KEY / NOT A KEY) - the
        source of truth for Insert/Update match keys, which the mapping's
        transformations never name."""
        targets: dict[str, list[FieldDef]] = {}
        for target in root.iter("TARGET"):
            name = target.get("NAME", "")
            if not name:
                continue
            fields = []
            for tf in target.iter("TARGETFIELD"):
                keytype = tf.get("KEYTYPE", "NOT A KEY")
                fields.append(FieldDef(
                    name=tf.get("NAME", ""),
                    datatype=tf.get("DATATYPE", "string"),
                    precision=_to_int(tf.get("PRECISION")),
                    scale=_to_int(tf.get("SCALE")),
                    nullable=tf.get("NULLABLE", "NULL") != "NOTNULL",
                    attrs={"KEYTYPE": keytype} if keytype != "NOT A KEY" else {}))
            targets[name] = fields
        return targets

    def parse_workflows(self, path: str | Path) -> list[Job]:
        """WORKFLOW elements -> Job IR (orchestration layer, ≈ PDI .kjb)."""
        root = self._root(path)
        # session name -> mapping name, defined at folder or workflow level
        session_mappings = {
            s.get("NAME", ""): s.get("MAPPINGNAME")
            for s in root.iter("SESSION")
        }
        task_details = self._parse_task_details(root)
        jobs = []
        for workflow in root.iter("WORKFLOW"):
            job = Job(name=workflow.get("NAME", "unnamed_workflow"))
            for task in workflow.iter("TASKINSTANCE"):
                name = task.get("NAME", "unnamed")
                task_type = task.get("TASKTYPE", "Unknown")
                entry = JobEntry(name=name, task_type=task_type)
                if task_type == "Session":
                    entry.mapping = session_mappings.get(task.get("TASKNAME", name))
                else:
                    # Command tasks carry a shell command list, Email tasks the
                    # recipient/subject/body - both keyed by the TASK name
                    detail = task_details.get(task.get("TASKNAME", name), {})
                    entry.commands = detail.get("commands", [])
                    entry.properties = detail.get("properties", {})
                job.entries.append(entry)
            for link in workflow.iter("WORKFLOWLINK"):
                job.hops.append(JobHop(
                    from_entry=link.get("FROMTASK", ""),
                    to_entry=link.get("TOTASK", ""),
                    condition=link.get("CONDITION") or None,
                ))
            jobs.append(job)
        return jobs

    def _parse_task_details(self, root: ElementTree.Element) -> dict[str, dict]:
        """Command/Email <TASK> definitions -> {task_name: {commands, properties}}.
        Command tasks store an ordered shell command list in <VALUEPAIR>; Email
        tasks store recipient/subject/body in <ATTRIBUTE>."""
        details: dict[str, dict] = {}
        for task in root.iter("TASK"):
            name, ttype = task.get("NAME", ""), task.get("TYPE", "")
            if ttype == "Command":
                pairs = sorted(
                    (vp for vp in task.iter("VALUEPAIR") if vp.get("VALUE")),
                    key=lambda vp: _to_int(vp.get("EXECORDER")) or 0)
                details[name] = {"commands": [vp.get("VALUE", "") for vp in pairs]}
            elif ttype == "Email":
                props = {a.get("NAME", ""): a.get("VALUE", "")
                         for a in task.iter("ATTRIBUTE") if a.get("VALUE")}
                details[name] = {"properties": props}
        return details

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

    def _parse_mapping(self, mapping: ElementTree.Element,
                       targets: dict[str, list[FieldDef]] | None = None,
                       mapplets: dict[str, dict] | None = None) -> Pipeline:
        targets = targets or {}
        mapplets = mapplets or {}
        pipeline = Pipeline(
            name=mapping.get("NAME", "unnamed_mapping"),
            source_tool=SourceTool.POWERCENTER,
            metadata={"isvalid": mapping.get("ISVALID", "")},
        )

        for xform in mapping.iter("TRANSFORMATION"):
            pipeline.steps.append(self._parse_transformation(xform))

        # mapplet instance name -> (input_boundary_step, output_boundary_step)
        # used to rewire the mapping's connectors through the expanded steps
        mapplet_boundaries: dict[str, tuple[str | None, str | None]] = {}
        for instance in mapping.iter("INSTANCE"):
            itype = instance.get("TYPE", "")
            if itype in ("SOURCE", "TARGET") and not pipeline.step(instance.get("NAME", "")):
                # a target instance carries its definition's key fields, so the
                # generator can infer Insert/Update match keys
                fields = (targets.get(instance.get("TRANSFORMATION_NAME", ""), [])
                          if itype == "TARGET" else [])
                pipeline.steps.append(
                    Step(name=instance.get("NAME", "unnamed"),
                         source_type=itype.title(), fields=list(fields)))
            elif itype == "MAPPLET" or instance.get("TRANSFORMATION_TYPE") == "Mapplet":
                definition = mapplets.get(instance.get("TRANSFORMATION_NAME", ""))
                if definition is not None:
                    mapplet_boundaries[instance.get("NAME", "")] = \
                        self._expand_mapplet(pipeline, instance.get("NAME", ""), definition)

        def _reroute(instance_name: str, *, as_source: bool) -> str:
            b = mapplet_boundaries.get(instance_name)
            if b is None:
                return instance_name
            return (b[1] if as_source else b[0]) or instance_name

        seen: set[tuple[str, str]] = set()
        for conn in mapping.iter("CONNECTOR"):
            src = _reroute(conn.get("FROMINSTANCE", ""), as_source=True)
            dst = _reroute(conn.get("TOINSTANCE", ""), as_source=False)
            edge = (src, dst)
            if all(edge) and edge[0] != edge[1] and edge not in seen:
                seen.add(edge)
                pipeline.hops.append(Hop(from_step=edge[0], to_step=edge[1]))

        return pipeline

    def _expand_mapplet(self, pipeline: Pipeline, instance_name: str,
                        definition: dict) -> tuple[str | None, str | None]:
        """Inline a mapplet's internal transformations into the parent pipeline,
        prefixed by the instance name. Returns (input_step, output_step) so the
        parent's connectors can rewire through the expanded chain. The Input/
        Output Transformation shells are kept as pass-through steps so the graph
        stays connected; the Expression/Filter/etc. inside are the real payload."""
        def qualified(name: str) -> str:
            return f"{instance_name}.{name}"

        for step in definition["steps"]:
            expanded = step.model_copy(deep=True)
            expanded.name = qualified(step.name)
            expanded.notes = [*expanded.notes,
                              f"expanded inline from mapplet instance {instance_name!r} "
                              "- verify port mapping"]
            pipeline.steps.append(expanded)
        for frm, to in definition["hops"]:
            pipeline.hops.append(Hop(from_step=qualified(frm), to_step=qualified(to)))

        inputs = definition["inputs"]
        outputs = definition["outputs"]
        return (qualified(inputs[0]) if inputs else None,
                qualified(outputs[0]) if outputs else None)

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
