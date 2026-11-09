"""Generador de titulares en español a partir de un partido ya modelado.

Recibe un partido con el formato que publica la capa de servicio (ver export.py) y
devuelve {"title": ..., "text": ...}. Son reglas, no un modelo de lenguaje: el mismo
partido produce siempre el mismo titular, y cada regla tiene su test.
"""
from __future__ import annotations

FEMININE = {"Real Sociedad", "Lazio", "Roma", "AS Roma", "Juventus", "Fiorentina", "Sampdoria",
            "Cultural Leonesa", "Real Sociedad B"}

# Umbrales por deporte: diferencia para "arrolla" y para "final ajustado"
BLOWOUT = {"futbol": 3, "nba": 20, "nfl": 21, "mlb": 6}
CLOSE = {"futbol": 1, "nba": 4, "nfl": 3, "mlb": 1}
# Ventaja al descanso del que acaba perdiendo para hablar de remontada
COMEBACK_LEAD = {"nba": 8, "nfl": 7, "mlb": 2}
REGULATION = {"futbol": 2, "nba": 4, "nfl": 4, "mlb": 9}

# Abreviaturas de estadísticas de ESPN → (singular, plural) en español
STAT_ES = {
    "YDS": ("yarda", "yardas"), "CAR": ("acarreo", "acarreos"), "REC": ("recepción", "recepciones"),
    "TD": ("TD", "TD"), "INT": ("intercepción", "intercepciones"),
    "IP": ("entrada", "entradas"), "ER": ("carrera limpia", "carreras limpias"), "H": ("hit", "hits"),
    "K": ("ponche", "ponches"), "BB": ("base por bolas", "bases por bolas"), "R": ("carrera", "carreras"),
    "RBI": ("impulsada", "impulsadas"), "HR": ("jonrón", "jonrones"), "SB": ("base robada", "bases robadas"),
    "2B": ("doble", "dobles"), "3B": ("triple", "triples"),
}


def article(name: str, sport: str) -> str:
    if sport == "futbol":
        return ("la " if name in FEMININE else "el ") + name
    return "los " + name


def prep(p: str, phrase: str) -> str:
    """a + el = al, de + el = del."""
    if phrase.startswith("el "):
        return ("al " if p == "a" else "del ") + phrase[3:]
    return f"{p} {phrase}"


def verb(sport: str, singular: str, plural: str) -> str:
    return singular if sport == "futbol" else plural


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def join_list(items: list[str]) -> str:
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def translate_stat(s: str) -> str:
    """'2-4, HR, 2 RBI, K' → '2 de 4, 1 jonrón, 2 impulsadas, 1 ponche'."""
    out = []
    for token in (t.strip() for t in s.split(",")):
        parts = token.split(" ")
        if len(parts) == 1 and token in STAT_ES:                 # "HR" = uno
            out.append(f"1 {STAT_ES[token][0]}")
        elif len(parts) == 2 and parts[1] in STAT_ES:            # "2 RBI", "6.0 IP"
            n, unit = parts
            one = n in ("1", "1.0")
            out.append(f"{n} {STAT_ES[unit][0 if one else 1]}")
        elif "-" in token and token.replace("-", "").isdigit():  # bateo "2-4"
            hits, at_bats = token.split("-")
            out.append(f"{hits} de {at_bats}")
        else:                                                    # "24/29" y otros, tal cual
            out.append(token)
    return ", ".join(out)


def _is_comeback(game: dict, winner: dict, loser: dict) -> bool:
    sport = game["sport"]
    if sport == "futbol":
        goals = [g for g in game.get("goals", []) if not g.get("own_goal")]
        return bool(goals) and goals[0]["team_key"] == loser["key"]
    half = REGULATION[sport] // 2
    w, l = winner.get("linescores") or [], loser.get("linescores") or []
    if len(w) < half or len(l) < half:
        return False
    return sum(l[:half]) - sum(w[:half]) >= COMEBACK_LEAD[sport]


def title(game: dict) -> str:
    sport, home, away = game["sport"], game["home"], game["away"]
    H, A = article(home["name"], sport), article(away["name"], sport)
    hs, as_ = home["score"], away["score"]

    if game["result"] == "draw" and not game.get("penalties"):
        return f"{cap(H)} y {A} empatan sin goles" if hs == 0 else f"{cap(H)} y {A} empatan a {hs}"

    winner, loser = (home, away) if game["result"] == "home" else (away, home)
    W, L = article(winner["name"], sport), article(loser["name"], sport)
    gana = verb(sport, "gana", "ganan")
    margin = abs(hs - as_)

    if game.get("penalties"):
        return f"{cap(W)} {gana} en los penaltis {prep('a', L)}"
    if margin >= BLOWOUT[sport]:
        return f"{cap(W)} {verb(sport, 'arrolla', 'arrollan')} {prep('a', L)}"
    if _is_comeback(game, winner, loser):
        return f"{cap(W)} {verb(sport, 'remonta', 'remontan')} y {gana} {prep('a', L)}"
    if game.get("extra_time"):
        cuando = "en entradas extra" if sport == "mlb" else "en la prórroga"
        return f"{cap(W)} {gana} {prep('a', L)} {cuando}"
    if margin <= CLOSE[sport]:
        coletilla = "por la mínima" if sport in ("futbol", "mlb") else "en un final ajustado"
        return f"{cap(W)} {gana} {prep('a', L)} {coletilla}"
    if winner is home:
        return f"{cap(W)} {gana} {prep('a', L)} en casa"
    return f"{cap(W)} {gana} en casa {prep('de', L)}"


def summary(game: dict) -> str:
    sport, home, away = game["sport"], game["home"], game["away"]
    bits: list[str] = []
    ordered = (home, away) if game["result"] in ("home", "draw") else (away, home)

    if sport == "futbol":
        for team in ordered:
            scorers: dict[str, list[str]] = {}
            for g in game.get("goals", []):
                if g["team_key"] != team["key"]:
                    continue
                minute = g["minute"] + (" pen." if g.get("penalty") else "") + (" p.p." if g.get("own_goal") else "")
                scorers.setdefault(g["player"] or "Gol", []).append(minute)
            if scorers:
                bits.append(f"{team['name']}: " + join_list([f"{p} ({', '.join(m)})" for p, m in scorers.items()]) + ".")
        reds = [r["player"] for r in game.get("red_cards", []) if r.get("player")]
        if reds:
            bits.append(f"{'Expulsados' if len(reds) > 1 else 'Expulsado'}: {join_list(reds)}.")
    elif sport == "nba":
        for team, verbo in zip(ordered, ("lideró a", "anotó para")):
            pts = next((l for l in game.get("leaders", [])
                        if l["team_key"] == team["key"] and l["category"] == "points"), None)
            if not pts:
                continue
            if verbo == "lideró a":
                bits.append(f"{pts['player']} lideró a {article(team['name'], sport)} con {pts['display']} puntos.")
            else:
                bits.append(f"Por {article(team['name'], sport)}, {pts['player']} anotó {pts['display']}.")
    else:
        for l in game.get("leaders", [])[:2]:
            bits.append(f"{l['player']}: {translate_stat(l['display'])}.")

    if sport != "futbol" and home.get("record") and away.get("record"):
        bits.append(f"Balance: {ordered[0]['name']} {ordered[0]['record']}, {ordered[1]['name']} {ordered[1]['record']}.")
    return " ".join(bits)


def headline(game: dict) -> dict | None:
    """Titular de un partido terminado; None si aún no ha acabado."""
    if game["state"] != "post" or game.get("result") is None:
        return None
    return {"title": title(game), "text": summary(game)}
