# ZCode on Steroids

Workspace modifikasi lokal ZCode **3.14.5** untuk Fedora: aplikasi berjalan sebagai **varian mandiri tanpa akun ZCode**, dengan Computer Use melalui MCP, reasoning model Vansrouter, serta voice command lokal dengan ucapan Indonesia–English.

Ini **workspace patch atas aplikasi Electron yang sudah dikemas**, bukan seluruh source tree upstream ZCode. Source modifikasi, baseline ASAR, runtime aplikasi, dan backend pendukung disimpan bersama agar bisa dilanjutkan lewat ohmypi.

## Cara kerja singkat

- Data aplikasi berada di `~/.local/share/zcode-on-steroids` (`data/`, `electron/`, `model-sync/`). Instalasi lama di `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis.
- Login akun ZCode tidak dipakai. Provider model diatur di Settings dan membawa autentikasinya sendiri; layanan akun/cloud (marketing, client config/scenes, usage stats, coding plan, OAuth, telemetri, remote control) tidak lagi terdaftar di host.
- Fitur lokal tetap: Computer Use `fedora-desktop`, Voice bilingual, engine task + SQLite lokal, MCP, reasoning sesuai metadata provider, dan guard izin desktop.

## Mulai dengan ohmypi

```bash
cd /home/andikaputra/Documents/zcode-on-steroids
omp
```

Minta agent membaca `AGENTS.md` dan `docs/ARCHITECTURE.md` terlebih dahulu. Contoh: “Perbaiki UI Voice, gunakan komponen menu ZCode yang sudah ada, lalu build dan jalankan pemeriksaan.”

## Struktur

| Lokasi | Isi |
|---|---|
| `src/renderer/` | Source UI Computer Use Linux dan Voice |
| `src/main/voice.cjs` | IPC Electron, rekaman mikrofon, worker voice |
| `src/local_only/` | Patch standalone: namespace data dan pembersihan akun/cloud |
| `services/desktop/` | screen-mcp dan profil `zcode-fast` |
| `services/voice/` | Whisper worker, kosakata bilingual, venv, model lokal |
| `services/model-sync/` | Sinkronisasi metadata reasoning, cache, state |
| `app/` | Aplikasi Electron modifikasi yang bisa dijalankan |
| `baselines/` | `app.asar` dan backend agent asli yang dipin sebagai sumber build |
| `scripts/` | Build ASAR, pemeriksaan, apply, backup/restore, integrasi lokal |
| `runtime/` | Build sementara dan cadangan; jangan commit |
| `project.json` | Versi upstream, hash baseline, nama asset yang dipatch |
| `docs/` | Arsitektur, pengembangan, operasi, dan keterbatasan |

## Perintah sehari-hari

```bash
make build        # hasil di runtime/build/, belum mengubah app aktif
make test         # syntax source + unit test + syntax hasil ASAR
make dry-run      # lihat integrasi lokal yang akan dipasang
make apply        # tutup ZCode dulu; promote build dan simpan cadangan
make install      # pasang launcher + timer standalone (tidak mengubah launcher lama)
make run          # buka app/zcode lewat scripts/run.sh
make obsidian     # salin README, AGENTS, dan docs/ ke vault Obsidian
make obsidian-check  # laporkan selisih vault tanpa menulis

python3 scripts/data_backup.py backup  --root ~/.local/share/zcode-on-steroids --destination ~/zcode-backups/$(date +%F)
python3 scripts/data_backup.py verify  ~/zcode-backups/2026-10-12
python3 scripts/data_backup.py restore ~/zcode-backups/2026-10-12
```

`make build` menolak baseline berbeda atau anchor upstream yang tidak cocok. Perubahan file di `src/main/` perlu build/apply; worker di `services/voice/` dimuat ulang setelah ZCode ditutup dan dibuka kembali.

Data instalasi lama di `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis; symlink kompatibilitas lama dibiarkan sampai proses yang memakainya benar-benar berhenti.

Data akun, task, plugin, dan provider tidak disalin ke source workspace.

Baca [panduan pengembangan](docs/DEVELOPMENT.md), [operasi/rollback](docs/OPERATIONS.md), dan [catatan third-party](docs/THIRD_PARTY.md).

Catatan Obsidian: folder project ini bisa dibuka langsung sebagai vault (`.obsidian/` ada → `make obsidian` hanya menyegarkan `Index.md`, sedangkan `README`, `AGENTS`, dan `docs/` adalah file asli). Untuk vault terpisah, `make obsidian` menyalin dokumen ke `<vault>/ZCode on Steroids/` dengan frontmatter tag `#zcode`; vault dideteksi dari `OBSIDIAN_VAULT_PATH`, konfigurasi MCP omp, atau `--vault`. `make obsidian-check` melaporkan selisih tanpa menulis.

## Batasan yang jujur

- Bukan port native Linux dari helper macOS/Windows: Computer Use memakai `fedora-desktop`/screen-mcp, dan kualitas model terpisah dari performa backend.
- Audit menyeluruh atas seluruh trafik keluar belum dilakukan; yang diverifikasi adalah tidak ada lagi channel akun/cloud di aplikasi dan tidak ada error/handler hilang saat startup.
- Permukaan akun yang tidak lagi punya pemilik (misalnya panel plan di Settings) menampilkan status tidak tersedia, bukan data palsu.
- Lisensi redistribusi paket installer dan komponen pihak ketiga belum diselesaikan; lihat docs/THIRD_PARTY.md.
