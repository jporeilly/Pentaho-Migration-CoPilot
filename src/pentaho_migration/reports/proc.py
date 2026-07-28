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


# Detach flags: a viewer or Report Designer window launched from the web
# server must OUTLIVE it - restarting the app killed the customer-facing
# window mid-demo. Breakaway can be denied by the parent job; fall back.
DETACH = (getattr(subprocess, "DETACHED_PROCESS", 0)
          | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
BREAKAWAY = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


def popen_detached(cmd, **kwargs):
    """Popen a GUI app that must survive the server's lifetime."""
    kwargs.setdefault("close_fds", True)
    try:
        return subprocess.Popen(cmd, creationflags=DETACH | BREAKAWAY, **kwargs)
    except OSError:
        return subprocess.Popen(cmd, creationflags=DETACH, **kwargs)
