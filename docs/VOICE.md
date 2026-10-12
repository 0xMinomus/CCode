# Voice

Source UI: `src/renderer/voice-input.js`. Rekaman/IPC: `src/main/voice.cjs`. Transcriber dan kosakata: `services/voice/worker.py` dan `terminology.py`.

- ID adalah bahasa yang diprioritaskan, bukan larangan istilah Inggris. Prompt/hotwords menyediakan vocabulary teknis; normalization hanya memperbaiki variasi yang telah disepakati.
- EN mengutamakan Inggris; Auto memilih ID/EN berdasarkan deteksi. Jangan mengubah nama aplikasi atau maksud umum dengan penggantian luas.
- Pilihan kirim dan bahasa memakai localStorage profil Electron standalone (`~/.local/share/zcode-on-steroids/electron`). Cek teks adalah default; auto-send hanya setelah user memilihnya.
- Audio tidak dikirim ke provider. Teks yang dikirim ke chat mengikuti model ZCode yang dipilih, seperti teks diketik.
- Model kecil multilingual tersimpan di `services/voice/model`, venv di `.venv`. Worker hangat bertahan selama app hidup; tutup/buka app untuk memuat kode/model baru.
- Main frame lokal divalidasi sebelum IPC; recorder dimiliki satu window, timeout 60 detik, dan temporary audio dibersihkan. Jangan menghapus pemeriksaan ini saat merapikan UI.

Unit test normalizer dijalankan `make test`. Untuk tes transkripsi, gunakan audio sintetis ke `worker.py` melalui JSON stdio (`id`, `path`, `language`), atau klik Voice dan bicara pada profil uji yang memang ingin dipakai. Jangan merekam mikrofon diam-diam untuk smoke test. Transkripsi sintetis tidak menjamin akurasi suara/mikrofon asli.

Dependensi bekerja dengan FFmpeg decode ke NumPy float32 agar kompatibel dengan versi PyAV yang terpasang. Bila decoder diubah, uji WAV yang dihasilkan pw-record, speech campuran, serta silence.
