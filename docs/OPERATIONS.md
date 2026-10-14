# Operasi dan rollback

Aplikasi aktif: `app/ccode`, dijalankan sebagai varian mandiri lewat `scripts/run.sh` (nama ini berasal dari rebrand CCode; `make apply` yang mengganti nama binary/launcher/ikon AppDir). Launcher `ccode.desktop` dan timer `ccode-model-sync.timer` adalah integrasi baru; launcher dan unit pra-rebrand serta shortcut AppImage lama dipensiunkan oleh `make install` (nama lama ada di konstanta `rebrand.PREVIOUS_*`). MCP mengarah ke `services/desktop/bin/screen-mcp`.

```bash
make dry-run
make install
make migrate
systemctl --user status ccode-model-sync.timer
journalctl --user -u ccode-model-sync.service -n 20
```

`make install` menulis config MCP di dalam namespace standalone, launcher `ccode.desktop`, ikon hicolor (`ccode.png` per ukuran + `ccode.svg`), dan unit timer/path `ccode-model-sync.*` yang memantau `provider_config.json` supaya model 9Router terisi begitu provider dibuat/diubah dari UI. Provider API keys tidak diubah. Bila namespace pra-rebrand (`rebrand.PREVIOUS_NAMESPACE`) masih ada dan root baru belum ada, install juga memindahkannya ke `~/.local/share/ccode` (rename, bukan salin), lalu memensiunkan launcher pra-rebrand (`rebrand.PREVIOUS_LAUNCHER_FILE`/`PREVIOUS_LAUNCHER`) dan unit `*-model-sync` lama (`rebrand.PREVIOUS_UNIT`/`PREVIOUS_VANSROUTER_UNIT`, di-`disable --now` lebih dulu) serta lock namespace usang (`rebrand.PREVIOUS_LOCK`). Cadangan semua file integrasi yang diganti/dihapus tersimpan di `<namespace>/integration-backups` dengan izin 0600. Install juga menyegarkan `gtk-update-i…

`make migrate` (`scripts/migrate_identity.py`) mengubah instalasi yang sudah ada ke ejaan baru dengan aplikasi tertutup: snapshot lewat `scripts/data_backup.py` (lewati dengan `--no-backup`), rename setiap path yang memuat token pra-rebrand (terdalam dulu), rewrite token di config/state/log di luar workspace, rewrite setiap kolom teks database (`data/.ccode/cli/db/db.sqlite`, `data/.ccode/v2/tasks-index.sqlite`), lalu hapus direktori layout lama yang kosong. `--dry-run` hanya melaporkan apa yang akan berubah.

Periksa/matikan integrasi sync bila perlu:

```bash
systemctl --user status ccode-model-sync.path ccode-model-sync.timer
journalctl --user -u ccode-model-sync.service -n 20
systemctl --user disable --now ccode-model-sync.path      # hentikan pengisian instan
systemctl --user disable --now ccode-model-sync.timer     # hentikan sync rutin
```

## MCP di Settings

Context7 dan Codegraph tersedia setelah instalasi aplikasi. **Settings → MCP Servers** menampilkan daftar **Installed** server native; LSP dan Ripgrep tersedia sebagai baris katalog dengan tombol **Install** di slot switch, tanpa label `Optional`. Setelah di-Install, baris native dengan switch on/off menggantikan baris katalog.

LSP membutuhkan language server untuk bahasa proyek (TypeScript/JavaScript dipasang bersama entri ini). Ripgrep mencari berkas lokal. Pemasangan melalui tombol **Install** memakai registry npm dan direktori privat di dalam namespace (`mcp/packages`), tanpa Node/npm sistem.

Default tidak berarti semua proses server berjalan terus; runtime MCP tetap mengikuti pemuatan oleh agent. Context7 memakai jaringan saat tool dokumentasi dipanggil. Codegraph menyimpan indeks lokal proyek. Mematikan atau menghapus server lewat pengelolaan native tidak dibatalkan oleh bootstrap berikutnya.

MCP lain (mis. GitHub) dapat ditambahkan sendiri lewat tombol **New** di halaman yang sama. MCP resmi `image_search` tidak dimuat karena memerlukan autentikasi akun Z.ai.

## Plugin n8n

1. Buka **Settings → Plugins → n8n**, atau pilih n8n di **Plugin Marketplace**.
2. Buka **Advanced details → Configuration**. Isi **n8n instance URL** (base URL tanpa `/api/v1`) dan **n8n API key** dari Settings → n8n API pada instance Anda. Gunakan HTTPS untuk instance remote; HTTP hanya diterima untuk loopback.
3. Token **n8n instance MCP access token** hanya diperlukan oleh fitur MCP instance seperti persisted agents dan resource dropdown. Isi jika fitur tersebut dipakai; workflow API biasa cukup memakai API key.
4. Tekan **Save configuration**, lalu aktifkan switch n8n di Plugins. MCP `n8n` dan seluruh 15 skill tersedia bersama. Matikan switch untuk menonaktifkan keduanya.

Server MCP dan dokumentasi node dikirim bersama aplikasi; tidak membutuhkan `npx` saat start. API key tetap diperlukan untuk mengelola instance. Permission key menentukan operasi yang diizinkan; HTTP 401/403 menandakan credentials/scope perlu diperiksa, bukan keberhasilan koneksi. Endpoint offline harus diperbaiki di form konfigurasi.

Alamat remote harus dapat diakses melalui HTTPS publik. Guard SSRF upstream tetap menolak alamat private non-loopback dan metadata cloud; instance lokal memakai URL loopback. Policy webhook mengikuti mode tersebut.

Field key/token disamarkan, tetapi nilai tersimpan dalam config private `data/.ccode/cli/config.json` di namespace CCode. Jangan membagikan config atau snapshot namespace. Telemetry n8n-mcp dimatikan; penggunaan tool tetap menghubungi instance yang Anda konfigurasi dan layanan template/dokumentasi upstream sesuai tool.

## Backup dan restore data standalone

Tutup aplikasi lebih dulu; snapshot diambil offline agar index task, database sesi, dan file task konsisten sebagai satu set. Pengaturan Token savers di `data/.ccode/v2/token-savers.json` ikut snapshot namespace.

```bash
python3 scripts/data_backup.py backup  --root ~/.local/share/ccode --destination ~/ccode-backups/$(date +%F)
python3 scripts/data_backup.py verify  ~/ccode-backups/2026-10-12
python3 scripts/data_backup.py restore ~/ccode-backups/2026-10-12 --root ~/.local/share/ccode
```

Snapshot memakai SQLite backup API, menolak symlink dan path traversal, dan menyimpan manifest berisi hash setiap entri. Restore menahan lock operasi eksklusif, menolak bila aplikasi masih berjalan, dan menyimpan namespace lama sebagai `<root>-pre-restore-<stamp>`.

## Rollback

Build baru tidak aktif sampai `make apply`. Apply menolak jika executable project masih berjalan dan mencadangkan inventory resource dari `scripts/apply_build.py` ke `runtime/backups`: file `FILES` (`app.asar`, `glm/ccode.cjs`, `glm/.node-bundle-meta.json`, `app-update.yml`, `voice/main.cjs`, `activity/main.cjs`, `token-savers/main.cjs`, `token-savers/token-savers-runtime.cjs`, `config/provider/ccode-builtin.json`), ikon packaged, pack skills, dan tree MCP; cache katalog per-endpoint disimpan di `derived/`. Promosi payload plugin menulis jurnal `runtime/backups/<stamp>/plugin-payload.json` (rename direktori, removal yang dicadangkan, rewrite berkas) dan memindahkan nama resource pra-rebrand (`glm/<ejaan-lama>.cjs`, `config/provider/<ejaan-lama>-builtin.json`) ke `legacy/` di cadangan yang sama; kegagalan memulihkan semuanya dari jurnal itu. Untuk rollback patch, tutup aplikasi lalu pulihkan satu snapshot resource beserta cache yang sesuai, atau pulihkan namespace lewat `data_backup.py restore`. Baseline asli dapat dipakai untuk investigasi, tetapi mengembalikannya langsung akan menghapus UI custom.

Apply menyisakan **dua** cadangan terbaru (`BACKUP_RETENTION` di `scripts/apply_build.py`); cadangan lebih tua dihapus otomatis, begitu pula marker `ccode-builtin-refresh.json` di namespace (`ccode-builtin.json` tidak pernah disentuh). Rollback hanya mungkin dari dua promote terakhir, jadi promote besar sebaiknya diikuti verifikasi cepat sebelum promote berikutnya.

Pack native `glm/packages/bundled-skills` ikut diverifikasi dan dicadangkan saat apply. Cutover memensiunkan resource `glm/packages/ccode-skills-plugin`, tetapi tidak menghapus skills atau cache di namespace user. Untuk rollback cutover, pulihkan pack dan resource plugin lama dari cadangan yang sama dengan agent dan ASAR; jangan mencampur resource dari build berbeda.

Ukuran yang perlu dijaga: `app/resources` (aset live), `runtime/build` (staged), `runtime/backups` (dua cadangan), `runtime/cutover-backups` (snapshot migrasi, salinan `app/` sudah dibuang saat pembersihan 2026-10-13), dan `runtime/no-login` (fixture uji; salinan `app/`-nya reproducible dan tidak disimpan). Snapshot lama dari instalasi pra-rebrand tetap ada di direktori backup lamanya (default baru: `~/.local/share/ccode-backups`).

Integrasi lama dapat dipulihkan dengan menyalin kembali launcher/unit dari `<namespace>/integration-backups`, tetapi perhatikan: sejak rebrand CCode, `make install` memindahkan namespace ke `~/.local/share/ccode` dan memensiunkan launcher/unit pra-rebrand. Rollback penuh berarti memindahkan namespace kembali (`mv ~/.local/share/ccode ~/.local/share/<rebrand.PREVIOUS_NAMESPACE>`) dan mengembalikan launcher/unit dari backup; tanpa langkah itu aplikasi akan memakai root yang baru.

AppImage upstream tetap tersedia di `~/Applications`. Empat symlink alias di `~/Documents/Codex/tools/` menunjuk ke komponen project ini: `ccode-app` → `app/`, `screen-mcp` → `services/desktop`, `ccode-voice` → `services/voice`, `ccode-model-sync` → `services/model-sync` (nama pra-rebrand komponen yang sama sudah diganti; daftarnya dicatat di `project.json.compatibility_links`). Jangan menghapus symlink selama launcher atau unit lama belum benar-benar dipensiunkan. Sisi lama yang sudah dipensiunkan: unit vansrouter pra-rebrand (`rebrand.PREVIOUS_VANSROUTER_UNIT`) di-`disable --now` karena `WorkingDirectory`-nya hilang saat repo pindah ke `Documents/CCode`, dan pekerjaannya sudah diambil `ccode-model-sync.timer`.

Preferences voice disimpan dalam localStorage profil Electron standalone (`<root>/electron`): `ccode-voice-send-mode` (`review`/`auto`) dan `ccode-voice-language` (`id`/`en`/`auto`). Data task/account tidak dipindahkan ke repo. Timer model sync standalone dapat dimatikan dengan `systemctl --user disable --now ccode-model-sync.timer`; perintah yang sama dengan nama timer lama mematikan sync instalasi lama.
