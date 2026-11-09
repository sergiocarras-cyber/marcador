import csv
import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from ingestion import extract
from ingestion.sources import LEAGUES, BY_KEY


class FakeClient:
    """Sustituye a httpx.Client: devuelve una respuesta fija y cuenta las llamadas."""
    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    def get(self, url):
        self.calls += 1
        payload = self.payload

        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return payload
        return R()


@pytest.fixture
def task(tmp_path):
    return extract.Task(url="https://example/x", dest=tmp_path / "league=nba" / "date=2026-11-08.json.gz",
                        meta={"entity": "scoreboard", "league": "nba", "date": "2026-11-08"})


def test_writes_envelope_with_lineage(task):
    res = extract.run_task(FakeClient({"events": [1, 2]}), task)
    assert res.status == "written"
    with gzip.open(task.dest, "rt") as f:
        doc = json.load(f)
    assert doc["payload"] == {"events": [1, 2]}
    assert doc["_meta"]["league"] == "nba"
    assert doc["_meta"]["source_url"] == "https://example/x"
    assert len(doc["_meta"]["payload_sha256"]) == 64


def test_rerun_is_idempotent(task):
    extract.run_task(FakeClient({"events": [1]}), task)
    mtime = task.dest.stat().st_mtime_ns
    assert extract.run_task(FakeClient({"events": [1]}), task).status == "unchanged"
    assert task.dest.stat().st_mtime_ns == mtime
    assert extract.run_task(FakeClient({"events": [1, 2]}), task).status == "written"


def test_scoreboard_tasks_respect_season_window():
    mlb = BY_KEY["mlb"]
    tasks = extract.scoreboard_tasks([mlb], date(2026, 11, 8), date(2026, 11, 20))
    # La MLB termina el 10 de noviembre: solo 8, 9 y 10
    assert [t.meta["date"] for t in tasks] == ["2026-11-08", "2026-11-09", "2026-11-10"]
    assert tasks[0].url.endswith("baseball/mlb/scoreboard?dates=20261108")


def test_sources_match_dbt_seed():
    seed = Path(__file__).parents[1] / "transform" / "seeds" / "leagues.csv"
    with seed.open() as f:
        seeded = {r["league_key"]: r["sport"] for r in csv.DictReader(f)}
    assert seeded == {lg.key: lg.sport for lg in LEAGUES}


def test_summary_keeps_only_modelled_sections(task):
    task.keep = ("header", "boxscore")
    extract.run_task(FakeClient({"header": 1, "boxscore": 2, "news": 3, "plays": [4] * 1000}), task)
    with gzip.open(task.dest, "rt") as f:
        doc = json.load(f)
    assert doc["payload"] == {"header": 1, "boxscore": 2}
    assert doc["_meta"]["sections_kept"] == ["header", "boxscore"]


def test_summary_tasks_skip_old_finished_games(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "BRONZE", tmp_path)
    nba = BY_KEY["nba"]

    def scoreboard(d, events):
        p = tmp_path / "scoreboard" / "league=nba" / f"date={d}.json.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt") as f:
            json.dump({"_meta": {}, "payload": {"events": events}}, f)

    final = lambda i: {"id": i, "status": {"type": {"state": "post", "name": "STATUS_FINAL"}}}
    scoreboard("2026-11-01", [final("old")])
    scoreboard("2026-11-08", [final("recent"), {"id": "future", "status": {"type": {"state": "pre", "name": "x"}}}])
    # La ficha antigua ya existe: no se vuelve a pedir; la reciente sí (puede corregirse)
    old = tmp_path / "summary" / "league=nba" / "event=old.json.gz"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"")
    tasks = extract.summary_tasks([nba], date(2026, 11, 1), date(2026, 11, 9), today=date(2026, 11, 9))
    assert [t.meta["event_id"] for t in tasks] == ["recent"]
    assert tasks[0].url.endswith("basketball/nba/summary?event=recent")
