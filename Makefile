# Pipeline: ingesta → transformación (dbt) → capa de servicio (JSON estático) → app
export DBT_PROFILES_DIR := transform
export DBT_TARGET_PATH  := data/dbt/target
export DBT_LOG_PATH     := data/dbt/logs
DBT := uv run dbt --no-use-colors
DBT_ARGS := --project-dir transform

.PHONY: setup backfill ingest transform serve test pipeline app clean

setup:            ## Instala dependencias
	uv sync

backfill:         ## Descarga la temporada completa (solo la primera vez)
	uv run python -m ingestion.extract backfill
	uv run python -m ingestion.extract standings
	uv run python -m ingestion.extract f1

ingest:           ## Ingesta incremental: últimos días, calendario, clasificaciones y F1
	uv run python -m ingestion.extract all

transform:        ## Construye silver y gold y pasa los tests de calidad
	$(DBT) seed $(DBT_ARGS) -q
	$(DBT) build $(DBT_ARGS)

serve:            ## Exporta la capa gold a JSON estático para la app
	uv run python -m serving.export

test:             ## Tests unitarios de Python
	uv run pytest -q

pipeline: ingest transform serve

app:              ## Sirve la app en http://localhost:8765
	cd app && python3 -m http.server 8765

clean:
	rm -rf data/warehouse.duckdb data/dbt app/data
