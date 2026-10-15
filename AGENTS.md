# Agent instructions: CCode

## Scope and reality

This is a local patch workspace for a packaged Electron install of the upstream agentic workspace (3.14.5) on Fedora, rebranded **CCode**. It is not the complete upstream TypeScript source tree. The app now runs as a **standalone variant without an account**: no login gate, no account/cloud services, and its own data namespace. Read README.md and docs/ARCHITECTURE.md before changes. User instructions take precedence.

- Edit canonical source under `src/` and `services/`, not the generated minified bundle in `app/resources/app.asar`.
- Use `scripts/build.py` to reproduce the UI/IPC modifications from the pinned original baseline. Preserve the upstream anchor assertions and checksum verification.
- Standalone patches live in `src/local_only/`: `rebrand.py` owns the product identity and rewrites every upstream token first, before any other module matches its anchors; `storage.py` owns data/config/profile/database namespacing and the env bootstrap; `cloud.py` owns account/cloud removal and the local answers for channels whose Z.ai owner is gone; `plugins.py` patches the bundled plugin payload from its own pristine baseline; `runtime_tuning.py` sets the cheap default reasoning level and the Harness discipline lines; `token_savers.py` owns the Token savers Settings and agent integration; `branding.py` owns only the CCode mark. All run after the renderer patch in `scripts/build.py`, with `rebrand.py` first and `branding.py` last.
- Branding is data-driven from `ccode-logo.svg` (mark paths, data URIs, rasterized icons in `assets/icons/`). Change the artwork, run `make icons`, then `make build`. Never hand-edit the generated PNGs or re-draw the mark inside a patch.
- `rebrand.py` is the only tracked place the upstream spelling is written: it rewrites every product token in one pass—environment variables, IPC channels, the `ccode://` scheme, the `.ccode` storage layout, plugin ids and directories, process titles, and identifiers—and `assert_clean()` fails the build on any survivor. Absolute `http(s)://` URLs are network contracts, not labels: they stay verbatim (the marketplace icon CDN and the electron-release URLs only answer to their real spelling), and `leftover()` ignores them. `branding.guard()` fails the build when an upstream mark path or viewBox survives. Keep both strict instead of widening their exception lists. `rebrand.previous()`/`PREVIOUS_*` expose the old spelling for migration code.
- Repositori: repo ini adalah workspace patch di `0xMinomus/CCode-archive` (remote `origin`). Fork rilisnya `0xMinomus/CCode` (fork dari `zai-org/ZCode`, Apache-2.0): `main` mengikuti upstream, `ccode` untuk hasil porting, `ccode-workspace` snapshot workspace ini. Push pekerjaan harian tetap ke `origin`; jangan menulis ke fork kecuali memang memindahkan hasil porting. Remote lokal: `origin` = workspace (`CCode-archive`, privat), `fork` = `0xMinomus/CCode` (fork publik; `ccode-workspace` adalah default branch-nya sehingga README kita yang tampil di halaman depan, sedangkan `main` tetap mengikuti upstream), `upstream` = `zai-org/ZCode` (belum di-fetch; sekitar 93 MB, jadi ambil hanya saat memang akan rebase).
- The packaged agent backend (`app/resources/glm/ccode.cjs`) is patched too. Keep it pinned to `baselines/upstream-3.14.5-original-agent.cjs` via `agent_baseline_sha256` in project.json; the bundled plugin payload (`glm/packages`) is patched from `baselines/upstream-3.14.5-original-plugins/`, pinned by `plugins_baseline_sha256`. Never edit the deployed copies directly; both baselines and the ASAR baseline are the only untouched copies of the upstream spelling.
- Do not present the MCP bridge as a native Linux port. Computer Use currently uses `fedora-desktop`/screen-mcp; model quality is separate from backend performance.
- Use existing upstream React/UI components where possible. Current bundled symbols are pinned to this version; consult ARCHITECTURE.md before using them.

## Kebiasaan kerja wajib

- Selalu buat dan perbarui TODO untuk setiap pekerjaan, termasuk pekerjaan kecil; tandai selesai berdasarkan hasil yang benar-benar diverifikasi.
- Gunakan subagent hanya bila memang diperlukan untuk bagian independen atau investigasi yang luas. Kerjakan langsung bila perubahan kecil dan terlokalisasi; jangan membuat delegasi hanya untuk formalitas.
- Untuk setiap pekerjaan yang mengubah file project, selalu jalankan `make build` dan pemeriksaan yang relevan sebelum menyerahkan hasil. Build gagal berarti jangan apply atau publish perubahan yang belum lolos.
- Selalu perbarui file Markdown yang terkait dalam pekerjaan yang sama, termasuk `docs/CHANGELOG.md`; jalankan `make obsidian` setelahnya.
- Setelah perubahan selesai dan terverifikasi, otomatis commit file yang termasuk pekerjaan tersebut dan push branch aktif ke remote yang sudah dikonfigurasi, tanpa menunggu pengingat. Jangan ikutkan perubahan pengguna yang tidak terkait, secret, atau artefak ignored; jangan force-push. Bila push ditolak atau autentikasi gagal, pertahankan commit lokal dan laporkan penyebabnya.

## Dokumentasi wajib

Setiap perubahan perilaku, arsitektur, operasi, atau daftar resource harus langsung diikuti pembaruan file .md yang bersangkutan pada commit/kerja yang sama — tanpa diminta ulang: `docs/CHANGELOG.md` (selalu), lalu `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/OPERATIONS.md`, `docs/MODELS.md` bila area itu tersentuh, `README.md` bila daftar fitur/struktur berubah, dan `AGENTS.md` bila aturan kerja berubah. Tutup dengan `make obsidian` (dan `make obsidian-check` bila ragu). Jangan menyerahkan pekerjaan dengan dokumentasi tertinggal.

## Build and validation

1. Make the smallest coherent source change.
2. Always run `make build` for project file changes and `make test` for relevant checks. `make test` covers syntax of source and patched assets plus the unit tests, including patch-helper regressions.
3. Inspect a rendered UI when changing layout. Do not send model prompts merely to inspect UI.
4. Smoke-test the standalone variant in an isolated root: `CCODE_STANDALONE_ROOT=<dir> scripts/run.sh --remote-debugging-port=<port>`. Expected result is an open workspace with no login screen, no `Unknown channel`/`No handler registered` lines, and no runtime `ReferenceError`/`TypeError`. Clean that root afterwards.
5. Never export the namespace env in a persistent shell. `scripts/data_backup.py` and `scripts/install_local.py` refuse to run when they see `CCODE_STANDALONE_ROOT` on another process, so a leaked variable looks like a running app. Unset it before apply/install/backup.
6. Close the app before `make apply`; do not forcibly kill an active task. `apply` verifies the staged manifest, rolls back the promoted resources on failure, keeps the previous set in `runtime/backups`, and then renames the deployed AppDir identity (binary `app/ccode`, launcher `app/ccode.desktop`, `.DirIcon`/`app/ccode.png`, `AppRun`, hicolor icons).
7. `make install` changes the user's standalone launcher, icon theme entries, MCP config inside the namespace, the standalone systemd user timer, and the model-sync path unit that fills 9Router models when the app writes the provider config. It also migrates the pre-rebrand namespace (`rebrand.PREVIOUS_NAMESPACE` → `~/.local/share/ccode`) and retires the old launcher and units, with backups under `<namespace>/integration-backups`. Use it for user-authorized deployment/migration, not automatically for every source edit. Separately, `make migrate` (`scripts/migrate_identity.py`) moves the stored paths and rewrites the token inside an existing namespace with the app closed; run it after `make apply` when upgrading a pre-rebrand install.
8. Apply and install both refuse while the app is running; `scripts/data_backup.py` refuses when the namespace looks in use. Do not point a smoke run at the real namespace root.

There is no need to reinstall dependencies or run vendor setup scripts for routine modifications. No root audio permissions or input-device permission changes are needed for the existing portal backend.

## Preserve behavior

- Never defeat the desktop mouse-takeover/STOPPED guard. Never force input after an access refusal.
- Screenshot click coordinates are view pixels; the backend maps them. Avoid extra OCR/diagnostic loops in normal desktop tasks.
- Reasoning levels must come from supported metadata or verified provider behavior. Do not invent Low/Max controls that only alter labels. Preserve manual overrides and fixed combo presets.
- Keep the standalone variant account-free: do not re-register Z.ai account/cloud services, do not reintroduce the login gate, and do not add automatic imports of the old installation's tasks, credentials, provider config, or MCP config. Local answers for removed channels (update state, telemetry ack, community check) are intentional, not stubs to be replaced with fake data.
- Keep local IPC handlers working: external links, task notifications, Docker/WSL/SSH inspection, and the local desktop-command path. Removing a cloud owner must not remove a local handler.
- Keep the storage bootstrap and unique-anchor assertions intact. If an upstream anchor stops matching, the build must fail instead of silently skipping a patch.

## Release scope (locked)

- Release order: Linux x64 first, then Windows x64. The concrete work list lives in `linuxrelease.md`.
- **Voice is removed entirely** — code, UI, resources, and artifacts, on Linux *and* Windows (Windows must stay light).
- n8n stays available but is installed by the user from the Plugin Marketplace: zip hosted as a release asset on the public fork `0xMinomus/CCode`, `n8n-mcp` dependencies inside that zip.
- Computer Use registers itself as the `linux-desktop` MCP server; the app seeds the entry, so packages work without `make install`.
- Never drop a shipped feature without the owner's approval; state unverified limits in the release notes.

## Data and handoff

- Standalone data lives in `~/.local/share/ccode` (`data/`, `electron/`, `model-sync/`). Never point verification runs at the pre-rebrand data directories (`rebrand.PREVIOUS_APPDATA`/`PREVIOUS_APPCONFIG`) and never copy them into the repo.
- Backups: `python3 scripts/data_backup.py backup --root ~/.local/share/ccode` (app closed), `verify <snapshot>`, `restore <snapshot>`. Snapshots hold user tasks and provider keys; keep them private.
- Do not copy credentials, portal tokens, user tasks, or live provider configs into tracked source. `runtime/install-backups`, model-sync backups, and namespace snapshots may contain secrets; keep them private and ignored.
- Do not commit `app/`, `baselines/`, models, virtualenvs, vendor Git metadata, runtime captures, or user configuration backups. Do not publish the bundled application as if the project had one universal license.
- Update docs/CHANGELOG.md and the affected architecture/operation notes when behavior changes.
- Keep compatibility symlinks until old launchers/process references are proven unused. Avoid editing unrelated home-directory settings.
- Obsidian: the project folder itself is a vault when `.obsidian/` exists (then `make obsidian` only refreshes the generated `Index.md`); otherwise `make obsidian` mirrors `README.md`, `AGENTS.md`, and `docs/` into the vault from `OBSIDIAN_VAULT_PATH`, the omp Obsidian MCP entry, or `--vault`, adding `tags`/`source` frontmatter. `make obsidian-check` reports drift without writing. `.obsidian/` is ignored by git; the mirror copy is generated, never the source of truth.
