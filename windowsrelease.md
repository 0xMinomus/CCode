# Rencana kerja rilis Windows x64

Status: 2026-10-15. Rencana tingkat tinggi tetap di [releaseplan.md](releaseplan.md); pelaksanaan Linux ada di [linuxrelease.md](linuxrelease.md). File ini daftar kerja Windows, dan **belum ada kode Windows yang diubah**. Eksekusi menunggu perintah pemilik.

Target: fitur Windows sama dengan rilis Linux 1.0.0 saat ini — tanpa akun, namespace data sendiri, provider BYOK + 9Router, 12 slash command, 32 skill Default, 12 subagent, Token savers, Activity, MCP katalog, Plugin Marketplace + n8n, backup/restore, dan Computer Use. Voice tetap dihapus.

## Keputusan yang sudah dikunci

| Hal | Keputusan |
|---|---|
| Urutan rilis | Linux x64 dulu (terbit `v1.0.0+upstream.3.14.5`), lalu Windows x64 |
| Voice | Dihapus juga di Windows; Windows harus tetap ringan |
| n8n | Plugin Marketplace yang sama; zip dan SHA256 identik dengan rilis plugin Linux |
| Computer Use | Nama MCP `windows-desktop` bila rute MCP dipakai; keputusan rute ada di bagian B |
| Akun | Tidak ada; login gate tidak dikembalikan, layanan cloud tidak didaftarkan |
| Model sync | Pengganti systemd: Task Scheduler atau scheduler dalam aplikasi |
| Signing | Di luar scope sampai pemilik memutuskan; installer unsigned ditulis apa adanya |

Aturan tetap: tidak ada fitur yang dihapus tanpa persetujuan pemilik; batasan yang belum terverifikasi ditulis di release notes, bukan diklaim setara Linux.

---

## Fakta yang sudah diverifikasi (2026-10-15)

Survei cepat terhadap aset yang ada; semua di bawah ini fakta dari repo, API publik, dan hasil membongkar installer Windows vendor, bukan asumsi.

| Fakta | Nilai |
|---|---|
| Asset rilis vendor | Hanya tag `v3.14.3`: `ZCode-3.14.3-win-x64.exe` dan `ZCode-3.14.3-mac-arm64.dmg`. Tag `v3.15.1` tanpa asset |
| Installer Windows vendor | 143,1 MiB, SHA256 `815721ad9888b03da2bba101faba7368896123849a6a82e3bc9e5fe5f3e5048b`; payload `$PLUGINSDIR/app-64.7z`; installer memuat `UAC.dll` dan `elevate.exe` (jalur vendor sendiri meminta elevasi) |
| Isi aplikasi Windows | `ZCode.exe`, `resources/app.asar` (27.564 entri), `resources/app.asar.unpacked/node_modules/node-pty/prebuilds/win32-x64/*.node`, `resources/glm/zcode.cjs` (16,7 MB, agent), `resources/tools/{ripgrep,ugrep}`, `resources/THIRD-PARTY-NOTICES.md`, `icon_windows.png`, `tray_icon.ico` |
| Kecocokan anchor | Hampir semua anchor patch **tidak ada** di build Windows 3.14.3: `Zu`, `AI`, `z9`, `Ft`, `VOn`, dan anchor registry agent tidak ditemukan; yang cocok hanya artwork (`0 0 256 218`). Nama chunk dan asset renderer juga berbeda (`out/main/chunk-3WLLXY4Q.js`, `styles-BdJsmXrN.css`, dst.) |
| Baseline kita | `baselines/upstream-3.14.5-original.asar` (Linux). Tidak ada baseline Windows |
| Native di ASAR terpinsel | Linux: `node-pty/prebuilds/linux-x64/pty.node`, `sshcrypto.node`. Windows: `win32-x64/conpty*.node`, `pty.node`, `sshcrypto.node` — payload **per platform** |
| Vendor Computer Use | Teks `out/main` dan `out/host` menyebut `computer-use` (5×), `cua` (44×), `helper` (26×), tetapi tidak ada helper biner/direktori di tree aplikasi; `elevate.exe` disertakan installer. Artinya helper diunduh/dipasang saat runtime, dan pemilik unduhan itu bisa jadi layanan akun yang sudah kita hapus — **wajib dibuktikan di Windows sebelum rute B1 dipilih** |
| Vendor CUA di build Windows 3.14.3 | `resources/glm/packages/` di build Windows hanya berisi `browser-use-plugin`, `bundled-skills`, dan `node-repl-host` — **plugin `computer-use` tidak dikirim sama sekali**. Di ASAR tidak ada paket producer (`ccode-cua`/`zcode-cua`); yang ada hanya UI izin (`out/preload/cuaPermissionPanel.cjs`, `out/renderer/cua-permission-panel.html`) dan service `cuaPermission`. Kode main/host mencari producer yang **sudah terpasang** di `<ZCODE_HOME>/computer-use/{dev/<versi>, dev/<nama>, <nama>, preview/<nama>}` dan berhenti kalau tidak ada; probe screen-capture-nya bahkan di-hardcode mati (`shouldRunCuaScreenCaptureProbe(){return !1}`). Jadi rute vendor **tidak bisa diandalkan sebagai plan** — ia butuh producer yang tidak dikirim installer |
| Seeding Computer Use | `src/main/mcp-catalog.cjs` menyemai server desktop hanya bila `process.platform === 'linux'`; jalur `win32` sudah ditangani untuk spawn/kill |
| Launcher MCP | `services/mcp/launch.cjs` menulis shim `#!/bin/sh` untuk `node`/`typescript-language-server`, `symlinkSync` untuk `rg`, dan memaku `@vscode/ripgrep-linux-x64` |
| Paket native katalog | `services/mcp/catalog.json` memaku `@sdsrs/code-graph-linux-x64` (codegraph) dan `@vscode/ripgrep-linux-x64` (ripgrep) |
| Root namespace | `src/local_only/storage.py` menulis default `os.homedir()/.local/share/ccode` tanpa cabang platform |
| Ikon | `branding.PACKAGED_ICONS` sudah memetakan `icon_windows.png` → `ccode-1024.png`; `assets/icons/` hanya PNG, belum ada `.ico` |
| Panel Computer Use | `src/renderer/linux-computer-use.js` hanya aktif untuk Linux lokal dan menyatakan "the macOS/Windows helper backends are not used" |
| Backend desktop | `services/desktop` Linux-only: X11/uinput/AT-SPI, ekstensi GNOME shell, `bin/screen-mcp` bash, venv + `run-python.sh` |
| Integrasi OS | `scripts/install_local.py` mengurus systemd unit dan icon theme (Linux-only); `scripts/pack_linux.py` hanya AppDir/deb/rpm |
| Update feed | `app/resources/app-update.yml` sudah dinetralkan (`http://localhost:8081`); tidak ada feed vendor untuk mengambil build Windows |
| Token savers | `src/main/token-savers-runtime.cjs` menjalankan `rtk` sebagai executable — binary Windows belum tersedia |

---

## A. Baseline dan portabilitas patch

**A1. Ambil baseline Windows dan pin terpisah.**
Ekstrak `ZCode-3.14.3-win-x64.exe` (asset publik vendor), ambil ASAR + payload unpacked + Electron win32, lalu simpan sebagai `baselines/upstream-3.14.3-win-x64/` dengan SHA256 di `project.json` sebagai `windows_baseline`/`windows_baseline_sha256`/`windows_agent_baseline_sha256`. **Jangan menimpa pin Linux.**
Konsekuensi yang harus diterima sadar: build Windows akan `1.0.0+upstream.3.14.3`, lebih tua dari Linux `3.14.5`. Alternatifnya menunggu vendor merilis build Windows 3.14.5, atau menempuh jalur fork source ([releaseplan.md](releaseplan.md) §2 jalur A) untuk versi yang sama. Pilih sadar, catat di release notes.

**A2. `scripts/build.py` menerima target platform.**
Tambahkan `--platform linux|win32` (default tetap Linux) yang memilih baseline, nama asset renderer/main/preload, dan tujuan staging. Assertion anchor tetap wajib unik per baseline: build harus **gagal**, bukan melompati patch.

**A3. Modul yang menyentuh platform, satu per satu.**
- `storage.py`: default root perlu cabang platform (lihat C1).
- `mcp-catalog.cjs`: gate `linux` dipertahankan, tambah gate `win32` hanya bila rute B2 dipakai.
- `services/mcp/launch.cjs`: shim `.cmd`, tanpa symlink, tanpa path ripgrep Linux (lihat D2).
- `scripts/run.sh`: kontrak launcher perlu padanan `.cmd`/PowerShell (lihat C2).
- `branding.py`, `token_savers.py`, `cloud.py`: sudah memuat cabang `win32`/`isWindowsDesktop`; verifikasi ulang terhadap baseline Windows.

**A4. Audit anchor di baseline Windows.** Hasil pemeriksaan installer 3.14.3 menunjukkan hampir semua anchor patch dan anchor agent **tidak cocok**: nama chunk, nama asset renderer, dan nama fungsi minified berbeda, hanya artwork yang sama. Jadi seluruh lapisan patch (host, renderer, scheduler, agent) harus dicari ulang di baseline Windows, bukan disalin apa adanya. Setiap anchor (`rebrand`, `storage`, `cloud`, `catalog`, `branding`, `skills_plugin`, `mcp_catalog`, `n8n_plugin`, `plugins`, `runtime_tuning`, `token_savers`, `marketplace`, `subagents`, `default_commands`) dicari ulang, dan build harus **gagal** bila anchor tidak unik. Prosedurnya sama dengan "Update the upstream baseline" di [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), dikerjakan dua kali: sekali untuk 3.14.3 Windows, sekali lagi bila nanti pindah ke basis versi lain.

---

## B. Computer Use di Windows — dan kenapa Linux memakai MCP

**Penjelasan singkat dulu.** MCP bukan kebutuhan Linux, hanya transport. Agent CCode memanggil kontrol desktop sebagai *tool* dari sebuah server MCP. Di Linux kita memilih jalur itu karena vendor tidak punya backend Linux dan portal PipeWire adalah satu-satunya cara sah mengambil layar dan menekan tombol di Wayland — jadi kita tulis backend sendiri (`services/desktop`, screen-mcp) dan aplikasi menyemai entry `linux-desktop` sendiri. Memilih MCP juga membuat permukaan tool, guard *takeover*, dan panel Settings tetap sama bentuknya lintas platform. Di Windows situasinya beda: kode upstream menyiapkan jalur helper sendiri untuk macOS/Windows (renderer membedakan `isMacDesktop`/`isWindowsDesktop`), tetapi helper-nya tidak ikut terpasang di tree aplikasi — ia dipasang/diunduh saat runtime. Jadi pertanyaannya bukan "MCP perlu atau tidak", melainkan "helper vendor masih bisa dipasang tanpa akun yang sudah kita buang, atau kita bangun backend sendiri".

**B1. Rute vendor helper (tanpa MCP kita).** Bukti dari dua build vendor sudah menutup rute ini sebagai rencana utama. Di Linux, plugin `computer-use` ada tetapi eksekutornya tidak terpasang (plugin `node_modules` hanya berisi library gambar bersama, paket `@ccode/ccode-cua` tidak ada). Di Windows, plugin itu bahkan tidak dikirim, dan kode main/host mencari producer yang sudah terpasang di `<ZCODE_HOME>/computer-use/...` sambil mematikan probe screen-capture-nya sendiri. Jadi "pakai helper vendor" hanya bisa dipakai kalau nanti terbukti ada producer resmi yang berjalan tanpa akun — jangan direncanakan sebagai jalur utama.

**B2. Rute MCP `windows-desktop` (jalur utama, karena B1 tidak bisa diandalkan).** Backend baru bergaya screen-mcp dengan permukaan sesingkat profil `ccode-fast`: `screen_screenshot`, `screen_read_text`, `screen_click` (`element=<id>` atau koordinat), `screen_type`, `screen_key`, `screen_scroll`, `screen_wait_text`, `screen_verify`, `screen_sense`, `screen_focus`. Implementasi memakai API Windows: capture (`Windows.Graphics.Capture`/DXGI), input (`SendInput`), teks dan elemen (`UI Automation`), fokus (`GetForegroundWindow`). Policy *takeover* dipakai ulang dari `services/desktop/ccode_fast_profile.py` — polling kursor lewat `GetCursorPos`, pengguna menggerakkan kursor berarti aksi dibatalkan dengan pesan `STOPPED`. Guard ini tidak boleh dilemahkan di versi Windows.

**B3. Panel Settings tidak boleh jadi tombol palsu.** Kalau B1 belum terbukti dan B2 belum ada, panel Windows tidak boleh menampilkan toggle mati atau halaman yang menunggu layanan yang sudah dihapus (pelanggaran yang sama dengan kontrol tanpa fungsi). Pilihannya: arahkan panel ke `windows-desktop`, atau sembunyikan dengan pesan jujur bahwa backend belum tersedia.

**B4. Batas yang wajib ditulis di release notes** (jangan diklaim setara Linux):
- Tidak ada dialog izin portal di Windows; consent-nya berbeda karena capture berjalan langsung. Jangan menyalin teks "pick a screen and allow mouse/keyboard in the system dialog" ke Windows.
- UIPI: jendela elevated (Task Manager, prompt UAC di secure desktop) tidak dapat dikendalikan dari proses non-elevated. Tidak ada mode `force` yang menembus UAC, dan tidak boleh ada klaim sebaliknya.
- Perilaku berbeda per-DPI dan multi-monitor harus diuji, bukan diasumsikan.
- Sesi RDP atau desktop terkunci belum tentu bekerja (input hilang saat secure desktop); uji dan catat apa adanya.
- Clipboard memakai API Windows, bukan `wl-clipboard`.

---

## C. Runtime standalone di Windows

**C1. Root namespace.** Putuskan: pertahankan `.local/share/ccode` (kompatibel lintas OS, aneh bagi pengguna Windows) atau pindah ke `%LOCALAPPDATA%\CCode`. Implementasinya di bootstrap `storage.py` (main/host/scheduler/agent), dan `CCODE_STANDALONE_ROOT` tetap harus bisa menimpanya untuk pengujian terisolasi. Migrasi dari layout lama hanya bila memang pernah terkirim.

**C2. Launcher dan lock.** Sediakan padanan kontrak `scripts/run.sh` (`.cmd` atau PowerShell): root privat, seluruh env `CCODE_*`/`STORAGE_DIR`/`DESKTOP_HOME_DIR`, dan lock operasi bersama `.<nama>.operations.lock`. `flock` tidak ada di Windows — pakai file lock eksklusif (`msvcrt.locking` atau create-exclusive) dengan nama file yang sama supaya `data_backup.py` dan `apply_build.py` tetap sepakat soal "aplikasi sedang berjalan". Kalau launcher dilewati, bootstrap env harus tetap menghasilkan root yang sama.

**C3. Integrasi OS.** `scripts/install_local.py` belum portabel. Windows butuh: shortcut Start Menu, ikon, entri uninstall, **tanpa admin**, dan penjadwalan model-sync lewat Task Scheduler (atau scheduler dalam aplikasi) sebagai pengganti unit `ccode-model-sync.timer` + path unit yang memicu pada write `provider_config.json`.

**C4. Alur kerja tanpa `make`.** Tidak ada GNU Make di target. Semua alur harus bisa dijalankan sebagai `python scripts/<skrip>.py`, dan dokumen memuat perintah setara (`make.ps1` opsional, bukan syarat). Tandai tes yang mengasumsikan POSIX (mode 0700, symlink, shell) sebagai skip eksplisit per platform — jangan melonggarkan assertion demi build hijau.

**C5. Backup dan migrate.** `scripts/data_backup.py` dan `scripts/migrate_identity.py` memakai tar, rename, dan symlink. Verifikasi dengan hak pengguna normal di Windows (symlink bisa butuh hak khusus); sediakan jalur aman kalau symlink tidak bisa dibuat.

**C6. Token savers.** RTK perlu binary Windows (atau shim `.cmd`). Kalau tidak tersedia, switch RTK tampil nonaktif dengan alasan di UI — jangan biarkan spawn gagal diam-diam. Caveman/Ponytail tidak terpengaruh karena hanya menyuntik instruksi prompt.

**C7. Activity.** `src/main/activity.cjs` memakai `node:sqlite`; verifikasi modul itu ada di Electron Windows dan fallback snapshot tetap bekerja saat handle read-only ditolak.

**C8. Provider dan model.** Sama seperti Linux: tanpa keluarga Zhipu, template 9Router, refresh katalog dari endpoint akun dimatikan. Verifikasi discovery gateway lokal menulis ke `provider_config.json` di namespace Windows.

---

## D. MCP katalog dan payload per platform

**D1. Paket native per platform.** `catalog.json` memaku paket Linux. Sediakan varian `…-win32-x64` (atau mekanisme pemilihan per platform) setelah **nama paket diverifikasi di npm** — jangan menebak. Codegraph memakai engine native; kalau paket win32 tidak ada, jangan membundel dan jangan menampilkan baris Install yang tidak bisa jalan.

**D2. `launch.cjs` portabel.** Di Windows: jangan tulis shim `#!/bin/sh`, jangan `symlinkSync` untuk `rg`, jangan hardcode path ripgrep Linux. Spawn langsung `process.execPath` dengan `ELECTRON_RUN_AS_NODE=1` adalah jalur utama; shim `.cmd` hanya bila memang dibutuhkan.

**D3. Staging payload.** `services/mcp/stage.cjs` memasang paket saat build. Simpan payload per platform (mis. `resources/mcp/runtime-win32` vs `runtime`), jangan saling menimpa, dan catat hash di `build-manifest.json` seperti sekarang.

**D4. Plugin n8n.** Host plugin memakai binary Electron sebagai Node (`__ccode-plugin-host` + `ELECTRON_RUN_AS_NODE`), dan `better-sqlite3` native tidak dipasang sehingga fallback sql.js/WASM yang dipakai. Zip plugin tidak memuat binary platform, jadi **asset publik yang sudah terbit dipakai apa adanya** — SHA256 tetap dipin. Verifikasi di Windows: install dari asset publik, 15 skill muncul, disable mencabut semuanya, dan satu operasi nyata (handshake `get_node` minimal).

**D5. Entry Computer Use.** Bila B2 dipakai, `mcp-catalog.cjs` menyemai `windows-desktop` dengan `command`/`env` dihitung dari tree tempat aplikasi berjalan (prefix paket atau folder install), marker `mcp/default-seed.json` tetap menghormati entry yang dihapus pengguna, dan `linux-desktop` tidak pernah muncul di Windows.

---

## E. Packaging dan instalasi

**E1. `scripts/pack_windows.py`.** Dari tree `app/` hasil `make apply` (payload Windows) menghasilkan installer NSIS `.exe` per-user dan opsional ZIP portable. Ikon: `make icons` perlu diperluas menghasilkan `.ico` multi-resolusi dari `ccode-logo.svg` (ImageMagick) selain PNG, plus `icon_windows.png` yang sudah ada untuk renderer.

**E1b. Identitas Windows harus CCode penuh, bukan ZCode.** Installer vendor hanya bahan mentah: setelah dipatch, seluruh identitas produk diganti — binary `CCode.exe` (bukan `ZCode.exe`), ikon aplikasi/taskbar/tray dari mark CCode (`tray_icon.ico` punya vendor harus diganti), judul jendela dan AppUserModelID, nama entri uninstall dan shortcut Start Menu, folder install (`%LOCALAPPDATA%\Programs\CCode`), skema URL `ccode://`, serta `THIRD-PARTY-NOTICES.md` versi kita sendiri. Penggantian ini bukan opsional: `rebrand.assert_clean()` dan `branding.guard()` **wajib lulus pada payload Windows** seperti pada payload Linux, dan build harus gagal kalau masih ada tulisan atau mark vendor yang tersisa. Verifikasi tambahan: cari nama vendor di seluruh tree terpasang dan pastikan nol (kecuali di berkas atribusi `NOTICE.md`/`docs/THIRD_PARTY.md` dan catatan provenance rilis).

**E2. Isi paket.** `app/` (Electron win32, ASAR, resources termasuk `glm/ccode.cjs`, `mcp/`, `commands/`, `bundled-skills/`, ikon), `services/{model-sync,desktop}`, `scripts/data_backup.py`, `project.json` minimal, launcher, shortcut, dan `LICENSE`/`NOTICE.md`/`docs/THIRD_PARTY.md`/`UNINSTALL.md`.

**E3. Tanpa update channel.** Feed sudah dinetralkan; installer tidak boleh melakukan panggilan jaringan saat runtime selain ke provider yang user konfigurasi.

**E4. Unsigned.** SmartScreen akan memperingatkan. Tulis status signing apa adanya; jangan menyiratkan signed tanpa sertifikat.

**E5. Checksum dan catatan.** `SHA256SUMS` + release notes berisi versi upstream, batas per fitur, dan hasil verifikasi. Fitur yang belum teruji tidak diklaim siap.

**E6. Tetap ringan.** Catat ukuran installer dan ZIP, bandingkan dengan Linux, dan pastikan tidak ada model atau runtime Python besar yang ikut (Voice sudah tidak ada; venv desktop Linux tidak boleh ikut).

---

## F. Verifikasi (gate rilis Windows)

Mengikuti [releaseplan.md](releaseplan.md) F4: build sukses bukan bukti siap. Verifikasi di mesin Windows x64 milik pengguna (VM atau desktop nyata; container tidak membuktikan Computer Use).

1. Installer berjalan, aplikasi terbuka tanpa layar login, tanpa `Unknown channel`, `No handler registered`, `ReferenceError`, atau `TypeError`.
2. `/` menampilkan 12 command; 0 kontrol Voice; Settings menampilkan 32 skill Default, 12 subagent, dan menu Token savers.
3. Provider BYOK + template 9Router; Auto Detect (Task Scheduler/in-app) mengisi provider terkelompok.
4. Task dan sesi persisten setelah restart; backup/verify/restore jalan; uninstall menghapus aplikasi tanpa menghapus data (kecuali diminta).
5. MCP bawaan (Context7, Codegraph) dipakai tanpa unduhan saat pemakaian; LSP dan Ripgrep bisa dipasang dari baris katalog dan berjalan.
6. Marketplace: pasang n8n dari asset publik, 15 skill aktif, disable mencabut semuanya, dan satu operasi workflow nyata di instance uji (atau handshake tool bila instance tidak tersedia — tulis mana yang dipakai).
7. Computer Use: screenshot, `read_text`, klik berbasis element, typing, scroll, dan guard takeover (`STOPPED`) pada aplikasi biasa; catat hasil dan batas UIPI/elevated secara eksplisit.
8. Token savers: RTK (bila binary tersedia) plus Caveman/Ponytail bertahan setelah restart.
9. Upgrade di atas instalasi lama lalu rollback; namespace tidak rusak dan tidak ada impor otomatis dari instalasi lain.
10. `python scripts/check.py` (atau daftar skip eksplisit per platform) hijau di Windows, termasuk tes lifecycle n8n dengan zip nyata.

Hasil ditulis sebagai catatan: versi Windows, nama artifact + SHA256, langkah, temuan, dan log yang sudah disensor. Tanpa catatan itu gate Windows belum lewat.

---

## G. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Baseline Windows vendor lebih tua (3.14.3) dari Linux (3.14.5) | Perilaku dan simbol berbeda; paritas versi tidak tercapai | Pin terpisah, tulis versi apa adanya di release notes, siapkan jalur source fork untuk versi yang sama |
| Anchor 3.14.3 tidak cocok dengan patch 3.14.5 | Build gagal berkali-kali | Cari ulang simbol/chunk seperti prosedur update baseline; jangan melemahkan assertion |
| Helper Computer Use vendor butuh akun atau feed vendor | Rute B1 mati | Siapkan rute B2 (`windows-desktop`) sebelum menjanjikan Computer Use di Windows |
| UIPI/UAC | "Setara Linux" tidak mungkin | Dokumentasikan batas; jangan janji elevated/secure desktop |
| Paket native MCP tidak ada untuk win32-x64 | Katalog menampilkan tombol Install yang gagal | Verifikasi nama paket dulu; kalau tidak ada, jangan bundel dan jangan tampilkan |
| Symlink dan izin Windows di backup/migrate | Data pengguna berisiko | Uji dengan hak pengguna normal, sediakan jalur tanpa symlink |
| Installer unsigned | SmartScreen warning, kepercayaan pengguna turun | Catat status; keputusan sertifikat ada di pemilik |
| Windows "tidak ringan" karena runtime tambahan | Bertentangan dengan keputusan terkunci | Batasi payload; ukur dan laporkan ukuran sebelum rilis |

---

## H. Menunggu (tidak dikerjakan sekarang)

- ARM64 Windows dan ZIP portable (opsional).
- Code signing/EV dan auto-update (tetap tidak ada).
- Uji di Windows Server, sesi RDP, atau tanpa desktop interaktif.
- Uji lintas distro Linux (masih terbuka dari [linuxrelease.md](linuxrelease.md)).

---

## Status

| Item | Status |
|---|---|
| Rencana Windows (file ini) | ✅ selesai |
| A. Baseline Windows + portabilitas patch | ⬜ belum |
| B. Keputusan rute Computer Use Windows | ⬜ belum (B1 perlu bukti, B2 cadangan) |
| C. Runtime standalone Windows | ⬜ belum |
| D. Payload MCP per platform + plugin n8n | ⬜ belum |
| E. Packaging installer Windows | ⬜ belum |
| F. Verifikasi Windows x64 | ⬜ belum |
| G/H. Risiko dan item tertunda | ⬜ belum |

Belum ada baris di tabel ini yang boleh ditandai selesai tanpa bukti yang dijalankan di Windows; build berhasil saja bukan bukti.
