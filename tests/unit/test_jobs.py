"""st_roto.jobs: background execution, progress, cancellation, failure reporting."""
import threading
import time

from st_roto import jobs


def test_runs_in_background_and_returns_result():
    seen = []

    def fn(job):
        for i in range(5):
            job.check(); job.report(i / 5.0, "step %d" % i); time.sleep(0.005)
        return threading.current_thread().name

    j = jobs.Job(fn, name="t", on_progress=lambda j: seen.append(j.progress)).start()
    assert j.wait(5)
    assert j.status == jobs.DONE and j.result.startswith("st_roto:") and seen == [0.0, 0.2, 0.4, 0.6, 0.8]


def test_cancel_is_cooperative_and_fast():
    started = threading.Event()

    def fn(job):
        started.set()
        while True:
            job.check(); time.sleep(0.002)

    finished = []
    j = jobs.Job(fn, on_finish=lambda j: finished.append(j.status)).start()
    started.wait(2)
    t0 = time.time(); j.cancel(); assert j.wait(2)
    assert j.status == jobs.CANCELLED and finished == [jobs.CANCELLED] and time.time() - t0 < 0.5


def test_failure_is_reported_not_swallowed():
    def fn(job):
        raise RuntimeError("boom")
    j = jobs.Job(fn).start(background=False)
    assert j.status == jobs.FAILED and "RuntimeError: boom" in j.error
