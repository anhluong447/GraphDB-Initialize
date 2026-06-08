.PHONY: up down init sync status

up:
	docker compose up -d

down:
	docker compose down

init:
	python initialize_graph.py

force-init:
	python initialize_graph.py --force-init

sync:
	python initialize_graph.py --sync

status:
	python initialize_graph.py --status

enrich:
	python initialize_graph.py --enrich
