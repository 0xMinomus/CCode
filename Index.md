---
tags: [zcode, fedora, project]
---
# ZCode on Steroids

Workspace patch untuk **ZCode 3.14.5** di Fedora. Aplikasi berjalan sebagai varian mandiri tanpa akun ZCode: Computer Use lewat `fedora-desktop`, Voice bilingual lokal, dan provider model diatur sendiri di Settings.

Folder repo ini dibuka langsung sebagai vault Obsidian. Catatan `README.md`, `AGENTS.md`, dan `docs/` adalah file asli; `make obsidian` hanya menyegarkan note ini.

## Dokumen

- [[README|README]] — ringkasan, struktur, perintah harian
- [[AGENTS|AGENTS]] — aturan kerja agent di repo
- [[docs/ARCHITECTURE|ARCHITECTURE]]
- [[docs/CHANGELOG|CHANGELOG]]
- [[docs/DEVELOPMENT|DEVELOPMENT]]
- [[docs/MODELS|MODELS]]
- [[docs/NO_LOGIN_TEST|NO_LOGIN_TEST]]
- [[docs/OPERATIONS|OPERATIONS]]
- [[docs/THIRD_PARTY|THIRD_PARTY]]
- [[docs/VOICE|VOICE]]

## Fakta kunci

- Repo: `/home/andikaputra/Documents/zcode-on-steroids`
- Vault: `/home/andikaputra/Documents/zcode-on-steroids`
- Data aplikasi: `~/.local/share/zcode-on-steroids` (`data/`, `electron/`, `model-sync/`)
- Launcher: `zcode-on-steroids.desktop`; timer: `zcode-on-steroids-model-sync.timer`
- Data lama `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis
- Build: `make build && make test`; promote: `make apply` (aplikasi harus tertutup)
- Backup/restore: `python3 scripts/data_backup.py backup|verify|restore`
- Snapshot terakhir: `~/.local/share/zcode-on-steroids-backups/20261012-161210-600068`
- Vault ini adalah folder project, jadi tidak ada salinan: catatan `README`, `AGENTS`, dan `docs/` adalah file asli repo.
