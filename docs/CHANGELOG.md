# Changelog

## 2026-10-13

### Model settings tidak lagi menggantung di grup akun

- Keluhan: membuka **Model settings** berarti menunggu lama untuk melihat provider yang tersedia. Ukur di root uji terpisah: panel berhenti di `Add provider` + grup **Providers** dengan kartu `Loading...` dan **tidak pernah selesai** (>10 menit; satu-satunya tab Settings yang begitu — General/Appearance/Computer Use/MCP/Activity settle ~1,2 dtk, Plugins ~4,3 dtk).
- Penyebab: `src/local_only/cloud.py` sudah mengosongkan keluarga akun (`Q1e`/`$1e`), tetapi navigasi Model settings tetap membangun grup **preset akun** (`{id:`preset`,title:…presetTitle…}`) yang barisnya berasal dari sumber OAuth. Grup itu tidak difilter saat kosong (`TCn` hanya membuang grup `custom` yang kosong), dan loading gate-nya (`presetLoading`) memakai state sumber akun, jadi header + kartu loading bertahan selamanya sementara daftar provider lokal tidak pernah tampil.
- Perbaikan (semua di `src/local_only/cloud.py::_renderer`, anchor unik + test): grup `preset` dihapus dari array navigasi (hanya `custom` tersisa), dan `presetLoading` pada dua call site (`DCn`, `rCn`) dipaku `!1`. Tidak ada data palsu: permukaan akun memang dihapus, daftar Custom providers + tombol Add provider (termasuk template 9Router) tetap seperti sebelumnya.
- Hasil terukur pada build staged, root baru: Model settings settle **80 ms** tanpa state loading sama sekali (sebelumnya tanpa batas). Verifikasi struktur: `assertNotIn('presetLoading:tt')`, grup `custom` tetap ada, `node --check` pada aset renderer hasil patch lolos.

### Katalog provider built-in tidak lagi di-refresh dari endpoint akun

- Host masih punya `ZCodeBuiltinRemoteSynchronizer`: katalog built-in di-refresh dari `https://zcode.z.ai` (endpoint akun yang pemiliknya sudah dihapus) dan release hasilnya ditulis menimpa salinan cache aktif — jalur itu ikut dipanggil saat provider settings di-refresh (`refreshZCodeBuiltin({force:!0})`). Selain menambah round trip jaringan, release upstream bisa mengembalikan template Zhipu dan menghapus template 9Router yang kita patch.
- `cloud._host` kini memaku facade `refreshZCodeBuiltin` dan `ZCodeBuiltinRemoteSynchronizer.refresh` untuk menjawab `"skipped"`, jadi tidak ada jalur pemanggil yang bisa mencapai endpoint itu. Terverifikasi pada instance staged: `zcode-builtin-refresh.json` tidak dibuat lagi, sementara `zcode-builtin.json` hasil build (tanpa Zhipu, berisi `9router`) tetap ada.
- Marker `zcode-builtin-refresh.json` yang lama dihapus saat apply (`scripts/apply_build.py`), dan `zcode-builtin.json` tidak pernah disentuh.

### Retensi backup + pembersihan artefak berat

- `scripts/apply_build.py` menyimpan cadangan tiap promote tanpa pernah menghapus: 22 cadangan dalam ~9 jam ≈ 7,1 GB. Kini ada `BACKUP_RETENTION = 2`: setelah promote sukses, hanya dua backup terbaru yang disimpan (nama non-timestamp dan symlink tidak pernah dihapus, kegagalan hapus diabaikan).
- Pembersihan sekali jalan: 20 backup lama (6,4 GB), duplikat basi `app/resources/app.asar.before-voice-language` (312 MB, nol referensi di source/docs), salinan `app/` di dalam snapshot cutover (966 MB; bagian launcher/systemd/config tetap disimpan untuk rollback), fixture `runtime/no-login/app` (654 MB; kecil & reproducible), dan `runtime/check/out` (11 MB). Total yang dibebaskan menurut ukuran tampak: repo 11,3 GB → 3,1 GB. Catatan: `/home` memakai btrfs `compress=zstd:1`, jadi ruang fisik yang kembali lebih kecil dari angka tampak, dan `df` di mesin ini bergerak 1–2 GB karena proses lain (browser, omp, ZCode) menulis terus.
- Temuan sampingan (bukan akibat perubahan ini, tidak ada aksi): log host menampilkan `workspaceKey` default ber-basis `~/.zcode/...` di samping key namespace; `~/.zcode` tidak menerima tulisan apa pun sejak cutover (mtime terbaru 2026-10-12 21:15).

### Empty state Model settings + kartu loading yang tersisa

- Laporan pengguna setelah perbaikan pertama: di **Model settings sebelum ada provider** tidak ada empty state dan ada elemen yang tampak "selalu loading". Diukur langsung di namespace pengguna: pane detail memuat kartu `Loading...` (`V5` + `lucide-loader-circle`) yang **menetap >20 detik** dan tidak pernah berganti, sementara kolom navigasi kosong.
- Penyebab: tanpa provider terkonfigurasi tidak ada satu pun item navigasi yang bisa dipilih, jadi `rCn` selalu jatuh ke cabang `if(!e.provider)return(0,$.jsx)(V5,{loadingLabel:k})`. Empty state tidak pernah dirender karena label `settings.modelProvider.empty` ("No custom model providers yet") memang sudah dikirim aplikasi tetapi tidak dipakai di jalur ini. Klaim verifikasi sebelumnya ("settle 80/140 ms tanpa loading") salah sasaran: yang diukur hanya node deskripsi, bukan pane detail.
- Perbaikan (`src/local_only/cloud.py::_renderer`, anchor unik + 1 tes baru): saat picker tertutup dan belum ada provider, pane detail merender `ZCodeProviderEmptyState` — komponen kecil yang memakai label ZCode sendiri (`settings.modelProvider.empty` + `.addProviderDescription`) dan token tampilan yang sama (`rounded-xl border border-dashed border-border bg-surface`, `text-ui-base text-foreground-subtle`). Jalur picker `OCn` tidak berubah begitu provider sudah ada.
- Verifikasi pada build yang dipromosikan (root pengguna, CDP): empty state muncul **78 ms**, teks `No custom model providers yet` + `Configure a custom API endpoint and initial model.`, **0 elemen spinner**, tidak ada teks `Loading...` di halaman, dan "Add provider" masih menampilkan template termasuk 9Router. `make test` **73 tes** hijau.

### Permukaan lambat lain yang diukur

- Tab **Plugins** ~3,8–4,3 dtk pada pembukaan pertama: `plugin-management.listPlugins` 3,8 dtk dan `getPluginsOverview` 4,0 dtk pada panggilan dingin (berikutnya 162/320 ms), ditambah `mcp-sync.listWorkspaceMcpServerStatuses` 4,4 dtk saat enumerasi MCP. Penyebabnya cold spawn proses agent (`durationMs: 26–32`) + handshake MCP, bukan patch kita; `official_auth_unavailable` untuk `image_search@zcode-plugins-official` selesai dalam 2 ms tanpa jaringan. Tidak diubah pada pekerjaan ini — mengubahnya berarti mengubah perilaku enumerasi upstream.

### Verifikasi

- `make build` + `make test` hijau: **72 tes** (dari 63), termasuk 3 tes renderer baru (grup preset akun hilang, grup custom tetap, loading gate akun `!1`), 1 tes host baru (katalog tidak pernah di-refresh dari endpoint akun), dan 5 tes retensi/marker baru.
- Loop merah→hijau pada root uji terpisah: sebelum perbaikan panel Model settings tidak pernah settle; sesudahnya **80 ms** untuk blok deskripsi. Koreksi (lihat bagian berikutnya): pengukuran itu hanya membaca node deskripsi, bukan pane detail — kartu `Loading...` permanen di pane detail baru ketahuan dan diperbaiki setelah laporan pengguna.
- `make apply` pada build ini: ZCode ditutup halus lebih dulu (host `exited with code 0`, tanpa dialog error), kelima resource live cocok dengan `build-manifest.json`, marker `zcode-builtin-refresh.json` lama dihapus, cadangan lama dipangkas ke dua terbaru.
- Smoke pada build yang sudah dipromosikan (root terpisah, CDP): Model settings settle **140 ms** tanpa state loading, picker "Add provider" masih memuat template 9Router, grup akun tidak ada, log bersih dari `Unknown channel`/`No handler registered`/`ReferenceError`/`TypeError`, dan `zcode-builtin-refresh.json` tidak dibuat lagi.
- Repo 11,3 GB → 3,1 GB (ukuran tampak). Pembersihan: 20 backup lama, duplikat `app.asar.before-voice-language`, salinan `app/` di snapshot cutover, fixture `runtime/no-login/app`, dan `runtime/check/out`.

### Bersih saat menutup jendela

- Penutupan jendela memunculkan dialog "A JavaScript error occurred in the main process" (`TypeError: Cannot read properties of undefined (reading 'disposeWindow')`) karena hook `window closed` masih memanggil manajer remote control yang sudah dihapus patch standalone. `src/local_only/cloud.py` mengawal pemanggilan itu dan menghapus fungsi registrasi IPC remote control yang tidak lagi punya pemanggil, sehingga akses layanan yang hilang tidak lagi dieksekusi.
- Port telemetri host tidak lagi memanggil core telemetri yang sudah tidak dibangun (`onSessionCreateTelemetry` menjadi no-op lokal).
- Guard build-time baru (`cloud.guard_main` + `REMOVED_MAIN_SYMBOLS`) menolak main bundle yang masih mereferensikan binding/layanan yang dihapus (`Eg`, `Gr`, `jo`, `Rk`, `VP`, `zP`) atau akses `webRemoteControlManager.` tanpa guard: build gagal keras, bukan menghasilkan crash runtime.
- Regresi: `tests/test_local_only_patches.py` menambah unit test guard dan test yang menjalankan patch `out/main/index.js` pada baseline pinned (hook close terjaga, `Rk`/`jo.reportEvent` hilang, `GetWebRemoteControlStatus` tetap dijawab lokal).
- Verifikasi: `make build` + `make test` (30 tes) hijau. Probe pada build lama menangkap error yang sama di titik yang sama dengan laporan pengguna; smoke root terpisah pada build baru membuka workspace tanpa login, menutup jendela tanpa `TypeError`/dialog dan keluar `exitCode: 0` (marker sebelum/sesudah pemanggilan terjaga tercatat).
- Artefak probe pengujian dan backup yang memuatnya sudah dibuang; rollback build pra-perbaikan tetap tersedia di `runtime/backups/20261013-000852-635047`.

### Kanal tanpa pemilik dan dependensi handler

- Kanal yang pemilik cloud-nya sudah dihapus kini dijawab lokal, bukan dibiarkan tanpa handler: remote connection SSH/WSL/Docker (`ConnectRemote`, `CancelPendingRemoteConnection`, `BindRemoteWorkspaceSessionContext`, `DisposeRemoteSession` → `{success:!1,error:"Remote connections are unavailable in the standalone build."}`/no-op), remote control (`StartWebRemoteControl`, `ResetWebRemoteControlPairing`, `StopWebRemoteControl`, `GetWebRemoteControlStatus` memakai bentuk kegagalan milik upstream sendiri: `reason:"unsupported-action"`, "Web remote control is disabled in this build."), serta preferensi auto-update. Sebelumnya renderer menerima `No handler registered` dan main mencatat `Error occurred in handler ...`.
- Dependensi lokal yang ikut terhapus di region registrasi IPC dikembalikan: `isDockerDaemonAvailable`, `listAvailableWSLDistros`, `listAvailableDockerContainers`, `listSSHConfigAliases`. Tanpa itu dialog SSH/Docker mengirim `TypeError: e.listSSHConfigAliases is not a function`.
- Guard build-time baru `cloud.guard_remote_ipc_dependencies` menolak build bila handler IPC memanggil `e.<service>` yang tidak dikirim ke `Ik()`; sebelumnya region registrasi yang diganti bisa menghilangkan provider lokal tanpa terdeteksi.
- Batas: fitur remote workspace (SSH/WSL/Docker) sendiri belum bisa dipakai pada varian standalone karena flow-nya memerlukan layanan client-config akun yang dihapus; melanjutkan fitur itu adalah keputusan terpisah (mengembalikan service tersebut atau membuat pengganti lokal), bukan bagian dari perbaikan ini.
- Verifikasi: `make build` + `make test` (33 tes) hijau; probe runtime pada root terpisah menunjukkan dialog Remote Connect (tab SSH dan Docker) terbuka tanpa `TypeError`, panel Mobile remote control menampilkan pesan "disabled in this build", penutupan jendela tetap bersih (`exitCode: 0`), dan seluruh log main bebas `No handler registered`, `TypeError`, serta `Unknown channel`.

### Sapuan jalur UI: kanal host tanpa pemilik

- Sweep lewat CDP atas menu yang bisa diklik (workspace/app/help menu, Plugin Marketplace, Automations, Settings + seluruh tab-nya, Usage stats, Remote Connect, Mobile remote control) menemukan tiga kanal service host yang masih diminta setelah pemilik cloud-nya dihapus: `client-config` dan `client-scenes` (permukaan plugin store dan automations), serta `usage-stats` (widget usage + tab Usage stats). Sebelumnya host menunggu timeout lalu mencatat `Unknown channel: <service>`.
- Kanal itu kini dijawab lokal lewat `CLOUD_SERVICE_STUBS`: `client-config` → `{pluginStoreOrder:null}`, `client-scenes` → `{code:0,data:[]}`, `usage-stats` → snapshot dari agent lokal (`Xe.getAppUsageStats`) sementara bagian BigModel/coding-plan menjawab error eksplisit "unavailable in the standalone build", dan `coding-plan-subscription` menjawab seluruh method permukaan plan dengan pesan yang sama (provider id tetap dari konstanta upstream). Permukaan akun tidak mengembalikan data palsu.
- `apply_service_boundary` menggantikan pola drop sebelumnya: simbol yang di-stub dijawab stub di semua registry chain, simbol lain yang cloud tetap dihapus; ada unit test untuk keduanya plus test bundel host pada baseline pinned.
- Catatan root uji baru (bukan akibat patch): `zcode-agent.subscribeSessionsIndexV4 FAIL` (`ZCODE_AGENT_RUNTIME_UNAVAILABLE`) dan `usage-stats.getAppUsageSnapshot FAIL` (`no_active_workspace`) muncul saat belum ada task/workspace aktif; keduanya state-dependent dan hilang pada aplikasi yang sudah dipakai normal.

### Provider Zhipu dihapus + 9Router native + Activity heatmap

- Katalog provider native (`resources/config/provider/zcode-builtin.json`) dibersihkan dari keluarga Zhipu: 4 template (`zai-api`, `zai-standard-api`, `bigmodel-api`, `bigmodel-standard-api`) dan 8 provider rule `account:zai-*`/`account:bigmodel-*` dihapus, plus aturan model/template yang menunjuk host Zhipu. `src/local_only/catalog.py` melakukan transform idempotent ini, sudah termasuk unit test dan gate di `scripts/check.py`.
- Dua sumber tambahan yang membuat permukaan akun tetap muncul juga ditutup: daftar keluarga akun di agen (`wXe` → kosong) dan konstanta keluarga/plan di renderer (`Q1e`, `$1e` → kosong, grup "Zhipu" di picker template dihapus). Hasil sweep: Model settings tidak lagi menampilkan Z.ai, BigModel, Start Plan, maupun tombol "Connect to Z.ai".
- **9Router** kini provider native: template `9router` (api-key, `openai-chat-completions`, baseUrl `http://127.0.0.1:20128/v1`) dengan satu model combo `combo/coding-harian` (context window 1.000.000, max output 384.000, tool+vision). Kontrol reasoning untuk model ini dimatikan (`values:["disabled"]`, `map:"{}"`) karena combo mengunci effort di sisi gateway — tidak ada kontrol yang hanya mengubah label.
- Resource build bertambah menjadi lima (`config/provider/zcode-builtin.json`). Karena katalog yang dipakai runtime adalah salinan cache per-endpoint (`<namespace>/data/.zcode/v2/runtime/provider/<platform>/<versi>/endpoint-<hash>/zcode-builtin.json`) yang menang atas salinan bundled, `make apply` menyegarkan cache itu dengan transform yang sama dan menyimpan salinan lamanya untuk rollback.
- Fitur **Activity** naik dari daftar 30 hari menjadi heatmap kontribusi penuh: modul mengembalikan seluruh riwayat harian + rekap per tahun, panel merender grid 7×N dengan label bulan/hari, legenda Less→More, pil rentang ("12 bulan" + setiap tahun yang punya data), dan memakai aksen tema ZCode (`bg-primary/25…` dengan latar `bg-foreground/5`). Kartu Prompt hari ini/Streak/Total tetap dipertahankan.
- Catatan proses: satu percobaan patch daftar keluarga renderer sempat meninggalkan terminasi `,` (bundle tidak valid) dan sempat ter-promote; `make test` menangkapnya (syntax check aset staged), diperbaiki menjadi `;`, dan build final sudah diterapkan. Tidak ada error runtime yang terlihat pengguna.

### Hapus total permukaan login/langganan + fitur Activity

- Fitur yang butuh akun/langganan dihapus dari akarnya, bukan disembunyikan: tombol Upgrade di composer (dua varian baris), kata Upgrade pada pesan `No model available…`, section plan/usage di menu profil (`Qen` mengembalikan `null` sebelum hook entitlement jalan), tab app/coding-plan di halaman usage, dan remote control web/mobile (trigger titlebar `xin`, dialognya, hook status yang polling tiap detik, empat channel main, serta referensi `webRemoteControlManager` di hook penutupan jendela).
- Plugin Marketplace tetap, tetapi entri ber-`requiresPaidPlan` disaring di katalog agen (filter pada manifest builder, berlaku untuk store desktop dan CLI) dan badge Coding Plan dimatikan di renderer; plugin gratis tidak berubah.
- Halaman Usage stats berganti menjadi **Activity** (100% lokal): halaman settings `usage` merender `ZCodeActivityPanel`, yang membaca jumlah prompt `role=user` per hari dan streak dari `cli/db/db.sqlite` lewat modul baru `src/main/activity.cjs` (IPC `zcode-activity:summary`, bridge `window.zcodeActivity`, resource keempat `activity/main.cjs`). Modul membuka DB read-only (`node:sqlite`) dengan fallback snapshot bila WAL menolak; prompt dari sesi mesin (automation/off-peak/bot/subagent) tidak dihitung; hari mengikuti zona lokal; streak saat ini toleran sehari dan streak terpanjang dihitung dari seluruh riwayat.
- Stub host disesuaikan: `xl` (usage stats) dibuang karena tidak ada pemanggil lagi, `Ol` (coding plan) tetap dijawab lokal dengan pesan eksplisit `Coding plans are unavailable in the standalone build` supaya hook latar belakang tidak berakhir timeout, `ea`/`Dl` tetap untuk plugin store dan automations.
- Tooling: `scripts/asar.py` kini menulis satu integrity block untuk member berukuran 0 byte (30 member di arsip ini), sehingga `app.asar` hasil build konsisten dengan baseline untuk pembaca ASAR yang ketat.
- Label i18n `out/renderer/assets/IntlProvider-B-44tSXQ.js` ikut dipatch (kini anggota `patched_assets`): `settings.usageTitle`/`sectionTitle` → Activity, deskripsi diarahkan ke riwayat lokal, dan pesan model tanpa upgrade.
- Verifikasi: `make build` + `make test` (47 tes, termasuk 5 tes modul Activity dan test bundel renderer/intl/agent) hijau; sweep UI pada root terpisah: tidak ada tombol Upgrade maupun trigger Mobile remote control, tab settings bernama Activity dan panelnya benar-benar merender (0 prompt di root uji), tanpa badge Coding Plan, log main tanpa `Unknown channel`/`No handler registered`/`TypeError`, dan penutupan jendela tetap `exitCode: 0`.

## 2026-10-12

### Varian mandiri tanpa akun

- Aplikasi berjalan dalam namespace sendiri di `~/.local/share/zcode-on-steroids` (`data/`, `electron/`, `model-sync/`) dan tidak lagi membaca atau menulis `~/.zcode` serta `~/.config/ZCode`. Data instalasi lama tidak diimpor otomatis; import provider personal bersifat opsional lewat `scripts/install_local.py --import-provider-from`.
- Gerbang login dan layanan akun/cloud dimatikan di batas kepemilikannya: registry layanan host (marketing, cloud content, OAuth, usage stats, coding plan, client config, client scenes) tidak lagi terdaftar, hook restore akun renderer diganti, dan channel telemetri/remote control dijawab lokal. Provider personal, reasoning, MCP, Voice, Computer Use, engine task, serta permission tidak berubah.
- Menu footer sidebar tetap ada (locale, tema, zoom, settings) tetapi labelnya kini identitas lokal dan tombol akun "Connect" hilang; panel plan akun menampilkan status tidak tersedia.
- Integrasi baru: launcher `zcode-on-steroids.desktop`, timer `zcode-on-steroids-model-sync.timer`, config MCP di dalam namespace. Launcher `zcode.desktop`, shortcut AppImage, dan timer lama tidak diubah.
- `scripts/data_backup.py` menambah snapshot/restore offline dengan SQLite backup API, manifest hash, penolakan symlink/path traversal, lock eksklusif, dan penyimpanan namespace lama sebelum restore.
- `src/local_only/` menjadi rumah patch standalone (storage + cloud); backend agent di `resources/glm/zcode.cjs` dipatch dari baseline terpisah dan ikut diverifikasi checksum saat `make apply`.
- Dokumentasi disinkronkan ke Obsidian lewat `scripts/export_obsidian.py` (`make obsidian`). Folder project bisa dipakai langsung sebagai vault: bila `.obsidian/` ada, script hanya menyegarkan `Index.md` (README, AGENTS, dan `docs/` adalah file asli). Untuk vault terpisah, dokumen disalin ke `<vault>/ZCode on Steroids/` dengan frontmatter `tags`/`source` untuk tag pane; vault dideteksi dari `OBSIDIAN_VAULT_PATH`, konfigurasi MCP omp, atau `--vault`. `make obsidian-check` melaporkan drift tanpa menulis dan memberi exit code non-nol.

### Bukti penerapan

- Build dan `make test` (25 unit test, termasuk regresi patch helper) hijau; smoke root terpisah membuka workspace tanpa login, tanpa `Unknown channel`/`No handler`, tanpa error runtime.
- Chat provider personal (`vansrouter/combo/coding-harian`) membalas `STANDALONE_SMOKE_OK` dalam ~4 detik; task bertahan setelah restart.
- `data_backup.py backup|verify|restore` diuji pada root smoke: 732 entri, integritas SQLite `ok`, namespace lama tersimpan sebagai `root-pre-restore-*`.
- `make install` memasang launcher + timer standalone; timer aktif dan service berjalan; launcher lama dan data lama tidak berubah. Menjalankan `app/zcode` langsung (tanpa env) memakai root standalone dan tidak menyentuh data lama.
- Menutup jendela dari dalam aplikasi (`closeWindow`) mengakhiri proses dalam ~6 detik; hook quit, host cleanup, dan IPC Voice tetap bekerja.
- Batas: audit keluar-masuk jaringan menyeluruh belum dilakukan, jadi jangan mengklaim seluruh trafik ZCode hilang; permukaan akun yang tidak lagi punya pemilik (mis. panel plan di Settings) menampilkan status tidak tersedia, bukan data palsu.

### Sebelumnya

- Satukan aplikasi modifikasi, desktop MCP, pengenal suara, dan model sync dalam workspace mandiri untuk ohmypi.
- Tambahkan source patch, baseline pinned, build staged, pemeriksaan, apply dengan cadangan, dan installer lokal.
- Pertahankan Computer Use Linux melalui MCP, profil desktop cepat, dan pilihan reasoning sesuai metadata.
- Voice memakai menu asli ZCode, tombol 32px/14px, mode kirim yang dapat dipilih, serta konteks Indonesia–English dan koreksi istilah terbatas.
- Uji no-login terpisah: native Skip membuka workspace, provider mandiri membalas, dan chat persisten setelah restart saat account backend selalu 503. Audit menemukan cloud polling dan legacy metadata import; produksi belum diubah ke mode local-only. Lihat NO_LOGIN_TEST.md.
