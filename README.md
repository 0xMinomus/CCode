<div align="center">

<img src="ccode-logo.svg" alt="CCode" width="150">

# CCode

**A no-account, local-first fork of [ZCode](https://github.com/zai-org/ZCode).**
Chat with coding agents, drive your desktop, and keep every byte of data on your own machine.

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Fork of ZCode](https://img.shields.io/badge/fork-zai--org%2FZCode-6f42c1.svg)](https://github.com/zai-org/ZCode)
[![No account required](https://img.shields.io/badge/account-not%20required-success.svg)](#why-ccode-exists)
[![Status: pre-release](https://img.shields.io/badge/status-pre--release-orange.svg)](releaseplan.md)

</div>

---

## Why CCode exists

CCode is a fork of **CCode**, the agentic coding workspace by Z.AI, rebuilt around three ideas:

1. **No account, ever.** There is no sign-in screen, no account service, no plan or subscription surface. The app opens
   straight into a workspace and talks only to the model providers *you* configure.
2. **Your machine, your data.** Everything, including tasks, sessions, provider keys, activity history, and token saver settings,
   lives in a dedicated namespace (`~/.local/share/ccode`). CCode never reads or writes another installation's data
   and never imports anything behind your back.
3. **Local capabilities first.** Desktop automation over MCP and a local activity dashboard run on your hardware,
   with no round-trip through a vendor service.

CCode is an independent, unaffiliated fork. Upstream attribution, license terms, and the full list of modifications
are recorded in [NOTICE.md](NOTICE.md).

## Highlights

| | |
|---|---|
| **Zero-account startup** | No login gate, no cloud handshake, no plan prompts. Launch it and work. |
| **Bring your own provider** | Any OpenAI-, Anthropic-, or Responses-compatible endpoint, plus a ready-made template for a local 9Router-compatible gateway. Keys are stored in your own config. |
| **Local task engine** | Conversations, tasks, and agent sessions persist in a local SQLite database that you can back up, inspect, or delete. |
| **Activity dashboard** | Prompt metrics, streaks, and a January–December heatmap for any year, computed read-only from your local session database. |
| **Token savers** | Optional RTK shell-command rewrites plus Caveman and Ponytail agent-instruction modes. The chart reports RTK's estimated shell-output tokens saved, not provider-billed model tokens. |
| **Bundled default skills** | 32 agent skills ship inside the app — antislop, GSAP, UI design, and engineering workflow — listed as Default in Settings → Skills without installing a plugin. |
| **Built-in subagents** | Twelve engineering roles cover architecture, backend/frontend, UI/UX, databases, debugging, QA, review, security, and DevOps. Each has its own enable switch and inherits the session model by default; user-scoped plugin subagents can also be toggled individually. |
| **Built-in slash commands** | Twelve defaults for PRDs, design/spec documents, planning, implementation, debugging, explanation, testing, and reviews. Settings → Commands groups them by purpose; scanner and command runner use the namespaced command directory without replacing user edits. |
| **MCP catalog** | Context7 and Codegraph ship preinstalled. LSP and Ripgrep are installable from native server rows without an “Optional” badge; account-bound `image_search` is excluded. |
| **n8n plugin** | Install n8n from Plugin Marketplace to download its pinned MCP server and all 15 n8n skills. Configure your instance URL and API key in native plugin settings; enable or disable the server and skills together. |
| **Computer Use over MCP** | A Linux desktop backend (`screen-mcp`) exposes screenshot, text-first screen reading, element-based clicks, waiting, and verification tools — with an explicit pointer-takeover guard that stops an agent the moment you take the mouse. |
| **Reasoning metadata that is real** | Reasoning levels come from provider metadata or verified behavior — no cosmetic Low/Max toggles. |
| **Own identity** | CCode name, mark, launcher, icons, and onboarding, generated from a single brand source ([`ccode-logo.svg`](ccode-logo.svg)). |
| **Apache-2.0 project code** | CCode modifications retain upstream attribution ([LICENSE](LICENSE), [NOTICE.md](NOTICE.md)). Bundled dependencies and skills have separate terms and unresolved rights noted in [third-party documentation](docs/THIRD_PARTY.md). |

## CCode vs ZCode

Side by side, at a glance:

| Aspect | ZCode (upstream) | CCode |
|---|---|---|
| **Account & sign-in** | Sign-in to a Z.ai account; account services drive plans, usage, and cloud features | **No account at all** — the login gate is gone and account/cloud/plan services are not registered |
| **Data location** | Vendor data directories (`~/.zcode`, `~/.config/ZCode`) | Dedicated namespace (`~/.local/share/ccode`); other installations are never read or written |
| **Providers** | Built-in Zhipu family (Z.ai, BigModel, coding plans) plus BYOK | Zhipu/plan family removed; BYOK for any compatible endpoint, plus a local 9Router template |
| **Model catalog** | Refreshed from the account endpoint at runtime | Account-driven refresh disabled; the catalog is local and pinned |
| **Usage analytics** | Cloud usage stats | **Activity**: prompt counts, streaks, and a per-year heatmap computed locally, laid out like the original usage page |
| **Computer Use** | Platform helper apps with their own permission flow | Linux desktop backend over MCP: text-first screen reading, element-based clicks, pointer-takeover guard, portal capture |
| **Auto-update** | Polls the vendor update feed | Update channel removed; a release never overwrites your build |
| **Startup network footprint** | Account and business-config calls, catalog refresh, update checks | None of the above; only the provider endpoints you configure, only when you use them |
| **Performance & resource use** | Account/cloud round-trips during startup and for stats | No account/cloud/update round-trips; Activity is read-only local SQLite. The Computer Use MCP defers model loading to the first observation (~60 MB less per idle session, measured), and an optional Chromium low-memory switch saves ~128 MB PSS when enabled (documented, off by default) |
| **Identity** | CCode branding and vendor endpoints | CCode branding end to end, with the `ccode://` scheme, `.ccode` layout, `CCODE_*` variables, and `ccode-*` IPC channels used consistently across the host and agent |
| **License** | Apache-2.0 — Copyright 2026 Z.AI Co., Ltd | Project code: Apache-2.0; bundled components retain separate terms |

<sub>Performance figures come from the project's reference workstation and are recorded in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); a reproducible head-to-head benchmark suite is on the roadmap.</sub>

## Requirements

- **Platform:** Linux x86-64 and Windows x64 are the supported targets. The Electron/Chromium runtime ships with the
  application, so no separate Node.js installation is needed to run it. macOS is not supported.
- **Source builds:** Python 3 and a checkout of this workspace; GNU Make on Linux, or `make build` plus
  `make pack-windows` with 7-Zip, ImageMagick, and NSIS on Windows. Regenerating the brand icons needs
  ImageMagick.
- **Optional capabilities:** On Linux, a desktop portal session with AT-SPI for Computer Use and `gtk-update-icon-cache`
  for launcher icons on GTK desktops. On Windows, Computer Use needs no extra packages: capture, UI Automation, and
  `SendInput` come from the OS.

## Linux downloads

Download the unsigned Linux x86-64 AppImage, `.deb`, or `.rpm` from the [1.0.0 Linux release](https://github.com/0xMinomus/CCode/releases/tag/v1.0.0%2Bupstream.3.14.5). Verify the download with the release's `SHA256SUMS` before running it.

The Linux build has been checked on the project's Fedora workstation, not clean installations of other distributions. Computer Use still needs compatible Python and system desktop libraries. See the release notes and [Linux verification record](linuxrelease.md) for exact limits. Windows ships as a separate release, below.

n8n is a separate [Marketplace plugin download](https://github.com/0xMinomus/CCode/releases/tag/n8n-plugin-v1.0.0), including its runtime and 15 skills. Voice is not shipped.

### Windows downloads

Download the unsigned Windows x64 installer or portable ZIP from the [1.0.0 Windows release](https://github.com/0xMinomus/CCode/releases/tag/v1.0.0-win-x64); verify `SHA256SUMS` first. The installer is per-user (no admin): it installs to `%LOCALAPPDATA%\Programs\CCode`, adds a Start Menu shortcut, registers the `ccode://` scheme and the model-sync scheduled tasks, and the uninstaller keeps `%LOCALAPPDATA%\CCode` unless you ask it to delete the data. Verification ran on Windows 11 x64 build 26200; Computer Use runs as the `windows-desktop` MCP server and cannot drive elevated windows (UIPI). See the [Windows verification record](windowsrelease.md) and the release notes for exact limits. The earlier M1 boot-test prerelease was withdrawn from GitHub once this release superseded it; its checksums stay recorded in that verification record.


## Build and run

```bash
git clone https://github.com/0xMinomus/CCode-archive.git
cd CCode-archive

make build      # stage the patched bundle in runtime/build (upstream baseline verified by SHA-256)
make test       # syntax checks for sources and patched assets, plus the unit test suite
make apply      # promote the staged build into app/ (close the app first)
make migrate    # move an existing pre-rebrand namespace and its stored paths to the CCode names
make install    # launcher, icon theme entries, model-sync units, and the CCode data namespace
make run        # launch
```

`make build` verifies the pinned upstream artifacts recorded in [`project.json`](project.json) before patching; a
mismatch fails the build instead of producing a half-patched application. Linux packages are available through
[GitHub Releases](https://github.com/0xMinomus/CCode/releases); the Windows installer remains deferred.

### Everyday commands

```bash
make models         # discover/refresh local gateway models (grouped per namespace)
make icons          # re-rasterize assets/icons/ from ccode-logo.svg
make obsidian       # mirror the docs into an Obsidian vault
make obsidian-check # report vault drift without writing
make dry-run        # show what the local integration would install
```

## Project layout

| Path | Contents |
|---|---|
| `src/renderer/` | UI sources: Computer Use settings, Activity and Token savers panels, and slash-command categories |
| `src/commands/` | Default slash-command prompts for documents, development, and quality checks |
| `src/skills/` | Default agent skills bundled into the app pack (`glm/packages/bundled-skills`) |
| `src/plugins/n8n/` | Marketplace plugin source: native manifest, self-contained MCP entrypoint, and all 15 n8n skills |
| `src/main/` | Electron main-process modules: Activity data, Token savers, Auto Detect, and default-command seeding |
| `src/local_only/` | Product patches: `rebrand` (identity and runtime contracts, runs first), `branding` (mark, runs last), storage namespacing, account/cloud removal, bundled plugin payload, default-command staging and grouping, built-in subagent catalog, agent runtime tuning, provider catalog, Token savers agent integration |
| `services/desktop/` | `screen-mcp` desktop backend and its fast profile |
| `services/mcp/` | Pinned default MCP packages and optional integration catalog |
| `services/model-sync/` | Gateway model discovery and reasoning-metadata sync |
| `scripts/` | Build, verification, apply, install, namespace migration (`migrate_identity.py`), backup/restore, icon generation, docs export |
| `assets/icons/` | Rasterized CCode icons committed for reproducible builds |
| `baselines/` | Pinned upstream artifacts, never edited: `upstream-3.14.5-original.asar`, `upstream-3.14.5-original-agent.cjs`, `upstream-3.14.5-original-plugins/` (checksums in `project.json`) |
| `ccode-logo.svg` | Single source of the CCode mark |
| `docs/` | Architecture, operations, development, models, and third-party notes (Indonesian) |
| `project.json` | Pinned upstream identities, checksums, and patched asset names |
| `releaseplan.md` | Release plan: source-fork route, license duties, packaging per platform |

## Repositories

| Repository | Contents |
|---|---|
| [**CCode**](https://github.com/0xMinomus/CCode) | The fork: `main` mirrors upstream, `ccode-workspace` (default branch) carries this project's docs and workspace, `ccode` will hold the ported source changes |
| [**CCode-archive**](https://github.com/0xMinomus/CCode-archive) | This patch workspace — current default home of development (private) |
| [**zai-org/ZCode**](https://github.com/zai-org/ZCode) | Upstream project, Apache-2.0 — Copyright 2026 Z.AI Co., Ltd |

<sub>Do not use the **Sync fork** / **Discard commits** button on the fork page: because the workspace branch has no
shared history with upstream, that button resets the branch and drops the workspace commits. Sync upstream locally
instead (`git fetch upstream && git rebase upstream/main` on `main`).</sub>

## Roadmap

- **Packaged releases** — signed AppImage, `.deb`/`.rpm`, portable tarball, and a Windows installer, so using CCode is
  a download instead of a build.
- **Source-based fork track**: the `ccode` branch ports the standalone, branding, provider, Activity, and
  Computer Use work into TypeScript on top of upstream, replacing binary patching.
- **Cross-platform**: Windows and macOS builds, including native desktop-automation backends.
- **Benchmarks** — a reproducible suite for cold start, idle memory, and disk footprint, published with each release.
- **More desktops** — verification across GNOME, KDE, and tiling compositors.

## Security

- **No telemetry surface.** Account, cloud, plan, telemetry, and remote-control services are not registered in the
  application; update checks against the vendor feed are disabled.
- **Credentials stay local.** Provider API keys live in your own configuration inside the CCode namespace. Nothing in
  this repository contains, imports, or transmits user credentials, task history, or provider configuration.
- **Reviews before release.** Every behavior change runs through `make test` (source syntax, patched-asset syntax, and
  the unit suite) plus an isolated-root smoke test before it reaches a build.
- **Reporting a vulnerability.** Please open a private report through the **Security** tab of this repository rather
  than a public issue, and include reproduction steps and the version you built.

## License

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE).

CCode is a fork of ZCode (Copyright 2026 Z.AI Co., Ltd); the modifications made here are released under the same
license, with attribution and a change summary in [NOTICE.md](NOTICE.md). CCode is **not affiliated with, sponsored by,
or endorsed by Z.AI or Zhipu**, and does not use their names or logos beyond describing the origin of the fork.

Third-party components keep their own terms — see [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
