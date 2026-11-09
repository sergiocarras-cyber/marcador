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
                "full": t.get("team_name"), "abbr": t.get("team_abbreviation"), "logo": t.get("team_logo"),
                "color": t.get("team_color"), "alt_color": t.get("team_alt_color"), "score": score,
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


# ---------- Ficha de partido ----------

# Tablas de jugadores por deporte: (grupo, título, [(clave, columna)], ordenar por, máximo por equipo)
PLAYER_TABLES = {
    "nba": [("general", "Jugadores", [("minutes", "MIN"), ("points", "PTS"), ("rebounds", "REB"), ("assists", "AST"),
             ("fieldGoalsMade-fieldGoalsAttempted", "TC"), ("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "T3")],
             "points", 10)],
    "nfl": [("passing", "Pase", [("completions/passingAttempts", "C/I"), ("passingYards", "YD"),
             ("passingTouchdowns", "TD"), ("interceptions", "INT")], "passingYards", 2),
            ("rushing", "Carrera", [("rushingAttempts", "ACA"), ("rushingYards", "YD"), ("rushingTouchdowns", "TD")],
             "rushingYards", 3),
            ("receiving", "Recepción", [("receptions", "REC"), ("receivingYards", "YD"), ("receivingTouchdowns", "TD")],
             "receivingYards", 3)],
    "mlb": [("batting", "Bateo", [("hits-atBats", "H-VB"), ("runs", "C"), ("RBIs", "CI"), ("homeRuns", "HR")], "hits", 9),
            ("pitching", "Pitcheo", [("fullInnings.partInnings", "EL"), ("hits", "H"), ("earnedRuns", "CL"),
             ("strikeouts", "K")], "strikeouts", 4)],
}
EVENT_ES = {"Goal": "Gol", "Penalty - Scored": "Gol de penalti", "Own Goal": "Gol en propia",
            "Yellow Card": "Amarilla", "Red Card": "Roja"}


def export_game_pages(con, games: dict) -> int:
    """game/<id>.json: todo lo que necesita la ficha de un partido, sin salir de la app."""
    stats = defaultdict(lambda: defaultdict(dict))
    for s in rows(con, "select * from gold.fct_team_game_stats order by sort_order"):
        stats[s["event_id"]][s["stat_name"]][s["team_key"]] = s

    players = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # evento → (equipo, grupo) → jugador → stats
    for p in rows(con, """select event_id, team_key, stat_group, player_id, player_short_name, position, is_starter,
                                 stat_key, display_value, value from gold.fct_player_game_stats"""):
        row = players[p["event_id"]][(p["team_key"], p["stat_group"])].setdefault(
            p["player_id"], {"name": p["player_short_name"], "position": p["position"], "starter": p["is_starter"], "v": {}})
        row["v"][p["stat_key"]] = (p["display_value"], p["value"])

    lineups = defaultdict(lambda: defaultdict(list))
    for l in rows(con, "select * from gold.fct_lineups order by event_id, team_key, formation_place nulls last, jersey"):
        lineups[l["event_id"]][l["team_key"]].append(l)

    timeline = defaultdict(list)
    for m in rows(con, """select event_id, 'futbol-' || team_id as team_key, event_type, minute_label, player_short_name,
                                 is_goal, is_penalty, is_own_goal, is_red_card, is_yellow_card
                          from silver.stg_espn__match_events
                          where (is_goal and not is_shootout) or is_red_card or is_yellow_card
                          order by event_id, clock_seconds"""):
        kind = "goal" if m["is_goal"] else "red" if m["is_red_card"] else "yellow"
        label = ("Gol de penalti" if m["is_penalty"] else "Gol en propia" if m["is_own_goal"] else "Gol") if kind == "goal" \
            else EVENT_ES.get(m["event_type"], "Roja" if kind == "red" else "Amarilla")
        timeline[m["event_id"]].append({"team_key": m["team_key"], "minute": m["minute_label"], "kind": kind,
                                        "label": label, "player": m["player_short_name"]})

    form = {f["team_key"]: f for f in rows(con, "select * from gold.team_form")}
    standing = {s["team_key"]: s for s in rows(con, "select * from gold.standings")}

    meetings = defaultdict(list)
    for g in games.values():
        meetings[(g["sport"], frozenset((g["home"]["key"], g["away"]["key"])))].append(g)

    def team_context(key):
        f, st = form.get(key) or {}, standing.get(key)
        return {"last_5": f.get("last_5"), "wins": f.get("wins"), "draws": f.get("draws"), "losses": f.get("losses"),
                "streak": f.get("streak_outcome"), "streak_length": f.get("streak_length"),
                "position": st["position"] if st else None, "points": st["points"] if st else None,
                "standing_group": (st["league_name"] if key.startswith("futbol") else st["group_name"]) if st else None}

    def player_tables(g):
        out = []
        for group, title, cols, sort_key, limit in PLAYER_TABLES.get(g["sport"], []):
            teams_out = []
            for side in (g["away"], g["home"]) if g["sport"] != "futbol" else (g["home"], g["away"]):
                ps = players[g["id"]].get((side["key"], group), {})
                ranked = sorted(ps.values(), key=lambda p: -((p["v"].get(sort_key) or (None, 0))[1] or 0))[:limit]
                if ranked:
                    teams_out.append({"team_key": side["key"], "rows": [
                        {"name": p["name"], "position": p["position"], "starter": p["starter"],
                         "values": [(p["v"].get(k) or ("–",))[0] for k, _ in cols]} for p in ranked]})
            if teams_out:
                out.append({"title": title, "columns": [c for _, c in cols], "teams": teams_out})
        return out

    def team_stats(g):
        out = []
        for name, by_team in stats[g["id"]].items():
            h, a = by_team.get(g["home"]["key"]), by_team.get(g["away"]["key"])
            if not (h and a):
                continue
            fmt = h["format"]
            show = lambda s: f"{int(s['value'])}%" if fmt in ("pct", "ratio") and s["value"] is not None else s["display_value"]
            out.append({"label": h["label_es"], "format": fmt, "home": show(h), "away": show(a),
                        "home_value": h["value"], "away_value": a["value"], "order": h["sort_order"]})
        return sorted(out, key=lambda x: x["order"])

    def lineup(g):
        out = []
        for side in (g["home"], g["away"]):
            ls = lineups[g["id"]].get(side["key"])
            if not ls:
                continue
            fmt = lambda l: {"name": l["player_short_name"], "jersey": l["jersey"], "position": l["position"],
                             "in": l["subbed_in"], "out": l["subbed_out"]}
            out.append({"team_key": side["key"], "formation": ls[0]["formation"],
                        "starters": [fmt(l) for l in ls if l["is_starter"]],
                        "subs": [fmt(l) for l in sorted((l for l in ls if not l["is_starter"]), key=lambda l: not l["subbed_in"])]})
        return out

    for g in games.values():
        h2h = sorted((m for m in meetings[(g["sport"], frozenset((g["home"]["key"], g["away"]["key"])))]
                      if m["id"] != g["id"] and m["state"] == "post"), key=lambda m: m["start_time"], reverse=True)[:5]
        write(OUT / "game" / f"{g['id']}.json", {
            "game": g,
            "timeline": timeline.get(g["id"], []),
            "stats": team_stats(g),
            "players": player_tables(g),
            "lineups": lineup(g),
            "context": {"home": team_context(g["home"]["key"]), "away": team_context(g["away"]["key"])},
            "meetings": [{"id": m["id"], "date": m["start_time"], "home": m["home"]["name"], "away": m["away"]["name"],
                          "home_score": m["home"]["score"], "away_score": m["away"]["score"], "league": m["league"]}
                         for m in h2h],
        })
    return len(games)


RECENT_HOURS, UPCOMING_HOURS = 40, 72
MAX_PER_LEAGUE = {"results": 2, "upcoming": 3, "live": 3}


def reasons(i: dict, g: dict, form: dict) -> list[str]:
    """Etiquetas que explican por qué se destaca un partido."""
    out = []
    if i["is_playoffs"]:
        out.append("Playoffs")
    if i["top_clash"]:
        out.append("Duelo de líderes")
    if i["comeback"]:
        out.append("Remontada")
    if i["overtime"]:
        out.append("Entradas extra" if g["sport"] == "mlb" else "Penaltis" if g.get("penalties") else "Prórroga")
    if i["goal_fest"]:
        out.append(f"{g['home']['score'] + g['away']['score']} goles")
    elif i["tight_finish"] and g["state"] == "post":
        out.append("Final ajustado")
    if g["state"] == "pre":
        for side in (g["home"], g["away"]):
            f = form.get(side["key"]) or {}
            if f.get("streak_outcome") == "W" and (f.get("streak_length") or 0) >= 4:
                out.append(f"{side['name']}: {f['streak_length']} victorias seguidas")
    return out


MIN_SCORE = 55  # por debajo no es "destacado", aunque falten partidos para llenar la lista


def pick(candidates: list[dict], limit: int, per_league: int) -> list[dict]:
    """Los mejores por puntuación, con un máximo por competición para que haya variedad
    y sin repetir enfrentamiento (series de varios partidos seguidos entre los mismos equipos)."""
    chosen, per, pairs = [], defaultdict(int), set()
    for c in sorted(candidates, key=lambda c: (-c["score"], c["game"]["start_time"])):
        g = c["game"]
        pair = frozenset((g["home"]["key"], g["away"]["key"]))
        if c["score"] >= MIN_SCORE and per[g["league_key"]] < per_league and pair not in pairs:
            chosen.append(c)
            per[g["league_key"]] += 1
            pairs.add(pair)
        if len(chosen) == limit:
            break
    return chosen


def export_featured(con, games: dict) -> dict:
    form = {f["team_key"]: f for f in rows(con, "select * from gold.team_form")}
    interest = rows(con, f"""
        select * from gold.game_interest
        where start_time between now() - interval {RECENT_HOURS} hour and now() + interval {UPCOMING_HOURS} hour""")
    buckets = defaultdict(list)
    for i in interest:
        g = games[i["event_id"]]
        bucket = {"in": "live", "post": "results", "pre": "upcoming"}[g["state"]]
        if bucket == "results" and not g["headline"]:
            continue
        buckets[bucket].append({"score": i["interest_score"], "reasons": reasons(i, g, form), "game": g})
    out = {
        "live": pick(buckets["live"], 6, MAX_PER_LEAGUE["live"]),
        "results": pick(buckets["results"], 6, MAX_PER_LEAGUE["results"]),
        "upcoming": sorted(pick(buckets["upcoming"], 8, MAX_PER_LEAGUE["upcoming"]), key=lambda c: c["game"]["start_time"]),
    }
    write(OUT / "featured.json", out)
    return {k: len(v) for k, v in out.items()}


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
    export_game_pages(con, games)
    featured = export_featured(con, games)
    print(f"Destacados: {featured}")
    last_ingest = con.execute("select max(ingested_at) from silver.stg_espn__events").fetchone()[0]
    write(OUT / "meta.json", {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "data_as_of": iso(last_ingest), "games": len(games), "teams": n_teams})
    print(f"{len(games)} partidos · {n_days} días · {n_teams} equipos exportados en {time.time() - t0:.1f}s → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
