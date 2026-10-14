# NOTICE

CCode is an independent fork of **ZCode** — <https://github.com/zai-org/ZCode> — Copyright 2026 Z.AI Co., Ltd,
licensed under the Apache License, Version 2.0 (see [LICENSE](LICENSE)).

## Attribution

- Upstream project: ZCode, <https://github.com/zai-org/ZCode> (Apache-2.0, Copyright 2026 Z.AI Co., Ltd).
- CCode modifications: Copyright 2026 0xMinomus and CCode contributors, released under the same license.

## Pinned upstream baseline

CCode tracks a specific upstream release. The identities and SHA-256 checksums of the artifacts this workspace
builds from are recorded in [`project.json`](project.json); the current baseline is ZCode **3.14.5**.

This repository is a patch workspace: it does not redistribute upstream source or binaries. Upstream artifacts are
obtained from the vendor release and verified against the pinned checksums before any build runs.

## Modifications

Every change relative to the pinned upstream build is recorded in [`docs/CHANGELOG.md`](docs/CHANGELOG.md). Summary:

- **Branding** — product name, mark/logo, window title, launcher, icon theme entries, and onboarding copy are CCode.
  Artwork is derived from [`ccode-logo.svg`](ccode-logo.svg).
- **Standalone runtime** — the application runs without a Z.ai account: the login gate is removed and account, cloud,
  plan, telemetry, and remote-control services are not registered in the host.
- **Data isolation** — CCode uses its own namespace (`~/.local/share/ccode`) and never reads or writes the ZCode data
  directories; no cross-installation import happens automatically.
- **Provider catalog** — the Zhipu account family (Z.ai, BigModel, coding plans) is removed; a local 9Router provider
  template is added, and the built-in catalog refresh from the account endpoint is disabled.
- **Local features** — Activity dashboard computed from the local session database, bilingual (Indonesian–English)
  local voice input, and a Linux desktop Computer Use backend exposed over MCP.
- **Bundled default skills** — 32 agent skills (antislop, GSAP, UI design, and engineering workflow) ship inside the
  app resources at `glm/packages/bundled-skills/skills`. Sources, provenance, and per-group license status are listed
  in [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md); several of them declare no license upstream.
- **Compatibility identifiers intentionally retained** — `ZCODE_*` environment variables, `zcode-*` IPC channels, the
  `zcode://` URL scheme, the `.zcode` storage layout, and the cross-process protocol strings are unchanged so that the
  packaged host and agent backend keep working.

Source files added or rewritten by CCode live under `src/`, `services/`, `scripts/`, `tests/`, and `assets/`.

## Not affiliated

CCode is not affiliated with, sponsored by, or endorsed by Z.AI or Zhipu. "ZCode" and any Z.ai or Zhipu names and logos
are the property of their respective owners and are used here only to describe the origin of this fork, as permitted
for that purpose by Apache-2.0 §6.

## Third-party components

Third-party components keep their own terms. See [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md) for the full list,
including the Electron/Chromium notices shipped inside the application directory, `screen-mcp` (FSL-1.1-ALv2),
the Whisper voice model, and the bundled default skills (MIT, Apache-2.0, and undeclared).
