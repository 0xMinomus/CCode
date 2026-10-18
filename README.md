<div align="center">

<img src="ccode-logo.svg" alt="CCode" width="150">

# CCode

**A no-account, local-first fork of [ZCode](https://github.com/zai-org/ZCode).**
Chat with coding agents, drive your desktop, and keep every byte of data on your own machine.

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Release: 1.0.3](https://img.shields.io/badge/release-1.0.3-brightgreen.svg)](https://github.com/0xMinomus/CCode/releases)
[![Platforms: Linux x64, Windows x64](https://img.shields.io/badge/platforms-Linux%20x64%20%7C%20Windows%20x64-6f42c1.svg)](#requirements)
[![No account required](https://img.shields.io/badge/account-not%20required-success.svg)](#why-ccode-exists)

**[Download for Windows](https://github.com/0xMinomus/CCode/releases/tag/v1.0.3-win-x64)** ·
**[Download for Linux](https://github.com/0xMinomus/CCode/releases/tag/v1.0.3%2Bupstream.3.14.5)** ·
**[Build from source](#build-and-run)**

</div>

---

## Why CCode exists

CCode is a fork of **ZCode**, the agentic coding workspace by Z.AI, rebuilt around three ideas:

1. **No account, ever.** There is no sign-in screen, no account service, no plan or subscription surface. The app opens
   straight into a workspace and talks only to the model providers *you* configure.
2. **Your machine, your data.** Everything, including tasks, sessions, provider keys, activity history, and token saver settings,
   lives in a dedicated namespace (`~/.local/share/ccode` on Linux, `%LOCALAPPDATA%\CCode` on Windows). CCode never reads
   or writes another installation's data and never imports anything behind your back.
3. **Local capabilities first.** Desktop automation over MCP and a local activity dashboard run on your hardware,
   with no round-trip through a vendor service.

CCode is an independent, unaffiliated fork. Upstream attribution, license terms, and the full list of modifications
are recorded in [NOTICE.md](NOTICE.md).

## Features

### Models and providers

- **Bring your own key.** Any OpenAI-, Anthropic-, or Responses-compatible endpoint works. Add providers from the
  built-in template catalog or as a custom endpoint, and keep the API key in your own configuration.
- **Local 9Router gateway, ready to go.** A ready-made template points at `http://127.0.0.1:20128/v1`, and
  **Auto Detect** pulls the gateway's model list, groups wide namespaces into their own providers, and writes
  provider plus per-model rules in one click.
- **Reasoning levels that are real.** Level pickers come from provider metadata or verified gateway behavior.
  No cosmetic Low/Max control that only changes a label.
- **No Zhipu/plan family.** Account-bound provider families and the account-driven catalog refresh are gone;
  the catalog is local and pinned.

### Token savers

Optional, off by default, each with its own switch in **Settings → Token savers**:

- **RTK** rewrites supported shell commands before the approval path, so everyday commands cost fewer output tokens.
  A match keeps CCode's normal approval, an error stops execution instead of guessing. The chart underneath reports
  RTK's estimated shell-output tokens saved across projects, not provider-billed model tokens.
  Missing RTK can be installed directly from its Settings row: one click downloads a pinned official binary into CCode's namespace, verifies it, and enables the saver.
- **Caveman** applies a concise response style to agent instructions, in Lite, Full, or Ultra.
- **Ponytail** avoids unnecessary work while preserving correctness and safety, also in Lite, Full, or Ultra.

Level pickers stay disabled and dimmed while a saver is off, and every value survives a restart.

### Background startup

Windows and Linux can preload the workspace at login without showing a window. Opening CCode normally reveals the same instance. **Settings → General → Start CCode in the background at login** disables this default-on behavior when background memory use is unwanted. Linux login behavior is awaiting owner validation.


### Task output folders without a project

Work started outside a project stays in the conversation workspace, so the sidebar keeps its single
task list and no folder name appears while you work. The moment the task — or you — hands over a
file, CCode archives it into a private per-task folder (`~/CCodeProject/task-<date>-<time>-<id>`,
`%USERPROFILE%\CCodeProject` on Windows): files you attach in the composer land there too, and a
later task that regenerates the same file name never overwrites the earlier result. To find a
task's folder, open the task menu (⋯) and pick **Open in File Manager**. In the change summary,
right-click a changed or generated file for **Reveal in File Manager**, **Copy path**, and **Copy
relative path** — all three resolve to the archived copy first.

### Built-in subagents

Twelve engineering roles ship enabled and inherit the session model by default:

Engineering Generalist, Codebase Explorer, Technical Architect, Backend Developer, Frontend Developer,
UI/UX Designer, Database Engineer, Debugger & Performance Engineer, QA / Test Engineer, Code Reviewer,
Security Reviewer, and DevOps Engineer.

Each role has its own enable switch in **Settings → Subagents**. Disabled profiles disappear from the agent roster
and cannot be dispatched, including through a short name alias. User-scoped plugin agents can be toggled the same way.

### Bundled skills

Thirty-two skills ship inside the application and appear as **Default** in **Settings → Skills**, with no plugin
install needed. The set covers anti-slop writing and code quality, UI and interface craft, the GSAP animation suite,
and engineering workflow: bug diagnosis, investigation-first debugging, prototyping, refactoring, migrations,
test-driven development, verification, code review, pull-request writing, and more.

### Slash commands

Twelve defaults, grouped by purpose in **Settings → Commands**, and available in the composer's `/` picker:

| Group | Commands |
|---|---|
| Documents | `/prd`, `/design`, `/tech-spec`, `/task-plan`, `/test-plan`, `/adr` |
| Development | `/implement`, `/debug`, `/explain` |
| Quality | `/review`, `/test`, `/security-review` |

Commands expand to full prompts, accept `$ARGUMENTS`, and never overwrite a file you edited, deleted, or created yourself.

### MCP, ready out of the box

- **Context7** for current library documentation and **Codegraph** for local architecture, AST symbols, references,
  and search are preinstalled. First use does not run `npx` to download dependencies.
- **LSP** and **Ripgrep** appear as installable rows in the same native MCP list; after **Install** they become
  normal server rows with an on/off switch.
- Configuration lives in your namespace, seeding never overwrites servers you disabled or deleted, and the
  account-bound `image_search` MCP is not registered.

### Plugin Marketplace

Browse the official marketplace and install plugins from it, alongside the plugins that ship with the app.
Plugin enablement, skills, and MCP servers are managed together in **Settings → Plugins**.

### n8n, downloaded on demand

Install n8n from Plugin Marketplace to get a bundled MCP runtime plus fifteen n8n skills. Point it at your own
instance URL and API key in the plugin's native settings; the server and all its skills turn on and off as one
switch. Nothing n8n-related is bundled in the application itself.

### Activity dashboard

Prompt counts, current and longest streaks, and a January to December heatmap for any year with history.
Everything is computed read-only from your local session database, on your machine, as the replacement for the
vendor's cloud usage page.

### Computer Use over MCP

Drive your desktop from a chat through the bundled desktop server:

- **Linux** uses the `linux-desktop` backend: screenshot, text-first screen reading, element-based clicks,
  typing, scrolling, waiting, and verification, with capture over the desktop portal.
- **Windows** uses the `windows-desktop` backend: the same ten tools, implemented with .NET capture,
  UI Automation for text and elements, and `SendInput` for input. No extra packages to install.
- **You stay in control.** Continuously using the mouse while an action is pending cancels it with a
  `STOPPED` message and the agent yields to you. A pointer you parked somewhere is not treated as a takeover.
  `force` never fights the user.

The same server entry appears in **Settings → Computer Use** and **Settings → MCP Servers**: two views of one
state, so flipping either switch is enough.

### Your data, in one namespace

| Platform | Root |
|---|---|
| Linux | `~/.local/share/ccode` |
| Windows | `%LOCALAPPDATA%\CCode` |

Tasks, sessions, provider configuration, MCP config, plugin data, and the Electron profile all live under that
one root, and `CCODE_STANDALONE_ROOT` can move it for isolated testing. `scripts/data_backup.py` takes SQLite-aware
snapshots (`backup`, `verify`, `restore`) while the app is closed, and the uninstaller keeps your data unless you
ask it to delete it.

### Quiet by default

No account handshake, no business-config calls, no catalog refresh from a vendor endpoint, and no update feed. The
only network traffic is to the model providers and integrations you configure, when you use them. The vendor
auto-updater is removed, so a new release never overwrites your build.

### Packaged for both platforms

| | |
|---|---|
| **Linux x64** | AppImage, `.deb`, and `.rpm` builds, with a systemd user timer for model sync |
| **Windows x64** | Per-user NSIS installer (no admin) and a portable ZIP, with Start Menu shortcut, `ccode://` URL scheme, and Task Scheduler entries for model sync |

The Windows installer is per-user by design: it installs under `%LOCALAPPDATA%\Programs\CCode`, and both the setup
and the uninstaller refuse to run while CCode is open from the install directory.

### Own identity

CCode name, mark, launcher, icons, tray icon, and onboarding, all generated from a single brand source
([`ccode-logo.svg`](ccode-logo.svg)). The Windows executable, shortcut, uninstall entry, and URL scheme carry the
same identity.

## CCode vs ZCode

Side by side, at a glance:

| Aspect | ZCode (upstream) | CCode |
|---|---|---|
| **Account & sign-in** | Sign-in to a Z.ai account; account services drive plans, usage, and cloud features | **No account at all**: the login gate is gone and account/cloud/plan services are not registered |
| **Data location** | Vendor data directories (`~/.zcode`, `~/.config/ZCode`) | Dedicated namespace (`~/.local/share/ccode`, `%LOCALAPPDATA%\CCode`); other installations are never read or written |
| **Providers** | Built-in Zhipu family (Z.ai, BigModel, coding plans) plus BYOK | Zhipu/plan family removed; BYOK for any compatible endpoint, plus a local 9Router template |
| **Model catalog** | Refreshed from the account endpoint at runtime | Account-driven refresh disabled; the catalog is local and pinned |
| **Usage analytics** | Cloud usage stats | **Activity**: prompt counts, streaks, and a per-year heatmap computed locally, laid out like the original usage page |
| **Computer Use** | Platform helper apps with their own permission flow | Desktop backends over MCP: `linux-desktop` (portal capture) and `windows-desktop` (.NET capture, UI Automation, SendInput), both with the pointer-takeover guard |
| **Auto-update** | Polls the vendor update feed | Update channel removed; a release never overwrites your build |
| **Startup network footprint** | Account and business-config calls, catalog refresh, update checks | None of the above; only the provider endpoints you configure, only when you use them |
| **Performance & resource use** | Account/cloud round-trips during startup and for stats | No account/cloud/update round-trips; Activity is read-only local SQLite. The Computer Use MCP defers model loading to the first observation (~60 MB less per idle session, measured), and an optional Chromium low-memory switch saves ~128 MB PSS when enabled (documented, off by default) |
| **Identity** | CCode branding and vendor endpoints | CCode branding end to end, with the `ccode://` scheme, `.ccode` layout, `CCODE_*` variables, and `ccode-*` IPC channels used consistently across the host and agent |
| **License** | Apache-2.0, Copyright 2026 Z.AI Co., Ltd | Project code: Apache-2.0; bundled components retain separate terms |

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

## Downloads

All builds are unsigned. Verify the download against the release's `SHA256SUMS` before running it.

### Windows x64

[**CCode 1.0.3 for Windows**](https://github.com/0xMinomus/CCode/releases/tag/v1.0.3-win-x64)

| File | What it is |
|---|---|
| `CCode-1.0.3-win-x64.exe` | Per-user installer, no administrator needed. Start Menu shortcut, `ccode://` scheme, and model-sync tasks included. |
| `CCode-1.0.3-win-x64.zip` | Portable build. Extract it and run `app\CCode.exe`, or use `CCode.ps1 -Root` for an isolated test namespace. |

### Linux x64

[**CCode 1.0.3 for Linux**](https://github.com/0xMinomus/CCode/releases/tag/v1.0.3%2Bupstream.3.14.5)

AppImage, `.deb`, and `.rpm` builds. The Linux packages were checked on the project's Fedora workstation rather than
clean installations of other distributions; the [Linux verification record](linuxrelease.md) has the details.
Computer Use additionally needs compatible Python and system desktop libraries.

### Optional plugin

n8n ships as a separate [Marketplace plugin download](https://github.com/0xMinomus/CCode/releases/tag/n8n-plugin-v1.0.0)
with its runtime and fifteen skills; or install it from inside the app's Plugin Marketplace.
Voice is not shipped on any platform.

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

On Windows the same flow runs with `python3` and `make` from an MSYS2 shell, and the release artifacts are built with
`make pack-windows` (portable ZIP plus per-user NSIS installer, using 7-Zip, ImageMagick, and NSIS).

`make build` verifies the pinned upstream artifacts recorded in [`project.json`](project.json) before patching; a
mismatch fails the build instead of producing a half-patched application. Both packaged platforms are published on
[GitHub Releases](https://github.com/0xMinomus/CCode/releases).

### Everyday commands

```bash
make models         # discover/refresh local gateway models (grouped per namespace)
make icons          # re-rasterize assets/ from ccode-logo.svg (PNG set plus the Windows .ico)
make obsidian       # mirror the docs into an Obsidian vault
make obsidian-check # report vault drift without writing
make dry-run        # show what the local integration would install
make pack-linux     # AppImage, deb, and rpm from the applied AppDir
make pack-windows   # portable ZIP and per-user installer for Windows x64
```

## Project layout

| Path | Contents |
|---|---|
| `src/renderer/` | UI sources: Computer Use settings (Linux and Windows panels), Activity and Token savers panels, and slash-command categories |
| `src/commands/` | Default slash-command prompts for documents, development, and quality checks |
| `src/skills/` | Default agent skills bundled into the app pack (`glm/packages/bundled-skills`) |
| `src/plugins/n8n/` | Marketplace plugin source: native manifest, self-contained MCP entrypoint, and all 15 n8n skills |
| `src/main/` | Electron main-process modules: Activity data, Token savers, Auto Detect, model-sync runtime (Windows), and default-command seeding |
| `src/local_only/` | Product patches: `rebrand` (identity and runtime contracts, runs first), `branding` (mark, runs last), storage namespacing, account/cloud removal, bundled plugin payload, default-command staging and grouping, built-in subagent catalog, agent runtime tuning, provider catalog, Token savers agent integration |
| `services/desktop/` | Linux `screen-mcp` desktop backend and its fast profile |
| `services/desktop-win/` | Windows Computer Use backend (Node server plus one PowerShell helper) |
| `services/mcp/` | Pinned default MCP packages and the optional integration catalog |
| `services/model-sync/` | Gateway model discovery and reasoning-metadata sync (Python implementation used on Linux) |
| `scripts/` | Build, verification, apply, install, packaging (Linux and Windows), namespace migration, backup/restore, icon generation, docs export |
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
| [**CCode-archive**](https://github.com/0xMinomus/CCode-archive) | This patch workspace: the current default home of development (private) |
| [**zai-org/ZCode**](https://github.com/zai-org/ZCode) | Upstream project, Apache-2.0, Copyright 2026 Z.AI Co., Ltd |

<sub>Do not use the **Sync fork** / **Discard commits** button on the fork page: because the workspace branch has no
shared history with upstream, that button resets the branch and drops the workspace commits. Sync upstream locally
instead (`git fetch upstream && git rebase upstream/main` on `main`).</sub>

## Roadmap

- **Code signing and update policy** for the packaged releases (both platforms ship unsigned today, and there is no
  auto-update by design).
- **Source-based fork track**: the `ccode` branch ports the standalone, branding, provider, Activity, and
  Computer Use work into TypeScript on top of upstream, replacing binary patching.
- **macOS** support, including a native desktop-automation backend.
- **Benchmarks**: a reproducible suite for cold start, idle memory, and disk footprint, published with each release.
- **Coverage**: verification across more Linux desktops (GNOME, KDE, tiling compositors) and multi-monitor,
  mixed-DPI Windows setups.

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

Licensed under the **Apache License 2.0**, see [LICENSE](LICENSE).

CCode is a fork of ZCode (Copyright 2026 Z.AI Co., Ltd); the modifications made here are released under the same
license, with attribution and a change summary in [NOTICE.md](NOTICE.md). CCode is **not affiliated with, sponsored by,
or endorsed by Z.AI or Zhipu**, and does not use their names or logos beyond describing the origin of the fork.

Third-party components keep their own terms, see [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
