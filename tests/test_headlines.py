from serving.headlines import headline, translate_stat, article, prep


def game(sport, home, hs, away, as_, **kw):
    result = kw.pop("result", "home" if hs > as_ else "away" if as_ > hs else "draw")
    return {
        "sport": sport, "state": "post", "result": result,
        "extra_time": kw.pop("extra_time", False), "penalties": kw.pop("penalties", False),
        "home": {"key": f"{sport}-1", "name": home, "score": hs, "record": kw.pop("home_record", None),
                 "linescores": kw.pop("home_lines", [])},
        "away": {"key": f"{sport}-2", "name": away, "score": as_, "record": kw.pop("away_record", None),
                 "linescores": kw.pop("away_lines", [])},
        "goals": kw.pop("goals", []), "red_cards": [], "leaders": kw.pop("leaders", []),
    }


def goal(team, player, minute):
    return {"team_key": f"futbol-{team}", "player": player, "minute": minute, "penalty": False, "own_goal": False}


def test_articles_and_contractions():
    assert article("Betis", "futbol") == "el Betis"
    assert article("Real Sociedad", "futbol") == "la Real Sociedad"
    assert article("Bulls", "nba") == "los Bulls"
    assert prep("a", "el Elche") == "al Elche"
    assert prep("de", "el Elche") == "del Elche"
    assert prep("a", "la Real Sociedad") == "a la Real Sociedad"


def test_away_win():
    h = headline(game("futbol", "Elche", 0, "Betis", 2, goals=[goal(2, "R. Riquelme", "81'"), goal(2, "M. Bartra", "89'")]))
    assert h["title"] == "El Betis gana en casa del Elche"
    assert h["text"] == "Betis: R. Riquelme (81') y M. Bartra (89')."


def test_comeback_in_soccer_uses_first_goal():
    g = game("futbol", "Atlético", 1, "Barcelona", 2,
             goals=[goal(1, "G. Simeone", "10'"), goal(2, "F. López", "45'"), goal(2, "F. López", "66'")])
    h = headline(g)
    assert h["title"] == "El Barcelona remonta y gana al Atlético"
    assert h["text"] == "Barcelona: F. López (45', 66'). Atlético: G. Simeone (10')."


def test_draws():
    assert headline(game("futbol", "Celta Vigo", 0, "Levante", 0))["title"] == "El Celta Vigo y el Levante empatan sin goles"
    assert headline(game("futbol", "Betis", 2, "Sevilla", 2))["title"] == "El Betis y el Sevilla empatan a 2"


def test_blowout_and_close_in_nba():
    assert headline(game("nba", "Celtics", 130, "Nets", 100))["title"] == "Los Celtics arrollan a los Nets"
    assert headline(game("nba", "Celtics", 101, "Nets", 99))["title"] == "Los Celtics ganan a los Nets en un final ajustado"


def test_nba_comeback_from_halftime_deficit():
    g = game("nba", "Bulls", 110, "Heat", 100, home_lines=[20, 20, 35, 35], away_lines=[30, 25, 25, 20])
    assert headline(g)["title"] == "Los Bulls remontan y ganan a los Heat"


def test_overtime_and_penalties():
    assert headline(game("nfl", "Bills", 27, "Jets", 20, extra_time=True))["title"] == "Los Bills ganan a los Jets en la prórroga"
    g = game("futbol", "Betis", 1, "Sevilla", 1, result="away", penalties=True)
    assert headline(g)["title"] == "El Sevilla gana en los penaltis al Betis"


def test_nba_summary_and_record():
    g = game("nba", "Bulls", 121, "76ers", 127, home_record="1-8", away_record="9-2", leaders=[
        {"team_key": "nba-2", "category": "points", "player": "Jaylen Brown", "display": "29"},
        {"team_key": "nba-1", "category": "points", "player": "Josh Giddey", "display": "19"},
    ])
    h = headline(g)
    assert h["title"] == "Los 76ers ganan en casa de los Bulls"
    assert h["text"] == ("Jaylen Brown lideró a los 76ers con 29 puntos. Por los Bulls, Josh Giddey anotó 19. "
                         "Balance: 76ers 9-2, Bulls 1-8.")


def test_no_headline_before_the_end():
    g = game("nba", "Bulls", 50, "Heat", 48)
    g["state"] = "in"
    assert headline(g) is None


def test_translate_stats():
    assert translate_stat("24/29, 271 YDS, 3 TD") == "24/29, 271 yardas, 3 TD"
    assert translate_stat("19 CAR, 100 YDS, 1 TD") == "19 acarreos, 100 yardas, 1 TD"
    assert translate_stat("2-4, HR, 2 RBI, 2 R, SB, K") == "2 de 4, 1 jonrón, 2 impulsadas, 2 carreras, 1 base robada, 1 ponche"
    assert translate_stat("6.0 IP, 0 ER, 3 H, 10 K, 0 BB") == "6.0 entradas, 0 carreras limpias, 3 hits, 10 ponches, 0 bases por bolas"
