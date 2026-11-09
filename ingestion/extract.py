"""Extractor de ESPN hacia la capa bronze.

Cada respuesta se guarda tal cual llega, envuelta con metadatos de linaje:

    data/bronze/espn/scoreboard/league=<liga>/date=<AAAA-MM-DD>.json.gz
    data/bronze/espn/standings/league=<liga>.json.gz
    data/bronze/espn/f1/season=<año>.json.gz

Propiedades:
- Idempotente: volver a ejecutar el mismo rango no duplica nada; un archivo solo
  se reescribe si el contenido de la API ha cambiado (comparando un hash).
- Reintentos con espera exponencial ante errores de red o 5xx.
- Concurrencia limitada para no castigar a la fuente.

Uso:
    python -m ingestion.extract backfill            # desde el inicio de cada temporada
    python -m ingestion.extract recent              # últimos días (resultados)
    python -m ingestion.extract fixtures            # próximas 3 semanas (calendario)
    python -m ingestion.extract standings
    python -m ingestion.extract f1
    python -m ingestion.extract summaries --days 21  # fichas de partidos terminados
    python -m ingestion.extract scoreboards --league nba --start 2026-11-01 --end 2026-11-08
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from ingestion.sources import ESPN_SITE, ESPN_STANDINGS, F1_PATH, LEAGUES, SEASON, BY_KEY, League

BRONZE = Path(os.environ.get("BRONZE_DIR", "data/bronze")) / "espn"
USER_AGENT = "stats-pipeline/0.1 (+https://github.com)"
MAX_WORKERS = 4


@dataclass
class Task:
    url: str
    dest: Path
    meta: dict
    keep: tuple[str, ...] | None = None  # secciones del payload a conservar (None = todo)


@dataclass
class Result:
    task: Task
    status: str  # written | unchanged | failed
    error: str = ""


def payload_hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def read_existing_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)["_meta"].get("payload_sha256")
    except (OSError, ValueError, KeyError):
        return None


def fetch(client: httpx.Client, url: str, attempts: int = 4):
    delay = 1.0
    for i in range(attempts):
        try:
            r = client.get(url)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r.json()
            err = f"HTTP {r.status_code}"
        except (httpx.TransportError, ValueError) as e:
            err = str(e)
        if i < attempts - 1:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{url}: {err}")


def run_task(client: httpx.Client, t: Task) -> Result:
    try:
        payload = fetch(client, t.url)
    except Exception as e:  # noqa: BLE001 - se registra y se sigue con el resto
        return Result(t, "failed", str(e))
    if t.keep:
        # Resumen de partido: se guardan solo las secciones que se modelan. El resto
        # (noticias, vídeos, jugada a jugada) multiplica por 30 el tamaño sin aportar.
        payload = {k: payload[k] for k in t.keep if k in payload}
    h = payload_hash(payload)
    if read_existing_hash(t.dest) == h:
        return Result(t, "unchanged")
    t.dest.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "_meta": {
            **t.meta,
            "source": "espn",
            "source_url": t.url,
            "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "payload_sha256": h,
            **({"sections_kept": list(t.keep)} if t.keep else {}),
        },
        "payload": payload,
    }
    tmp = t.dest.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(envelope, f, separators=(",", ":"))
    tmp.replace(t.dest)  # escritura atómica
    return Result(t, "written")


def run(tasks: list[Task]) -> int:
    if not tasks:
        print("Nada que descargar.")
        return 0
    counts = {"written": 0, "unchanged": 0, "failed": 0}
    started = time.time()
    with httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client, \
         ThreadPoolExecutor(MAX_WORKERS) as pool:
        futures = [pool.submit(run_task, client, t) for t in tasks]
        for fut in as_completed(futures):
            res = fut.result()
            counts[res.status] += 1
            if res.status == "failed":
                print(f"  ERROR {res.error}", file=sys.stderr)
    print(f"{len(tasks)} peticiones en {time.time() - started:.1f}s · "
          f"{counts['written']} nuevas o cambiadas · {counts['unchanged']} sin cambios · {counts['failed']} fallidas")
    # Fallar el job solo si falla una parte importante, no por un error aislado de la fuente
    return 1 if counts["failed"] > max(2, len(tasks) * 0.1) else 0


# ---------- Construcción de tareas ----------

def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def scoreboard_tasks(leagues: list[League], start: date, end: date) -> list[Task]:
    tasks = []
    for lg in leagues:
        lo = max(start, lg.season_start)
        hi = min(end, lg.season_end) if lg.season_end else end
        for d in daterange(lo, hi):
            tasks.append(Task(
                url=f"{ESPN_SITE}/{lg.path}/scoreboard?dates={d:%Y%m%d}",
                dest=BRONZE / "scoreboard" / f"league={lg.key}" / f"date={d.isoformat()}.json.gz",
                meta={"entity": "scoreboard", "league": lg.key, "sport": lg.sport, "date": d.isoformat()},
            ))
    return tasks


def standings_tasks() -> list[Task]:
    return [Task(
        url=f"{ESPN_STANDINGS}/{lg.path}/standings",
        dest=BRONZE / "standings" / f"league={lg.key}.json.gz",
        meta={"entity": "standings", "league": lg.key, "sport": lg.sport},
    ) for lg in LEAGUES if lg.has_standings]


def f1_tasks(season: int) -> list[Task]:
    return [Task(
        url=f"{ESPN_SITE}/{F1_PATH}/scoreboard?dates={season}",
        dest=BRONZE / "f1" / f"season={season}.json.gz",
        meta={"entity": "f1_season", "season": season, "sport": "f1"},
    )]


SUMMARY_SECTIONS = {
    "futbol": ("header", "boxscore", "rosters", "keyEvents"),
    "default": ("header", "boxscore"),
}
FINAL_AFTER_DAYS = 2  # pasado este margen, la ficha de un partido terminado ya no cambia


def finished_events(league: League, start: date, end: date):
    """Partidos terminados según los marcadores ya guardados en bronze (sin llamar a la API)."""
    for d in daterange(start, end):
        path = BRONZE / "scoreboard" / f"league={league.key}" / f"date={d.isoformat()}.json.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as f:
            events = json.load(f)["payload"].get("events", [])
        for e in events:
            status = e.get("status", {}).get("type", {})
            if status.get("state") == "post" and status.get("name") not in ("STATUS_POSTPONED", "STATUS_CANCELED"):
                yield d, e["id"]


def summary_tasks(leagues: list[League], start: date, end: date, today: date) -> list[Task]:
    tasks = []
    for lg in leagues:
        for d, event_id in finished_events(lg, start, end):
            dest = BRONZE / "summary" / f"league={lg.key}" / f"event={event_id}.json.gz"
            if dest.exists() and (today - d).days > FINAL_AFTER_DAYS:
                continue
            tasks.append(Task(
                url=f"{ESPN_SITE}/{lg.path}/summary?event={event_id}",
                dest=dest,
                meta={"entity": "summary", "league": lg.key, "sport": lg.sport, "event_id": event_id,
                      "date": d.isoformat()},
                keep=SUMMARY_SECTIONS.get(lg.sport, SUMMARY_SECTIONS["default"]),
            ))
    return tasks


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["backfill", "recent", "fixtures", "standings", "f1", "summaries", "scoreboards", "all"])
    p.add_argument("--league", action="append", help="limitar a una o varias ligas (clave)")
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    p.add_argument("--days", type=int, default=21, help="summaries: días hacia atrás")
    args = p.parse_args(argv)

    leagues = [BY_KEY[k] for k in args.league] if args.league else LEAGUES
    today = datetime.now(timezone.utc).date()
    tasks: list[Task] = []

    if args.command == "backfill":
        tasks = scoreboard_tasks(leagues, min(lg.season_start for lg in leagues), today)
    elif args.command == "recent":
        # Fechas de ESPN van en hora de EE. UU.: cubrimos de sobra el cambio de día
        tasks = scoreboard_tasks(leagues, today - timedelta(days=3), today + timedelta(days=1))
    elif args.command == "fixtures":
        tasks = scoreboard_tasks(leagues, today + timedelta(days=2), today + timedelta(days=21))
    elif args.command == "standings":
        tasks = standings_tasks()
    elif args.command == "f1":
        tasks = f1_tasks(SEASON)
    elif args.command == "summaries":
        tasks = summary_tasks(leagues, today - timedelta(days=args.days), today, today)
    elif args.command == "all":
        code = run(scoreboard_tasks(leagues, today - timedelta(days=3), today + timedelta(days=21))
                   + standings_tasks() + f1_tasks(SEASON))
        # Los resúmenes dependen de los marcadores recién descargados: van después
        return max(code, run(summary_tasks(leagues, today - timedelta(days=3), today, today)))
    elif args.command == "scoreboards":
        if not (args.start and args.end):
            p.error("scoreboards necesita --start y --end")
        tasks = scoreboard_tasks(leagues, args.start, args.end)
    return run(tasks)


if __name__ == "__main__":
    sys.exit(main())
