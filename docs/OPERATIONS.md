# Operasi dan rollback

Aplikasi aktif: `app/ccode`, dijalankan sebagai varian mandiri lewat `scripts/run.sh` (nama ini berasal dari rebrand CCode; `make apply` yang mengganti nama binary/launcher/ikon AppDir). Launcher `ccode.desktop` dan timer `ccode-model-sync.timer` adalah integrasi baru; launcher `zcode.desktop`, shortcut AppImage, dan timer `zcode-vansrouter-model-sync.timer` milik instalasi lama tidak diubah. MCP mengarah ke `services/desktop/bin/screen-mcp`.

```bash
make dry-run
make install
systemctl --user status ccode-model-sync.timer
journalctl --user -u ccode-model-sync.service -n 20
```

`make install` menulis config MCP di dalam namespace standalone, launcher `ccode.desktop`, ikon hicolor (`ccode.png` per ukuran + `ccode.svg`), dan unit timer/path `ccode-model-sync.*` yang memantau `provider_config.json` supaya model 9Router terisi begitu provider dibuat/diubah dari UI. Provider API keys tidak diubah. Bila namespace lama masih ada dan root baru belum ada, install juga memindahkan `~/.local/share/zcode-on-steroids` → `~/.local/share/ccode` (rename, bukan salin), lalu memensiunkan launcher `zcode-on-steroids.desktop` dan unit `zcode-on-steroids-model-sync.*` (di-`disable --now` lebih dulu). Cadangan semua file integrasi yang diganti/dihapus tersimpan di `<namespace>/integration-backups` dengan izin 0600. Install juga menyegarkan `gtk-update-icon-cache` untuk `~/.local/share/icons/hicolor`: tanpa itu shell bisa tetap memakai ikon fallback karena `icon-theme.cache` dibuat sebelum `ccode.png` ada. Data ikon yang salah pakai bisa dipastikan lewat `strings ~/.local/share/icons/hicolor/icon-theme.cache | grep ccode` (harus ada) dan `Gtk.IconTheme` resolve ke `.../apps/ccode.png`.

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

MCP lain (mis. n8n atau GitHub) dapat ditambahkan sendiri lewat tombol **New** di halaman yang sama; tidak ada entri bawaan untuk keduanya. MCP resmi `image_search` tidak dimuat karena memerlukan autentikasi akun Z.ai.

## Backup dan restore data standalone

Tutup aplikasi lebih dulu; snapshot diambil offline agar index task, database sesi, dan file task konsisten sebagai satu set.

```bash
python3 scripts/data_backup.py backup  --root ~/.local/share/ccode --destination ~/ccode-backups/$(date +%F)
python3 scripts/data_backup.py verify  ~/ccode-backups/2026-10-12
python3 scripts/data_backup.py restore ~/ccode-backups/2026-10-12 --root ~/.local/share/ccode
```

Snapshot memakai SQLite backup API, menolak symlink dan path traversal, dan menyimpan manifest berisi hash setiap entri. Restore menahan lock operasi eksklusif, menolak bila aplikasi masih berjalan, dan menyimpan namespace lama sebagai `<root>-pre-restore-<stamp>`.

## Rollback

Build baru tidak aktif sampai `make apply`. Apply menolak jika executable project masih berjalan dan menyimpan resource sebelumnya (`app.asar`, `glm/zcode.cjs`, `voice/main.cjs`, `activity/main.cjs`, `config/provider/zcode-builtin.json`) di `runtime/backups`, beserta cache katalog per-endpoint di `runtime/backups/<stamp>/derived/`. Untuk rollback patch, tutup aplikasi lalu salin kembali kelima file dan cache tersebut, atau pulihkan namespace lewat `data_backup.py restore`. Baseline asli dapat dipakai untuk investigasi, tetapi mengembalikannya langsung akan menghapus UI custom.

Apply menyisakan **dua** cadangan terbaru (`BACKUP_RETENTION` di `scripts/apply_build.py`); cadangan lebih tua dihapus otomatis, begitu pula marker `zcode-builtin-refresh.json` di namespace (`zcode-builtin.json` tidak pernah disentuh). Rollback hanya mungkin dari dua promote terakhir, jadi promote besar sebaiknya diikuti verifikasi cepat sebelum promote berikutnya.

Pack native `glm/packages/bundled-skills` ikut diverifikasi dan dicadangkan saat apply. Cutover memensiunkan resource `glm/packages/ccode-skills-plugin`, tetapi tidak menghapus skills atau cache di namespace user. Untuk rollback cutover, pulihkan pack dan resource plugin lama dari cadangan yang sama dengan agent dan ASAR; jangan mencampur resource dari build berbeda.

Ukuran yang perlu dijaga: `app/resources` (aset live), `runtime/build` (staged), `runtime/backups` (dua cadangan), `runtime/cutover-backups` (snapshot migrasi, salinan `app/` sudah dibuang saat pembersihan 2026-10-13), dan `runtime/no-login` (fixture uji; salinan `app/`-nya reproducible dan tidak disimpan). Snapshot lama tetap di `~/.local/share/zcode-on-steroids-backups` (default baru: `~/.local/share/ccode-backups`).

Integrasi lama dapat dipulihkan dengan menyalin kembali launcher/unit dari `<namespace>/integration-backups`, tetapi perhatikan: sejak rebrand CCode, `make install` memindahkan namespace ke `~/.local/share/ccode` dan memensiunkan launcher/unit ZCode-era. Rollback penuh berarti memindahkan namespace kembali (`mv ~/.local/share/ccode ~/.local/share/zcode-on-steroids`) dan mengembalikan launcher/unit dari backup; tanpa langkah itu aplikasi akan memakai root yang baru.

AppImage ZCode asli tetap tersedia di `~/Applications`. Empat symlink alias di `~/Documents/Codex/tools/` menunjuk ke komponen project ini: `ccode-app` → `app/`, `screen-mcp` → `services/desktop`, `ccode-voice` → `services/voice`, `ccode-model-sync` → `services/model-sync` (nama ZCode-era `zcode-linux-cua-voice-v2`/`zcode-voice`/`zcode-vansrouter-sync` diganti; daftarnya dicatat di `project.json.compatibility_links`). Jangan menghapus symlink selama launcher atau unit lama belum benar-benar dipensiunkan. Sisi lama yang sudah dipensiunkan: timer `zcode-vansrouter-model-sync.timer` di-`disable --now` karena `WorkingDirectory`-nya hilang saat repo pindah ke `Documents/CCode`, dan pekerjaannya sudah diambil `ccode-model-sync.timer`.

Preferences voice disimpan dalam localStorage profil Electron standalone (`<root>/electron`): `zcode-voice-send-mode` (`review`/`auto`) dan `zcode-voice-language` (`id`/`en`/`auto`). Data task/account tidak dipindahkan ke repo. Timer model sync standalone dapat dimatikan dengan `systemctl --user disable --now ccode-model-sync.timer`; perintah yang sama dengan nama timer lama mematikan sync instalasi lama.
