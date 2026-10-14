# Arsitektur

## UI dan build

`project.json` menyimpan hash ASAR upstream asli, hash backend agent asli, identitas aplikasi standalone, dan nama tiga asset ASAR yang diubah. Build membaca baseline, mengganti anchor yang harus muncul tepat sekali, lalu menulis ASAR baru ke `runtime/build/resources` dengan offset dan integrity SHA256 yang dihitung ulang. Entri unpacked asli tetap mengacu pada `app/resources/app.asar.unpacked`.

Patch renderer:

1. Halaman `iOn` asli diubah menjadi `originalCuaSettings`.
2. Wrapper memilih `FedoraCuaSettings` untuk workspace Linux lokal; workspace lain memakai halaman asli.
3. Composer `mit` memilih pintasan Linux; `ZCodeVoiceInput` ditambahkan di dekat toolbar Computer Use.
4. Source custom ditambahkan pada modul renderer yang sama sehingga dapat menggunakan React dan komponen bundled.

Simbol versi ini: `Q` = React, `$` = JSX runtime, `X` = Button, `bA/xA/SA` = dropdown root/trigger/content, `TA/EA` = radio group/item, `DA/OA` = label/separator, `Iv` = MCP store, `gv` = settings hook, `uA` = Tooltip (dipakai sel heatmap Activity dan pintasan Computer Use; props `title`, `side`, `children`). Simbol dan anchor dapat berubah pada update upstream. Jangan menebak bahwa nama ini stabil antarversi.

Sidebar Settings desktop Linux mempertahankan strip drag-window 16px di bagian atas (bukan spacer upstream 48px), sehingga tombol Back to workspace dan daftar menu naik 32px. Patch anchor unik berada di `cloud._renderer`; layout macOS/Windows, padding menu, dan footer tidak berubah.

### Halaman Activity

`src/renderer/activity-panel.js` memakai tata letak halaman Usage upstream yang lama (komponen `Bwn`/`vwn`/`p7` di baseline): strip lima metrik (`flex flex-col overflow-hidden rounded-xl bg-surface sm:flex-row sm:items-center` dengan pemisah `hidden h-7 w-px bg-border sm:block`, nilai `text-ui-lg font-medium` di atas label `text-ui-base text-foreground-subtle`), lalu kartu `rounded-xl bg-surface px-3 py-3` berisi judul + kontrol segmen (`flex flex-wrap items-center gap-0.5 rounded-full bg-surface p-0.5`, segmen aktif `bg-background text-foreground`, tidak aktif `text-foreground-subtle`), grid heatmap `style={{gridTemplateColumns:'repeat(N, minmax(0, 1fr))'}}` dengan sel `aspect-square w-full min-w-0 rounded-[4px] border` berwarna `var(--color-usage-heatmap-0..4)`, dan label bulan di bawah grid.

Segmen adalah **tahun**, bukan rentang: `ZCodeActivityYears` menggabungkan tahun yang punya prompt (dari `summarize`) dengan tahun berjalan, urut menaik, dan tahun terakhir (tahun berjalan) dipilih sebagai default — pada 2027 segmen baru muncul otomatis di kanan dan 2026 bergeser ke kiri. Grid selalu satu tahun kalender penuh: 1 Januari–31 Desember, 365 sel (366 pada tahun kabisat), label Jan–Des di bawah, tanpa label hari. Hover sel memakai komponen tooltip bundled `uA` (pola yang sama dengan heatmap upstream), bukan atribut `title` bawaan browser; gaya hover kotak tetap `hover:scale-110 hover:border-border-hover`.

CSS renderer adalah hasil build Tailwind statis dari upstream: kelas yang tidak dipakai di sana (mis. `grid-cols-5`, `divide-x`, `h-[11px]`, `bg-foreground/5`, `bg-primary/25`) tidak punya aturan sama sekali, jadi utilitas seperti itu tidak berefek walau ditulis di JSX. Saat mengubah panel ini, pakai kelas/token yang benar-benar ada di `out/renderer/assets/styles-*.css` baseline, atau gaya inline untuk geometri dan warna. Seluruh teks panel ditulis langsung dalam bahasa Inggris (tidak lewat hook intl) supaya locale zh-CN tidak menggantinya; label dan istilah mengikuti kunci `settings.usage.*` upstream bila padanannya ada.

### Default skills

Skill bawaan dikirim sebagai **plugin bawaan**, bukan sebagai pack skill: halaman Settings → Skills hanya menampilkan skill yang datang lewat plugin (pack `glm/packages/bundled-skills` terbaca agent tapi tidak pernah muncul di UI).

- Payload: `src/skills/<nama>/` (32 skill). `scripts/build.py` merakit paket plugin di `runtime/build/resources/glm/packages/ccode-skills-plugin/` (`.zcode-plugin/plugin.json` dengan `"skills": "skills"` + salinan payload) dan mencatat setiap berkasnya di `build-manifest.json` (`sha256`, `bundled_plugin`). Daftar nama skill ada di `bundled_skills`.
- Registrasi di sisi agent: `src/local_only/skills_plugin.py` menambahkan definisi plugin ke daftar definisi plugin bawaan agent (`rootCandidates: packages/ccode-skills-plugin`, `requiredSeedPaths`, listing), menambah id `ccode-skills@zcode-plugins-official` ke `DEFAULT_ENABLED_OFFICIAL_PLUGIN_IDS`, dan menambahkan nama/`packages/…` plugin ke dua daftar plugin bawaan di renderer (yang dipakai UI untuk menandai skill plugin bawaan). Semua anchor unik; `replace_once` menggagalkan build bila anchor bergeser.
- `scripts/apply_build.py::promote_skill_pack` mengganti paket plugin di `app/resources` sebagai satu unit (hash diverifikasi, snapshot `.part` + rename, rollback bila gagal). Pack `bundled-skills` milik vendor tidak pernah disentuh.
- Verifikasi tanpa GUI: `ZCODE_STANDALONE_ROOT=<dir> ELECTRON_RUN_AS_NODE=1 app/ccode app/resources/glm/zcode.cjs plugins list` harus memuat `ccode-skills@zcode-plugins-official [enabled] … skills: 32`, dan `skills list` memuat skill kita sebagai `system/plugin`.
- Batas yang masih terbuka: halaman Skills memanggil service `skillsService.list({provider:'glm'})` (dijawab agent lewat channel protokol, minified) dan pada uji terakhir masih mengembalikan 14 skill vendor saja, walau plugin kita `[enabled]` dengan 32 skill dan muncul di halaman Plugins sebagai "CCode Skills". Filter di service itu belum ditemukan; jangan mengklaim halaman Skills sudah memuat skill bawaan sebelum terbukti.

Patch standalone hidup di `src/local_only/` dan dijalankan setelah patch renderer:

1. `storage.py` menetapkan namespace data, profil, database task, database sesi agent, config MCP, dan menghapus migrasi/scan lintas instalasi. Ini juga berisi bootstrap env untuk chunk `out/main`, `out/host`, `out/scheduler`, dan backend agent.
2. `cloud.py` menghapus pemilik layanan akun/cloud di registry host, menghapus gerbang login renderer, dan memberi jawaban lokal untuk channel yang pemiliknya sudah tidak ada. Di main, jawabannya eksplisit pada `Ik`; di host, service yang masih diminta UI lokal diganti stub lewat `CLOUD_SERVICE_STUBS` (plugin store, automations, coding plan) supaya permintaan tidak berakhir timeout `Unknown channel`.
3. Backend agent di luar ASAR (`app/resources/glm/zcode.cjs`) dipatch dari baseline terpisah `baselines/zcode-3.14.5-original-agent.cjs` dengan hash di `project.json`.
4. Modul main lokal berbagi satu berkas `src/main/activity.cjs` → `app/resources/activity/main.cjs`: IPC `zcode-activity:summary` (Activity) dan `zcode-detect:run` (**Auto Detect** di Model settings, menjalankan `services/model-sync/sync.py --discover --bootstrap` untuk namespace aktif lalu mengembalikan ringkasan provider/model). Keduanya hanya menerima main frame lokal. Preload mengekspos `window.zcodeActivity` dan `window.zcodeDetect`.
5. `catalog.py` membersihkan katalog provider native dari keluarga Zhipu dan menambahkan template **9Router** (api-key, baseUrl `http://127.0.0.1:20128/v1`, model `combo/coding-harian`) secara idempotent; `apply_build.py` juga menyegarkan cache katalog per-endpoint di namespace karena salinan itu yang menang atas file bundled, lalu menghapus marker `zcode-builtin-refresh.json` yang dijadwalkan oleh host.
6. Refresh katalog built-in dari endpoint akun dimatikan di host: facade `refreshZCodeBuiltin` dan `ZCodeBuiltinRemoteSynchronizer.refresh` menjawab `"skipped"`, jadi tidak ada fetch ke `https://zcode.z.ai` dan release upstream tidak bisa menimpa katalog yang sudah dipatch (tanpa Zhipu, dengan 9Router).
7. Fitur akun/langganan dihapus dari akarnya: tombol Upgrade composer, section plan/usage di menu profil, tab app/coding-plan, grup **Providers** akun di Model settings (hanya Custom providers + template katalog yang tersisa; loading gate akun dipaku mati), dan remote control web/mobile (trigger, dialog, channel, hook status). Tanpa provider terkonfigurasi, pane detail Model settings merender empty state lokal (`ZCodeProviderEmptyState`, label ZCode sendiri) alih-alih kartu `common.loading` yang menunggu item navigasi yang tidak ada. Halaman Usage stats diganti **Activity** lokal: `src/main/activity.cjs` membaca `ZCODE_SESSION_DB_PATH` (`cli/db/db.sqlite`) read-only lewat `node:sqlite` (fallback snapshot bila WAL menolak handle read-only) dan menghitung prompt `role=user` per hari (seluruh riwayat) plus streak serta rekap per tahun; renderer memakainya lewat `window.zcodeActivity` (`src/renderer/activity-panel.js`). Katalog marketplace disaring di agen (`requiresPaidPlan` dibuang sebelum manifest), badge Coding Plan dimatikan di renderer, dan label akun di `IntlProvider-B-44tSXQ.js` ikut dipatch.
8. `build-manifest.json` menyimpan SHA256 hasil staging untuk `app.asar`, `glm/zcode.cjs`, `voice/main.cjs`, `activity/main.cjs`, dan `config/provider/zcode-builtin.json`; `scripts/apply_build.py` menolak promote bila checksum tidak cocok dan mengembalikan kelima resource bila salah satu penggantian gagal. Apply juga menyisakan **dua** cadangan terbaru di `runtime/backups` (`BACKUP_RETENTION`) supaya cadangan penuh tiap promote tidak menumpuk tanpa batas.

Anchor cloud terikat versi upstream dan sengaja gagal bila tidak unik. Jangan melemahkan assertion agar build terlihat berhasil. `cloud.guard_main` menutup celah yang tidak terlihat oleh anchor: setelah semua edit, build menolak main bundle yang masih mereferensikan binding/layanan yang sudah dihapus (`REMOVED_MAIN_SYMBOLS`) atau referensi `webRemoteControlManager` — hook `window closed` dan port telemetri host berjalan pada pemakaian normal, jadi referensi sisa berarti crash main process, bukan kode mati. `cloud.guard_remote_ipc_dependencies` memeriksa hal yang sama untuk region registrasi IPC yang diganti: setiap `e.<service>` yang dipanggil handler terdaftar harus dikirim ke `Ik({...})`, karena provider lokal (Docker/WSL/SSH) pernah hilang bersama region …

## Branding

Satu sumber mark: `ccode-logo.svg` di root repo. `scripts/make_icons.py` (`make icons`) merasterisasinya lewat ImageMagick/librsvg menjadi `assets/icons/ccode-{16,24,32,48,64,128,256,512,1024}.png`; PNG itu di-commit supaya `make build` tidak bergantung pada tool gambar. Nama dan ukuran ikon ada di `branding.LOCAL_ICON_SIZES` dan `branding.PACKAGED_ICONS`.

`src/local_only/branding.py` berjalan paling akhir di `scripts/build.py` dan mengerjakan dua hal:

1. **Mark** — mengganti setiap mark produk dengan glyph dari `ccode-logo.svg`: komponen mark onboarding/login (`tkn`), logo title bar/sidebar yang dikirim shell sebagai `appLogoUrl` (data URI `IS`), logo startup animasi (`Zkn`) dan splash pra-hidrasi di `out/renderer/index.html`, watermark draft (`Qgt`/`Kgt`), dialog About di main (`class="app-logo"`), plus aset PNG `icon_512@2x` di renderer. Semua anchor terikat versi: `_replace_quoted_after` menolak bila mark upstream tidak lagi tunggal, dan `guard()` menolak build bila path mark upstream (`LEGACY_MARK_PREFIXES`) atau viewBox `0 0 256 218` masih ada.
2. **Nama** — mengganti nama produk di dalam string literal saja: `ZCode on Steroids` → `CCode`, dan `ZCode` → `CCode` untuk kemunculan kata utuh. Lexer kecil (`_literal_spans`) memisahkan literal (termasuk template dengan interpolasi) dari kode, komentar, dan regex, sehingga identifier, nama properti, dan `id` pesan i18n tidak ikut berubah; `_is_key` melindungi kunci objek dari ternary yang juga diikuti `:`.

Yang sengaja tidak diganti dan dijaga tetap: env `ZCODE_*`, kanal IPC `zcode-*`, skema `zcode://`, layout `.zcode` di dalam namespace, id provider/plugin/MCP, maupun string bersama antarproses (`ZCode Protocol`, error transport/runtime, direktori profil Chromium lama) — semuanya kontrak runtime, bukan label. Daftar itu hidup di `branding.PROTECTED_COPY`/`PROFILE_*`, dan `guard()` menolak build bila ada `ZCode` lain yang lolos (kecuali di dalam literal yang memang dilindungi).

Ikon aplikasi disalurkan lewat rantai yang sama dengan resource lain: `scripts/build.py` menyalin `assets/icons/*` ke `runtime/build/resources/{icon.png,icon_512x512.png,icon_windows.png}` dan mencatat SHA256-nya di `build-manifest.json`; `scripts/apply_build.py` mempromosikannya bersama lima resource lain, lalu mengganti nama identitas AppDir di tempat (binary `app/zcode` → `app/ccode`, `app/zcode.desktop` → `app/ccode.desktop`, symlink `.DirIcon`/`app/ccode.png`, ikon hicolor per ukuran, `BIN="$APPDIR/ccode"` di `AppRun`). Langkah itu idempotent dan menyimpan versi lamanya di `runtime/backups/<stamp>/appdir/`. `scripts/install_local.py` menambahkan sisi user: launcher `ccode.desktop` (`Name=CCode`, `Icon=ccode`, `StartupWMClass=ccode`, cocok dengan `ZCODE_DESKTOP_APPLICATION_NAME=ccode`), ikon hicolor di `~/.local/share/icons`, unit `ccode-model-sync.{service,timer,path}`, migrasi namespace lama, dan pensiun launcher/unit ZCode-era.

## Desktop

UI mengatur MCP bernama `fedora-desktop`. `services/desktop/server.py` memuat `zcode_fast_profile.py` saat `MCP_SCREEN_PROFILE=zcode-fast`. Profil itu batas edit project untuk backend desktop: file vendor (`server.py`, `capture.py`, `input.py`, `grounding.py`) dibiarkan apa adanya.

Yang ditetapkan profil:

- Permukaan tool 15 buah: tool screenshot/aksi yang lama plus `screen_read_text`, `screen_wait_text`, `screen_verify`, `screen_sense`, dan `screen_focus`. Empat tool yang menulis lebih jauh ke desktop (`screen_read_page`, `screen_read_selection`, `screen_tour`, `screen_reload`) tidak diekspos.
- Jalur murah lebih dulu: `screen_read_text` mengembalikan teks plus id elemen dan koordinat desktop tanpa gambar, dan klik memakai `element=<id>` sehingga server menyelesaikan koordinatnya. Deskripsi `screen_screenshot` menyebut Set-of-Marks (`annotate`), cache elemen (`use_cache`), dan crop `region` untuk teks kecil.
- Aksi mengembalikan screenshot + baris SENSE secara default; gambar dilewati bila SENSE menyatakan frame tidak berubah, supaya aksi no-op tidak membayar token gambar.
- Tunggu perubahan memakai mode `hybrid` (event damage dengan lantai poll), bukan polling tiap 60 ms.
- Kebijakan pointer menggantikan guard takeover: gerakan kursor yang berhenti dianggap idle dan aksi tetap jalan; pengendalian kursor berkelanjutan selama `ZCODE_CUA_TAKEOVER_MS` tetap dianggap pengambilalihan dan membatalkan aksi dengan pesan `STOPPED`. `force=true` tetap tersedia dan tetap dilarang dipakai untuk melawan pengguna. Capture dan input memakai portal Fedora/PipeWire; pengendalian kursor yang berkelanjutan oleh pengguna menghentikan aksi agent.

Rincian dan batasnya ada di [COMPUTER_USE_IMPROVEMENTS.md](COMPUTER_USE_IMPROVEMENTS.md).

### Memori dan CPU

`scripts/run.sh` sengaja **tidak** menambahkan flag Chromium apa pun; perilaku render dan hover harus tetap seperti upstream. `--enable-low-end-device-mode` diukur menghemat sekitar 128 MB PSS (876 ke 748 MB, idle, root terisolasi) dan sempat dinyalakan default, lalu dikembalikan karena flag Chromium menyentuh perilaku render/hover. Uji A/B pada viewport 1568x980 menunjukkan geometri pemilih model identik dengan dan tanpa flag (panel 1070x65 194x458, submenu 1259x104 236x112, overlap 560 px²), jadi flag itu bukan penyebab keluhan hover; tetap dikembalikan supaya default tetap upstream. Untuk mengujinya lagi, tambahkan flag secara manual saat menjalankan `app/zcode`.

Server MCP desktop tidak memuat model OCR/OmniParser saat start; sesi dibangun saat observasi pertama (knob `ZCODE_CUA_WARMUP=1` mengembalikan prefetch). Penghematannya sekitar 60 MB untuk setiap sesi MCP yang tidak mengambil gambar.

CPU saat idle terukur rendah (sekitar 1% untuk seluruh pohon proses setelah startup); timer model-sync memakai 0,17 sampai 0,25 detik CPU dan 60 MB transient sekali per menit.

## Voice

Preload mengekspos `window.zcodeVoice.start/stop/cancel`. IPC `zcode-voice:*` hanya menerima main frame lokal `out/renderer/index.html`. `src/main/voice.cjs`, yang disalin ke `app/resources/voice/main.cjs`, menemukan root project melalui `project.json`, lalu memakai `services/voice`.

Rekaman `pw-record` disimpan di direktori privat sementara, maksimal 60 detik. Worker Python dimuat saat pertama dipakai, mempertahankan model hangat selama aplikasi hidup, dan menerima request JSON via stdio. Audio didekode FFmpeg menjadi NumPy float32, lalu Whisper melakukan transkripsi. Jalur ini menghindari ketidakcocokan API decode PyAV yang ditemukan saat setup.

`terminology.py` memberikan prompt/hotwords bilingual dan koreksi terbatas “komputer rius/use” → “computer use”. Jangan mengubah normalizer menjadi pengganti umum yang menebak maksud semua ucapan.

## Model sync

`services/model-sync/sync.py` mengerjakan dua hal untuk namespace standalone:

1. **Discovery 9Router** (aktif begitu provider keluarga 9Router ada): menarik `GET /v1/models` dari gateway lokal, mengelompokkan per namespace (combo terpisah, ambang 10 model, sisanya `· lainnya`), lalu menulis provider + manual rule di `provider_config.json`. Template katalog tidak menyemai model, jadi pengisian pertama datang dari discovery. Pemicunya: unit path systemd pada `provider_config.json` (write dari app), kondisi `needs_fill` untuk provider kosong/belum dikelompokkan, dan timer 60 detik dengan TTL 12 jam. Backoff 15 menit saat gateway mati, dan `make models` untuk memaksa. Metadata diambil dari `capabilities` gateway; snapshot models.dev hanya sebagai fallback; model tanpa limit dilewati dan dicatat. `commit()` menolak write yang mengurangi inventori model, dan hilangnya model secara massal diperlakukan sebagai file ditulis ulang (diisi ulang, bukan di-blacklist).
2. **Enrich reasoning Vansrouter**: hanya melengkapi model yang sudah didaftarkan dalam provider `vansrouter` di CCode. Metadata berasal dari snapshot OpenCode/models.dev, cache diperbarui paling sering sekali hari, timer berjalan sekitar satu menit.

Aturan yang sama berlaku untuk keduanya: fingerprint pemetaan sebelumnya melindungi override manual, switch per model (`rule.config.enabled`) dipertahankan, model/rule yang dihapus user tidak dihidupkan lagi, dan schema host divalidasi (mis. `optionSpecs.reasoningLevel` wajib ada; model dengan rule katalog tidak boleh juga punya rule manual). Model tak dikenal dan combo tidak ditebak, dan tidak ada inference. Timer standalone `ccode-model-sync.timer` menunjuk config/state di dalam namespace lewat env `ZCODE_MODEL_SYNC_CONFIG`/`ZCODE_MODEL_SYNC_STATE`; tanpa env itu script tetap memakai jalur lama.

## Data pengguna

Aplikasi berjalan sebagai varian mandiri. Root default `~/.local/share/ccode`:

| Path | Isi |
|---|---|
| `data/.zcode/v2` | setting, provider config, `tasks-index.sqlite`, snapshot sesi |
| `data/.zcode/cli/db/db.sqlite` | database sesi/message agent |
| `data/.zcode/cli/config.json` | config MCP pengguna |
| `data/.zcode/workspace`, `plugin-workspace` | workspace percakapan dan plugin |
| `electron/` | profil Electron (localStorage voice, cookies) |
| `model-sync/` | state, cache, dan backup model sync varian ini |

`ZCODE_STANDALONE_ROOT` dapat memindahkan seluruh root (dipakai untuk pengujian terisolasi). `scripts/run.sh` menetapkan env namespace dan menahan lock operasi bersama (`~/.local/share/.ccode.operations.lock`); menjalankan `app/ccode` langsung juga memakai root yang sama karena bootstrap env berjalan sebelum modul membaca path. `make install` memindahkan namespace ZCode-era (`~/.local/share/zcode-on-steroids`) ke root ini satu kali dan tidak menyalinnya; `scripts/data_backup.py` memakai root baru sebagai default dan menyimpan snapshot di `~/.local/share/ccode-backups`.

Data instalasi lama di `~/.zcode` dan `~/.config/ZCode` tidak disentuh dan tidak diimpor otomatis. Import provider bersifat eksplisit lewat `scripts/install_local.py --import-provider-from` dan hanya menyalin provider personal ber-API-key beserta rule model manualnya. Compatibility symlink lama hanya menjaga proses yang belum direstart.
