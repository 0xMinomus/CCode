.PHONY: build test check apply run install dry-run models icons obsidian obsidian-check migrate
# Standalone namespace the model sync reads and writes; override with
# `make models STANDALONE_ROOT=/path` when testing against another root.
STANDALONE_ROOT ?= $(HOME)/.local/share/ccode
build:
	python3 scripts/build.py
test check:
	python3 scripts/check.py
icons:
	python3 scripts/make_icons.py
apply:
	python3 scripts/apply_build.py
run:
	bash scripts/run.sh
install:
	python3 scripts/install_local.py
migrate:
	python3 scripts/migrate_identity.py
dry-run:
	python3 scripts/install_local.py --dry-run
models:
	CCODE_STANDALONE_ROOT=$(STANDALONE_ROOT) CCODE_MODEL_SYNC_CONFIG=$(STANDALONE_ROOT)/data/.ccode/v2/provider_config.json CCODE_MODEL_SYNC_STATE=$(STANDALONE_ROOT)/model-sync python3 services/model-sync/sync.py --discover --bootstrap
obsidian:
	python3 scripts/export_obsidian.py
obsidian-check:
	python3 scripts/export_obsidian.py --check
