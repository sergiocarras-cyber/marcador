from serving.export import pick, reasons, MIN_SCORE


def cand(score, league, home, away, start="2026-11-10T00:00:00Z"):
    return {"score": score, "reasons": [], "game": {
        "league_key": league, "start_time": start,
        "home": {"key": home, "name": home}, "away": {"key": away, "name": away}}}


def test_pick_orders_caps_league_and_skips_low_scores():
    cs = [cand(90, "nba", "a", "b"), cand(85, "nba", "c", "d"), cand(80, "nba", "e", "f"),
          cand(70, "esp.1", "g", "h"), cand(MIN_SCORE - 1, "eng.1", "i", "j")]
    chosen = pick(cs, limit=10, per_league=2)
    assert [c["score"] for c in chosen] == [90, 85, 70]


def test_pick_keeps_one_game_per_matchup():
    cs = [cand(80, "nba", "a", "b", "2026-11-11T00:00:00Z"), cand(80, "nba", "b", "a", "2026-11-10T00:00:00Z")]
    chosen = pick(cs, limit=10, per_league=5)
    assert len(chosen) == 1 and chosen[0]["game"]["start_time"] == "2026-11-10T00:00:00Z"


def test_reasons():
    flags = {"is_playoffs": False, "top_clash": True, "comeback": True, "overtime": False,
             "goal_fest": False, "tight_finish": True}
    g = {"sport": "futbol", "state": "post", "home": {"key": "h", "name": "Atlético", "score": 1},
         "away": {"key": "a", "name": "Barcelona", "score": 2}}
    assert reasons(flags, g, {}) == ["Duelo de líderes", "Remontada", "Final ajustado"]

    up = {**g, "state": "pre"}
    form = {"a": {"streak_outcome": "W", "streak_length": 5}}
    flags_up = {**flags, "top_clash": False, "comeback": False, "tight_finish": False}
    assert reasons(flags_up, up, form) == ["Barcelona: 5 victorias seguidas"]
