.PHONY: build test check apply run install dry-run models obsidian obsidian-check
# Standalone namespace the model sync reads and writes; override with
# `make models STANDALONE_ROOT=/path` when testing against another root.
STANDALONE_ROOT ?= $(HOME)/.local/share/zcode-on-steroids
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
models:
	ZCODE_STANDALONE_ROOT=$(STANDALONE_ROOT) ZCODE_MODEL_SYNC_CONFIG=$(STANDALONE_ROOT)/data/.zcode/v2/provider_config.json ZCODE_MODEL_SYNC_STATE=$(STANDALONE_ROOT)/model-sync python3 services/model-sync/sync.py --discover --bootstrap
obsidian:
	python3 scripts/export_obsidian.py
obsidian-check:
	python3 scripts/export_obsidian.py --check
