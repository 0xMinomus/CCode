# CCode

Branding **CCode** untuk workspace modifikasi lokal ZCode **3.14.5** di Fedora: aplikasi berjalan sebagai **varian mandiri tanpa akun ZCode**, dengan Computer Use melalui MCP, reasoning model Vansrouter, serta voice command lokal dengan ucapan Indonesia–English. Nama produk, judul window, launcher, ikon, dan onboarding memakai CCode; akar datanya `~/.local/share/ccode`.

Ini **workspace patch atas aplikasi Electron yang sudah dikemas**, bukan seluruh source tree upstream ZCode. Source modifikasi, baseline ASAR, runtime aplikasi, dan backend pendukung disimpan bersama agar bisa dilanjutkan lewat ohmypi.

## Repositori

| Repo | Isi | URL |
|---|---|---|
| **CCode** (fork) | Fork resmi dari upstream dan rumah rilis: branch `main` mengikuti upstream, `ccode` untuk hasil porting, `ccode-workspace` snapshot workspace patch ini | https://github.com/0xMinomus/CCode |
| **CCode-archive** | Repo workspace patch (dokumen ini): source patch Linux/Fedora, build/apply, services, docs — saat ini **privat** | https://github.com/0xMinomus/CCode-archive |
| **zai-org/ZCode** | Upstream asli ZCode — Apache-2.0, `Copyright 2026 Z.AI Co., Ltd`; sumber fork | https://github.com/zai-org/ZCode |

Versi publik dari dokumen ini ada di branch `ccode-workspace` pada fork **CCode**. Rilis nanti dibangun dari fork (build dari sumber), bukan dari patch binary di repo workspace; jalurnya ada di [releaseplan.md](releaseplan.md). Kalau workspace ini dibuka untuk publik, jalankan dulu pembersihan F0 di dokumen itu (buang jalur machine-specific di `project.json`).

## Cara kerja singkat

- Data aplikasi berada di `~/.local/share/ccode` (`data/`, `electron/`, `model-sync/`); `make install` memindahkan sekali dari namespace lama `~/.local/share/zcode-on-steroids`. Instalasi lama di `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis.
- Provider native **9Router** (`http://127.0.0.1:20128/v1`, combo `combo/coding-harian`) tersedia lewat "Add provider" seperti provider bawaan lain; keluarga akun Zhipu (Z.ai, BigModel, plan) sudah dihapus dari katalog. Model gateway-nya dikelompokkan per namespace (`9Router`, `9Router · cmc`, `9Router · kios`, … `9Router · lainnya`); setelah API key diisi, tombol **Auto Detect** di Model settings mengisi semuanya sekaligus — lihat [docs/MODELS.md](docs/MODELS.md).
- Login akun ZCode tidak dipakai. Provider model diatur di Settings dan membawa autentikasinya sendiri; layanan akun/cloud (marketing, client config/scenes, usage stats, coding plan, OAuth, telemetri, remote control) tidak lagi terdaftar di host.
- Fitur lokal tetap: Computer Use `fedora-desktop`, Voice bilingual, Activity (prompt/hari + streak dari riwayat lokal), engine task + SQLite lokal, MCP, reasoning sesuai metadata provider, dan guard izin desktop.
- Fitur akun/langganan (login, plan/upgrade, coding plan, web/mobile remote control, plugin ber-`requiresPaidPlan`) dihapus dari build, bukan disembunyikan; halaman Usage stats berganti menjadi Activity yang seluruhnya lokal.

## Mulai dengan ohmypi

```bash
# repo workspace (patch Linux/Fedora)
git clone https://github.com/0xMinomus/CCode-archive.git ~/Documents/CCode
cd ~/Documents/CCode
omp
```

Minta agent membaca `AGENTS.md` dan `docs/ARCHITECTURE.md` terlebih dahulu. Contoh: “Perbaiki UI Voice, gunakan komponen menu ZCode yang sudah ada, lalu build dan jalankan pemeriksaan.”

## Struktur

| Lokasi | Isi |
|---|---|
| `src/renderer/` | Source UI Computer Use Linux, Voice, dan Activity |
| `src/main/voice.cjs` | IPC Electron, rekaman mikrofon, worker voice |
| `src/main/activity.cjs` | Modul Activity lokal: prompt/hari (seluruh riwayat), streak, dan rekap tahun |
| `src/local_only/catalog.py` | Patch katalog provider native: buang keluarga Zhipu, tambah template 9Router |
| `src/local_only/` | Patch standalone: namespace data, pembersihan akun/cloud, dan branding CCode |
| `ccode-logo.svg` | Sumber tunggal mark CCode (dipakai patch mark, data URI, dan ikon) |
| `assets/icons/` | Ikon hasil rasterisasi `ccode-logo.svg` (`make icons`), dipakai paket dan launcher |
| `services/desktop/` | screen-mcp dan profil `zcode-fast` |
| `services/voice/` | Whisper worker, kosakata bilingual, venv, model lokal |
| `services/model-sync/` | Discovery model 9Router + sinkronisasi metadata reasoning, cache, state |
| `app/` | Aplikasi Electron modifikasi yang bisa dijalankan |
| `baselines/` | `app.asar` dan backend agent asli yang dipin sebagai sumber build |
| `scripts/` | Build ASAR, pemeriksaan, apply, backup/restore, integrasi lokal |
| `runtime/` | Build sementara dan cadangan; jangan commit |
| `project.json` | Versi upstream, hash baseline, nama asset yang dipatch |
| `releaseplan.md` | Rencana rilis: jalur source-fork, kewajiban lisensi Apache-2.0, packaging per platform |
| `docs/` | Arsitektur, pengembangan, operasi, dan keterbatasan |

## Perintah sehari-hari

```bash
make build        # hasil di runtime/build/, belum mengubah app aktif
make icons        # rasterisasi ulang assets/icons/ dari ccode-logo.svg
make test         # syntax source + unit test + syntax hasil ASAR
make dry-run      # lihat integrasi lokal yang akan dipasang
make apply        # tutup aplikasi dulu; promote build + rename identitas AppDir ke CCode, simpan cadangan
make install      # pasang launcher/ikon/timer CCode, migrasikan namespace lama, pensiunkan integrasi ZCode-era
make run          # buka app/ccode lewat scripts/run.sh
make models       # deteksi/segarkan semua model 9Router (kelompok per namespace)
make obsidian     # salin README, AGENTS, dan docs/ ke vault Obsidian
make obsidian-check  # laporkan selisih vault tanpa menulis

python3 scripts/data_backup.py backup  --root ~/.local/share/ccode --destination ~/ccode-backups/$(date +%F)
python3 scripts/data_backup.py verify  ~/ccode-backups/2026-10-12
python3 scripts/data_backup.py restore ~/ccode-backups/2026-10-12
```

`make build` menolak baseline berbeda atau anchor upstream yang tidak cocok. Perubahan file di `src/main/` perlu build/apply; worker di `services/voice/` dimuat ulang setelah aplikasi ditutup dan dibuka kembali. `make apply` sekaligus mengganti nama identitas AppDir (`app/zcode` → `app/ccode`, launcher, ikon, `AppRun`), jadi jalankan `make build && make test && make apply` lalu `make run`; `make install` hanya bila ada perubahan integrasi user.

Data instalasi lama di `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis; symlink kompatibilitas lama dibiarkan sampai proses yang memakainya benar-benar berhenti.

Data akun, task, plugin, dan provider tidak disalin ke source workspace.

Baca [panduan pengembangan](docs/DEVELOPMENT.md), [operasi/rollback](docs/OPERATIONS.md), dan [catatan third-party](docs/THIRD_PARTY.md).

Catatan Obsidian: folder project ini bisa dibuka langsung sebagai vault (`.obsidian/` ada → `make obsidian` hanya menyegarkan `Index.md`, sedangkan `README`, `AGENTS`, dan `docs/` adalah file asli). Untuk vault terpisah, `make obsidian` menyalin dokumen ke `<vault>/ZCode on Steroids/` dengan frontmatter tag `#zcode`; vault dideteksi dari `OBSIDIAN_VAULT_PATH`, konfigurasi MCP omp, atau `--vault`. `make obsidian-check` melaporkan selisih tanpa menulis.

## Batasan yang jujur

- Bukan port native Linux dari helper macOS/Windows: Computer Use memakai `fedora-desktop`/screen-mcp, dan kualitas model terpisah dari performa backend.
- Audit menyeluruh atas seluruh trafik keluar belum dilakukan; yang diverifikasi adalah tidak ada lagi channel akun/cloud di aplikasi dan tidak ada error/handler hilang saat startup.
- Permukaan akun yang tidak lagi punya pemilik (misalnya panel plan di Settings) menampilkan status tidak tersedia, bukan data palsu.
- Yang sengaja **tidak** diganti nama: env `ZCODE_*`, kanal IPC (`zcode-*`), skema URL `zcode://`, layout penyimpanan `.zcode` di dalam namespace, id provider/plugin/MCP, dan string protokol/transport (`ZCode Protocol`, error transport/runtime). Semua itu kontrak dengan host dan agent yang dipaketkan — menggantinya tidak mengubah apa pun yang terlihat dan berisiko memutus handshake.
- Mark CCode berasal dari satu file `ccode-logo.svg`; PNG di `assets/icons/` adalah hasil rasterisasi yang di-commit supaya `make build` tidak butuh tool tambahan (ImageMagick hanya perlu saat `make icons`).
- Rilis sebagai aplikasi mandiri belum jalan: repo ini masih workspace patch (butuh AppImage ZCode 3.14.5 + baseline + venv), Linux-only, dan belum ada artifact siap-unduh. Jalur rilisnya ada di [releaseplan.md](releaseplan.md).
- Source upstream ZCode publik dan berlisensi **Apache-2.0** (Copyright 2026 Z.AI Co., Ltd), jadi forking diizinkan dengan kewajiban atribusi/NOTICE dan tanpa hak merek; status lengkap di docs/THIRD_PARTY.md.
