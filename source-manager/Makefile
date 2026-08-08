.PHONY: init test publish docker-build docker-run cron

init:
	uv run python -m ponyo_source_manager.core.initdb --reset
	uv run python -m ponyo_source_manager.discovery.import_sources --ponyo ../subscription/ponyo.json --health ../subscription/source-health-final.json --namemap ../subscription/source-name-map.json --batch bootstrap

test:
	uv run python -m ponyo_source_manager.scheduler --phase deep

publish:
	uv run python -m ponyo_source_manager.publishing.release

docker-build:
	docker compose build

docker-run:
	docker compose up -d

cron:
	uv run python -m ponyo_source_manager.scheduler --phase crontab
