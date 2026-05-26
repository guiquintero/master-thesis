import tempfile
from pathlib import Path

from backend.cache import DiskKVStore, make_key


def test_keys_are_canonical():
    a = make_key("ns", "  Hello  WORLD ")
    b = make_key("ns", "hello world")
    assert a == b


def test_keys_with_accents():
    a = make_key("ns", "cães")
    b = make_key("ns", "caes")
    assert a == b


def test_disk_kv_set_get(tmp_path: Path):
    store = DiskKVStore(tmp_path)
    store.set("k", {"v": 1})
    assert store.get("k") == {"v": 1}


def test_disk_kv_ttl(tmp_path: Path):
    store = DiskKVStore(tmp_path)
    store.set("k", "val", ttl_s=0)
    import time as t
    t.sleep(0.1)
    assert store.get("k") is None
