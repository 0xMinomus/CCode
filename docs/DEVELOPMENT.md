# Pengembangan lewat ohmypi

Jalankan `omp` dari root project. Mulai dengan meminta pembacaan AGENTS.md, lalu jelaskan perubahan dan hasil yang diinginkan.

## UI atau IPC

Edit `src/renderer/voice-input.js`, `src/renderer/linux-computer-use.js`, atau `src/main/voice.cjs`. Gunakan `make build && make test`. Hasil masih staged. Tutup ZCode sebelum `make apply`, lalu buka melalui `make run`/launcher. `make install` hanya diperlukan bila path integrasi berubah.

Untuk preview terisolasi, jalankan `app/zcode` dengan `ZCODE_DESKTOP_APPLICATION_NAME`, `ZCODE_DESKTOP_USER_DATA_DIR`, dan `ZCODE_DATA_BASE_DIR` menunjuk profil di `runtime/preview`. Sejak patch standalone, cara paling sederhana adalah menetapkan `ZCODE_STANDALONE_ROOT` ke direktori uji lalu memakai `scripts/run.sh`; bootstrap env akan mengisi seluruh namespace (data, profil, database task/sesi, config MCP) dari root tersebut.

Ini bukan sandbox penuh: sebagian jalur masih menyentuh path di luar namespace (misalnya ikon/deep-link AppImage dan pembacaan config oleh proses yang belum direstart). Uji dengan root terpisah, jangan mengubah live MCP, dan jangan mengirim prompt saat hanya menguji UI. Port debugging lokal hanya digunakan untuk inspeksi pengembangan; jangan memasukkannya dalam launcher harian.

Jangan mengekspor env namespace di shell harian. Beberapa skrip menolak berjalan ketika menemukan variabel `ZCODE_STANDALONE_ROOT` pada proses lain; shell persisten yang menyimpan variabel itu akan dianggap sebagai aplikasi yang masih aktif. Bersihkan env sebelum menjalankan `make install`, `data_backup.py`, atau verifikasi lain.

Pemeriksaan smoke minimal setelah `make build && make test`:

1. Jalankan `scripts/run.sh` dengan `ZCODE_STANDALONE_ROOT` uji; pastikan workspace terbuka tanpa layar login.
2. Pastikan tidak ada `Unknown channel`, `No handler registered`, `ReferenceError`, atau `TypeError` pada log.
3. Kirim satu prompt pendek ke provider personal yang sudah dikonfigurasi, lalu restart dan pastikan task masih ada.
4. Jalankan `python3 scripts/data_backup.py backup|verify|restore` pada root uji.

Setelah mengubah README, AGENTS, atau `docs/`, jalankan `make obsidian`: bila folder project ini dipakai sebagai vault (`.obsidian/` ada) perintah itu hanya menyegarkan `Index.md`, sedangkan untuk vault terpisah perintah itu menyalin dokumen plus frontmatter tag. `make obsidian-check` memeriksa selisih tanpa menulis.

## Backend

- Desktop: edit `services/desktop/zcode_fast_profile.py`; source vendor juga tersedia untuk investigasi. Mulai chat baru setelah restart ZCode agar daftar tool baru dimuat.
- Voice: edit `services/voice/worker.py` / `terminology.py`. Restart ZCode untuk melepas worker yang masih menyimpan kode/model lama.
- Model sync: edit `services/model-sync/sync.py`; jalankan unit test lalu `systemctl --user start zcode-on-steroids-model-sync.service` untuk namespace standalone (atau `zcode-vansrouter-model-sync.service` bila memang ingin menyentuh konfigurasi instalasi lama).

Venv dan model sudah dipindahkan. Untuk mesin baru, buat kembali venv, pasang dependency yang tercatat, sediakan PyGObject/GStreamer/PipeWire/portal/wl-clipboard untuk desktop dan FFmpeg/pw-record untuk voice. Jangan menyalin venv antarversi Python lalu menganggapnya portabel.

## Update ZCode upstream

Simpan baseline baru di baselines, baca package identity/hash, lalu perbarui project.json setelah meninjau versi. Cari kembali asset renderer dan simbol komponen. Build sengaja gagal saat anchor berubah; jangan menghapus assertion agar build terlihat berhasil. Verifikasi Computer Use, reasoning, Voice, profile pengguna, dan rollback sebelum mengganti launcher.
