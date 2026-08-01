"""Staged background jobs the UI polls - ONE implementation.

The release gate proved the pattern: a POST /x/start endpoint creates a
job dict, a daemon thread works through named stages, and the UI polls
GET /x/status rendering the stages as a progress bar. The gate, the
translator and every new agent each grew their own copy of the store,
the eviction and the error plumbing - this module is that machinery,
once. Jobs stay PLAIN DICTS (the status endpoint returns them verbatim,
so each job type keeps its own extra keys: done/total for counted work,
result for the payload).
"""

import threading
import time
import uuid

MAX_JOBS = 40          # evict the oldest beyond this many
MAX_AGE_S = 3600.0     # ... or older than an hour


class JobStore:
    """One family of background jobs (gate, translate, review, ...)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}

    def start(self, stages: list[str] | None = None, **extra) -> tuple[str, dict]:
        """Create a job and return (id, job). With `stages`, the job starts
        at the first stage and the UI renders the list as a progress bar;
        `extra` keys (done/total/...) ride along verbatim."""
        job_id = uuid.uuid4().hex[:12]
        job: dict = {"status": "running", "detail": "", "result": None,
                     "created": time.time(), **extra}
        if stages:
            job["stages"] = stages
            job["stage"] = stages[0]
        self._jobs[job_id] = job
        self._evict()
        return job_id, job

    def get(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        # `created` is bookkeeping, not part of any status contract
        return {k: v for k, v in job.items() if k != "created"}

    def run(self, job: dict, worker) -> None:
        """Run `worker()` on a daemon thread; it owns stage/result updates.
        An exception becomes status=error with the message in detail. A
        worker that already set its own terminal status (its own error
        handling, say) is left alone."""
        def _run() -> None:
            try:
                worker()
                if job.get("status") == "running":
                    job["status"] = "done"
                    if "stages" in job:
                        job["stage"] = job["stages"][-1]
            except Exception as exc:   # the poller shows this verbatim
                job["status"] = "error"
                job["detail"] = str(exc)
        threading.Thread(target=_run, daemon=True).start()

    def _evict(self) -> None:
        now = time.time()
        for key in [k for k, j in self._jobs.items()
                    if j.get("status") != "running"
                    and now - j.get("created", now) > MAX_AGE_S]:
            self._jobs.pop(key, None)
        while len(self._jobs) > MAX_JOBS:
            oldest = min(self._jobs, key=lambda k: self._jobs[k].get("created", 0))
            self._jobs.pop(oldest)
