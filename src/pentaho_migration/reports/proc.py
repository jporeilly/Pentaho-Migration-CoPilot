"""Shared subprocess policy for the heavy externals (Java renders, the
Crystal viewer export, RptToXml, rpt-rs).

They are CPU-hungry and often run while a human is WATCHING the app - a
release check renders through two engines back to back, and at normal
priority that starves the browser compositor into blank-screen territory on
a single machine. Below-normal priority costs seconds of wall clock and
buys a UI that keeps painting.
"""

import subprocess

# Windows-only flag; 0 elsewhere.
NICE = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


def run_nice(cmd, **kwargs):
    """subprocess.run at below-normal priority."""
    kwargs.setdefault("creationflags", NICE)
    return subprocess.run(cmd, **kwargs)
