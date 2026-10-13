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
2. `cloud.py` menghapus pemilik layanan akun/cloud di registry host, menghapus gerbang login renderer, dan memberi jawaban lokal untuk channel yang pemiliknya sudah tidak ada. Di main, jawabannya eksplisit pada `Ik`; di host, service yang masih diminta UI lokal diganti stub lewat `CLOUD_SERVICE_STUBS` (plugin store, automations, coding plan) supaya permintaan tidak berakhir timeout `Unknown channel`.
3. Backend agent di luar ASAR (`app/resources/glm/zcode.cjs`) dipatch dari baseline terpisah `baselines/zcode-3.14.5-original-agent.cjs` dengan hash di `project.json`.
4. Modul main lokal berbagi satu berkas `src/main/activity.cjs` → `app/resources/activity/main.cjs`: IPC `zcode-activity:summary` (Activity) dan `zcode-detect:run` (**Auto Detect** di Model settings, menjalankan `services/model-sync/sync.py --discover --bootstrap` untuk namespace aktif lalu mengembalikan ringkasan provider/model). Keduanya hanya menerima main frame lokal. Preload mengekspos `window.zcodeActivity` dan `window.zcodeDetect`.
5. `catalog.py` membersihkan katalog provider native dari keluarga Zhipu dan menambahkan template **9Router** (api-key, baseUrl `http://127.0.0.1:20128/v1`, model `combo/coding-harian`) secara idempotent; `apply_build.py` juga menyegarkan cache katalog per-endpoint di namespace karena salinan itu yang menang atas file bundled, lalu menghapus marker `zcode-builtin-refresh.json` yang dijadwalkan oleh host.
6. Refresh katalog built-in dari endpoint akun dimatikan di host: facade `refreshZCodeBuiltin` dan `ZCodeBuiltinRemoteSynchronizer.refresh` menjawab `"skipped"`, jadi tidak ada fetch ke `https://zcode.z.ai` dan release upstream tidak bisa menimpa katalog yang sudah dipatch (tanpa Zhipu, dengan 9Router).
7. Fitur akun/langganan dihapus dari akarnya: tombol Upgrade composer, section plan/usage di menu profil, tab app/coding-plan, grup **Providers** akun di Model settings (hanya Custom providers + template katalog yang tersisa; loading gate akun dipaku mati), dan remote control web/mobile (trigger, dialog, channel, hook status). Tanpa provider terkonfigurasi, pane detail Model settings merender empty state lokal (`ZCodeProviderEmptyState`, label ZCode sendiri) alih-alih kartu `common.loading` yang menunggu item navigasi yang tidak ada. Halaman Usage stats diganti **Activity** lokal: `src/main/activity.cjs` membaca `ZCODE_SESSION_DB_PATH` (`cli/db/db.sqlite`) read-only lewat `node:sqlite` (fallback snapshot bila WAL menolak handle read-only) dan menghitung prompt `role=user` per hari (seluruh riwayat) plus streak serta rekap per tahun; renderer memakainya lewat `window.zcodeActivity` (`src/renderer/activity-panel.js`). Katalog marketplace disaring di agen (`requiresPaidPlan` dibuang sebelum manifest), badge Coding Plan dimatikan di renderer, dan label akun di `IntlProvider-B-44tSXQ.js` ikut dipatch.
8. `build-manifest.json` menyimpan SHA256 hasil staging untuk `app.asar`, `glm/zcode.cjs`, `voice/main.cjs`, `activity/main.cjs`, dan `config/provider/zcode-builtin.json`; `scripts/apply_build.py` menolak promote bila checksum tidak cocok dan mengembalikan kelima resource bila salah satu penggantian gagal. Apply juga menyisakan **dua** cadangan terbaru di `runtime/backups` (`BACKUP_RETENTION`) supaya cadangan penuh tiap promote tidak menumpuk tanpa batas.

Anchor cloud terikat versi upstream dan sengaja gagal bila tidak unik. Jangan melemahkan assertion agar build terlihat berhasil. `cloud.guard_main` menutup celah yang tidak terlihat oleh anchor: setelah semua edit, build menolak main bundle yang masih mereferensikan binding/layanan yang sudah dihapus (`REMOVED_MAIN_SYMBOLS`) atau referensi `webRemoteControlManager` — hook `window closed` dan port telemetri host berjalan pada pemakaian normal, jadi referensi sisa berarti crash main process, bukan kode mati. `cloud.guard_remote_ipc_dependencies` memeriksa hal yang sama untuk region registrasi IPC yang diganti: setiap `e.<service>` yang dipanggil handler terdaftar harus dikirim ke `Ik({...})`, karena provider lokal (Docker/WSL/SSH) pernah hilang bersama region itu dan handler-nya gagal dengan "is not a function".

## Desktop

UI mengatur MCP bernama `fedora-desktop`. `services/desktop/server.py` memuat `zcode_fast_profile.py` saat `MCP_SCREEN_PROFILE=zcode-fast`. Profil menawarkan 10 tool inti, default screenshot setelah aksi/batch, dan peluncur Gio untuk aplikasi terpasang. Capture/input menggunakan portal Fedora/PipeWire. OCR tidak wajib untuk model Vision. Kontrol mouse pengguna tetap menghentikan aksi agent.

## Voice

Preload mengekspos `window.zcodeVoice.start/stop/cancel`. IPC `zcode-voice:*` hanya menerima main frame lokal `out/renderer/index.html`. `src/main/voice.cjs`, yang disalin ke `app/resources/voice/main.cjs`, menemukan root project melalui `project.json`, lalu memakai `services/voice`.

Rekaman `pw-record` disimpan di direktori privat sementara, maksimal 60 detik. Worker Python dimuat saat pertama dipakai, mempertahankan model hangat selama aplikasi hidup, dan menerima request JSON via stdio. Audio didekode FFmpeg menjadi NumPy float32, lalu Whisper melakukan transkripsi. Jalur ini menghindari ketidakcocokan API decode PyAV yang ditemukan saat setup.

`terminology.py` memberikan prompt/hotwords bilingual dan koreksi terbatas “komputer rius/use” → “computer use”. Jangan mengubah normalizer menjadi pengganti umum yang menebak maksud semua ucapan.

## Model sync

`services/model-sync/sync.py` mengerjakan dua hal untuk namespace standalone:

1. **Discovery 9Router** (aktif begitu provider keluarga 9Router ada): menarik `GET /v1/models` dari gateway lokal, mengelompokkan per namespace (combo terpisah, ambang 10 model, sisanya `· lainnya`), lalu menulis provider + manual rule di `provider_config.json`. Template katalog tidak menyemai model, jadi pengisian pertama datang dari discovery. Pemicunya: unit path systemd pada `provider_config.json` (write dari app), kondisi `needs_fill` untuk provider kosong/belum dikelompokkan, dan timer 60 detik dengan TTL 12 jam. Backoff 15 menit saat gateway mati, dan `make models` untuk memaksa. Metadata diambil dari `capabilities` gateway; snapshot models.dev hanya sebagai fallback; model tanpa limit dilewati dan dicatat. `commit()` menolak write yang mengurangi inventori model, dan hilangnya model secara massal diperlakukan sebagai file ditulis ulang (diisi ulang, bukan di-blacklist).
2. **Enrich reasoning Vansrouter**: hanya melengkapi model yang sudah didaftarkan dalam provider `vansrouter` di ZCode. Metadata berasal dari snapshot OpenCode/models.dev, cache diperbarui paling sering sekali hari, timer berjalan sekitar satu menit.

Aturan yang sama berlaku untuk keduanya: fingerprint pemetaan sebelumnya melindungi override manual, switch per model (`rule.config.enabled`) dipertahankan, model/rule yang dihapus user tidak dihidupkan lagi, dan schema host divalidasi (mis. `optionSpecs.reasoningLevel` wajib ada; model dengan rule katalog tidak boleh juga punya rule manual). Model tak dikenal dan combo tidak ditebak, dan tidak ada inference. Timer standalone `zcode-on-steroids-model-sync.timer` menunjuk config/state di dalam namespace lewat env `ZCODE_MODEL_SYNC_CONFIG`/`ZCODE_MODEL_SYNC_STATE`; tanpa env itu script tetap memakai jalur lama.

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
