# Rencana kerja rilis Linux (dan catatan Windows)

Status: 2026-10-15. Rencana tingkat tinggi tetap di [releaseplan.md](releaseplan.md); file ini daftar kerja konkret yang sudah disetujui pemilik proyek.

## Keputusan yang sudah dikunci

| Hal | Keputusan |
|---|---|
| Urutan rilis | Linux x64 dulu (`.AppImage`, `.deb`, `.rpm`), lalu Windows x64 |
| Voice | **Dihapus total** dari kode, UI, resource, dan artifact — Linux maupun Windows (Windows: agar tetap ringan) |
| n8n | Tetap ada, tetapi dipasang user dari **Plugin Marketplace** |
| Hosting plugin n8n | Release asset di fork publik `0xMinomus/CCode` |
| Dependensi n8n | `n8n-mcp` (±150 MB) ikut **di dalam zip**; satu unduhan, offline setelahnya |
| Computer Use | Nama MCP `linux-desktop`; entry didaftarkan aplikasi sendiri (keduanya sudah selesai) |

Aturan tetap: tidak ada fitur yang dihapus tanpa persetujuan pemilik proyek; batasan yang belum terverifikasi ditulis apa adanya di release notes.

---

## A. Hapus Voice total

Fitur hilang sepenuhnya — bukan disembunyikan.

**A1. Hapus sumber**
- `src/main/voice.cjs`
- `src/renderer/voice-input.js`
- `services/voice/**` (worker, terminology, model Whisper 464 MB, venv ±450 MB)
- `tests/test_voice_terms.py`

**A2. Cabut dari jalur build** (kalau tidak dicabut, build gagal atau menyisakan kontrol mati)
- `scripts/build.py`: injeksi `CCodeVoiceInput` di composer, injeksi modul renderer, registrasi main process, jembatan preload `ccodeVoice`, staging `voice/main.cjs`
- `scripts/apply_build.py`: entri `voice/main.cjs` pada `FILES`
- `scripts/check.py`: `node --check` untuk `voice/main.cjs`
- `.gitignore`: baris `services/voice/model/`

**A3. Bersihkan sisa**
- `scripts/pack_linux.py`: buang komponen `voice` dari `ALL_COMPONENTS` dan dari teks `release-notes.md` (dependensi PipeWire/ffmpeg tidak lagi relevan)
- Dokumen: hapus `docs/VOICE.md`; perbarui `docs/ARCHITECTURE.md` (bagian Voice), `docs/OPERATIONS.md`, `docs/DEVELOPMENT.md`, `README.md` (daftar fitur + tabel banding), `releaseplan.md`, `docs/THIRD_PARTY.md` (model Whisper), `docs/CHANGELOG.md`
- Bersihkan referensi `voice` yang tersisa (`grep` sampai nol, kecuali nama lama yang memang bagian migrasi)

**A4. Verifikasi**
- `make build && make test`
- Smoke root terisolasi: composer tanpa kontrol Voice, 12 command tetap muncul, 0 error renderer
- Ukur ulang ukuran artifact dan catat angka nyatanya

Perkiraan: −921 MB mentah, ± −600 MB terkompresi (diukur ulang setelah selesai).

---

## B. n8n lewat Plugin Marketplace

**B1. Audit dependensi.** Cari paket npm yang hanya dipakai `n8n-mcp`. Kandidat sekarang: `n8n-mcp` 78M, `@opentelemetry` 30M, `sql.js` 24M, `@modelcontextprotocol` 15M, `better-sqlite3` 9.8M, `zod` 8.1M. Sebagian dipakai server MCP lain — jangan ikut terbuang.

**B2. Bangun artefak plugin.** Skrip baru (mis. `scripts/pack_n8n_plugin.py`) yang menghasilkan zip: entrypoint `dist/mcp/server.js`, seluruh skill, manifest plugin, `package.json`, dan `node_modules` (sesuai keputusan). SHA256 dipin di repo.

**B3. Hosting.** Unggah zip sebagai release asset di fork publik `0xMinomus/CCode`; catat URL + SHA256 di entri marketplace.

**B4. Daftarkan di marketplace.** Tambahkan entri + SHA256 ke manifest marketplace bawaan aplikasi supaya muncul di daftar Marketplace user.

**B5. Keluarkan dari bundle.** Hapus `plugins/n8n` dan paket npm khusus n8n dari payload MCP runtime; arahkan registry agent (`src/local_only/n8n_plugin.py`) ke plugin hasil install, bukan payload bawaan.

**B6. Verifikasi.**
- Install dari marketplace di root terisolasi (manifest lokal + zip): plugin terpasang, MCP n8n konek, 15 skill muncul
- Disable: MCP dan seluruh skill hilang
- Tanpa install: tidak ada sisa entri/berkas di namespace

**B7. Risiko.** Butuh jaringan saat install; versi `n8n-mcp` harus dipin; dependency bersama tidak boleh ikut terhapus.

Perkiraan: −150 MB mentah (± −65 MB terkompresi) dari artifact; user yang mau n8n mengunduh ~150 MB sendiri.

---

## C. Rebuild dan rilis

1. `make build`, `make test`, `make obsidian`
2. `make apply` (aplikasi harus ditutup)
3. `make pack-linux` dengan komponen `model-sync,desktop`
4. Verifikasi artifact: `sha256sum -c SHA256SUMS`, install RPM ke root sementara, jalankan AppImage di root terisolasi
5. Perbarui `release-notes.md`, `docs/CHANGELOG.md`, `releaseplan.md`, lalu commit + push

---

## D. Menunggu (tidak dikerjakan sekarang)

- **Computer Use portabilitas**: perkakas Python dibuat di komputer user (lapis 1) dan tombol "Pasang komponen" via `pkexec` dengan perintah per distro (lapis 2)
- **Uji lintas distro**: container Ubuntu/Debian untuk klaim "jalan di distro lain"
- **Windows x64**: installer `.exe` dengan Voice juga dihapus; packaging Windows belum dimulai

---

## Status

| Item | Status |
|---|---|
| Rename MCP jadi `linux-desktop` | ✅ selesai (`2357847`) |
| Entry Computer Use didaftarkan aplikasi sendiri | ✅ selesai (`7a616f7`, `b58b654`) |
| A. Hapus Voice total | Selesai: source/resource/build/apply bersih; AppImage dan RPM terpasang membuka workspace dengan 12 command, 0 kontrol Voice, dan 0 error renderer. Ukuran akhir dicatat di bawah. |
| B. n8n lewat marketplace | Selesai: zip 53.556.338 byte, native install + handshake MCP + 15 skill + disable lulus; [release plugin](https://github.com/0xMinomus/CCode/releases/tag/n8n-plugin-v1.0.0). |
| C. Rebuild dan rilis | Selesai: [Linux prerelease `v1.0.0+upstream.3.14.5`](https://github.com/0xMinomus/CCode/releases/tag/v1.0.0%2Bupstream.3.14.5) publik, berisi AppImage/deb/rpm, SHA256SUMS, LICENSE, dan NOTICE. Digest asset GitHub cocok dengan hasil lokal. |
| D. Portabilitas Computer Use, uji lintas distro, Windows | Ditunda sesuai instruksi pemilik; tidak dikerjakan. |

Pin plugin: SHA256 `2e6f31257601c64b69be1a04386e5ad5193992b2a0e13aa46481652d49023dfd`, runtime `n8n-mcp` 2.92.1. Download ulang asset publik menghasilkan checksum yang sama. Audit dependency mengeluarkan 56 paket eksklusif, mempertahankan 346 paket dan seluruh resolusi dependency bersama.

Gate kode: `make build && make test && make obsidian` lulus (189 tes, 6 dilewati). Smoke tool nyata Context7, Codegraph, LSP, dan Ripgrep lulus setelah pemangkasan dependency. Tidak ada prompt model yang dikirim untuk inspeksi UI.

Artifact akhir: AppImage 345.135.608 byte (329,15 MiB), deb 273.278.176 byte (260,62 MiB), rpm 287.562.286 byte (274,24 MiB). Masing-masing hasil RPM/deb memuat 13.612 berkas reguler di `/opt/ccode`; hash ASAR, agent, launcher, metadata, dan NOTICE cocok. Tidak ada resource Voice, plugin n8n bawaan, atau paket `n8n-mcp` pada artifact.

AppImage diuji lewat `--appimage-extract-and-run` dengan AppImageLauncher dinonaktifkan hanya untuk proses uji. RPM diuji memakai `sudo rpm --root <root sementara> -i --nodeps --noscripts`, lalu launcher hasil instalasi dibuka pada namespace terpisah. Ini bukan pengujian dependency atau scriptlet di distro bersih; batas distro/Computer Use tetap berlaku.

UI tetap memakai composer, kartu Marketplace, detail plugin, form konfigurasi, dan switch native. Screenshot composer dan konfigurasi diperiksa pada aplikasi nyata; tidak ada stylesheet, font, ikon, atau pola layout baru. Instalasi n8n dari asset publik, penyimpanan form native, disable native, dan operasi MCP `get_node` pada database terpaket lulus.

Source rilis: commit `e1af2ee`, dipush ke `origin/main` dan snapshot publik `fork/ccode-workspace`. Rilis diberi label prerelease karena unsigned dan belum diuji pada distro/mesin bersih lain; Windows tidak dibangun atau diunggah.

Publikasi tetap mencatat batas lisensi pihak ketiga yang belum terverifikasi di `docs/THIRD_PARTY.md`. Pemilik mengizinkan upload gratis/open source; izin itu bukan bukti lisensi dari pemegang hak pihak ketiga.
