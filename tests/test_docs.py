"""Documentation consistency: enforced, not hoped for.

Fails the suite whenever the version markers drift apart or a required
document is missing — so every release necessarily updates the docs.
"""

import re
import tomllib
from pathlib import Path

from pdi_migration import __version__

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    "README.md",
    "VERSION.md",
    "CHANGELOG.md",
    "docs/INSTALL.md",
    "docs/BEST_PRACTICES.md",
]


def test_required_docs_exist():
    missing = [d for d in REQUIRED_DOCS if not (ROOT / d).exists()]
    assert not missing, f"required documentation missing: {missing}"


def test_version_markers_agree():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__, "pyproject.toml vs __init__.py"

    version_md = (ROOT / "VERSION.md").read_text(encoding="utf-8")
    assert f"**{__version__}**" in version_md, "VERSION.md not bumped"

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first_entry = re.search(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
    assert first_entry, "CHANGELOG.md has no release entries"
    assert first_entry.group(1) == __version__, (
        f"newest CHANGELOG entry is {first_entry.group(1)}, but the code version "
        f"is {__version__} — add a changelog entry for this release"
    )


def test_readme_references_version_and_changelog():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "VERSION.md" in readme and "CHANGELOG.md" in readme