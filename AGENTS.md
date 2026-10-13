# Agent instructions: ZCode on Steroids

## Scope and reality

This is a local patch workspace for a packaged Electron ZCode 3.14.5 installation on Fedora. It is not the complete upstream TypeScript source tree. The app now runs as a **standalone variant without a ZCode account**: no login gate, no account/cloud services, and its own data namespace. Read README.md and docs/ARCHITECTURE.md before changes. User instructions take precedence.

- Edit canonical source under `src/` and `services/`, not the generated minified bundle in `app/resources/app.asar`.
- Use `scripts/build.py` to reproduce the UI/IPC modifications from the pinned original baseline. Preserve the upstream anchor assertions and checksum verification.
- Standalone patches live in `src/local_only/`: `storage.py` owns data/config/profile/database namespacing and the env bootstrap; `cloud.py` owns account/cloud removal and the local answers for channels whose Z.ai owner is gone. Both run after the renderer patch in `scripts/build.py`.
- The packaged agent backend (`app/resources/glm/zcode.cjs`) is patched too. Keep it pinned to `baselines/zcode-3.14.5-original-agent.cjs` via `agent_baseline_sha256` in project.json; never edit the deployed copy directly.
- Do not present the MCP bridge as a native Linux port. Computer Use currently uses `fedora-desktop`/screen-mcp; model quality is separate from backend performance.
- Use existing ZCode React/UI components where possible. Current bundled symbols are pinned to this version; consult ARCHITECTURE.md before using them.

## Kebiasaan kerja wajib

- Selalu buat dan perbarui TODO untuk setiap pekerjaan, termasuk pekerjaan kecil; tandai selesai berdasarkan hasil yang benar-benar diverifikasi.
- Gunakan subagent hanya bila memang diperlukan untuk bagian independen atau investigasi yang luas. Kerjakan langsung bila perubahan kecil dan terlokalisasi; jangan membuat delegasi hanya untuk formalitas.
- Untuk setiap pekerjaan yang mengubah file project, selalu jalankan `make build` dan pemeriksaan yang relevan sebelum menyerahkan hasil. Build gagal berarti jangan apply atau publish perubahan yang belum lolos.
- Selalu perbarui file Markdown yang terkait dalam pekerjaan yang sama, termasuk `docs/CHANGELOG.md`; jalankan `make obsidian` setelahnya.
- Setelah perubahan selesai dan terverifikasi, otomatis commit file yang termasuk pekerjaan tersebut dan push branch aktif ke remote yang sudah dikonfigurasi, tanpa menunggu pengingat. Jangan ikutkan perubahan pengguna yang tidak terkait, secret, atau artefak ignored; jangan force-push. Bila push ditolak atau autentikasi gagal, pertahankan commit lokal dan laporkan penyebabnya.

## Dokumentasi wajib

Setiap perubahan perilaku, arsitektur, operasi, atau daftar resource harus langsung diikuti pembaruan file .md yang bersangkutan pada commit/kerja yang sama — tanpa diminta ulang: `docs/CHANGELOG.md` (selalu), lalu `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/OPERATIONS.md`, `docs/VOICE.md`/`docs/MODELS.md` bila area itu tersentuh, `README.md` bila daftar fitur/struktur berubah, dan `AGENTS.md` bila aturan kerja berubah. Tutup dengan `make obsidian` (dan `make obsidian-check` bila ragu). Jangan menyerahkan pekerjaan dengan dokumentasi tertinggal.

## Build and validation

1. Make the smallest coherent source change.
2. Always run `make build` for project file changes and `make test` for relevant checks. `make test` covers syntax of source and patched assets plus the unit tests, including patch-helper regressions.
3. For voice changes, test bilingual recognition or terminology preservation as appropriate. Synthetic audio is not proof of microphone accuracy.
4. Inspect a rendered UI when changing layout. Do not send model prompts merely to inspect UI.
5. Smoke-test the standalone variant in an isolated root: `ZCODE_STANDALONE_ROOT=<dir> scripts/run.sh --remote-debugging-port=<port>`. Expect an open workspace with no login screen, no `Unknown channel`/`No handler registered` lines, and no runtime `ReferenceError`/`TypeError`. Clean that root afterwards.
6. Never export the namespace env in a persistent shell. `scripts/data_backup.py` and `scripts/install_local.py` refuse to run when they see `ZCODE_STANDALONE_ROOT` on another process, so a leaked variable looks like a running app. Unset it before apply/install/backup.
7. Close ZCode before `make apply`; do not forcibly kill an active task. `apply` verifies the staged manifest, rolls back all three resources on failure, and keeps the previous set in `runtime/backups`.
8. `make install` changes the user's standalone launcher, MCP config inside the namespace, the standalone systemd user timer, and the model-sync path unit that fills 9Router models when the app writes the provider config. Use it for user-authorized deployment/migration, not automatically for every source edit.

There is no need to reinstall dependencies or run vendor setup scripts for routine modifications. No root audio permissions or input-device permission changes are needed for the existing portal backend.

## Preserve behavior

- Never defeat the desktop mouse-takeover/STOPPED guard. Never force input after an access refusal.
- Screenshot click coordinates are view pixels; the backend maps them. Avoid extra OCR/diagnostic loops in normal desktop tasks.
- Voice records only after activation, has a 60-second limit, deletes temporary audio, and supports preview-before-send. Preserve ownership checks, main-frame IPC validation, and cancellation.
- ID/EN denote preferred language; keep English technical terms in mixed speech. Term repairs must be narrowly scoped. Preserve ordinary speech such as “komputer saya rusak” and “computer user account”.
- Reasoning levels must come from supported metadata or verified provider behavior. Do not invent Low/Max controls that only alter labels. Preserve manual overrides and fixed combo presets.
- Keep the standalone variant account-free: do not re-register Z.ai account/cloud services, do not reintroduce the login gate, and do not add automatic imports of the old installation's tasks, credentials, provider config, or MCP config. Local answers for removed channels (update state, telemetry ack, community check) are intentional, not stubs to be replaced with fake data.
- Keep local IPC handlers working: external links, task notifications, Docker/WSL/SSH inspection, and the local desktop-command path. Removing a cloud owner must not remove a local handler.
- Keep the storage bootstrap and unique-anchor assertions intact. If an upstream anchor stops matching, the build must fail instead of silently skipping a patch.

## Data and handoff

- Standalone data lives in `~/.local/share/zcode-on-steroids` (`data/`, `electron/`, `model-sync/`). Never point verification runs at the real `~/.zcode` or `~/.config/ZCode`, and never copy them into the repo.
- Backups: `python3 scripts/data_backup.py backup --root ~/.local/share/zcode-on-steroids` (app closed), `verify <snapshot>`, `restore <snapshot>`. Snapshots hold user tasks and provider keys; keep them private.
- Do not copy credentials, portal tokens, user tasks, or live provider configs into tracked source. `runtime/install-backups`, model-sync backups, and namespace snapshots may contain secrets; keep them private and ignored.
- Do not commit `app/`, `baselines/`, models, virtualenvs, vendor Git metadata, runtime captures, or user configuration backups. Do not publish the bundled application as if the project had one universal license.
- Update docs/CHANGELOG.md and the affected architecture/operation notes when behavior changes.
- Keep compatibility symlinks until old launchers/process references are proven unused. Avoid editing unrelated home-directory settings.
- Obsidian: the project folder itself is a vault when `.obsidian/` exists (then `make obsidian` only refreshes the generated `Index.md`); otherwise `make obsidian` mirrors `README.md`, `AGENTS.md`, and `docs/` into the vault from `OBSIDIAN_VAULT_PATH`, the omp Obsidian MCP entry, or `--vault`, adding `tags`/`source` frontmatter. `make obsidian-check` reports drift without writing. `.obsidian/` is ignored by git; the mirror copy is generated, never the source of truth.
