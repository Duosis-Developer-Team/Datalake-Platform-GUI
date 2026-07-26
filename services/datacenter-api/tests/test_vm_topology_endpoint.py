"""get_vm_topology: 6h cached, delegates to shared vm_topology.build_tree."""


def test_get_vm_topology_builds_tree(monkeypatch):
    from app.services import dc_service as m
    svc = m.DatabaseService.__new__(m.DatabaseService)
    rows = [("DC13", "CL1", "esx1", "web-01", "Microsoft Windows Server 2019", "poweredOn")]
    monkeypatch.setattr(svc, "_run_rows", lambda cur, sql, params=None: rows)

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()

    monkeypatch.setattr(svc, "_get_connection", lambda: _Conn())
    monkeypatch.setattr(m.cache, "get", lambda k: None)
    monkeypatch.setattr(m.cache, "run_singleflight", lambda key, fn, ttl=None: fn())

    out = svc.get_vm_topology(with_os=True)
    assert out["totals"]["vms"] == 1
    assert out["totals"]["running"] == 1
    assert out["dcs"][0]["name"] == "DC13"
    assert out["dcs"][0]["os"]["windows"] == 1


def test_get_vm_topology_empty_on_db_error(monkeypatch):
    from app.services import dc_service as m
    from psycopg2 import OperationalError
    svc = m.DatabaseService.__new__(m.DatabaseService)
    monkeypatch.setattr(m.cache, "get", lambda k: None)

    def _boom(key, fn, ttl=None):
        raise OperationalError("no db")

    monkeypatch.setattr(m.cache, "run_singleflight", _boom)
    out = svc.get_vm_topology(with_os=False)
    assert out["dcs"] == [] and out["totals"]["vms"] == 0
