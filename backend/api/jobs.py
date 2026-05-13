"""In-memory job manager for long-running pipeline runs."""
import threading
import time
import uuid
from typing import Any, Callable


class Job:
    def __init__(self, kind: str, params: dict):
        self.id = str(uuid.uuid4())[:8]
        self.kind = kind
        self.params = params
        self.status = "pending"
        self.stage = ""
        self.progress = 0.0
        self.log: list[str] = []
        self.result: Any = None
        self.error: str | None = None
        self.started_at = time.time()
        self.finished_at: float | None = None

    def append_log(self, line: str):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {line}")
        if len(self.log) > 500:
            self.log = self.log[-500:]

    def to_dict(self, include_log: bool = True, log_tail: int = 50) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }
        if include_log:
            d["log_tail"] = self.log[-log_tail:]
        return d


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, params: dict) -> Job:
        job = Job(kind, params)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: -j.started_at)

    def run(self, job: Job, target: Callable[[Job], Any]):
        """Execute target(job) in a background thread, capture result/errors."""
        def _runner():
            job.status = "running"
            try:
                result = target(job)
                job.result = result
                job.status = "done"
                job.progress = 1.0
            except Exception as e:
                job.error = str(e)
                job.status = "error"
                job.append_log(f"ERROR: {e}")
            finally:
                job.finished_at = time.time()

        threading.Thread(target=_runner, daemon=True).start()


manager = JobManager()
