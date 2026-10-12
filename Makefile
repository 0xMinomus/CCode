.PHONY: build test check apply run install dry-run obsidian obsidian-check
build:
	python3 scripts/build.py
test check:
	python3 scripts/check.py
apply:
	python3 scripts/apply_build.py
run:
	bash scripts/run.sh
install:
	python3 scripts/install_local.py
dry-run:
	python3 scripts/install_local.py --dry-run
obsidian:
	python3 scripts/export_obsidian.py
obsidian-check:
	python3 scripts/export_obsidian.py --check
