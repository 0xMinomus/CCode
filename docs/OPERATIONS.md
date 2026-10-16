# Operasi dan rollback

Aplikasi aktif: `app/ccode`, dijalankan sebagai varian mandiri lewat `scripts/run.sh` (nama ini berasal dari rebrand CCode; `make apply` yang mengganti nama binary/launcher/ikon AppDir). Launcher `ccode.desktop` dan timer `ccode-model-sync.timer` adalah integrasi baru; launcher dan unit pra-rebrand serta shortcut AppImage lama dipensiunkan oleh `make install` (nama lama ada di konstanta `rebrand.PREVIOUS_*`). MCP mengarah ke `services/desktop/bin/screen-mcp`.

```bash
make dry-run
make install
make migrate
systemctl --user status ccode-model-sync.timer
journalctl --user -u ccode-model-sync.service -n 20
```

`make install` menulis config MCP di dalam namespace standalone, launcher `ccode.desktop`, ikon hicolor (`ccode.png` per ukuran + `ccode.svg`), dan unit timer/path `ccode-model-sync.*` yang memantau `provider_config.json` supaya model 9Router terisi begitu provider dibuat/diubah dari UI. Provider API keys tidak diubah. Bila namespace pra-rebrand (`rebrand.PREVIOUS_NAMESPACE`) masih ada dan root baru belum ada, install juga memindahkannya ke `~/.local/share/ccode` (rename, bukan salin), lalu memensiunkan launcher pra-rebrand (`rebrand.PREVIOUS_LAUNCHER_FILE`/`PREVIOUS_LAUNCHER` beserta salinan cadangannya seperti `*.desktop.before-*`), entri AppImageLauncher lama, unit `*-model-sync` lama (`rebrand.PREVIOUS_UNIT`/`PREVIOUS_VANSROUTER_UNIT`, di-`disable --now` lebih dulu), lock namespace usang (`rebrand.PREVIOUS_LOCK`), dan direktori config Electron pra-rebrand (`~/.config/<rebrand.PREVIOUS_CONFIG_DIR>`). Cadangan semua file integrasi yang diganti/dihapus tersimpan di `<namespace>/integration-backups` dengan izin 0600. Install juga menyegarkan `gtk-update-i…

`make migrate` (`scripts/migrate_identity.py`) mengubah instalasi yang sudah ada ke ejaan baru dengan aplikasi tertutup: snapshot tar state di `migration-backups/` (lewati dengan `--no-backup`; workspace dikecualikan karena ukurannya), merge layout lama ke layout baru bila `make install` sudah menyemai sebagian, rename setiap path yang memuat token pra-rebrand (terdalam dulu), rewrite token di config/state/log di luar workspace, lalu rewrite setiap kolom teks database (`data/.ccode/cli/db/db.sqlite`, `data/.ccode/v2/tasks-index.sqlite`). `--dry-run` hanya melaporkan apa yang akan berubah.

Periksa/matikan integrasi sync bila perlu:

```bash
systemctl --user status ccode-model-sync.path ccode-model-sync.timer
journalctl --user -u ccode-model-sync.service -n 20
systemctl --user disable --now ccode-model-sync.path      # hentikan pengisian instan
systemctl --user disable --now ccode-model-sync.timer     # hentikan sync rutin
```

## Paket rilis Linux

`make pack-linux` membangun tiga artifact x86_64 di `runtime/release/` dari AppDir yang sudah `make apply`: `CCode-<versi>-x86_64.AppImage`, `ccode_<versi>_amd64.deb`, dan `ccode-<versi>-1.x86_64.rpm`, plus `SHA256SUMS` dan `release-notes.md`. Versi default `1.0.0+upstream.<versi upstream>`; pilih komponen (default `model-sync,desktop`) lewat `--components` dan format lewat `--formats`. Build memerlukan `squashfs-tools`, `dpkg`, dan `rpm-build`.

Paket sistem memasang aplikasi di `/opt/ccode` (termasuk `services/`, `scripts/data_backup.py`, dan `project.json`), lalu `usr/bin/ccode`, entri desktop `ccode.desktop` dengan skema `ccode://`, ikon hicolor, serta dokumen di `/usr/share/doc/ccode` (`LICENSE`, `NOTICE.md`, `THIRD_PARTY.md`, `UNINSTALL.md`). Launcher paket menjalankan kontrak namespace yang sama dengan `scripts/run.sh`, jadi data tetap di `~/.local/share/ccode` dan `CCODE_STANDALONE_ROOT` tetap berlaku.

```bash
make pack-linux
make pack-linux PACK_ARGS="--version 1.0.1 --components model-sync --formats deb"
sha256sum -c runtime/release/SHA256SUMS
```

Verifikasi sebelum dipublikasikan: jalankan AppImage dengan root uji lewat `CCODE_STANDALONE_ROOT=$PWD/runtime/verify/root ./runtime/release/*.AppImage`, uji RPM tanpa menyentuh sistem dengan `sudo rpm --root $PWD/runtime/verify/rpm-root -i --nodeps --noscripts <rpm>`, dan buka deb lewat `dpkg-deb -x <deb> runtime/verify/deb-root`. Operator `rm -rf ~/.local/share/ccode` menghapus seluruh data CCode; snapshot bisa dibuat lebih dulu dengan `python3 scripts/data_backup.py backup --root ~/.local/share/ccode`.

Stage menolak build bila jalur home mesin build atau `provider_config*.json` ikut terbawa, dan menormalkan izin berkas supaya tree dapat dibaca pengguna yang memasangnya. Venv layanan hanya membawa interpreter (`bin/python*`); console script, `pyvenv.cfg` yang memuat jalur build, cache `__pycache__`, dan state lokal model-sync dibuang. Computer Use masih memerlukan paket sistem (PyGObject, GStreamer + plugin PipeWire, portal, `wl-clipboard`) karena layer itu tidak dapat dibundel.

## Paket rilis Windows

`make pack-windows` membangun `CCode-<versi>-win-x64.exe` (installer NSIS per-user), `CCode-<versi>-win-x64.zip` (portable), `SHA256SUMS`, dan `package-manifest.json` di `runtime/release-windows/`. Prasyarat: 7-Zip, ImageMagick, dan NSIS (dicari lewat PATH lalu lokasi instalasi standar), plus jaringan untuk installer vendor dan paket native. Versi rilis Windows ada di `project.json` (`windows_release_version`). Kandidat prarilis M1 sudah digantikan installer rilis.

Installer tidak meminta admin: aplikasi dipasang di `%LOCALAPPDATA%\Programs\CCode`, dengan shortcut Start Menu, entri uninstall di HKCU, skema URL `ccode://`, dan dua task model-sync (`CCode Model Sync` ONLOGON dan `CCode Model Sync (daily)`). Installer dan uninstaller hanya menahan bila ada `CCode.exe` yang berjalan dari folder install tujuan; instance lain (mis. ZIP uji atau salinan portable) tidak memblokir. Uninstaller menghapus aplikasi, shortcut, registry, dan task; data `%LOCALAPPDATA%\CCode` dipertahankan kecuali pengguna mencentang opsi hapus.

Portable ZIP: ekstrak ke folder yang dapat ditulis, lalu jalankan `app\CCode.exe` (namespace default yang sama), atau `powershell -NoProfile -ExecutionPolicy Bypass -File .\CCode.ps1` untuk root uji terisolasi. Artifact unsigned sehingga SmartScreen memperingatkan. Tidak ada feed update; aplikasi hanya menghubungi endpoint provider yang pengguna konfigurasi.

Verifikasi cepat di mesin Windows: cocokkan `SHA256SUMS` (`certutil -hashfile` atau `Get-FileHash`), pasang, buka workspace tanpa layar login, pastikan `/` menampilkan 12 command dan Settings tidak menampilkan kontrol Voice, jalankan `cmd /c echo CCODE_PTY_OK` di terminal bawaan, tutup normal lalu buka ulang untuk persistensi, dan ambil snapshot dengan `python3 scripts/data_backup.py backup --root %LOCALAPPDATA%\CCode` saat aplikasi tertutup. Batas yang wajib ditulis di release notes: Computer Use Windows tidak dapat mengendalikan jendela elevated atau secure desktop (UIPI), perilaku multi-monitor/mixed-DPI belum terverifikasi, dan `lsp_diagnostics` per-file mengembalikan kosong di Windows — pakai `lsp_workspace_diagnostics` atau tool navigasi `lsp_*`.

## Computer Use: satu backend, dua tempat

Computer Use Linux diatur dari **Settings → Computer Use**, dan entry yang sama (`linux-desktop`) juga tampil sebagai baris di **Settings → MCP Servers**. Keduanya menulis state `enabled` yang sama. Panel berisi dua baris: **Enable Computer Use** dan **Show Computer Use button in the composer**. Tombol composer membuka panel Settings ini; mematikannya hanya menyembunyikan tombol, bukan mematikan backend.

Di Windows pola yang sama berlaku untuk `windows-desktop`, termasuk tombol composer. Backend yang hilang dan kegagalan toggle tetap dilaporkan, bukan disembunyikan sebagai kontrol palsu. Windows mengambil layar langsung tanpa dialog portal; UIPI memblokir input ke jendela elevated dan secure desktop. Multi-monitor/mixed-DPI belum terverifikasi. Linux meminta izin screen-sharing/input dari portal saat penggunaan pertama. Gunakan model vision. Gerakan kecil ditoleransi 16 px; gerakan berkelanjutan selama 2500 ms tetap menghasilkan STOPPED dan agent wajib menyerahkan kontrol, bukan memaksa input. Agent memakai tool MCP desktop — skill `computer-use` bawaan sudah diarahkan ke `windows-desktop`/`linux-desktop`, bukan runtime plugin — dan aksi pertama bisa perlu beberapa detik saat backend menyusun helper; ulangi sekali, jangan beralih ke teknologi otomasi lain.

## Startup prewarm

**Settings → General → Start CCode in the background at login** mengatur prewarm, default aktif. Windows memakai HKCU Run milik pengguna; Linux memakai entry XDG autostart `ccode-startup-prewarm.desktop`. Login menjalankan `--hidden`: workspace dimuat tanpa jendela/taskbar, lalu shortcut normal menampilkan instance yang sama. RAM tetap terpakai sejak login; matikan toggle bila tidak menginginkannya. Keluar sepenuhnya sebelum apply/install/backup; instance background tetap aplikasi berjalan. Root smoke terisolasi tidak mengubah autostart pengguna. Verifikasi Linux login/restore dilakukan pemilik di mesin Linux.

## Pemasangan RTK dan pemulihan MCP

Saat RTK belum tersedia, slot kontrol di **Settings → Token savers** menampilkan **Install**. Satu klik mengunduh binary resmi ter-pin, memverifikasi SHA256, memasangnya dalam namespace privat, lalu mengaktifkan RTK. Tombol menjadi toggle biasa setelah sukses; kegagalan menampilkan alasan dan dapat dicoba ulang. RTK yang sudah dipasang pengguna tetap didahulukan. Rewrite terkelola membawa binding PATH berbentuk POSIX (`export PATH=…`), jadi di Windows ia mengikuti shell Git Bash (default); dengan dialek CMD, perintah hasil rewrite tidak jalan — RTK milik pengguna yang sudah ada di PATH tidak memakai binding ini.

Path entry katalog MCP milik aplikasi dihitung ulang saat bootstrap setelah aplikasi dipindah. Entry Context7/Codegraph lama yang menunjuk folder portable terhapus dipulihkan tanpa unduhan ulang; server custom, env tambahan, disabled state, dan entry yang sengaja dihapus tetap dihormati. Payload opsional yang hilang masih memerlukan tindakan Install eksplisit.


## Computer Use: klik/ketik ditolak

Gejala: agent melaporkan klik atau ketik gagal, dan `/tmp/screen_err.txt` memuat
`GDBus.Error:org.freedesktop.DBus.Error.Failed: Session is not allowed to call NotifyPointer methods (0)`.
Artinya sesi portal tidak punya izin pointer/keyboard, sedangkan jalur kernel (`uinput`) juga tidak aktif — jadi input tidak punya jalur yang berhasil. Capture tetap jalan (screenshot dan `screen_read_text`), hanya injeksi input yang mati.

Backend desktop memakai dua jalur: kernel `uinput` (dipakai bila tersedia, presisi, tidak bergantung izin portal) dan portal `RemoteDesktop` sebagai cadangan. Sejak profil `ccode-fast`, penolakan portal diterjemahkan menjadi pesan yang menyebut dua perbaikan ini, bukan traceback mentah.

Perbaikan 1 — aktifkan jalur kernel (disarankan):

```bash
printf 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660"\n' \
  | sudo tee /etc/udev/rules.d/99-uinput-ccode.rules
printf 'uinput\n' | sudo tee /etc/modules-load.d/uinput.conf
sudo modprobe uinput && sudo usermod -aG input "$USER"
sudo udevadm control --reload-rules && sudo udevadm trigger --name-match=uinput
# agar berlaku tanpa logout pada sesi berjalan:
sudo setfacl -m "u:$USER:rw" /dev/uinput
```

Verifikasi: `/dev/uinput` menjadi `660 root:input`, `services/desktop/.venv/bin/python -c "import sys;sys.path.insert(0,'services/desktop');import os;print(os.access('/dev/uinput',os.W_OK))"` mencetak `True`. Paket Python `evdev` sudah ada di venv layanan; tanpa grup `input` + aturan udev, izin akan kembali setelah reboot.

Perbaikan 2 — beri ulang izin portal (cadangan): hapus `~/.config/mcp-screen/token`, lalu setujui dialog berikutnya dengan remote control (pointer dan keyboard) diizinkan. Selama salah satu perbaikan belum dilakukan, klik dan ketik akan ditolak lagi; jangan mengulang perintah yang sama.

## MCP di Settings

Context7 dan Codegraph tersedia setelah instalasi aplikasi. **Settings → MCP Servers** menampilkan daftar **Installed** server native; LSP dan Ripgrep tersedia sebagai baris katalog dengan tombol **Install** di slot switch, tanpa label `Optional`. Setelah di-Install, baris native dengan switch on/off menggantikan baris katalog.

LSP membutuhkan language server untuk bahasa proyek (TypeScript/JavaScript dipasang bersama entri ini). Ripgrep mencari berkas lokal. Pemasangan melalui tombol **Install** memakai registry npm dan direktori privat di dalam namespace (`mcp/packages`), tanpa Node/npm sistem.

Default tidak berarti semua proses server berjalan terus; runtime MCP tetap mengikuti pemuatan oleh agent. Context7 memakai jaringan saat tool dokumentasi dipanggil. Codegraph menyimpan indeks lokal proyek. Mematikan atau menghapus server lewat pengelolaan native tidak dibatalkan oleh bootstrap berikutnya.

MCP lain (mis. GitHub) dapat ditambahkan sendiri lewat tombol **New** di halaman yang sama. MCP resmi `image_search` tidak dimuat karena memerlukan autentikasi akun Z.ai.

## Plugin n8n

1. Buka **Plugin Marketplace**, pilih **n8n**, lalu **Install**. Unduhan zip mencakup `n8n-mcp` 2.92.1, seluruh dependency, dan 15 skill; tidak ada runtime n8n dalam aplikasi sebelum pemasangan.
2. Buka **Advanced details → Configuration**. Isi **n8n instance URL** (base URL tanpa `/api/v1`) dan **n8n API key** dari Settings → n8n API pada instance Anda. Gunakan HTTPS untuk instance remote; HTTP hanya diterima untuk loopback.
3. Token **n8n instance MCP access token** hanya diperlukan oleh fitur MCP instance seperti persisted agents dan resource dropdown. Isi jika fitur tersebut dipakai; workflow API biasa cukup memakai API key.
4. Tekan **Save configuration**, lalu aktifkan switch n8n di Plugins. MCP `n8n` dan seluruh 15 skill tersedia bersama. Matikan switch untuk menonaktifkan keduanya.

Server MCP dan dokumentasi node dikirim bersama zip plugin terpisah; setelah diunduh, start server tidak membutuhkan `npx` atau unduhan dependency lain. API key tetap diperlukan untuk mengelola instance. Permission key menentukan operasi yang diizinkan; HTTP 401/403 menandakan credentials/scope perlu diperiksa, bukan keberhasilan koneksi. Endpoint offline harus diperbaiki di form konfigurasi.

Alamat remote harus dapat diakses melalui HTTPS publik. Guard SSRF upstream tetap menolak alamat private non-loopback dan metadata cloud; instance lokal memakai URL loopback. Policy webhook mengikuti mode tersebut.

Field key/token disamarkan, tetapi nilai tersimpan dalam config private `data/.ccode/cli/config.json` di namespace CCode. Jangan membagikan config atau snapshot namespace. Telemetry n8n-mcp dimatikan; penggunaan tool tetap menghubungi instance yang Anda konfigurasi dan layanan template/dokumentasi upstream sesuai tool.

## Backup dan restore data standalone

Tutup aplikasi lebih dulu; snapshot diambil offline agar index task, database sesi, dan file task konsisten sebagai satu set. Pengaturan Token savers di `data/.ccode/v2/token-savers.json` ikut snapshot namespace.

```bash
python3 scripts/data_backup.py backup  --root ~/.local/share/ccode --destination ~/ccode-backups/$(date +%F)
python3 scripts/data_backup.py verify  ~/ccode-backups/2026-10-12
python3 scripts/data_backup.py restore ~/ccode-backups/2026-10-12 --root ~/.local/share/ccode
```

Snapshot memakai SQLite backup API, menolak path traversal, dan menyimpan manifest berisi hash setiap entri. Symlink yang menunjuk di dalam namespace (mis. `node_modules/.bin/*` di workspace atau link tool MCP) dicatat sebagai `links` dan dibuat ulang saat restore; symlink yang keluar namespace, entri non-regular, dan alias root tetap ditolak. Restore menahan lock operasi eksklusif, menolak bila aplikasi masih berjalan, dan menyimpan namespace lama sebagai `<root>-pre-restore-<stamp>`.

Di Windows perintahnya sama dengan `--root %LOCALAPPDATA%\CCode`. Deteksi "aplikasi sedang berjalan" mencocokkan argumen `--user-data-dir` proses `CCode.exe` dengan `<root>\electron`, jadi snapshot root uji terisolasi tetap dapat diambil sementara instance default pengguna berjalan; lock antar-skrip memakai `LockFileEx`, bukan `flock`.

## Rollback

Build baru tidak aktif sampai `make apply`. Apply menolak jika executable project masih berjalan dan mencadangkan inventory resource dari `scripts/apply_build.py` ke `runtime/backups`: file `FILES` (`app.asar`, `glm/ccode.cjs`, `glm/.node-bundle-meta.json`, `app-update.yml`, `activity/main.cjs`, `token-savers/main.cjs`, `token-savers/token-savers-runtime.cjs`, prompt dan main module `commands/`, `marketplace/marketplace-compat.cjs`, `config/provider/ccode-builtin.json`), ikon packaged, pack skills, dan tree MCP; cache katalog per-endpoint disimpan di `derived/`. Promosi payload plugin menulis jurnal `runtime/backups/<stamp>/plugin-payload.json` (rename direktori, removal yang dicadangkan, rewrite berkas) dan memindahkan nama resource pra-rebrand (`glm/<ejaan-lama>.cjs`, `config/provider/<ejaan-lama>-builtin.json`) ke `legacy/` di cadangan yang sama. Untuk rollback patch, tutup aplikasi lalu pulihkan satu snapshot resource beserta cache yang sesuai, atau pulihkan namespace lewat `data_backup.py restore`. Baseline asli dapat dipakai untuk investigasi, tetapi mengembalikannya langsung akan menghapus UI custom.

Voice telah dihapus. Build membersihkan resource staged lama; apply menolak inventory yang masih membawanya dan memindahkan resource deployed `voice/` ke `runtime/backups/<stamp>/retired/voice` sebelum promote selesai. Kegagalan promote mengembalikannya bersama resource lain. Packaging menolak AppDir yang masih memuat resource pensiun itu. Model, venv, dan worker tidak dikirim lagi; profil Electron lama tidak dihapus agar pengaturan dan data lain tetap utuh.

Apply menyisakan **dua** cadangan terbaru (`BACKUP_RETENTION` di `scripts/apply_build.py`); cadangan lebih tua dihapus otomatis, begitu pula marker `ccode-builtin-refresh.json` di namespace (`ccode-builtin.json` tidak pernah disentuh). Rollback hanya mungkin dari dua promote terakhir, jadi promote besar sebaiknya diikuti verifikasi cepat sebelum promote berikutnya.

Pack native `glm/packages/bundled-skills` ikut diverifikasi dan dicadangkan saat apply. Cutover memensiunkan resource `glm/packages/ccode-skills-plugin`, tetapi tidak menghapus skills atau cache di namespace user. Untuk rollback cutover, pulihkan pack dan resource plugin lama dari cadangan yang sama dengan agent dan ASAR; jangan mencampur resource dari build berbeda.

Ukuran yang perlu dijaga: `app/resources` (aset live), `runtime/build` (staged), `runtime/backups` (dua cadangan), `runtime/cutover-backups` (snapshot migrasi, salinan `app/` sudah dibuang saat pembersihan 2026-10-13), dan `runtime/no-login` (fixture uji; salinan `app/`-nya reproducible dan tidak disimpan). Snapshot lama dari instalasi pra-rebrand tetap ada di direktori backup lamanya (default baru: `~/.local/share/ccode-backups`).

Integrasi lama dapat dipulihkan dengan menyalin kembali launcher/unit dari `<namespace>/integration-backups`, tetapi perhatikan: sejak rebrand CCode, `make install` memindahkan namespace ke `~/.local/share/ccode` dan memensiunkan launcher/unit pra-rebrand. Rollback penuh berarti memindahkan namespace kembali (`mv ~/.local/share/ccode ~/.local/share/<rebrand.PREVIOUS_NAMESPACE>`) dan mengembalikan launcher/unit dari backup; tanpa langkah itu aplikasi akan memakai root yang baru.

AppImage upstream tetap tersedia di `~/Applications`. Alias aktif di `~/Documents/Codex/tools/` yang dicatat dalam `project.json.compatibility_links`: `ccode-app` → `app/`, `screen-mcp` → `services/desktop`, dan `ccode-model-sync` → `services/model-sync`. Jangan menghapus symlink lama di home selama launcher atau unit pemakainya belum terbukti dipensiunkan. Sisi lama yang sudah dipensiunkan: unit vansrouter pra-rebrand (`rebrand.PREVIOUS_VANSROUTER_UNIT`) di-`disable --now` karena `WorkingDirectory`-nya hilang saat repo pindah ke `Documents/CCode`, dan pekerjaannya sudah diambil `ccode-model-sync.timer`.

Data task/account tidak dipindahkan ke repo. Timer model sync standalone dapat dimatikan dengan `systemctl --user disable --now ccode-model-sync.timer`; perintah yang sama dengan nama timer lama mematikan sync instalasi lama.
