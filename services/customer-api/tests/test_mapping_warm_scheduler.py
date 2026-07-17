import threading
import time

from app.services.customer_service import CustomerService
from app.services.mapping_warm_scheduler import MappingWarmScheduler


def test_warms_the_name_after_the_delay():
    warmed: list[str] = []
    done = threading.Event()

    def warm(name):
        warmed.append(name)
        done.set()

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.05)
    sched.schedule(["Boyner"])

    assert done.wait(timeout=2.0)
    assert warmed == ["Boyner"]


def test_does_not_warm_before_the_delay_elapses():
    warmed: list[str] = []
    sched = MappingWarmScheduler(warm_fn=warmed.append, delay_seconds=5.0)
    sched.schedule(["Boyner"])

    time.sleep(0.05)
    assert warmed == []
    sched.cancel_all()


def test_second_save_within_the_window_cancels_the_first():
    warmed: list[str] = []
    done = threading.Event()

    def warm(name):
        warmed.append(name)
        done.set()

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.1)
    sched.schedule(["Boyner"])
    time.sleep(0.02)
    sched.schedule(["Boyner"])  # rollout: correcting the same customer again

    assert done.wait(timeout=2.0)
    time.sleep(0.15)
    # Debounced to a single warm, not one per save.
    assert warmed == ["Boyner"]


def test_distinct_names_each_get_warmed():
    warmed: list[str] = []
    lock = threading.Lock()

    def warm(name):
        with lock:
            warmed.append(name)

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.05)
    sched.schedule(["Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."])

    time.sleep(0.5)
    assert sorted(warmed) == sorted(["Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."])


def test_warm_failure_does_not_propagate():
    done = threading.Event()

    def warm(name):
        done.set()
        raise RuntimeError("query timed out")

    sched = MappingWarmScheduler(warm_fn=warm, delay_seconds=0.05)
    sched.schedule(["Boyner"])  # must not raise

    assert done.wait(timeout=2.0)
    time.sleep(0.05)


def test_cancel_all_stops_pending_warms():
    warmed: list[str] = []
    sched = MappingWarmScheduler(warm_fn=warmed.append, delay_seconds=0.2)
    sched.schedule(["Boyner"])
    sched.cancel_all()

    time.sleep(0.35)
    assert warmed == []


def test_concurrent_first_calls_share_one_scheduler_instance():
    """Task 6 review finding: _get_warm_scheduler's lazy init was an
    unguarded check-then-act. FastAPI runs sync handlers from a thread pool,
    so two concurrent first calls could each see no scheduler yet, each
    construct one, and race on the assignment — orphaning one instance whose
    running Timer still fires, producing a duplicate warm during the very
    window the debounce exists to collapse. A threading.Barrier forces the
    race to actually happen (no sleep-based sequencing, which would defeat
    the point) and asserts every thread gets back the identical object."""
    svc = CustomerService.__new__(CustomerService)
    thread_count = 16
    barrier = threading.Barrier(thread_count)
    results: list[MappingWarmScheduler] = [None] * thread_count  # type: ignore[list-item]

    def call(index: int) -> None:
        barrier.wait()  # release all threads at once to force the race
        results[index] = svc._get_warm_scheduler()

    threads = [threading.Thread(target=call, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    first = results[0]
    assert first is not None
    assert all(r is first for r in results)
