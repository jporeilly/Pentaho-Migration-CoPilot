"""Shared subprocess policy for the heavy externals (Java renders, the
Crystal viewer export, RptToXml, rpt-rs).

They are CPU-hungry and often run while a human is WATCHING the app - a
release check renders through two engines back to back, and at normal
priority that starves the browser compositor into blank-screen territory on
a single machine. Below-normal priority costs seconds of wall clock and
buys a UI that keeps painting.
"""

import os
import subprocess
import threading

# Windows-only flag; 0 elsewhere.
NICE = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)

# At most this many heavy renders at once. Each render is a whole JVM
# (or the Crystal viewer); three release checks fired together used to
# spawn three of each and thrash a demo laptop. Excess renders WAIT
# their turn rather than competing - below-normal priority already keeps
# the UI painting, this keeps the wall clock sane.
RENDER_SLOTS = max(1, int(os.environ.get("COPILOT_RENDER_SLOTS", "2")))
RENDER_GATE = threading.BoundedSemaphore(RENDER_SLOTS)


def run_nice(cmd, **kwargs):
    """subprocess.run at below-normal priority."""
    kwargs.setdefault("creationflags", NICE)
    return subprocess.run(cmd, **kwargs)


def run_render(cmd, **kwargs):
    """run_nice for the HEAVY externals (JVM renders, viewer exports),
    gated so only RENDER_SLOTS run concurrently."""
    with RENDER_GATE:
        return run_nice(cmd, **kwargs)


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


# A GUI app fronted by a .bat that uses `start` (Report Designer) needs a
# DIFFERENT flag. DETACHED_PROCESS gives cmd NO console, and `start` cannot
# spawn its window without one - so the batch ran, wrote nothing, and Report
# Designer never opened. CREATE_NO_WINDOW gives cmd a HIDDEN console: `start`
# works, launches javaw as its own independent GUI process (which outlives
# the server on its own), and no console flashes on screen.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def popen_gui_via_batch(cmd, **kwargs):
    """Popen a GUI app launched through a `start`-using .bat. See NO_WINDOW."""
    kwargs.setdefault("close_fds", True)
    return subprocess.Popen(cmd, creationflags=NO_WINDOW, **kwargs)
