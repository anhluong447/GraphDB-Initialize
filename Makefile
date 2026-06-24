.PHONY: up down init sync status hook viz

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

community:
	python initialize_graph.py --community

semantics:
	python initialize_graph.py --semantics

hook:
	python initialize_graph.py --install-hooks

viz:
	python initialize_graph.py --viz
