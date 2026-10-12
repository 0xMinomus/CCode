# Arsitektur

## UI dan build

`project.json` menyimpan hash ASAR upstream asli, hash backend agent asli, identitas aplikasi standalone, dan nama tiga asset ASAR yang diubah. Build membaca baseline, mengganti anchor yang harus muncul tepat sekali, lalu menulis ASAR baru ke `runtime/build/resources` dengan offset dan integrity SHA256 yang dihitung ulang. Entri unpacked asli tetap mengacu pada `app/resources/app.asar.unpacked`.

Patch renderer:

1. Halaman `iOn` asli diubah menjadi `originalCuaSettings`.
2. Wrapper memilih `FedoraCuaSettings` untuk workspace Linux lokal; workspace lain memakai halaman asli.
3. Composer `mit` memilih pintasan Linux; `ZCodeVoiceInput` ditambahkan di dekat toolbar Computer Use.
4. Source custom ditambahkan pada modul renderer yang sama sehingga dapat menggunakan React dan komponen bundled.

Simbol versi ini: `Q` = React, `$` = JSX runtime, `X` = Button, `bA/xA/SA` = dropdown root/trigger/content, `TA/EA` = radio group/item, `DA/OA` = label/separator, `Iv` = MCP store, `gv` = settings hook. Simbol dan anchor dapat berubah pada update upstream. Jangan menebak bahwa nama ini stabil antarversi.

Patch standalone hidup di `src/local_only/` dan dijalankan setelah patch renderer:

1. `storage.py` menetapkan namespace data, profil, database task, database sesi agent, config MCP, dan menghapus migrasi/scan lintas instalasi. Ini juga berisi bootstrap env untuk chunk `out/main`, `out/host`, `out/scheduler`, dan backend agent.
2. `cloud.py` menghapus pemilik layanan akun/cloud di registry host, menghapus gerbang login renderer, dan memberi jawaban lokal untuk channel yang pemiliknya sudah tidak ada.
3. Backend agent di luar ASAR (`app/resources/glm/zcode.cjs`) dipatch dari baseline terpisah `baselines/zcode-3.14.5-original-agent.cjs` dengan hash di `project.json`.
4. `build-manifest.json` menyimpan SHA256 hasil staging untuk `app.asar`, `glm/zcode.cjs`, dan `voice/main.cjs`; `scripts/apply_build.py` menolak promote bila checksum tidak cocok dan mengembalikan ketiga resource bila salah satu penggantian gagal.

Anchor cloud terikat versi upstream dan sengaja gagal bila tidak unik. Jangan melemahkan assertion agar build terlihat berhasil.

## Desktop

UI mengatur MCP bernama `fedora-desktop`. `services/desktop/server.py` memuat `zcode_fast_profile.py` saat `MCP_SCREEN_PROFILE=zcode-fast`. Profil menawarkan 10 tool inti, default screenshot setelah aksi/batch, dan peluncur Gio untuk aplikasi terpasang. Capture/input menggunakan portal Fedora/PipeWire. OCR tidak wajib untuk model Vision. Kontrol mouse pengguna tetap menghentikan aksi agent.

## Voice

Preload mengekspos `window.zcodeVoice.start/stop/cancel`. IPC `zcode-voice:*` hanya menerima main frame lokal `out/renderer/index.html`. `src/main/voice.cjs`, yang disalin ke `app/resources/voice/main.cjs`, menemukan root project melalui `project.json`, lalu memakai `services/voice`.

Rekaman `pw-record` disimpan di direktori privat sementara, maksimal 60 detik. Worker Python dimuat saat pertama dipakai, mempertahankan model hangat selama aplikasi hidup, dan menerima request JSON via stdio. Audio didekode FFmpeg menjadi NumPy float32, lalu Whisper melakukan transkripsi. Jalur ini menghindari ketidakcocokan API decode PyAV yang ditemukan saat setup.

`terminology.py` memberikan prompt/hotwords bilingual dan koreksi terbatas “komputer rius/use” → “computer use”. Jangan mengubah normalizer menjadi pengganti umum yang menebak maksud semua ucapan.

## Model sync

`services/model-sync/sync.py` hanya melengkapi model yang sudah didaftarkan dalam provider `vansrouter` di ZCode. Metadata berasal dari snapshot OpenCode/models.dev, cache diperbarui paling sering sekali sehari, timer berjalan sekitar satu menit. Fingerprint pemetaan sebelumnya melindungi override manual. Model tak dikenal dan combo tidak ditebak. Tidak ada inference. Timer standalone `zcode-on-steroids-model-sync.timer` menunjuk config/state di dalam namespace lewat env `ZCODE_MODEL_SYNC_CONFIG`/`ZCODE_MODEL_SYNC_STATE`; tanpa env itu script tetap memakai jalur lama.

## Data pengguna

Aplikasi berjalan sebagai varian mandiri. Root default `~/.local/share/zcode-on-steroids`:

| Path | Isi |
|---|---|
| `data/.zcode/v2` | setting, provider config, `tasks-index.sqlite`, snapshot sesi |
| `data/.zcode/cli/db/db.sqlite` | database sesi/message agent |
| `data/.zcode/cli/config.json` | config MCP pengguna |
| `data/.zcode/workspace`, `plugin-workspace` | workspace percakapan dan plugin |
| `electron/` | profil Electron (localStorage voice, cookies) |
| `model-sync/` | state, cache, dan backup model sync varian ini |

`ZCODE_STANDALONE_ROOT` dapat memindahkan seluruh root (dipakai untuk pengujian terisolasi). `scripts/run.sh` menetapkan env namespace dan menahan lock operasi bersama; menjalankan `app/zcode` langsung juga memakai root yang sama karena bootstrap env berjalan sebelum modul membaca path.

Data instalasi lama di `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis. Import provider bersifat eksplisit lewat `scripts/install_local.py --import-provider-from` dan hanya menyalin provider personal ber-API-key beserta rule model manualnya. Compatibility symlink lama hanya menjaga proses yang belum direstart.
