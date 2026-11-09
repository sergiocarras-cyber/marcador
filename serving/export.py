"""Capa de servicio: publica la capa gold como una API de JSON estático para la app.

    app/data/meta.json                     frescura de los datos
    app/data/days/<deporte>/index.json     días con partidos
    app/data/days/<deporte>/<fecha>.json   partidos de un día, agrupados por competición
    app/data/teams/<deporte>.json          equipos para el selector
    app/data/team/<team_key>.json          último partido con titular, forma y próximo partido
    app/data/f1.json                       Gran Premio actual y siguiente

Uso: python -m serving.export
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from serving.headlines import headline

WAREHOUSE = os.environ.get("WAREHOUSE_PATH", "data/warehouse.duckdb")
OUT = Path(os.environ.get("SERVING_DIR", "app/data"))

# Jugadores destacados que enseña la app, por deporte
LEADER_CATEGORIES = {
    "nba": ("team", ["points", "rebounds", "assists"]),
    "nfl": ("game", ["passingYards", "rushingYards", "receivingYards"]),
    "mlb": ("game", ["MLBRating"]),
}


def rows(con, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def iso(ts) -> str | None:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if ts else None


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_games(con) -> dict[str, dict]:
    teams = {t["team_key"]: t for t in rows(con, "select * from gold.dim_team")}
    games = rows(con, "select * from gold.fct_game")

    goals, reds = defaultdict(list), defaultdict(list)
    for m in rows(con, """
        select event_id, 'futbol-' || team_id as team_key, minute_label, player_short_name,
               is_goal, is_penalty, is_own_goal, is_red_card, is_shootout
        from silver.stg_espn__match_events
        where (is_goal and not is_shootout) or is_red_card
        order by event_id, clock_seconds"""):
        if m["is_goal"]:
            goals[m["event_id"]].append({"team_key": m["team_key"], "player": m["player_short_name"],
                                         "minute": m["minute_label"], "penalty": m["is_penalty"],
                                         "own_goal": m["is_own_goal"]})
        else:
            reds[m["event_id"]].append({"team_key": m["team_key"], "player": m["player_short_name"],
                                        "minute": m["minute_label"]})

    leaders = defaultdict(list)
    for sport, (level, cats) in LEADER_CATEGORIES.items():
        for l in rows(con, f"""
            select l.event_id, e.sport || '-' || l.team_id as team_key, l.category, l.category_label,
                   l.player_name, l.player_headshot, l.display_value
            from silver.stg_espn__leaders l join silver.stg_espn__events e using (event_id)
            where e.sport = ? and l.leader_level = ? and l.category in ({','.join('?' * len(cats))})
              and e.status_state <> 'pre'""", [sport, level, *cats]):
            leaders[l["event_id"]].append({
                "team_key": l["team_key"], "category": l["category"], "player": l["player_name"],
                "headshot": l["player_headshot"], "display": l["display_value"]})
    for ev in leaders.values():
        order = {c: i for _, cats in LEADER_CATEGORIES.values() for i, c in enumerate(cats)}
        ev.sort(key=lambda x: order.get(x["category"], 99))

    def side(key, score, record, lines):
        t = teams.get(key, {})
        return {"key": key, "id": t.get("team_id"), "name": t.get("team_short_name") or t.get("team_name"),
                "abbr": t.get("team_abbreviation"), "logo": t.get("team_logo"), "score": score,
                "record": record, "linescores": [int(x) for x in (lines or [])]}

    out = {}
    for g in games:
        game = {
            "id": g["event_id"], "sport": g["sport"], "league_key": g["league_key"], "league": g["league_name"],
            "start_time": iso(g["start_time"]), "date": g["local_date"].isoformat(),
            "state": g["status_state"], "status": g["status_name"], "period": g["period"],
            "clock": g["display_clock"], "venue": g["venue"], "broadcast": g["broadcast"], "link": g["link"],
            "preseason": g["is_preseason"], "result": g["result"],
            "extra_time": g["went_to_extra_time"], "penalties": g["decided_by_penalties"],
            "home": side(g["home_team_key"], g["home_score"], g["home_record"], g["home_linescores"]),
            "away": side(g["away_team_key"], g["away_score"], g["away_record"], g["away_linescores"]),
            "goals": goals.get(g["event_id"], []), "red_cards": reds.get(g["event_id"], []),
            "leaders": leaders.get(g["event_id"], []),
        }
        game["headline"] = headline(game)
        out[g["event_id"]] = game
    return out


def export_days(games: dict, league_order: dict) -> int:
    by_day = defaultdict(list)
    for g in games.values():
        by_day[(g["sport"], g["date"])].append(g)
    for (sport, day), gs in by_day.items():
        groups = defaultdict(list)
        for g in sorted(gs, key=lambda g: g["start_time"]):
            groups[(g["league_key"], g["league"])].append(g)
        write(OUT / "days" / sport / f"{day}.json", {
            "sport": sport, "date": day,
            "groups": [{"league_key": k, "league": n, "games": v}
                       for (k, n), v in sorted(groups.items(), key=lambda x: league_order.get(x[0][0], 99))],
        })
    for sport in {s for s, _ in by_day}:
        write(OUT / "days" / sport / "index.json", sorted(d for s, d in by_day if s == sport))
    return len(by_day)


def export_teams(con, games: dict) -> int:
    teams = rows(con, """
        select t.*, l.league_name, l.sort_order, f.last_5, f.played, f.wins, f.draws, f.losses,
               f.streak_outcome, f.streak_length, f.last_event_id, f.live_event_id, f.next_event_id
        from gold.dim_team t
        left join ref.leagues l on l.league_key = t.primary_league_key
        left join gold.team_form f using (team_key)""")
    standings = {s["team_key"]: s for s in rows(con, "select * from gold.standings")}

    by_sport = defaultdict(list)
    for t in teams:
        # El selector solo ofrece equipos con liga doméstica conocida (no rivales sueltos de copas)
        if t["has_standings"]:
            by_sport[t["sport"]].append({
                "key": t["team_key"], "id": t["team_id"], "name": t["team_short_name"], "full": t["team_name"],
                "logo": t["team_logo"], "league_key": t["primary_league_key"], "league": t["league_name"]})
        st = standings.get(t["team_key"])
        write(OUT / "team" / f"{t['team_key']}.json", {
            "team": {"key": t["team_key"], "sport": t["sport"], "name": t["team_short_name"],
                     "full": t["team_name"], "logo": t["team_logo"], "league": t["league_name"]},
            "form": {"last_5": t["last_5"], "played": t["played"], "wins": t["wins"], "draws": t["draws"],
                     "losses": t["losses"], "streak": t["streak_outcome"], "streak_length": t["streak_length"]},
            "standing": {"position": st["position"], "points": st["points"],
                         # En fútbol la posición es en la liga; en EE. UU., en la conferencia
                         "league": st["league_name"] if t["sport"] == "futbol" else st["group_name"],
                         "note": st["qualification_note"]} if st else None,
            "last": games.get(t["last_event_id"]),
            "live": games.get(t["live_event_id"]),
            "next": games.get(t["next_event_id"]),
        })
    for sport, ts in by_sport.items():
        write(OUT / "teams" / f"{sport}.json", sorted(ts, key=lambda t: t["full"]))
    return len(teams)


def export_f1(con) -> None:
    res = rows(con, "select * from gold.f1_results order by session_start, position")
    gps = defaultdict(lambda: {"sessions": defaultdict(list)})
    for r in res:
        gp = gps[r["grand_prix_id"]]
        gp.update(id=r["grand_prix_id"], name=r["grand_prix_name"], circuit=r["circuit"])
        gp["sessions"][(r["session_id"], r["session_label"], iso(r["session_start"]), r["status_state"])].append(r)
    out = []
    for gp in gps.values():
        sessions = []
        for (sid, label, start, state), rs in gp["sessions"].items():
            top = [{"position": r["position"], "driver": r["driver_name"], "short": r["driver_short_name"],
                    "country": r["driver_country"], "flag": r["driver_flag"]}
                   for r in rs if r["position"] and r["position"] <= 3]
            sessions.append({"id": sid, "label": label, "start": start, "state": state, "top3": top})
        sessions.sort(key=lambda s: s["start"] or "")
        out.append({"id": gp["id"], "name": gp["name"], "circuit": gp["circuit"],
                    "start": sessions[0]["start"], "end": sessions[-1]["start"], "sessions": sessions})
    out.sort(key=lambda g: g["start"] or "")
    now = datetime.now(timezone.utc).isoformat()
    # Actual: el último GP que ya ha empezado; si ya terminó su carrera y queda menos de 3 días, se mantiene
    started = [g for g in out if g["start"] and g["start"] <= now]
    upcoming = [g for g in out if g["start"] and g["start"] > now]
    write(OUT / "f1.json", {"current": started[-1] if started else None,
                            "next": upcoming[0] if upcoming else None})


def main() -> int:
    t0 = time.time()
    con = duckdb.connect(WAREHOUSE, read_only=True)
    if OUT.exists():
        shutil.rmtree(OUT)  # la salida se regenera entera: sin restos de ejecuciones anteriores
    league_order = {r["league_key"]: r["sort_order"] for r in rows(con, "select * from ref.leagues")}
    games = load_games(con)
    n_days = export_days(games, league_order)
    n_teams = export_teams(con, games)
    export_f1(con)
    last_ingest = con.execute("select max(ingested_at) from silver.stg_espn__events").fetchone()[0]
    write(OUT / "meta.json", {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "data_as_of": iso(last_ingest), "games": len(games), "teams": n_teams})
    print(f"{len(games)} partidos · {n_days} días · {n_teams} equipos exportados en {time.time() - t0:.1f}s → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
