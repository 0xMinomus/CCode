# Operasi dan rollback

Aplikasi aktif: `app/zcode`, dijalankan sebagai varian mandiri lewat `scripts/run.sh`. Launcher `zcode-on-steroids.desktop` dan timer `zcode-on-steroids-model-sync.timer` adalah integrasi baru; launcher `zcode.desktop`, shortcut AppImage, dan timer `zcode-vansrouter-model-sync.timer` milik instalasi lama tidak diubah. MCP mengarah ke `services/desktop/bin/screen-mcp`.

```bash
make dry-run
make install
systemctl --user status zcode-on-steroids-model-sync.timer
journalctl --user -u zcode-on-steroids-model-sync.service -n 20
```

`make install` menulis config MCP di dalam namespace standalone, launcher baru, dan unit timer baru. Provider API keys tidak diubah. Cadangan integrasi tersimpan di `<namespace>/integration-backups` dengan izin 0600.

## Backup dan restore data standalone

Tutup aplikasi lebih dulu; snapshot diambil offline agar index task, database sesi, dan file task konsisten sebagai satu set.

```bash
python3 scripts/data_backup.py backup  --root ~/.local/share/zcode-on-steroids --destination ~/zcode-backups/$(date +%F)
python3 scripts/data_backup.py verify  ~/zcode-backups/2026-10-12
python3 scripts/data_backup.py restore ~/zcode-backups/2026-10-12 --root ~/.local/share/zcode-on-steroids
```

Snapshot memakai SQLite backup API, menolak symlink dan path traversal, dan menyimpan manifest berisi hash setiap entri. Restore menahan lock operasi eksklusif, menolak bila aplikasi masih berjalan, dan menyimpan namespace lama sebagai `<root>-pre-restore-<stamp>`.

## Rollback

Build baru tidak aktif sampai `make apply`. Apply menolak jika executable project masih berjalan dan menyimpan resource sebelumnya (`app.asar`, `glm/zcode.cjs`, `voice/main.cjs`, `activity/main.cjs`, `config/provider/zcode-builtin.json`) di `runtime/backups`, beserta cache katalog per-endpoint di `runtime/backups/<stamp>/derived/`. Untuk rollback patch, tutup aplikasi lalu salin kembali kelima file dan cache tersebut, atau pulihkan namespace lewat `data_backup.py restore`. Baseline asli dapat dipakai untuk investigasi, tetapi mengembalikannya langsung akan menghapus UI custom.

Apply menyisakan **dua** cadangan terbaru (`BACKUP_RETENTION` di `scripts/apply_build.py`); cadangan lebih tua dihapus otomatis, begitu pula marker `zcode-builtin-refresh.json` di namespace (`zcode-builtin.json` tidak pernah disentuh). Rollback hanya mungkin dari dua promote terakhir, jadi promote besar sebaiknya diikuti verifikasi cepat sebelum promote berikutnya.

Ukuran yang perlu dijaga: `app/resources` (aset live), `runtime/build` (staged), `runtime/backups` (dua cadangan), `runtime/cutover-backups` (snapshot migrasi, salinan `app/` sudah dibuang saat pembersihan 2026-10-13), dan `runtime/no-login` (fixture uji; salinan `app/`-nya reproducible dan tidak disimpan). Snapshot namespace lama tetap di `~/.local/share/zcode-on-steroids-backups`.

Integrasi lama dapat dipulihkan dengan menyalin kembali launcher/unit dari `<namespace>/integration-backups`; timer lama tetap berjalan sendiri karena tidak pernah dimatikan.

AppImage ZCode asli tetap tersedia di Applications. Versi modifikasi sebelumnya masih tersedia di direktori tools lama selain empat komponen yang dipindahkan. Path empat komponen tersebut sekarang symlink ke project baru. Jangan menghapus symlink sampai aplikasi lama benar-benar ditutup dan referensi eksternal sudah diperbarui.

Preferences voice disimpan dalam localStorage profil Electron standalone (`<root>/electron`): `zcode-voice-send-mode` (`review`/`auto`) dan `zcode-voice-language` (`id`/`en`/`auto`). Data task/account tidak dipindahkan ke repo. Timer model sync standalone dapat dimatikan dengan `systemctl --user disable --now zcode-on-steroids-model-sync.timer`; perintah yang sama dengan nama timer lama mematikan sync instalasi lama.
