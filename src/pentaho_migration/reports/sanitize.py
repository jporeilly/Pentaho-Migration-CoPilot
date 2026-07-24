"""Scrub credentials from RptToXml dumps.

Real .rpt files embed their connection details, and RptToXml faithfully dumps
them: `ConnectionInfo` elements carry UserName / Password / logon-property
attributes. Dumps get committed to corpora and attached to tickets, so scrub
them at the source. The converter itself never reads these attributes — JNDI
replaces the connection entirely — so blanking them loses nothing.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

SENSITIVE_TOKENS = ("password", "username", "user id", "logonproperties", "pwd")


def scrub_dump(path: Path | str) -> int:
    """Blank credential-bearing attributes in one dump. Returns the number of
    attributes blanked; the file is rewritten only when something changed."""
    path = Path(path)
    tree = ET.parse(path)
    changed = 0
    for node in tree.getroot().iter():
        if not node.tag.endswith("ConnectionInfo"):
            continue
        for attr in list(node.attrib):
            lowered = attr.lower()
            if any(token in lowered for token in SENSITIVE_TOKENS) and node.attrib[attr]:
                node.set(attr, "")
                changed += 1
    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


def scrub_directory(directory: Path | str) -> tuple[int, int]:
    """Scrub every dump in a directory. Returns (files_changed, attrs_blanked)."""
    files_changed = attrs_blanked = 0
    for xml in sorted(Path(directory).glob("*.xml")):
        blanked = scrub_dump(xml)
        if blanked:
            files_changed += 1
            attrs_blanked += blanked
    return files_changed, attrs_blanked
