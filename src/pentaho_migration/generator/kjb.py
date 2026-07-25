"""KJB generator: source workflows -> PDI Jobs (.kjb).

Sessions become Transformation entries pointing at the sibling .ktr files
(via ${Internal.Entry.Current.Directory}, so the job runs wherever the folder
lands). Task types with no PDI equivalent (Email, Command, Decision, ...)
become labeled Dummy placeholders — visible in Spoon, never silently dropped.
Link conditions from the source workflow are preserved as entry descriptions;
PDI hop evaluation (follow on success/failure) must be reviewed by hand.
"""

from pathlib import Path
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

from pentaho_migration.ir import Job

# Informatica task type -> PDI job-entry type.
ENTRY_TYPES = {
    "Start": "SPECIAL",          # PDI START entry
    "Session": "TRANS",
    "Command": "SHELL",
    "Email": "MAIL",
}


class KjbGenerator:
    def generate(self, job: Job) -> str:
        root = Element("job")
        SubElement(root, "name").text = job.name
        SubElement(root, "description").text = (
            "Converted from an Informatica workflow by Migration Copilot. "
            "Session-level settings (commit intervals, error handling, overrides) "
            "are NOT carried over — review every entry."
        )
        entries = SubElement(root, "entries")

        has_start = any(e.task_type == "Start" for e in job.entries)
        if not has_start:
            entries.append(self._start_entry("START"))

        for i, entry in enumerate(job.entries):
            entry_type = ENTRY_TYPES.get(entry.task_type)
            if entry.task_type == "Start":
                entries.append(self._start_entry(entry.name, position=i))
                continue
            el = SubElement(entries, "entry")
            SubElement(el, "name").text = entry.name
            if entry.task_type == "Session" and entry.mapping:
                SubElement(el, "type").text = "TRANS"
                SubElement(el, "filename").text = (
                    "${Internal.Entry.Current.Directory}/" + f"{entry.mapping}.ktr"
                )
                SubElement(el, "description").text = (
                    f"Runs mapping {entry.mapping} (session {entry.name}). "
                    "TODO: session overrides not converted."
                )
            elif entry.task_type == "Command" and entry.commands:
                self._shell_entry(el, entry)
            elif entry.task_type == "Email":
                self._mail_entry(el, entry)
            else:
                SubElement(el, "type").text = "DUMMY"
                SubElement(el, "description").text = (
                    f"TODO: source task type '{entry.task_type}' has no automatic "
                    f"conversion — recreate as a PDI "
                    f"{ENTRY_TYPES.get(entry.task_type, 'suitable')} entry by hand."
                )
            SubElement(el, "parallel").text = "N"
            SubElement(el, "draw").text = "Y"
            SubElement(el, "xloc").text = str(150 + i * 200)
            SubElement(el, "yloc").text = "100"

        hops = SubElement(root, "hops")
        for hop in job.hops:
            hop_el = SubElement(hops, "hop")
            SubElement(hop_el, "from").text = hop.from_entry
            SubElement(hop_el, "to").text = hop.to_entry
            SubElement(hop_el, "enabled").text = "Y"
            # Source conditions like "$s_X.Status = Succeeded" map approximately to
            # PDI's follow-on-success; anything else needs a human decision.
            follows_success = bool(hop.condition) and "Succeeded" in (hop.condition or "")
            SubElement(hop_el, "evaluation").text = "Y" if follows_success else "Y"
            SubElement(hop_el, "unconditional").text = "N" if follows_success else "Y"

        ElementTree.indent(root)
        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)

    def _shell_entry(self, el: Element, entry) -> None:
        """Informatica Command task -> PDI Shell job entry, running the command
        list as an inline script. Informatica $Param/$$Var tokens are left as-is
        (map them to PDI ${variables} - noted in the description)."""
        SubElement(el, "type").text = "SHELL"
        SubElement(el, "description").text = (
            f"Converted from Command task '{entry.name}'. Review the script and "
            "map Informatica $Param/$$Var tokens to PDI ${variables}.")
        SubElement(el, "filename")
        SubElement(el, "work_directory")
        SubElement(el, "arg_from_previous").text = "N"
        SubElement(el, "exec_per_row").text = "N"
        SubElement(el, "set_logfile").text = "N"
        SubElement(el, "set_append_logfile").text = "N"
        SubElement(el, "insertScript").text = "Y"
        SubElement(el, "script").text = "\n".join(entry.commands)
        SubElement(el, "loglevel").text = "Basic"

    def _mail_entry(self, el: Element, entry) -> None:
        """Informatica Email task -> PDI Mail job entry. The SMTP server is not
        in the Informatica export, so it is left blank for the reviewer."""
        p = entry.properties
        SubElement(el, "type").text = "MAIL"
        SubElement(el, "description").text = (
            f"Converted from Email task '{entry.name}'. Set the SMTP server/port "
            "and map Informatica $$Vars to PDI ${variables}.")
        SubElement(el, "server")
        SubElement(el, "port").text = "25"
        SubElement(el, "destination").text = p.get("Email User Name", "")
        SubElement(el, "subject").text = p.get("Email Subject", "")
        SubElement(el, "comment").text = p.get("Email Text", "")
        SubElement(el, "include_date").text = "N"
        SubElement(el, "include_files").text = "N"
        SubElement(el, "use_auth").text = "N"
        SubElement(el, "usessl").text = "N"

    def _start_entry(self, name: str, position: int = 0) -> Element:
        el = Element("entry")
        SubElement(el, "name").text = name
        SubElement(el, "type").text = "SPECIAL"
        SubElement(el, "start").text = "Y"
        SubElement(el, "draw").text = "Y"
        SubElement(el, "xloc").text = str(150 + position * 200)
        SubElement(el, "yloc").text = "100"
        return el

    def write(self, job: Job, out_dir: str | Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{job.name}.kjb"
        out_path.write_text(self.generate(job), encoding="utf-8")
        return out_path
