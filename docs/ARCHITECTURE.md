# Arsitektur

## UI dan build

`project.json` menyimpan hash ASAR upstream asli, hash backend agent asli, identitas aplikasi standalone, dan nama tiga asset ASAR yang diubah. Build membaca baseline, mengganti anchor yang harus muncul tepat sekali, lalu menulis ASAR baru ke `runtime/build/resources` dengan offset dan integrity SHA256 yang dihitung ulang. Entri unpacked asli tetap mengacu pada `app/resources/app.asar.unpacked`.

Patch renderer:

1. Halaman `iOn` asli diubah menjadi `originalCuaSettings`.
2. Wrapper memilih `FedoraCuaSettings` untuk workspace Linux lokal; workspace lain memakai halaman asli.
3. Composer `mit` memilih pintasan Linux; `CCodeVoiceInput` ditambahkan di dekat toolbar Computer Use.
4. Source custom ditambahkan pada modul renderer yang sama sehingga dapat menggunakan React dan komponen bundled.

Simbol versi ini: `Q` = React, `$` = JSX runtime, `X` = Button, `bA/xA/SA` = dropdown root/trigger/content, `TA/EA` = radio group/item, `DA/OA` = label/separator, `Iv` = MCP store, `gv` = settings hook, `uA` = Tooltip (dipakai sel heatmap Activity dan pintasan Computer Use; props `title`, `side`, `children`). Simbol dan anchor dapat berubah pada update upstream. Jangan menebak bahwa nama ini stabil antarversi.

Sidebar Settings desktop Linux mempertahankan strip drag-window 16px di bagian atas (bukan spacer upstream 48px), sehingga tombol Back to workspace dan daftar menu naik 32px. Patch anchor unik berada di `cloud._renderer`; layout macOS/Windows, padding menu, dan footer tidak berubah.

### Halaman Activity

`src/renderer/activity-panel.js` memakai tata letak halaman Usage upstream yang lama (komponen `Bwn`/`vwn`/`p7` di baseline): strip lima metrik (`flex flex-col overflow-hidden rounded-xl bg-surface sm:flex-row sm:items-center` dengan pemisah `hidden h-7 w-px bg-border sm:block`, nilai `text-ui-lg font-medium` di atas label `text-ui-base text-foreground-subtle`), lalu kartu `rounded-xl bg-surface px-3 py-3` berisi judul + kontrol segmen (`flex flex-wrap items-center gap-0.5 rounded-full bg-surface p-0.5`, segmen aktif `bg-background text-foreground`, tidak aktif `text-foreground-subtle`), grid heatmap `style={{gridTemplateColumns:'repeat(N, minmax(0, 1fr))'}}` dengan sel `aspect-square w-full min-w-0 rounded-[4px] border` berwarna `var(--color-usage-heatmap-0..4)`, dan label bulan di bawah grid.

Segmen adalah **tahun**, bukan rentang: `CCodeActivityYears` menggabungkan tahun yang punya prompt (dari `summarize`) dengan tahun berjalan, urut menaik, dan tahun terakhir (tahun berjalan) dipilih sebagai default — pada 2027 segmen baru muncul otomatis di kanan dan 2026 bergeser ke kiri. Grid selalu satu tahun kalender penuh: 1 Januari–31 Desember, 365 sel (366 pada tahun kabisat), label Jan–Des di bawah, tanpa label hari. Hover sel memakai komponen tooltip bundled `uA` (pola yang sama dengan heatmap upstream), bukan atribut `title` bawaan browser; gaya hover kotak tetap `hover:scale-110 hover:border-border-hover`.

CSS renderer adalah hasil build Tailwind statis dari upstream: kelas yang tidak dipakai di sana (mis. `grid-cols-5`, `divide-x`, `h-[11px]`, `bg-foreground/5`, `bg-primary/25`) tidak punya aturan sama sekali, jadi utilitas seperti itu tidak berefek walau ditulis di JSX. Saat mengubah panel ini, pakai kelas/token yang benar-benar ada di `out/renderer/assets/styles-*.css` baseline, atau gaya inline untuk geometri dan warna. Seluruh teks panel ditulis langsung dalam bahasa Inggris (tidak lewat hook intl) supaya locale zh-CN tidak menggantinya; label dan istilah mengikuti kunci `settings.usage.*` upstream bila padanannya ada.

### Token savers

`src/renderer/token-savers-panel.js` menambahkan menu Settings → Token savers tepat di bawah Memory dengan ikon `PiggyBank` dari keluarga Lucide yang sama dengan ikon Settings lain. Panel memakai `Q1`, `Z1`, `Xx`, tooltip `uA`, dan warna heatmap usage upstream. Toggle RTK, Caveman, dan Ponytail tersimpan terpisah. Baris Caveman/Ponytail masing-masing menempatkan pilihan Lite/Full/Ultra di kiri toggle; saat fitur mati, pilihan level nonaktif dan pudar tanpa mengubah level yang tersimpan. Deskripsi setiap baris tetap menjelaskan efek level pada instruksi agent.

RTK memakai kontrak `rtk rewrite`: output `rtk ...` yang valid pada status 0, atau status 3 (RTK 0.51.0 yang terpasang), mengganti perintah sebelum jalur approval CCode; status 1 tanpa output mempertahankan perintah dan approval normal. Status lain, kegagalan RTK, atau output rewrite tidak valid menghentikan perintah.

Grafik 30 hari membaca `saved_tokens` dari `rtk gain --daily --format json`. Nilainya estimasi output shell RTK lintas proyek, bukan token yang ditagihkan provider. Main IPC `window.ccodeTokenSavers` hanya menerima main frame lokal; preferensi disimpan di `data/.ccode/v2/token-savers.json`.

### Built-in subagents

`src/local_only/subagents.py` menjadi satu sumber katalog peran untuk registry host, kontrol Settings, dan runtime agent. Katalog ini menyediakan 12 default: Engineering Generalist, Codebase Explorer, Technical Architect, Backend Developer, Frontend Developer, UI/UX Designer, Database Engineer, Debugger & Performance Engineer, QA / Test Engineer, Code Reviewer, Security Reviewer, dan DevOps Engineer. Generalist dan Explorer menggantikan dua default upstream; agent plugin `visual-judge` tetap terpisah dari katalog.

Semua default aktif saat pemasangan dan mewarisi model sesi induk kecuali pengguna memilih override. Toggle Settings memakai `disabledAgentIds` pada file state subagent yang sudah ada. Host meneruskan status built-in dan plugin ber-scope user; alias nama pendek plugin menyimpan `canonicalAgentId`, sehingga profil yang dimatikan tidak tetap dapat dipanggil lewat alias. Runtime agent memakai ID/status aktif yang sama untuk prompt daftar agent dan resolver dispatch. Profil nonaktif tidak ditawarkan dan tidak dapat dipanggil. Override model lama untuk `general-purpose` dan `Explore` dipindahkan ke role penggantinya.

### Default slash commands

`src/commands/*.md` mengirim 12 command: `/prd`, `/design`, `/tech-spec`, `/task-plan`, `/test-plan`, `/adr`, `/implement`, `/debug`, `/explain`, `/review`, `/test`, dan `/security-review`. Prompt memakai model serta tools sesi yang tersedia; tidak ada skill atau MCP wajib.

`scripts/build.py` menyalin prompt dan `src/main/commands.cjs` ke resource `commands/`, lalu memasukkan semua berkas ke manifest SHA256. Main process menjalankan seeder saat startup. `src/local_only/default_commands.py` menambal resolver scanner dan command creator native agar keduanya memakai `${CCODE_STORAGE_DIR}/commands`; tanpa patch itu, CLI tetap mencari command di home yang tidak termasuk namespace standalone. Seeder menaruh prompt user-scope di lokasi yang sama. Marker `.ccode-default-commands.json` membedakan berkas milik CCode dari berkas user: seed baru hanya mengisi nama yang belum ada, update hanya mengganti default yang belum diedit, dan file yang diedit, dihapus, atau sudah dimiliki user tetap tidak ditimpa atau dibuat ulang.

Composer memakai slash picker native. Composer memuat katalog lewat `commandsService.list` saat dibuka, termasuk tanpa project terpilih (`workspacePath: null`) agar command user-scope tersedia. Picker menggabungkan command aktif dari state Settings dengan katalog native pada setiap render; inisialisasi agent yang memuat ulang katalog native tidak menghilangkan command tersebut. Setelah project dipilih, katalog dimuat ulang dengan command project-scope. Agent native mengembangkan template dan menyisipkan `$ARGUMENTS`; `/design` menulis `DESIGN.md`, bukan implementasi.

Resolver root command di agent (`default_commands.patch_agent`) juga mengarahkan scope user ke `${CCODE_STORAGE_DIR}/commands`; scope project tetap mengikuti direktori project. Patch scanner host saja tidak cukup: katalog UI dan pemuatan template agent adalah jalur terpisah. Ekspansi native meneruskan isi prompt serta `$ARGUMENTS`, bukan sekadar nama command. Semua prompt mengizinkan skills/MCP yang tersedia dan relevan tanpa menyerahkan tujuan command kepada helper.

`src/renderer/default-commands.js` mengelompokkan command bawaan menjadi **Documents**, **Development**, dan **Quality**. Command user lain masuk **Custom**. Header memakai komponen native `H7`; daftar command dan kontrol enablement tetap komponen upstream. Enam command Documents hanya membuat file target Markdown. Prompt Harness melarang pembuatan Markdown sebagai efek samping kecuali diminta pengguna atau diwajibkan instruksi workspace.

`scripts/apply_build.py` memverifikasi hash dan mempromosikan main module serta prompt dengan mekanisme backup/rollback resource statis yang sama. Seeder tidak memerlukan provider untuk instalasi dan tidak mengimpor konfigurasi dari instalasi lain.

### Default skills

Skill bawaan dikirim sebagai **pack skill native**, bukan plugin CCode Skills. Settings → Skills menampilkan skill pack sebagai **Default**, dan agent memuatnya sebagai `system/bundled`.

- Payload kanonik tetap `src/skills/<nama>/` (32 skill). `scripts/build.py` merakit `runtime/build/resources/glm/packages/bundled-skills/`, mempertahankan seed `dynamic-workflows` vendor, dan mencatat hash setiap berkas serta daftar `bundled_skills` di `build-manifest.json`.
- `src/local_only/skills_plugin.py` mempatch listing host (`skillsService.list`), discovery agent, dan klasifikasi renderer agar skill system bundled tidak dibuang oleh filter plugin. Registrasi plugin CCode Skills tidak dipakai lagi; anchor tetap unik dan gagal bila baseline berubah.
- `scripts/apply_build.py::promote_skill_pack` memverifikasi hash dan menyimpan snapshot sebelum mengganti pack. Resource plugin CCode lama dipensiunkan dengan cadangan untuk rollback.
- Skills buatan user dan konfigurasi namespace tidak ditimpa. Cache plugin lama tidak perlu dihapus: identitas plugin bawaan yang sudah pensiun tidak dimuat lagi.
- Verifikasi mencakup instalasi baru, namespace yang pernah memakai plugin lama, listing agent tanpa duplikasi, serta Settings → Skills dengan label Default.

### MCP bawaan dan katalog opsional

Settings → MCP Servers mempertahankan daftar server native. Dua MCP dikirim bersama resource aplikasi dan disemai otomatis: **Context7** (dokumentasi library) dan **Codegraph** (navigasi simbol lokal). Pemakaian pertama tidak menjalankan `npx` untuk mengunduh dependency.

Baris katalog **LSP** dan **Ripgrep** tampil di daftar **Installed** yang sama, memakai grid, ikon, dan slot kontrol milik baris native. Tombol **Install** tidak menampilkan label `Optional`; setelah server ditulis ke config MCP, baris native dengan switch on/off menggantikannya. Tidak ada bagian katalog terpisah, kartu, atau tombol Test di UI.

`services/mcp/` menyimpan katalog dan dependency yang dipin. `src/main/mcp-catalog.cjs` menangani penyemaian default dan instalasi lewat IPC main-frame lokal (`ccode-mcp-catalog:list/install`). `src/renderer/mcp-catalog.js` hanya menyediakan baris katalog; pemasangannya ke daftar native ada di `src/local_only/mcp_catalog.py` (`FTn`).

Konfigurasi tetap berada di `data/.ccode/cli/config.json` milik namespace standalone. Penyemaian tidak menimpa server user, switch disabled, atau penghapusan yang disengaja. Semua entri katalog bebas credentials; Context7 mengirim permintaan dokumentasi ke layanan Context7, dan Codegraph mengindeks proyek lokal dengan update otomatis serta download model embedding dimatikan.

Websearch, Obsidian, dan GitHub tidak dibundel: Browser Use sudah menyediakan pencarian web, vault Obsidian tersedia lewat plugin, dan GitHub dapat ditambahkan manual lewat formulir **New**. MCP `image_search` dari plugin resmi tidak diregistrasikan karena autentikasi akun Z.ai tidak tersedia.

### Plugin Marketplace

Marketplace resmi mengambil manifest dari `https://cdn-zcode.z.ai/zcode/official-plugin/marketplace.json`. Nama di dalam kontrak publisher itu tetap ejaan upstream — id marketplace `zcode-plugins-official`, direktori manifest `.zcode-plugin/` di dalam zip plugin, variabel `${ZCODE_PLUGIN_ROOT}`/`${ZCODE_PROJECT_DIR}` pada manifest, dan env `<PREFIX>_PLUGIN_DATA` yang dibaca runtime plugin — sehingga `src/local_only/marketplace.py` menambalnya di batas, bukan me-rename-nya. Resource `resources/marketplace/marketplace-compat.cjs` dihasilkan build dari `src/main/marketplace-compat.cjs`: enam ejaan kontrak diisi dari `rebrand.previous()`, dan `render_runtime()` menolak template yang masih memuat placeholder atau token upstream di luar kontrak itu. Dengan begitu ejaan upstream tetap hanya tertulis di `rebrand.py`, sementara agen CCode tidak pernah memuatnya.

Sembilan anchor pada agent ditambal. Validasi manifest marketplace resmi menerima id publisher lalu mengganti nama manifest ke id lokal (`acceptOfficialName`/`adoptOfficialName`), sehingga `jun()` menerima manifest itu dan cache ditulis dengan id lokal. Pencarian manifest plugin menerima direktori publisher di tiga jalur (`sct` untuk direktori dan zip, `BBs` untuk akar zip, `g3s` untuk adapter skill). Ekspansi `${…}` mengenali prefiks publisher (`resolveRemoteVar`), dan proses plugin menerima kembaran env berprefiks publisher (`envAliases`) di jalur MCP stdio maupun hook. Terakhir, setiap pohon plugin yang sudah di-resolve (`ict`, satu titik untuk describe, validate, dan install) dilokalkan (`localizeResolved`), dan listing marketplace dinormalkan di `OJr` sebelum jalur cepat manifest yang sudah ternormalisasi (`localizeManifestEntries`); entri tanpa `displayName` terbitan mendapat nama tampilan dari namanya dalam ejaan lokal, bukan identitas plugin itu sendiri.

Lokalisasi payload menulis ulang hanya label yang dibaca UI dan agent, pada salinan plugin di namespace: `description` manifest memakai varian `description_i18n.en` bila label dasarnya berbahasa Cina, `userConfig.*.title` berbahasa Cina menjadi nama field (`blenderPath` → `Blender path`), `userConfig.*.description` Cina tanpa sisa Latin dibuang, dan frontmatter `description`/`when_to_use` skill berbahasa Cina memakai deskripsi Inggris plugin. Body SKILL.md, README, dan panel web milik publisher tidak diterjemahkan. Pemanggilan berulang tidak mengubah apa pun, dan kegagalan tulis tidak pernah menggagalkan describe/install.

`claude-plugins-official` (sumber GitHub) berjalan tanpa modul ini: manifest-nya sudah memakai `.claude-plugin` dan tanpa label Cina.

### Plugin n8n

`src/plugins/n8n/` menyimpan manifest native, entrypoint `dist/mcp/server.js`, dan 15 skill n8n beserta seluruh berkas pendukungnya. `services/mcp/stage.cjs` menyalin plugin ke `resources/mcp/plugins/n8n` dan memasang `n8n-mcp` 2.92.1 dari lockfile. Seluruh payload ikut inventori SHA256, promosi, dan rollback resource MCP yang sudah ada.

`src/local_only/n8n_plugin.py` menambahkan registry lokal dengan root `../mcp/plugins/n8n`, relatif terhadap entrypoint agent di `resources/glm`. Native runtime menyemai cache plugin, membangun listing Marketplace, dan memakai `__ccode-plugin-host` untuk menjalankan entrypoint dengan binary Electron sebagai Node. Tidak membutuhkan Node/npm sistem dan tidak mengunduh server saat pemakaian pertama.

Plugin tersedia tetapi mati secara default. Enable/disable native menjadi satu gerbang untuk MCP `plugin:n8n:n8n` dan seluruh 15 skill; tidak ada salinan n8n di pack skill Default. Form native **Advanced details → Configuration** menyimpan URL instance, API key, serta token MCP instance bila fitur terkait memerlukannya. API key/token memakai field `sensitive` dan hanya diinterpolasikan ke environment server, bukan argv atau URL. Konfigurasi disimpan lokal dalam file private, bukan dienkripsi oleh keychain.

Entrypoint membatasi endpoint ke HTTPS, kecuali HTTP loopback, dan menolak URL yang memuat credentials/query/fragment. Data runtime memakai `CCODE_PLUGIN_DATA`; telemetry upstream dimatikan melalui `N8N_MCP_TELEMETRY_DISABLED=true`. Key kosong atau URL tidak valid menghasilkan error konfigurasi, bukan koneksi palsu.

Policy SSRF upstream memakai `strict` untuk endpoint remote dan `moderate` untuk loopback yang dipilih eksplisit, agar instance lokal dapat diakses. Keduanya mempertahankan larangan endpoint metadata cloud dan alamat private non-loopback; tidak ada mode `permissive` atau pelemahan guard secara global.

Scanner Skills host memakai resolver `Up()` untuk lokasi config dan user skills. `storage.py` mengarahkannya ke `Ai()` (data root standalone), sehingga switch plugin dibaca dari namespace yang sama dengan cache dan agent. Sebelumnya scanner membaca enablement dari HOME asli walaupun cache sudah memakai namespace; plugin opt-in tidak muncul di Settings → Skills.

Patch standalone hidup di `src/local_only/`. `rebrand.py` berjalan paling awal — setiap pembacaan arsip lewat view `Rebranded` sudah membawa identitas CCode — modul lain setelah patch renderer, dan `branding.py` paling akhir:

1. `rebrand.py` menulis ulang setiap token produk upstream dalam satu pass (env `CCODE_*`, kanal IPC `ccode-*`, skema `ccode://`, layout `.ccode` di dalam namespace, id dan direktori plugin, judul proses, identifier), sehingga kedua sisi setiap batas tetap konsisten. `leftover()`/`assert_clean()` menggagalkan build bila masih ada sisa; `previous()` plus konstanta `PREVIOUS_*` memberi ejaan lama untuk kode migrasi. Ini satu-satunya tempat terlacak yang menulis ejaan upstream, bersama atribusi NOTICE.md/`docs/THIRD_PARTY.md` dan fixture `tests/test_branding.py`.
2. `storage.py` menetapkan namespace data, profil, database task, database sesi agent, config MCP, dan menghapus migrasi/scan lintas instalasi. Ini juga berisi bootstrap env untuk chunk `out/main`, `out/host`, `out/scheduler`, dan backend agent.
3. `cloud.py` menghapus pemilik layanan akun/cloud di registry host, menghapus gerbang login renderer, dan memberi jawaban lokal untuk channel yang pemiliknya sudah tidak ada. Di main, jawabannya eksplisit pada `Ik`; di host, service yang masih diminta UI lokal diganti stub lewat `CLOUD_SERVICE_STUBS` (plugin store, automations, coding plan) supaya permintaan tidak berakhir timeout `Unknown channel`.
4. Backend agent di luar ASAR (`app/resources/glm/ccode.cjs`) dipatch dari baseline terpisah `baselines/upstream-3.14.5-original-agent.cjs` dengan hash di `project.json`.
- `plugins.py` mempatch payload plugin bawaan dari salinan pristine `baselines/upstream-3.14.5-original-plugins/` (digest dipin sebagai `plugins_baseline_sha256` di `project.json`; payload ini bukan bagian ASAR yang dipin). Empat agent `visual-judge` (documents, pdf, presentations, spreadsheets) kehilangan pin model akun dan `thoughtLevel: max` sehingga subagent mewarisi model sesi induk; re-run overflow skill deck dibatasi satu pass; `image-search-plugin` dihapus (MCP-nya hanya bisa autentikasi dengan akun Z.ai dan tidak ada pengganti lokal); plugin CUA dan guide dinamai ulang berawalan `ccode-` dan setiap direktori manifest plugin menjadi `.ccode-plugin`. Setiap segmen path ikut diganti ejaan (`skills/ccode-configuration-guide/…`), dan plan `legacy` membuang berkas *beserta direktori kosong* yang masih memakai ejaan lama di tree terpasang.
6. `runtime_tuning.py` menjadikan level reasoning default sesi baru sebagai level termurah yang ditawarkan model (`low`) alih-alih yang tertinggi, diterapkan pada bundle agent plus completer pemilihan model di host dan renderer (keduanya memakai helper `ccodePreferredReasoningLevel` yang disisipkan: rantai member opsional tidak boleh diulang di dalam kondisional); blok sistem Harness agent mendapat tiga baris disiplin loop (jawab lalu berhenti, satu pass cukup, lakukan cek inline sekali bila tool gate tidak bisa start). Cap giliran subagent tetap 4 (`maxTurns`).
7. Modul main lokal berbagi satu berkas `src/main/activity.cjs` → `app/resources/activity/main.cjs`: IPC `ccode-activity:summary` (Activity) dan `ccode-detect:run` (**Auto Detect** di Model settings, menjalankan `services/model-sync/sync.py --discover --bootstrap` untuk namespace aktif lalu mengembalikan ringkasan provider/model). Keduanya hanya menerima main frame lokal. Preload mengekspos `window.ccodeActivity` dan `window.ccodeDetect`.
8. `catalog.py` membersihkan katalog provider native dari keluarga Zhipu dan menambahkan template **9Router** (api-key, baseUrl `http://127.0.0.1:20128/v1`, model `combo/coding-harian`) secara idempotent; `apply_build.py` juga menyegarkan cache katalog per-endpoint di namespace karena salinan itu yang menang atas file bundled, lalu menghapus marker `ccode-builtin-refresh.json` yang dijadwalkan oleh host.
9. Refresh katalog built-in dari endpoint akun dimatikan di host: facade `refreshCCodeBuiltin` dan `CCodeBuiltinRemoteSynchronizer.refresh` menjawab `"skipped"`, jadi tidak ada fetch ke `https://zcode.z.ai` dan release upstream tidak bisa menimpa katalog yang sudah dipatch (tanpa Zhipu, dengan 9Router).
10. Fitur akun/langganan dihapus dari akarnya: tombol Upgrade composer, section plan/usage di menu profil, tab app/coding-plan, grup **Providers** akun di Model settings (hanya Custom providers + template katalog yang tersisa; loading gate akun dipaku mati), dan remote control web/mobile (trigger, dialog, channel, hook status). Tanpa provider terkonfigurasi, pane detail Model settings merender empty state lokal (`CCodeProviderEmptyState`, label CCode sendiri) alih-alih kartu `common.loading` yang menunggu item navigasi yang tidak ada. Halaman Usage stats diganti **Activity** lokal: `src/main/activity.cjs` membaca `CCODE_SESSION_DB_PATH` (`cli/db/db.sqlite`) read-only lewat `node:sqlite` (fallback snapshot bila WAL menolak handle read-only) dan menghitung prompt `role=user` per hari (seluruh riwayat) plus streak serta rekap per tahun; renderer memakainya lewat `window.ccodeActivity` (`src/renderer/activity-panel.js`). Katalog marketplace disaring di agen (`requiresPaidPlan` dibuang sebelum manifest), badge Coding Plan dimatikan di renderer, dan label akun di `IntlProvider-B-44tSXQ.js` ikut dipatch.
11. `build-manifest.json` menyimpan SHA256 hasil staging, termasuk `app.asar`, `glm/ccode.cjs`, `glm/.node-bundle-meta.json`, `app-update.yml`, `voice/main.cjs`, `activity/main.cjs`, `token-savers/main.cjs`, `token-savers/token-savers-runtime.cjs`, `config/provider/ccode-builtin.json`, dan plan `plugin_payload` (berkas, rename direktori, removal). `scripts/apply_build.py` menolak promote bila checksum inventory tidak cocok dan mengembalikan resource yang dipromosikan bila penggantian gagal. Promosi payload plugin menjalankan rename direktori, removal (dicadangkan), lalu rewrite berkas, menulis jurnal rollback ke `runtime/backups/<stamp>/plugin-payload.json`, dan pada akhirnya memindahkan nama resource pra-rebrand (`glm/<ejaan-lama>.cjs` dan `config/provider/<ejaan-lama>-builtin.json`) ke cadangan. Apply juga menyisakan **dua** cadangan terbaru di `runtime/backups` (`BACKUP_RETENTION`) supaya cadangan penuh tiap promote tidak menumpuk tanpa batas.
12. `src/local_only/token_savers.py` memasang menu di bawah Memory, label locale, dan integrasi prompt/approval pada agent dari baseline. `src/main/token-savers.cjs` dan `src/main/token-savers-runtime.cjs` menyediakan persistence privat, bridge IPC lokal, RTK rewrite, dan data chart; keduanya ikut hash serta rollback.

Anchor cloud terikat versi upstream dan sengaja gagal bila tidak unik. Jangan melemahkan assertion agar build terlihat berhasil. `cloud.guard_main` menutup celah yang tidak terlihat oleh anchor: setelah semua edit, build menolak main bundle yang masih mereferensikan binding/layanan yang sudah dihapus (`REMOVED_MAIN_SYMBOLS`) atau referensi `webRemoteControlManager` — hook `window closed` dan port telemetri host berjalan pada pemakaian normal, jadi referensi sisa berarti crash main process, bukan kode mati. `cloud.guard_remote_ipc_dependencies` memeriksa hal yang sama untuk region registrasi IPC yang diganti: setiap `e.<service>` yang dipanggil handler terdaftar harus dikirim ke `Ik({...})`, karena provider lokal (Docker/WSL/SSH) pernah hilang bersama region …

## Branding

Satu sumber mark: `ccode-logo.svg` di root repo. `scripts/make_icons.py` (`make icons`) merasterisasinya lewat ImageMagick/librsvg menjadi `assets/icons/ccode-{16,24,32,48,64,128,256,512,1024}.png`; PNG itu di-commit supaya `make build` tidak bergantung pada tool gambar. Nama dan ukuran ikon ada di `branding.LOCAL_ICON_SIZES` dan `branding.PACKAGED_ICONS`.

Identitas produk dipecah dua lapis yang tidak boleh tumpang tindih:

1. **Nama dan kontrak** — `src/local_only/rebrand.py` berjalan **paling awal** di `scripts/build.py`, sebelum modul patch lain mencari anchor, sehingga anchor ditulis dalam ejaan yang dikirim. `apply()` menulis ulang setiap token produk upstream dalam satu pass: env `CCODE_*`, kanal IPC `ccode-*`, skema `ccode://`, layout `.ccode` di dalam namespace, id dan direktori plugin, judul proses, serta identifier — kedua sisi setiap batas tetap konsisten. URL absolut (`http(s)://…`) adalah kontrak jaringan, bukan label: host dan path-nya dipertahankan apa adanya (CDN ikon marketplace dan URL rilis Electron hanya menjawab ejaan aslinya), dan `leftover()` mengabaikannya. `leftover()`/`assert_clean()` menggagalkan build bila masih ada sisa ejaan upstream di asset yang dikirim; label lama dua kata (`LABELS`) runtuh menjadi `CCode`; `previous()` plus konstanta `PREVIOUS_*` mengembalikan ejaan lama untuk kode migrasi (installer, backup, `scripts/migrate_identity.py`). Modul ini satu-satunya tempat terlacak yang menulis ejaan upstream, bersama atribusi di NOTICE.md/`docs/THIRD_PARTY.md` dan fixture uji `tests/test_branding.py`.
2. **Mark** — `src/local_only/branding.py` berjalan **paling akhir** dan hanya mengurus mark; nama produk tidak ditangani di sini. Setiap mark produk diganti glyph dari `ccode-logo.svg`: komponen mark onboarding/login (`tkn`), logo title bar/sidebar yang dikirim shell sebagai `appLogoUrl` (data URI `IS`), logo startup animasi (`Zkn`) dan splash pra-hidrasi di `out/renderer/index.html`, watermark draft (`Qgt`/`Kgt`), dialog About di main (`class="app-logo"`), plus aset PNG `icon_512@2x` di renderer. Anchor terikat versi: `_replace_quoted_after` menolak bila mark upstream tidak lagi tunggal, dan `guard()` menolak build bila path mark upstream (`LEGACY_MARK_PREFIXES`) atau viewBox `0 0 256 218` masih ada.

`scripts/migrate_identity.py` (`make migrate`) memindahkan instalasi yang sudah ada ke ejaan baru saat aplikasi tertutup: snapshot tar khusus state (workspace dikecualikan karena ukurannya, dan migration hanya me-rename satu nama berkas di sana), merge layout lama ke layout baru bila `make install` sudah menyemai sebagian (berkas lama yang menang, yang tertimpa diarsipkan ke `migration-backups/`), rename setiap path yang memuat token pra-rebrand (terdalam dulu; bila saudara bernama CCode sudah ada karena runtime men-seed ulang payload, path lama dipindahkan ke `migration-backups/<stamp>-superseded/` alih-alih menggagalkan migration), rewrite token di berkas config/state/log di luar workspace, lalu rewrite setiap kolom teks `data/.ccode/cli/db/db.sqlite` dan `data/.ccode/v2/tasks-index.sqlite` di tempat.

Ikon aplikasi disalurkan lewat rantai yang sama dengan resource lain: `scripts/build.py` menyalin `assets/icons/*` ke `runtime/build/resources/{icon.png,icon_512x512.png,icon_windows.png}` dan mencatat SHA256-nya di `build-manifest.json`; `scripts/apply_build.py` mempromosikannya bersama resource lain, lalu mengganti nama identitas AppDir di tempat (binary pra-rebrand → `app/ccode`, launcher pra-rebrand → `app/ccode.desktop`, symlink `.DirIcon`/`app/ccode.png`, ikon hicolor per ukuran, `BIN="$APPDIR/ccode"` di `AppRun`). Langkah itu idempotent dan menyimpan versi lamanya di `runtime/backups/<stamp>/appdir/`. `scripts/install_local.py` menambahkan sisi user: launcher `ccode.desktop` (`Name=CCode`, `Icon=ccode`, `StartupWMClass=ccode`, cocok dengan `CCODE_DESKTOP_APPLICATION_NAME=ccode`), ikon hicolor di `~/.local/share/icons`, unit `ccode-model-sync.{service,timer,path}`, migrasi satu kali namespace pra-rebrand, dan pensiun launcher/unit pra-rebrand (lihat `rebrand.PREVIOUS_*`).

## Desktop

UI mengatur MCP bernama `fedora-desktop`. `services/desktop/server.py` memuat `ccode_fast_profile.py` saat `MCP_SCREEN_PROFILE=ccode-fast`. Profil itu batas edit project untuk backend desktop: file vendor (`server.py`, `capture.py`, `input.py`, `grounding.py`) dibiarkan apa adanya.

Yang ditetapkan profil:

- Permukaan tool 15 buah: tool screenshot/aksi yang lama plus `screen_read_text`, `screen_wait_text`, `screen_verify`, `screen_sense`, dan `screen_focus`. Empat tool yang menulis lebih jauh ke desktop (`screen_read_page`, `screen_read_selection`, `screen_tour`, `screen_reload`) tidak diekspos.
- Jalur murah lebih dulu: `screen_read_text` mengembalikan teks plus id elemen dan koordinat desktop tanpa gambar, dan klik memakai `element=<id>` sehingga server menyelesaikan koordinatnya. Deskripsi `screen_screenshot` menyebut Set-of-Marks (`annotate`), cache elemen (`use_cache`), dan crop `region` untuk teks kecil.
- Aksi mengembalikan screenshot + baris SENSE secara default; gambar dilewati bila SENSE menyatakan frame tidak berubah, supaya aksi no-op tidak membayar token gambar.
- Tunggu perubahan memakai mode `hybrid` (event damage dengan lantai poll), bukan polling tiap 60 ms.
- Kebijakan pointer menggantikan guard takeover: gerakan kursor yang berhenti dianggap idle dan aksi tetap jalan; pengendalian kursor berkelanjutan selama `CCODE_CUA_TAKEOVER_MS` tetap dianggap pengambilalihan dan membatalkan aksi dengan pesan `STOPPED`. `force=true` tetap tersedia dan tetap dilarang dipakai untuk melawan pengguna. Capture dan input memakai portal Fedora/PipeWire; pengendalian kursor yang berkelanjutan oleh pengguna menghentikan aksi agent.

Rincian dan batasnya ada di [COMPUTER_USE_IMPROVEMENTS.md](COMPUTER_USE_IMPROVEMENTS.md).

### Memori dan CPU

`scripts/run.sh` sengaja **tidak** menambahkan flag Chromium apa pun; perilaku render dan hover harus tetap seperti upstream. `--enable-low-end-device-mode` diukur menghemat sekitar 128 MB PSS (876 ke 748 MB, idle, root terisolasi) dan sempat dinyalakan default, lalu dikembalikan karena flag Chromium menyentuh perilaku render/hover. Uji A/B pada viewport 1568x980 menunjukkan geometri pemilih model identik dengan dan tanpa flag (panel 1070x65 194x458, submenu 1259x104 236x112, overlap 560 px²), jadi flag itu bukan penyebab keluhan hover; tetap dikembalikan supaya default tetap upstream. Untuk mengujinya lagi, tambahkan flag secara manual saat menjalankan `app/ccode`.

Server MCP desktop tidak memuat model OCR/OmniParser saat start; sesi dibangun saat observasi pertama (knob `CCODE_CUA_WARMUP=1` mengembalikan prefetch). Penghematannya sekitar 60 MB untuk setiap sesi MCP yang tidak mengambil gambar.

CPU saat idle terukur rendah (sekitar 1% untuk seluruh pohon proses setelah startup); timer model-sync memakai 0,17 sampai 0,25 detik CPU dan 60 MB transient sekali per menit.

## Voice

Preload mengekspos `window.ccodeVoice.start/stop/cancel`. IPC `ccode-voice:*` hanya menerima main frame lokal `out/renderer/index.html`. `src/main/voice.cjs`, yang disalin ke `app/resources/voice/main.cjs`, menemukan root project melalui `project.json`, lalu memakai `services/voice`.

Rekaman `pw-record` disimpan di direktori privat sementara, maksimal 60 detik. Worker Python dimuat saat pertama dipakai, mempertahankan model hangat selama aplikasi hidup, dan menerima request JSON via stdio. Audio didekode FFmpeg menjadi NumPy float32, lalu Whisper melakukan transkripsi. Jalur ini menghindari ketidakcocokan API decode PyAV yang ditemukan saat setup.

`terminology.py` memberikan prompt/hotwords bilingual dan koreksi terbatas “komputer rius/use” → “computer use”. Jangan mengubah normalizer menjadi pengganti umum yang menebak maksud semua ucapan.

## Model sync

`services/model-sync/sync.py` mengerjakan dua hal untuk namespace standalone:

1. **Discovery 9Router** (aktif begitu provider keluarga 9Router ada): menarik `GET /v1/models` dari gateway lokal, mengelompokkan per namespace (combo terpisah, ambang 10 model, sisanya `· lainnya`), lalu menulis provider + manual rule di `provider_config.json`. Template katalog tidak menyemai model, jadi pengisian pertama datang dari discovery. Pemicunya: unit path systemd pada `provider_config.json` (write dari app), kondisi `needs_fill` untuk provider kosong/belum dikelompokkan, dan timer 60 detik dengan TTL 12 jam. Backoff 15 menit saat gateway mati, dan `make models` untuk memaksa. Metadata diambil dari `capabilities` gateway; snapshot models.dev hanya sebagai fallback; model tanpa limit dilewati dan dicatat. `commit()` menolak write yang mengurangi inventori model, dan hilangnya model secara massal diperlakukan sebagai file ditulis ulang (diisi ulang, bukan di-blacklist).
2. **Enrich reasoning Vansrouter**: hanya melengkapi model yang sudah didaftarkan dalam provider `vansrouter` di CCode. Metadata berasal dari snapshot OpenCode/models.dev, cache diperbarui paling sering sekali hari, timer berjalan sekitar satu menit.

Aturan yang sama berlaku untuk keduanya: fingerprint pemetaan sebelumnya melindungi override manual, switch per model (`rule.config.enabled`) dipertahankan, model/rule yang dihapus user tidak dihidupkan lagi, dan schema host divalidasi (mis. `optionSpecs.reasoningLevel` wajib ada; model dengan rule katalog tidak boleh juga punya rule manual). Model tak dikenal dan combo tidak ditebak, dan tidak ada inference. Timer standalone `ccode-model-sync.timer` menunjuk config/state di dalam namespace lewat env `CCODE_MODEL_SYNC_CONFIG`/`CCODE_MODEL_SYNC_STATE`; tanpa env itu script tetap memakai jalur lama.

## Data pengguna

Aplikasi berjalan sebagai varian mandiri. Root default `~/.local/share/ccode`:

| Path | Isi |
|---|---|
| `data/.ccode/v2` | setting (termasuk `token-savers.json`), provider config, `tasks-index.sqlite`, snapshot sesi |
| `data/.ccode/cli/db/db.sqlite` | database sesi/message agent |
| `data/.ccode/cli/config.json` | config MCP pengguna |
| `data/.ccode/workspace`, `plugin-workspace` | workspace percakapan dan plugin |
| `electron/` | profil Electron (localStorage voice, cookies) |
| `model-sync/` | state, cache, dan backup model sync varian ini |

`CCODE_STANDALONE_ROOT` dapat memindahkan seluruh root (dipakai untuk pengujian terisolasi). `scripts/run.sh` menetapkan env namespace dan menahan lock operasi bersama (`~/.local/share/.ccode.operations.lock`); menjalankan `app/ccode` langsung juga memakai root yang sama karena bootstrap env berjalan sebelum modul membaca path. `make install` memindahkan namespace pra-rebrand (`~/.local/share/<rebrand.PREVIOUS_NAMESPACE>`) ke root ini satu kali dan tidak menyalinnya; `scripts/data_backup.py` memakai root baru sebagai default dan menyimpan snapshot di `~/.local/share/ccode-backups`.

Data instalasi upstream (direktori pra-rebrand `rebrand.PREVIOUS_APPDATA`/`rebrand.PREVIOUS_APPCONFIG`) tidak disentuh dan tidak diimpor otomatis. Import provider bersifat eksplisit lewat `scripts/install_local.py --import-provider-from` dan hanya menyalin provider personal ber-API-key beserta rule model manualnya. Compatibility symlink lama hanya menjaga proses yang belum direstart.
