# Rencana kerja rilis Windows x64

Status: 2026-10-16. Pemilik mengizinkan eksekusi **Windows hibrida M1–M5**. Kandidat ZIP M1 sudah dirakit dan diperiksa di Linux; bukti boot/terminal Windows belum ada. M2–M5 menunggu gate tersebut. Rencana tingkat tinggi tetap di [releaseplan.md](releaseplan.md); pelaksanaan Linux ada di [linuxrelease.md](linuxrelease.md).

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
| Paket MCP win32 | Diverifikasi ada di npm: `@sdsrs/code-graph-win32-x64@0.169.0` dan `@vscode/ripgrep-win32-x64@1.18.0` — versinya sama dengan pin Linux, jadi tinggal dipilih per platform |
| Perkakas packaging di mesin ini | `makensis` **belum terpasang** (Fedora), jadi installer NSIS belum bisa dibangun di sini tanpa menambah paket NSIS; `mksquashfs`/`dpkg-deb`/`rpmbuild` yang dipakai Linux tidak relevan untuk Windows |
| Shell kedua build | **Sama versinya.** Linux kita: `Chrome/146.0.7680.80 Electron/41.0.3` (node_module_version 145, `node_shared_sqlite` aktif). Windows vendor 3.14.3: `Chrome/146.0.7680.80 Electron/41.0.3`. `node-pty` 1.1.0 dan `ssh2` 1.17.0 juga sama di kedua ASAR — jadi native yang dipakai dua build itu ABI-compatible |
| RTK | Binary lokal `~/.local/bin/rtk` v0.51.0 adalah Rust static-pie untuk Linux; build Windows-nya belum diverifikasi ada |

---

## Keputusan yang belum diambil (harus beres sebelum mulai)

| # | Keputusan | Pilihan | Menghambat |
|---|---|---|---|
| K1 | Versi dasar Windows | Pakai `3.14.3` (cepat, versi lebih tua dari Linux), tunggu vendor rilis `3.14.5` Windows, atau jalur fork source (versi sama, kerja jauh lebih besar) | Semua langkah A–F |
| K2 | Lokasi namespace data | `%LOCALAPPDATA%\CCode` (cara Windows) vs pertahankan `.local/share/ccode` (seragam lintas OS) | C1, C2, backup/migrate, dokumentasi |
| K3 | Penjadwal model-sync | Task Scheduler (mengikuti pola Linux) vs scheduler di dalam aplikasi | C3 |
| K4 | Runtime backend Computer Use | Bahasa + cara paket: Python (seperti Linux, tapi menambah runtime besar di paket Windows), Node/Electron (sudah ada di paket), atau biner kecil (Rust/Go) | B2, D5, E2, ukuran paket |
| K5 | Strategi payload MCP | Payload per platform dalam satu paket vs paket terpisah per platform | D1, D3 |
| K6 | Lingkungan uji | PC Windows pemilik (sesuai releaseplan) vs VM Windows; siapa yang menjalankan tiap milestone | F1–F3, semua kriteria lulus |
| K7 | Signing | Tanpa sertifikat (SmartScreen warning, ditulis apa adanya) vs beli sertifikat | E4, F |

K1 dan K4 yang paling menentukan: keduanya mengubah bentuk pekerjaan, bukan sekadar detail.

### Rekomendasi saya untuk tiap keputusan (pakai ini kalau tidak ada keberatan)

| # | Rekomendasi | Alasan | Kalau ditolak |
|---|---|---|---|
| K1 | **Hibrida** (bagian A0): pakai lapisan aplikasi 3.14.5 kita, ganti shell jadi berkas Windows vendor | Shell kedua build Electron 41.0.3 dan native-nya sama versi; ini melewati pekerjaan mencari ulang semua anchor | Jalur lama: patch build 3.14.3 dari nol (jauh lebih besar), atau tunggu vendor rilis 3.14.5 Windows |
| K2 | `%LOCALAPPDATA%\CCode`, `CCODE_STANDALONE_ROOT` tetap bisa menimpa | Konvensi Windows; pengguna tidak mencari data di `.local/share` | `.local/share/ccode` seragam lintas OS, tapi terasa asing di Windows |
| K3 | Task Scheduler per-user (tanpa admin) saat install, plus pemicu tulis `provider_config.json` bila bisa | Meniru semantik unit Linux tanpa layanan tambahan | Scheduler di dalam aplikasi (lebih sederhana, tapi berjalan hanya saat aplikasi hidup) |
| K4 | Backend Computer Use berbasis **Node (Electron-as-Node) + helper PowerShell**: capture lewat .NET, input lewat `SendInput` (Add-Type), teks/elemen lewat UI Automation | Tidak menambah runtime besar (tetap "ringan"), memakai pola launcher MCP yang sudah ada, dan policy takeover bisa diport ke JS | Python (seperti Linux) menambah ~100 MB ke paket; biner Rust/Go menambah toolchain baru |
| K5 | Payload MCP per platform di repo yang sama, direktori terpisah (`runtime` vs `runtime-win32`), hash dicatat per platform | Tidak menimpa payload Linux; installer memuat hanya payload platformnya | Payload dalam zip terpisah per platform (lebih ribet untuk pengguna) |
| K6 | PC Windows pemilik (Anda) untuk M1/M5; VM kalau perlu uji bersih berulang | Mengikuti releaseplan dan pernyataan Anda | VM Windows tetap diperlukan untuk uji instalasi bersih |
| K7 | Unsigned dulu, ditulis apa adanya di release notes | Tidak menahan rilis demi sertifikat | Sertifikat code signing sebelum rilis (menambah biaya dan waktu) |

### Keputusan eksekusi 2026-10-16

- K1: pemilik memilih **Windows hibrida M1–M5**, bukan port source fork F0–F4.
- K2: bootstrap bersama memakai `%LOCALAPPDATA%\CCode` di Windows, dengan fallback `%USERPROFILE%\AppData\Local\CCode`; `CCODE_STANDALONE_ROOT` tetap menang. Default Linux tidak berubah. Tidak ada impor atau migrasi otomatis.
- K3–K5: rekomendasi di atas tetap menjadi arah implementasi milestone terkait, bukan bukti fitur selesai.
- K6: pengujian pada PC Windows pemilik. Mesin build Linux tidak memiliki Wine atau PowerShell; pemeriksaan struktur/paket tidak menggantikan gate Windows.
- K7: kandidat M1 unsigned dan bukan installer rilis.

Jangan menjalankan M2–M5 sebelum hasil M1 dicatat: versi Windows, checksum kandidat, startup tanpa login, namespace terisolasi, log IPC/runtime, dan terminal/pty.

## Urutan eksekusi: milestone dan kriteria lulus

Rencana ini sengaja dibuat bertahap supaya kegagalan ketahuan di awal, bukan setelah semua dikerjakan.

| Milestone | Isi | Kriteria lulus | Risiko kalau gagal |
|---|---|---|---|
| **M0 — Fakta & baseline** (selesai) | Pin installer vendor, bongkar isinya, catat temuan | Dokumen ini + SHA256 tercatat | — |
| **M1 — Bukti boot di Windows** (spike, paling penting) | Rute hibrida A0: rakit tree Windows = ASAR patch kita + native win32 + shell vendor, rename identitas | Di Windows: aplikasi terbuka sebagai CCode, tanpa layar login, namespace sendiri, tanpa `Unknown channel`/`ReferenceError`, terminal/pty jalan (bukti native win32 benar). Fitur lain belum diklaim | Kalau ini gagal, jatuh ke jalur lama: patch build 3.14.3 Windows dicari ulang dari nol (K1 berubah) — dan itu lebih mahal |
| **M2 — Paritas fitur** | Sisanya: commands, 32 skill, subagents, token savers, marketplace + n8n, model-sync, Activity, katalog MCP | Daftar periksa fitur Linux terpenuhi di Windows satu per satu; tidak ada kontrol mati | Fitur yang tidak bisa diport ditulis sebagai batas, bukan dihapus diam-diam |
| **M3 — Computer Use** | Backend `windows-desktop` (K4) + panel Settings versi Windows | Screenshot, `read_text`, klik element, typing, dan guard takeover `STOPPED` bekerja pada aplikasi biasa; batas UIPI diuji dan dicatat | Kalau tidak selesai, panel harus menyembunyikan diri dengan pesan jujur (B3) — jangan tampilkan toggle mati |
| **M4 — Packaging** | `pack_windows.py`, NSIS per-user, ikon `.ico`, shortcut, uninstall | Installer jalan di Windows, uninstall bersih, data tetap kecuali diminta hapus, ukuran dicatat | Tanpa NSIS (perkakas belum ada) M4 tidak bisa dijalankan |
| **M5 — Gate rilis** | 10 langkah verifikasi F1 + catatan hasil | Catatan lengkap: versi Windows, artifact + SHA256, temuan, log tersensor | Tanpa catatan ini rilis Windows belum boleh terbit |

Aturan main: setiap milestone diverifikasi dengan menjalankan aplikasinya di Windows, bukan dari "build hijau". Kalau satu milestone gagal, mundur dan selesaikan keputusan yang menghambatnya sebelum lanjut.

---

## A0. Rute hibrida (rekomendasi untuk K1)

Karena shell kedua build memakai Electron yang sama (41.0.3) dan native yang sama versinya (node-pty 1.1.0, ssh2 1.17.0), jalan terpendek bukan "cari ulang semua anchor di build 3.14.3", melainkan **pakai lapisan aplikasi kita yang sudah dipatch, lalu ganti shell-nya**:

| Bagian | Dari mana |
|---|---|
| `resources/app.asar` | Hasil patch kita sekarang (aplikasi 3.14.5, sudah CCode) |
| Unpacked native | Diambil dari build Windows: `node-pty/prebuilds/win32-x64/{pty,conpty,conpty_console_list}.node` + `ssh2/.../sshcrypto.node` (ABI sama) |
| Shell Electron | Berkas Windows vendor: `CCode.exe` (rename dari `ZCode.exe`), DLL, `locales/`, `*.pak`, `resources.pak` |
| Agent | `resources/glm/ccode.cjs` hasil patch kita |
| `resources/tools/` | Binary Windows vendor (`ripgrep`, `ugrep`) — kita tidak membangun ulang |
| Ikon | `icon_windows.png` dari build kita; `tray_icon.ico` diganti mark CCode |
| `THIRD-PARTY-NOTICES.md` + `licenses/` | Milik vendor tetap disertakan (kewajiban lisensi), ditambah `NOTICE.md`/`LICENSE` kita |

Yang perlu ditambah di sisi kita: `scripts/asar.py` sekarang hanya mengganti isi entri, belum bisa **menambah** entri — padahal ASAR Windows butuh dua entri native yang tidak ada di ASAR Linux (`conpty*.node`). Tambahan itu kecil (tambah entri + tandai `unpacked` + tulis berkasnya ke `app.asar.unpacked/`), dan hasilnya: satu lapisan JS yang dipatch, dua varian archive (Linux dan Windows) dari sumber yang sama.

Konsekuensi jujur:
- Ini tetap **hibrida**: kode aplikasi 3.14.5, berkas shell dari paket Windows vendor 3.14.3 (Electron-nya sama versi). Label rilis memakai versi aplikasi, dan release notes menyebut dari mana berkas shell diambil.
- Yang belum terbukti: apakah kode aplikasi 3.14.5 berjalan bersih di shell itu (kemungkinan besar ya karena Electron-nya identik, tapi ini justru yang harus dibuktikan M1, bukan diasumsikan).
- Kalau M1 gagal, jatuh ke jalur lama: patch 3.14.3 dicari ulang dari nol.

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
| Paket native MCP untuk win32 | Sudah diverifikasi ada di npm (`@sdsrs/code-graph-win32-x64@0.169.0`, `@vscode/ripgrep-win32-x64@1.18.0`), tetapi perilakunya di Windows belum diuji | Pilih paket per platform saat build; uji tool nyata (bukan handshake) di M1/M2 |
| `makensis` belum terpasang di mesin build | M4 tidak bisa dijalankan sampai paket NSIS ditambahkan (atau installer dibangun di mesin Windows) | Catat sebagai prasyarat M4; jangan menjanjikan artifact sebelum perkakas ada |
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
| M0. Fakta + pin baseline vendor | ✅ selesai (SHA256 installer + isi tercatat) |
| K1–K7. Keputusan pemilik | K1 hibrida dipilih; K2 namespace Windows diterapkan; K3–K5 mengikuti rekomendasi saat milestone terkait; K6 PC pemilik; K7 kandidat unsigned |
| M1. Bukti boot di Windows (spike) | ⬜ belum — gate untuk lanjut ke M2 |
| Kandidat ZIP M1 (bukan bukti boot) | Dirakit; CRC ZIP dan 10.937 hash berkas lulus; 13 native Windows, tanpa native Linux |
| M2. Paritas fitur | ⬜ belum |
| M3. Computer Use `windows-desktop` + panel | ⬜ belum |
| M4. Packaging installer Windows | ⬜ belum (butuh `makensis`, belum terpasang) |
| M5. Gate verifikasi di Windows | ⬜ belum |
| A–H. Rincian pekerjaan | ⬜ belum |

Belum ada baris di tabel ini yang boleh ditandai selesai tanpa bukti yang dijalankan di Windows; build berhasil saja bukan bukti.

### Kandidat yang harus diuji pengguna

- Berkas: `runtime/release-windows/CCode-3.14.5-win-x64-M1.zip`, 255.163.953 byte.
- SHA256: `7b9a90ef87c27ad42c1b9e5fbff9afaf860f9ce9aa5d086d831cc9f7bca45962`.
- Pendamping: `SHA256SUMS`, `candidate-manifest.json`, `M1-INSTRUCTIONS.txt` pada direktori yang sama.
- Build/check akhir Linux: `make build && make test`, 198 tes, 6 dilewati. Smoke staged Linux membuka workspace tanpa login; tidak ada error renderer atau empat pola error IPC/runtime pada gate. Ini bukan pengujian Windows.
- Ekstrak ZIP di Windows, lalu jalankan `powershell -NoProfile -ExecutionPolicy Bypass -File .\CCode.ps1`. Launcher memakai `m1-isolated-root` di folder hasil ekstrak dan menyimpan log/metadata di `<root>\logs`.
- Buka terminal terintegrasi, jalankan `cmd /c echo CCODE_M1_PTY_OK`, catat versi Windows, hasil, screenshot, dan log tersensor. Tutup normal, buka lagi pada root sama, lalu periksa persistensi.
- Installer vendor terpinsel memiliki metadata native dan hash header ASAR embedded yang stale; fuse validasi ASAR vendor memang mati. Packager mencatat ketidaksesuaian, memperbarui metadata kandidat, dan mempertahankan fuse `101100011`, bukan mematikan validasi untuk melewati kegagalan.

Kandidat diterbitkan atas permintaan pemilik sebagai [prerelease uji M1](https://github.com/0xMinomus/CCode/releases/tag/windows-m1-20261016), bukan rilis final. Ukuran dan digest SHA256 asset GitHub cocok dengan kandidat lokal. Untuk pengujian awal tanpa terminal: unduh ZIP, pilih **Extract All**, buka folder `app`, lalu klik dua kali `CCode.exe`. Jalur langsung memakai `%LOCALAPPDATA%\CCode`; screenshot startup dan hasil buka ulang tidak menutup gate terminal/pty. Tidak ada hasil Windows yang dicatat sebagai lulus sampai bukti diterima.
