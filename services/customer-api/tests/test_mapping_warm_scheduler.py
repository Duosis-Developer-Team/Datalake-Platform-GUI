import threading
import time

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
