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
- **Windows x64**: installer `.exe` dengan Voice juga dihapus; rancangan kerjanya kini ada di [windowsrelease.md](windowsrelease.md), eksekusi menunggu perintah pemilik

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
| Batch 1.0.3 di Linux (guard/panel, RTK install, prewarm, MCP heal, skill fix) | Selesai: prerelease `v1.0.3+upstream.3.14.5` (AppImage/deb/rpm + SHA256SUMS); bukti, digest, dan batas ada di bagian "Batch 1.0.3: validasi Linux" di atas. |

Pin plugin: SHA256 `2e6f31257601c64b69be1a04386e5ad5193992b2a0e13aa46481652d49023dfd`, runtime `n8n-mcp` 2.92.1. Download ulang asset publik menghasilkan checksum yang sama. Audit dependency mengeluarkan 56 paket eksklusif, mempertahankan 346 paket dan seluruh resolusi dependency bersama.

Gate kode: `make build && make test && make obsidian` lulus (189 tes, 6 dilewati). Smoke tool nyata Context7, Codegraph, LSP, dan Ripgrep lulus setelah pemangkasan dependency. Tidak ada prompt model yang dikirim untuk inspeksi UI.

Artifact akhir: AppImage 345.135.608 byte (329,15 MiB), deb 273.278.176 byte (260,62 MiB), rpm 287.562.286 byte (274,24 MiB). Masing-masing hasil RPM/deb memuat 13.612 berkas reguler di `/opt/ccode`; hash ASAR, agent, launcher, metadata, dan NOTICE cocok. Tidak ada resource Voice, plugin n8n bawaan, atau paket `n8n-mcp` pada artifact.

AppImage diuji lewat `--appimage-extract-and-run` dengan AppImageLauncher dinonaktifkan hanya untuk proses uji. RPM diuji memakai `sudo rpm --root <root sementara> -i --nodeps --noscripts`, lalu launcher hasil instalasi dibuka pada namespace terpisah. Ini bukan pengujian dependency atau scriptlet di distro bersih; batas distro/Computer Use tetap berlaku.

UI tetap memakai composer, kartu Marketplace, detail plugin, form konfigurasi, dan switch native. Screenshot composer dan konfigurasi diperiksa pada aplikasi nyata; tidak ada stylesheet, font, ikon, atau pola layout baru. Instalasi n8n dari asset publik, penyimpanan form native, disable native, dan operasi MCP `get_node` pada database terpaket lulus.

Source rilis: commit `e1af2ee`, dipush ke `origin/main` dan snapshot publik `fork/ccode-workspace`. Rilis diberi label prerelease karena unsigned dan belum diuji pada distro/mesin bersih lain; Windows tidak dibangun atau diunggah.

Publikasi tetap mencatat batas lisensi pihak ketiga yang belum terverifikasi di `docs/THIRD_PARTY.md`. Pemilik mengizinkan upload gratis/open source; izin itu bukan bukti lisensi dari pemegang hak pihak ketiga.

---

## Batch 1.0.3: validasi Linux (2026-10-16)

Batch yang sudah dirilis di Windows sebagai 1.0.2/1.0.3 pertama kali dibangun dan dijalankan di Linux pada sesi ini. Tidak ada fitur Linux baru di luar batch itu; pekerjaannya adalah gerbang build, artifact, dan validasi runtime pertama untuk jalur Linux-nya (`v1.0.3+upstream.3.14.5`, prerelease, unsigned).

**Gate kode.** `make build && make test` lulus: 325 tes (9 dilewati) plus pemeriksaan staged (`Checks passed`). Dua celah suite ditemukan dan diperbaiki di sumber, bukan dengan melonggarkan assertion:

- `tests/test_apply_build.py` menurunkan daftar resource yang dipromosikan langsung dari `apply_build.FILES` + `branding.PACKAGED_ICONS`. Fixture lama menulis daftar itu manual dan tertinggal ketika `startup-prewarm/main.cjs` dan `token-savers/rtk-installer.cjs` masuk `FILES` (commit `69b7d3d`), sehingga seluruh PromotionTests merah di Linux.
- `tests/test_model_sync_node.py` mem-pin `process.platform` ke `win32` di tiga tes port Node (`DetectionWiringTests`). Tes itu menguji cabang yang di Windows dijalankan Electron-as-Node; di host Linux cabang ambient-nya berbeda. Pin platform membuatnya berjalan di platform mana pun tanpa mengubah satu assertion pun.

**Prewarm (validasi runtime pertama).** Root default-shaped disandbox (`HOME`/`XDG_CONFIG_HOME` sementara): entry `$XDG_CONFIG_HOME/autostart/ccode-startup-prewarm.desktop` dibuat dengan `Exec="<app>/ccode" --hidden` dan penanda `X-CCode-Startup-Prewarm=true`; `<root>/startup-prewarm.json` menulis `enabled: true`. Peluncuran `--hidden` memuat workspace tanpa jendela (page target CDP ada, window belum fokus); peluncuran eksplisit berikutnya menampilkan instance yang sama — PID main (23733) dan id target CDP tidak berubah, `document.hasFocus()` false → true. Switch asli di Settings → General: OFF menghapus entry dan menulis `enabled: false`. Root terisolasi melaporkan `supported: false` dengan pesan “Login startup is not changed for an isolated CCode data root.” dan tidak membuat entry. Instance `--hidden` dihitung aplikasi berjalan: `make apply` menolak dengan “Close CCode before applying the build. Current app PID: 27302”.

**RTK (binary Linux-nya dieksekusi pertama kali).** Root terisolasi tanpa rtk user yang terlihat: panel menampilkan tombol Install. Klik Install (`data-testid=ccode-token-savers-rtk-install`) mengunduh arsip ter-pin, memverifikasi SHA256 arsip + binary, memasang di `<root>/data/.ccode/v2/tools/rtk/v1.0.1-oss-linux-x64-ca544dad-e01b-4fd4-aa73-dd1a318496c4/`, lalu auto-aktif setelah kontrak lulus (`enabled: true`) — status panel berubah dalam ~10 detik. Dari shell: `rtk --version` → `rtk 1.0.1` (ELF static-pie musl), `rtk rewrite "git status"` → `rtk git status` (status 3), perintah tanpa match → status 1 tanpa output, `rtk gain --daily --format json` → JSON valid. Runtime: `resolveRtkPath` mengembalikan `/home/andikaputra/.local/bin/rtk` dengan PATH/HOME nyata (RTK user menang) dan binary terkelola saat keduanya di-sandbox; `rewriteShellCommand` menghasilkan `export PATH='<managed dir>':"$PATH"; rtk git status`, dan perintah itu dijalankan nyata di bash (rc 0). Rewrite dari rtk user tidak membawa binding PATH.

**Computer Use.** Panel Settings menampilkan dua baris native (“Enable Linux Computer Use”, “Show Linux Computer Use shortcut”); setelah diaktifkan, tombol composer `linux-computer-use-shortcut` muncul di workspace. Guard dijalankan dengan konstanta rilis (IDLE_PX 16, IDLE_MS 600, TAKEOVER_MS 2500) terhadap pointer bergerak terus-menerus → `STOPPED` pada 2501 ms; nudge ≤16 px dan pointer parkir lanjut tanpa STOPPED. Skill terpasang `glm/packages/ccode-cua-plugin/skills/computer-use/SKILL.md` mengarahkan ke `linux-desktop`/`windows-desktop` dan melarang `mcp__node_repl__js`; tidak ada salinan lain yang menyuruh nodeRepl. Batas: tidak ada sesi portal nyata dengan mouse sungguhan yang diuji; guard dijalankan sebagai modul profil dengan pointer tersimulasi.

**MCP heal.** Bootstrap di root sementara dengan entry katalog menunjuk pohon AppImage lama: `command`/`args` context7 pindah ke pohon aktif, `linux-desktop` memakai `services/desktop/bin/screen-mcp` yang aktif, `disabled: true`, env user, entry user, dan entry yang sengaja dihapus semuanya tidak berubah, marker seed tetap. Di runtime AppImage penyemaian juga bekerja dari mount: `linux-desktop` menulis path `/tmp/appimage_extracted_…/services/desktop/bin/screen-mcp`.

**Artifact dan verifikasi.** AppImage 345.168.376 byte (329,18 MiB) SHA256 `1f345ebb1b29b71567a311c069498b589b981d49ae54ea92d367648338ea5fc9`; deb 273.263.228 byte (260,60 MiB) SHA256 `6cbc419f16a1cc27b46af085f8ad00935a1f6ead2e6d35c2f6d5abc2eb2331e8`; rpm 287.592.178 byte (274,27 MiB) SHA256 `cf1c063c171f25075c695ecf59a7a643d57ec5a50a09ea0eb60ff891baee86cf`. `sha256sum -c SHA256SUMS` lulus untuk ketiganya. deb diekstrak dengan `dpkg-deb -x` (13.630 berkas) dan rpm dipasang dengan `sudo rpm --root <dir> -i --nodeps --noscripts` (13.614 berkas di bawah `/opt/ccode`); keduanya membawa `app/resources/startup-prewarm/main.cjs`, `app/resources/token-savers/rtk-installer.cjs`, `services/model-sync/sync.py`, launcher `/usr/bin/ccode`, `project.json` versi `1.0.3+upstream.3.14.5`, dan tanpa resource Voice.

Payload squashfs AppImage (offset 944.632 byte, seukuran runtime ter-pin) diekstrak dengan `unsquashfs` langsung dari byte rilis, lalu `AppRun` dijalankan di root terisolasi: workspace terbuka sebagai `CCode` tanpa login, 0 baris `Unknown channel`/`No handler registered`/`ReferenceError`/`TypeError`, data ditulis di root terisolasi, autostart tidak disentuh, `linux-desktop` tersemai menunjuk pohon hasil ekstraksi, dan SHA256 berkas AppImage tidak berubah sesudah uji. Mount FUSE tidak diuji. Percobaan `--appimage-extract-and-run` di mesin ini gagal dipakai untuk artifact final karena AppImageLauncher (daemon + `binfmt-bypass`) memindahkan file yang dieksekusi — persis perilaku yang dicatat pada rilis 1.0.0 — sehingga boot diuji lewat ekstraksi langsung dari byte artifact; daemon kini kembali aktif dan tidak ada setting pengguna yang diubah.

**Source rilis batch ini:** commit `432fe61` (batch Windows) plus commit perbaikan suite dan dokumentasi rilis Linux. Prerelease Linux pertama yang memuat batch Computer Use/RTK/prewarm/MCP-heal; label prerelease dipertahankan karena unsigned dan belum diuji di distro/mesin bersih lain.
