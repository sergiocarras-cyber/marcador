"""Catálogo de fuentes: qué ligas se ingestan, de dónde y desde cuándo."""
from dataclasses import dataclass
from datetime import date

ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_STANDINGS = "https://site.api.espn.com/apis/v2/sports"


@dataclass(frozen=True)
class League:
    key: str            # identificador estable en el lakehouse, p. ej. "esp.1"
    sport: str          # futbol | nba | nfl | mlb
    path: str           # ruta en la API de ESPN
    name: str           # nombre para mostrar
    season_start: date  # desde dónde hacer backfill
    season_end: date | None = None
    has_standings: bool = True


SEASON = 2026

LEAGUES: list[League] = [
    League("esp.1", "futbol", "soccer/esp.1", "LaLiga", date(2026, 8, 1)),
    League("esp.2", "futbol", "soccer/esp.2", "Segunda", date(2026, 8, 1)),
    League("eng.1", "futbol", "soccer/eng.1", "Premier League", date(2026, 8, 1)),
    League("ita.1", "futbol", "soccer/ita.1", "Serie A", date(2026, 8, 1)),
    League("ger.1", "futbol", "soccer/ger.1", "Bundesliga", date(2026, 8, 1)),
    League("fra.1", "futbol", "soccer/fra.1", "Ligue 1", date(2026, 8, 1)),
    League("uefa.champions", "futbol", "soccer/uefa.champions", "Champions League", date(2026, 9, 1), has_standings=False),
    League("uefa.europa", "futbol", "soccer/uefa.europa", "Europa League", date(2026, 9, 1), has_standings=False),
    League("uefa.europa.conf", "futbol", "soccer/uefa.europa.conf", "Conference League", date(2026, 9, 1), has_standings=False),
    League("esp.copa_del_rey", "futbol", "soccer/esp.copa_del_rey", "Copa del Rey", date(2026, 10, 1), has_standings=False),
    League("nba", "nba", "basketball/nba", "NBA", date(2026, 10, 1)),
    League("nfl", "nfl", "football/nfl", "NFL", date(2026, 9, 1)),
    League("mlb", "mlb", "baseball/mlb", "MLB", date(2026, 3, 20), date(2026, 11, 10)),
]

F1_PATH = "racing/f1"

BY_KEY = {lg.key: lg for lg in LEAGUES}
