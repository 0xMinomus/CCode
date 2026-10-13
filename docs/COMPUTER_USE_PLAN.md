# Rencana penggantian Computer Use dengan Codex

Tanggal riset: 2026-10-13. Status: planning, belum ada perubahan runtime atau penghapusan backend.

## Keputusan

Gunakan runtime Codex yang sudah terpasang, bukan membangun ulang computer-use engine. Kandidat reuse utama adalah actuator desktop Codex (`@oai/sky`) yang benar-benar ada di paket ini dan dapat dipanggil tanpa agent Codex; delegasi ke `codex app-server` tetap opsi terpisah bila pengguna ingin planner Codex.

Permintaan tidak bisa dinyatakan terpenuhi apa adanya. Paket membawa SDK desktop Linux, tetapi produk hanya mengaktifkan permukaan **browser**, dan actuator Linux-nya berbasis X11. Probe cakupan di bawah menunjukkan konsekuensi praktisnya pada sesi nyata, bukan sekadar kecurigaan teoretis.

Hasil probe cakupan membatalkan jalur yang paling diharapkan: actuator desktop Codex tidak bekerja pada sesi ini. Actuator-nya X11/EWMH, seluruh aplikasi berjalan sebagai klien Wayland, dan GNOME Shell 50 di mesin ini tidak lagi menyediakan sesi Xorg. Menyalakan permukaan `computer` pada harness Codex tidak mengubah hal itu, karena actuator yang dipakai sama.

Konsekuensinya harus dinyatakan apa adanya: "hapus total Computer Use ZCode, pakai Computer Use Codex" tidak dapat dieksekusi untuk desktop di mesin ini. Yang tersisa adalah tiga pilihan nyata:

1. **Pertahankan backend portal yang ada dan kejar keluhan kecepatannya** (jalur E). Ini satu-satunya cara desktop Wayland tetap bisa dikendalikan, dan pekerjaannya berupa pengukuran lalu perbaikan loop, bukan penggantian backend.
2. **Kendalikan hanya aplikasi yang dijalankan sebagai klien XWayland**, memakai actuator Codex (jalur D). Sempit, rapuh, dan tidak menyentuh aplikasi Wayland native.
3. **Serahkan task web ke otomasi browser terstruktur** (bagian dari jalur E). Ini yang paling mungkin menjelaskan mengapa pengalaman Codex terasa cepat, dan tidak memerlukan actuator desktop sama sekali.

Menyalakan kembali permukaan `computer` pada `cua-repl` atau mengubah flag produk bukan opsi: itu tetap berakhir di actuator X11 yang sama.

## Masalah dan batas kesimpulan

Pengguna melaporkan Computer Use ZCode sangat lambat bahkan pada task sederhana; Codex terasa lebih cepat dan lebih mampu. Laporan itu diterima, tidak diuji ulang untuk menyangkalnya.

Kecepatan end-to-end memiliki beberapa pemilik: inferensi model, keputusan agent, jumlah observasi dan tool call, capture, eksekusi input, serta waktu halaman/app siap. Mengganti MCP atau menyalin nama tool tidak membuktikan bahwa kualitas dan kecepatan Codex akan ikut pindah. Riset ini belum mengisolasi penyebab lambat dan belum membuat benchmark pembanding.

`[INFERENCE]` Hipotesis utama yang perlu diukur lebih dulu: yang membuat pengalaman Codex terasa cepat pada tugas web bukan actuator desktop, melainkan otomasi browser yang terstruktur. Pekerjaan web di sana tidak dilakukan dengan menebak koordinat dari screenshot, melainkan lewat DOM/CDP dan aksesibilitas, sehingga satu langkah jarang berarti satu observasi gambar penuh. Bila hipotesis ini benar, menyelesaikan keluhan kecepatan tidak memerlukan penggantian actuator sama sekali.

Cara mengujinya murah dan tidak menyentuh produksi: catat untuk beberapa tugas nyata berapa banyak observasi gambar yang dikirim, berapa token konteks yang terpakai, dan berapa lama bagian inferensi versus bagian tool. Bila biaya observasi mendominasi, arah perbaikannya jelas (aksesibilitas/DOM lebih dulu, screenshot sebagai verifikasi terakhir). Bila inferensi mendominasi, arahnya pemilihan model dan pengurangan putaran keputusan. Sampai angka itu ada, tidak ada perbaikan performa yang boleh diklaim.



## Bukti instalasi dan interface

| Bukti | Hasil teramati | Implikasi |
|---|---|---|
| `command -v codex` | Tidak ditemukan pada PATH | Temukan executable lewat paket, bukan menganggap Codex belum terpasang |
| `rpm -qf /usr/bin/chatgpt` | `chatgpt-26.930.61225-1.x86_64` | App desktop tersedia |
| `/usr/lib/chatgpt/resources/codex --version` | `codex-cli 0.160.1` | Executable ini dapat dipakai sebagai prerequisite lokal |
| `rpm -qi chatgpt` | Lisensi paket `Proprietary` | Jangan menyalin paket/SDK desktop ke tracked source atau menganggap lisensi CLI mencakup semuanya |
| Manifest plugin `unified-computer-use` aktif | `cua_repl`, tool `js`, `js_reset`, `turn_ended`; `CUA_REPL_ENABLED_SURFACES=browser` | Codex sendiri memakai MCP untuk permukaan ini; bebas Fedora MCP tidak berarti bebas semua MCP |
| Manifest yang sama | `BROWSER_USE_AVAILABLE_BACKENDS=chrome,iab,mcpapps` | Ada browser bawaan dan jalur browser terhubung, bukan bukti backend desktop Linux |
| App-server, `CODEX_HOME` sementara, `initialize` | Berhasil; versi `0.160.1`, `platformOs=linux`; exit 0 | Transport stdio dan handshake dapat dipakai dari aplikasi lain tanpa login pada probe ini |
| Schema dari executable terpasang | 104 metode request; tidak ada metode khusus `computer*` atau `browser*` | App-server bukan API langsung `computer.click` |
| Schema yang sama | `thread/start`, `turn/start`, `turn/interrupt`, `mcpServerStatus/list`, `mcpServer/tool/call` | Agent delegation dan tool-call transport tersedia, bukan bukti layanan browser otomatis tersedia |
| `McpServerToolCallParams` | Field wajib `server`, `threadId`, `tool`; `arguments` opsional | Tool dipanggil pada MCP yang dikonfigurasi untuk thread, bukan sembarang helper desktop global |
| Probe provider `wire_api="chat"` pada executable terpasang | Ditolak, exit 1: `wire_api = "chat" is no longer supported` | Provider ZCode chat-completions tidak boleh dianggap plug-and-play untuk executor Codex |
| Paket SDK `@oai/sky` di dalam `cua_node` | Versi 0.7.5, helper `bin/linux/sky_linux_x64` (3,4 MB), protokol JSONL stdio `{id,command,input}` → `{id,ok,output}`/`{id,ok,false,error,restart}` | Actuator desktop Linux benar-benar ada di instalasi ini dan dapat dipanggil di luar aplikasi Codex |
| Import modul SDK tanpa aksi (`sky.target`) | Exit 0; `target="linux"`; method: `get_screenshot`, `get_window_state`, `list_apps`, `list_windows`, `click`, `move`, `move_relative`, `drag`, `drag_handle`, `scroll`, `type_text`, `press_key`, `key_down/up`, `launch_app`, `activate_window`, `clipboard_read/write/release`, `perform_secondary_action` | Cakupan tool setara atau lebih luas dari profil `zcode-fast` yang sekarang dipakai |
| `ldd` dan `strings` helper | Hanya `libX11.so.6`; referensi `XTEST` dan AT-SPI; tidak ada Wayland, portal, PipeWire, atau libei | Actuator Codex Linux berbasis X11, bukan portal seperti backend Fedora yang ada |
| Sesi pengguna | `loginctl ... -p Type` → `wayland` | Jendela Wayland native tidak dapat dienumerasi/dikendalikan lewat jalur X11; cakupan penuh desktop tidak terpenuhi |

Probe di atas tidak mengirim prompt model, tidak membaca kredensial/user chat, tidak merekam layar, dan tidak menggerakkan mouse/keyboard. Seluruh direktori probe sementara sudah dibersihkan.

### Sumber lokal

- `/usr/share/applications/chatgpt.desktop`: launcher dan handler skema `codex`.
- `/usr/lib/chatgpt/resources/cua_node/manifest.json`: runtime Linux x64, `node_version=24.21.0-cua.1`.
- `~/.codex/plugins/cache/openai-bundled/unified-computer-use/26.930.61225/.mcp.json`: konfigurasi permukaan browser di instalasi aktif. Path ditulis untuk bukti, jangan commit salinan config pengguna.
- `/usr/lib/chatgpt/resources/cua_node/lib/node_modules/@oai/cua-repl/README.md`: launcher membutuhkan daftar permukaan; trusted services dan approval diwariskan dari host; desktop memasok browser/Sky services. File instruksi `linux/computer` sendiri bukan bukti provider input Linux tersedia.
- `~/.codex/plugins/cache/openai-bundled/browser/26.930.61225/.codex-plugin/plugin.json`: plugin browser berlisensi `Proprietary` dan hook cleanup memakai `node_repl`.

### Sumber resmi

- [Computer Use](https://learn.chatgpt.com/docs/computer-use): desktop macOS/Windows, izin app/OS, pembatasan tindakan dan user takeover.
- [Browser](https://learn.chatgpt.com/docs/browser): browser bawaan, Linux disebut dalam kontrol desktop, permukaan ini berbeda dari desktop computer use.
- [Browser extension](https://learn.chatgpt.com/docs/chrome-extension): Chrome/Edge/Brave/Opera/Vivaldi, native app cooperation dan izin per situs.
- [Codex App Server](https://learn.chatgpt.com/docs/app-server): integrasi produk melalui stdio JSON-RPC, thread/turn, event, approval, interrupt, dan MCP tool call. Sebagian API masih experimental; schema harus diambil dari versi terpasang, bukan ditebak dari dokumentasi terbaru.
- [Open Source](https://learn.chatgpt.com/docs/open-source): CLI, SDK, dan app-server terbuka; tidak memberikan izin universal atas paket desktop.
- [Konfigurasi Computer Use](https://github.com/openai/codex/blob/main/codex-rs/config/src/computer_use.rs): konfigurasi macOS/Windows, tidak ada konfigurasi Linux desktop.
- [Protokol provider](https://github.com/openai/codex/blob/main/codex-rs/model-provider-info/src/lib.rs): wire API Responses, chat-completions ditolak. Perilaku ini juga dipastikan pada binary lokal.

## Hasil probe cakupan (2026-10-13)

Probe dijalankan pada sesi kerja nyata dan pada X server terisolasi. Tidak ada aksi input ke desktop pengguna, tidak ada prompt model, dan seluruh artefak sementara sudah dihapus.

| Probe | Hasil | Arti |
|---|---|---|
| `list_apps()` pada sesi nyata | 56 entri, semuanya aplikasi terpasang (daftar Gio), setiap entri `windows: []` | Daftar aplikasi berasal dari berkas `.desktop`, bukan dari jendela yang benar-benar hidup |
| `list_windows()` pada sesi nyata | 2 jendela: satu 1×1 tak terlihat dan `"mutter guard window"` 1920×1200 | Tidak ada satu pun jendela aplikasi yang terlihat |
| `xprop -root _NET_CLIENT_LIST` pada sesi nyata | Kosong | Xwayland tidak punya klien; Firefox, ptyxis, ChatGPT, dan Brave semuanya klien Wayland native |
| `get_screenshot()` pada sesi nyata | Gagal: `X11 error ... request_name: Some("GetImage")` | Capture layar tidak mungkin lewat jalur X11 di sesi ini |
| Helper tanpa `DISPLAY` | Gagal: `Active X11 display is required for screenshot and command input` | Actuator memang mensyaratkan X server |
| `strings` helper | Membaca `_NET_CLIENT_LIST`, `_NET_CLIENT_LIST_STACKING`, `_NET_ACTIVE_WINDOW`, `_NET_WM_WINDOW_TYPE`, `_NET_WM_STATE`, `_NET_WM_PID` | Penemuan jendela bergantung pada window manager EWMH, bukan enumerasi X11 mentah |
| `list_windows()` pada Xvfb tanpa WM | Kosong meski ada jendela GTK yang hidup | Konsisten dengan ketergantungan EWMH di atas |
| Cakupan SDK | Tidak ada string `wayland` di seluruh `dist`; target hanya `linux`, `mac`, `windows` | Tidak ada backend Wayland yang bisa diaktifkan lewat konfigurasi |
| Sesi yang tersedia di mesin ini | `/usr/share/xsessions/` kosong; GNOME Shell 50.5 hanya menyediakan sesi Wayland | Sesi X11 tidak tersedia untuk dipilih |

Kesimpulan: pada mesin ini jalur actuator desktop Codex tidak dapat dipakai. Bukan karena konfigurasi yang kurang, tetapi karena actuator-nya X11/EWMH dan seluruh desktop berjalan sebagai klien Wayland, sementara sesi Xorg tidak lagi tersedia di GNOME 50. Menyalakan permukaan `computer` pada `cua-repl` tidak akan mengubah hasil ini.



## Opsi yang memenuhi bagian berbeda dari permintaan

| Jalur | Yang dipakai ulang | Fedora MCP | Model/loop | Status |
|---|---|---|---|---|
| A. Actuator `@oai/sky` langsung dari worker Node ZCode | Actuator desktop Codex (`sky_linux_x64`) + dokumentasi/skill Linux bundled | Tidak diperlukan | Model dan loop ZCode dipertahankan | **Gagal pada mesin ini**: actuator X11/EWMH, desktop berjalan Wayland, dan sesi Xorg tidak tersedia |
| B. Harness `@oai/cua-repl` lewat transport MCP yang sudah ada | Harness MCP Codex + trusted service mapping | Mungkin tetap ada untuk tool lain | Model ZCode | `computer` surface memakai actuator yang sama, jadi hasilnya mengikuti jalur A; menambah lapisan MCP tanpa menyelesaikan cakupan |
| C. Delegasi ke agent Codex lewat app-server | Planner, harness, dan model Codex sekaligus | Tergantung tool yang dipakai Codex | Model/provider Codex, bukan model ZCode | Mengganti planner, bukan hanya backend. Layanan browser milik host Codex tidak terbukti tersedia untuk client eksternal; provider harus Responses-compatible |
| D. Actuator Codex untuk X11/XWayland + portal untuk Wayland native | Actuator Codex untuk app yang terlihat X11; backend Fedora untuk sisa | Masih ada, cakupannya menyusut | Model dan loop ZCode | Pada sesi ini tidak ada jendela X11 untuk diambil alih, jadi bagian Codex-nya tidak berkontribusi. Hanya berguna untuk aplikasi yang sengaja dijalankan sebagai klien XWayland |
| E. Optimasi jalur portal yang ada (tanpa Codex) | Tidak ada runtime Codex | Tetap ada | Model dan loop ZCode | Satu-satunya jalur yang bisa dieksekusi sekarang untuk desktop Wayland; menyasar keluhan kecepatan, bukan mengganti backend |

VM macOS/Windows, backend Linux buatan sendiri, atau mengganti ke proyek computer-use lain tidak termasuk rekomendasi: semuanya mengubah target pengguna dan menambah prerequisite yang tidak tersedia dari permintaan ini.

Jalur A adalah kandidat reuse minimum: source SDK membangun client langsung ketika `globalThis.nodeRepl` tidak ada, dan target Linux dipilih dari `process.platform`. Penghapusan MCP Fedora untuk aplikasi yang tercakup menjadi konsekuensi wajar, bukan tujuan yang dipaksakan. Jalur B dan C tetap didokumentasikan agar keputusan pengguna berbasis pilihan nyata, bukan satu jalur yang disamarkan.

## Interface yang sudah terverifikasi

Import SDK dari instalasi terpasang:

```js
import { sky } from '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/@oai/sky/dist/project/cua/sky_js/src/index.js'
// sky.target === 'linux'
await import('@oai/sky/docs/skills/oai_sky_lib/linux/SKILL.md') // panduan penggunaan bundled
```

Helper yang di-spawn SDK saat request pertama: `/usr/lib/chatgpt/resources/cua_node/lib/node_modules/@oai/sky/bin/linux/sky_linux_x64 server` (`--mouse-size-px <n>` opsional, `OAI_SKY_LINUX_BIN` menimpa path). Stdin JSONL `{id:number,command:string,input:object}`; stdout sukses `{id,ok:true,output}` dan gagal `{id,ok:false,error,restart?}`. Protokol biner ini implementasi privat, bukan kontrak publik berversi, jadi sebaiknya lewat SDK dan bukan menulis ulang protokolnya.

Method Linux yang terbaca: `list_apps`, `launch_app`, `list_windows`, `activate_window`, `get_window_state`, `perform_secondary_action`, `get_screenshot`, `click`, `drag`, `drag_handle`, `move`, `move_relative`, `press_key`, `key_down`, `key_up`, `scroll`, `type_text`, `clipboard_read`, `clipboard_release`, `clipboard_write`. Contoh bentuk argumen: `click({window?,element_id?,x?,y?,mouse_button?,click_count?,duration?,key?})`, `type_text({text,window?,element_id?})`, `get_window_state({window,include_screenshot?,query?})`.

Resolver modul harus ditangani eksplisit: paket ini tidak terpasang di `node_modules` project, jadi bridge perlu path absolut atau alias, bukan berharap resolusi paket global.

## Kontrak integrasi yang diusulkan

ZCode tetap account-free terhadap Z.ai. Reuse Codex tidak berarti menghidupkan kembali login/cloud ZCode. Executor Codex dapat punya autentikasi provider sendiri; pilihan memakai akun Codex atau gateway Responses harus dinyatakan di UI dan dipilih eksplisit. Jangan membaca/menyalin `~/.codex/auth.json` ke namespace ZCode.

- Satu task ZCode memiliki satu executor/thread Codex; simpan pemetaan ID saja pada namespace standalone.
- Electron main memiliki child process app-server lewat stdio. Renderer tidak boleh menjalankan proses, memilih command bebas, atau memegang kredensial.
- Gunakan event streaming untuk progress, approval, hasil, dan error; jangan polling screenshot melalui prompt agent luar.
- Mulai/resume thread dan `turn/start` hanya untuk task yang diminta pengguna. `initialize` bukan izin untuk bertindak.
- Approval dari Codex diteruskan ke pengguna; deny/cancel tetap deny/cancel. Jangan mengubahnya menjadi always-allow untuk mengejar kecepatan.
- Stop ZCode menghentikan turn aktif dengan `turn/interrupt` dan cleanup tool host sesuai kontrak versi; completion dibuktikan dari event/state, bukan hanya acknowledgement request.
- Satu pemilik input pada satu permukaan; tidak ada dua executor yang saling mengklik layar/tab.
- Situs, screenshot, DOM dan file adalah data tidak tepercaya, bukan instruksi sistem. Tindakan sensitif tetap memerlukan konfirmasi.
- App-server stdio dipilih agar tidak membuka port kontrol desktop ke jaringan. Socket/pipe milik Codex tidak dibuka dengan impersonasi session atau pengabaian izin host.
- Model hanya dipilih bila mendukung image input dan tool calling yang benar-benar tersedia. Klaim bahwa semua model murah akan setara dengan Codex tidak dibuat.

Untuk A, jalur target adalah UI/task ZCode, agent ZCode, lalu worker Node main yang memanggil SDK `@oai/sky`; tidak ada MCP dan tidak ada app-server. Untuk B, harness `cua-repl` berjalan sebagai MCP server. Untuk C, app-server menggantikan planner ZCode dan akses tool mengikuti kebijakan host Codex. Jangan menyamakan ketiga jalur tersebut di label UI atau dokumentasi.

## Tahapan dan gate

### 1. Proof-of-integration, sebelum penghapusan

Langkah cakupan **sudah dijalankan** dan hasilnya ada di bagian "Hasil probe cakupan": actuator Codex tidak melihat jendela aplikasi apa pun dan gagal menangkap layar pada sesi ini. Karena jalur A dan B berakhir di actuator yang sama, tidak ada gunanya melangkah ke input/restart test untuk keduanya sebelum cakupan berubah (mis. desktop dipindah ke sesi X11).

Yang masih layak dan aman dijalankan berikutnya:

1. Pin versi paket Codex dan catat pada jurnal bila runtime ini akan dipakai lagi; jangan mengandalkan path yang berubah saat paket diperbarui.
2. Ukur jalur desktop yang ada sekarang (jalur E) pada fixture disposable: berapa observasi gambar dan token konteks yang terpakai per tugas, berapa bagian waktu untuk inferensi versus tool. Ini gate yang menentukan arah perbaikan.
3. Bila memilih jalur D, tentukan lebih dulu aplikasi mana yang benar-benar berjalan sebagai klien XWayland, lalu uji satu siklus penuh pada aplikasi itu di layar terpisah.
4. Untuk jalur C, verifikasi handshake app-server, event approval/interrupt, dan apakah thread eksternal benar-benar memperoleh layanan browser host. Jangan hanya menguji server hidup atau `tools/list` yang tidak kosong.
5. Untuk gateway model existing, validasi Responses streaming, tool-call round trip, image input, dan resume. `/v1/models` saja tidak membuktikan kompatibilitas.
6. Jangan patch flag `computer`, jangan memalsukan atom EWMH, dan jangan mengubah sesi desktop hanya supaya probe terlihat berhasil.

### 2. Pengukuran jalur yang ada (jalur E)

Tujuan tahap ini bukan membandingkan backend impian, melainkan menemukan di mana waktu benar-benar habis pada jalur portal yang dipakai sekarang. Fixture disposable, tanpa akun pribadi.

- Task web sederhana: navigasi, satu form, hasil yang bisa diverifikasi.
- Task web panjang: beberapa halaman/form plus satu pemulihan dari state error.
- Task aplikasi non-browser: buka aplikasi terpasang, ubah state disposable, verifikasi hasil.
- Ukur waktu total, waktu inferensi, jumlah observasi gambar, ukuran konteks, jumlah tool call, latensi tool, keberhasilan task, dan intervensi pengguna. Pisahkan cold start dari warm run.
- Bila ingin pembanding Codex, ukur pada task web yang sama di aplikasi Codex dan catat bahwa harness serta modelnya berbeda; jangan menyimpulkan sebab dari satu selisih waktu.
- Keputusan yang dihasilkan: bila biaya observasi/gambar mendominasi, prioritaskan jalur aksesibilitas/DOM dan screenshot sebagai verifikasi; bila inferensi mendominasi, prioritaskan model dan pengurangan putaran keputusan. Angka target ditetapkan dari hasil ukur, bukan dikarang sebelum pengukuran.

### 3. Integrasi produk (hanya bila cakupan berubah)

Bagian ini berlaku **hanya jika** salah satu dari dua hal terjadi: desktop berpindah ke sesi X11 yang benar-benar tersedia, atau ada backend Codex/Vendor lain yang terbukti melihat jendela Wayland. Selama kondisi itu belum ada, jalur A/B tidak boleh diimplementasikan dan backend lama tidak boleh dihapus.

Buat bridge sekecil yang perlu untuk start/resume/stream/approval/stop. Gunakan komponen ZCode yang ada; desain UI belum dilakukan pada planning ini.

Dua seam yang berbeda dan tidak boleh dicampur:

- Jalur A/B mempertahankan task dan loop model ZCode; bridge hanya bereperan sebagai penyedia tool (menggantikan registrasi tool managed) dan menerjemahkan input/output/gambar/stop. Loop model tetap satu pemilik keputusan.
- Jalur C mengganti harness: app-server dimiliki main sebagai child process, satu task satu thread, progress/approval/result dialirkan sebagai event, stop diteruskan sebagai `turn/interrupt`. Jangan membuat loop ZCode meminta tiap klik/screenshot dari Codex; itu mempertahankan overhead keputusan ganda dan tidak memakai ulang harness Codex.

Jangan mengikat adapter ke broker internal ZCode atau menganggap kemiripan SDK sebagai interoperabilitas; kontrak yang dipakai adalah interface yang benar-benar terverifikasi pada tahap proof-of-integration.

Komposer menampilkan executor aktif dan pemilik model secara jelas. Settings menampilkan readiness Codex, versi, permukaan browser/desktop yang benar-benar tersedia, serta izin. Dependency mati menghasilkan error nyata, bukan fallback diam-diam ke backend lama.

Voice tetap menghasilkan teks melalui composer yang sama; pilihan bahasa, preview/auto-send, recorder ownership dan timeout tidak berubah. Activity/riwayat task tetap lokal; jangan mengimpor task Codex yang sudah ada.

### 4. Clean cutover dan penghapusan total (kondisional)

Berlaku hanya setelah tahap 3 lolos. Penghapusan berlangsung dalam satu cutover koheren setelah replacement memenuhi seluruh scope yang dipilih pengguna. Build tetap berbasis baseline pinned dengan assertion anchor unik. Daftar di bawah berasal dari pemetaan caller di repo, bukan tebakan: jalur Linux aktif adalah MCP `fedora-desktop`, sedangkan CUA native upstream masih dikemas terpisah dan bukan backend yang dipakai sekarang.

Canonical yang wajib ikut berubah:

- `src/renderer/linux-computer-use.js`: seluruh UI Linux (guard workspace, lookup/toggle MCP, shortcut Settings, salinan readiness). Catatan: shortcut hanya membuka settings, bukan tombol run/stop, dan tetap tampil saat backend mati.
- `scripts/build.py`: anchor `iOn`/`originalCuaSettings` dan wrapper `mit`, plus daftar resource staging. Sisipan Voice terpisah dan tidak boleh ikut dicabut.
- `scripts/install_local.py`: pembuatan/perawatan entri managed `data/.zcode/cli/config.json` (`mcp.servers.fedora-desktop` beserta enam env backend) dan migrasi yang membedakan entri managed dari server user bernama sama.
- `scripts/check.py`: pemeriksaan syntax `zcode_fast_profile.py` saat profile itu tidak lagi dipakai.
- `project.json` dan symlink kompatibilitas `screen-mcp`: jangan dihapus sebelum pemakaian eksternal terbukti tidak ada.
- `src/local_only/storage.py`: anchor native computer-use yang menunjuk path owner yang akan hilang.

Setelah seluruh caller pindah, `services/desktop/` (server, capture, input, state, reliability, profile, launcher, dependency) menjadi obsolete sebagai satu paket. Boundari sisi native yang juga perlu ditangani bila scope-nya dihapus:

- Renderer baseline: routing settings `computerUse` dan readiness, aktivasi composer native, serta permukaan yang mencari `originalCuaSettings`.
- Host baseline: lifecycle/resolver helper, admission plugin, env, dan state reporter (`shouldEnableDefaultCuaProductHelper` hanya darwin/win32, jadi Linux memang tidak pernah memakai helper native).
- Main baseline: IPC permission/onboarding drag, PiP session, `GetCuaOsSupport`, dan ekspor diagnostik terkait.
- Paket bundled `app/resources/glm/packages/zcode-cua-plugin` (skill, client, docs) serta id plugin resmi `computer-use@zcode-plugins-official` (dan id lama `zcode-cua@zcode-plugins-official`).
- `app/resources/glm/packages/node-repl-host` dipakai bersama runtime browser; bila bridge CUA native dicabut, itu penghapusan selektif, bukan menghapus paket bersama.
- Renderer/komponen yang mengandung kata `cua` tetapi milik browser tidak dihapus hanya karena namanya.

Packaging dan pengujian:

- Bila adapter baru menjadi modul sendiri, `scripts/build.py` (resource + proof), `scripts/apply_build.py` (promotion set), dan `tests/test_apply_build.py` (nama resource) ikut berubah. Bila adapter tetap di dalam asset yang sudah dipatch, daftar resource tidak perlu berubah.
- `tests/test_local_only_patches.py` dan guard cloud perlu diperbarui saat layanan/channel hilang; IPC browser dan lokal yang tidak terkait tetap.
- Suite pytest `services/desktop/tests/` (input, contract, capture, output budget, reliability, grounding, sense, watch, dan seterusnya) menguji kontrak keselamatan; kasus yang relevan dipindahkan ke interface pengganti, bukan dihapus tanpa pengganti. Test normalizer Voice tidak termasuk yang obsolete.
- Dokumentasi terkait: `README.md` (fitur/struktur), `AGENTS.md` (aturan desktop), `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/OPERATIONS.md`, `docs/THIRD_PARTY.md` (provenance screen-mcp), dan `CHANGELOG.md` sebagai catatan baru, bukan penulisan ulang riwayat.
- Migrasi config namespace harus mempertahankan MCP lain, keadaan disabled milik pengguna, dan jalan rollback.

Yang tidak boleh diwariskan sebagai klaim ke pengganti: backend lama **tidak** memiliki approval destruktif yang selalu aktif (`MCP_SCREEN_GUARD` mati secara default) dan batch `screen_do` melewati wrapper ack/allowlist. Pengganti tidak boleh mengklaim lebih ketat daripada kenyataan, dan guard yang benar-benar ada (guard tiap langkah input, yield pada STOPPED, stale-view/focus check, cleanup PipeWire/uinput) harus tetap punya padanan.

### 5. Verifikasi dan rollout

`make build && make test`; smoke aplikasi staged pada namespace terpisah tanpa login gate/channel hilang/runtime exception. UI diuji langsung untuk start/progress/approval/stop/error/restart, tanpa prompt ke akun pribadi sekadar inspeksi layout.

Task acceptance menggunakan fixture terisolasi dan provider yang dipilih secara eksplisit. Restore backup diuji pada salinan, bukan aplikasi/data pengguna. Setelah itu tutup app normal, apply checksum-manifest dan verifikasi ulang. Jangan menjalankan install atau mematikan task aktif tanpa kebutuhan deployment yang disetujui.

## Rollback

Backup versi terpasang sebelum riset: `runtime/backups/current`, lima resource dan `backup-manifest.json`. Perubahan docs pada planning ini tidak mengubah resource live atau backup itu.

Sebelum implementasi, verifikasi ulang checksum backup serta kecocokan baseline/source yang akan dipulihkan. Backup tersebut hanya resource patch, bukan snapshot task atau semua dependency. Backup namespace offline dan config MCP/integrasi dilakukan terpisah sebelum migrasi config; backup tetap privat dan tidak di-commit.

Rollback menutup app normal, memulihkan resource/config/integrasi sebagai satu set, lalu smoke di root terpisah. Revert source commit saja tidak memulihkan config pengguna yang sudah dimigrasikan. Jangan mengekspor namespace env di shell persisten.

## Gate yang masih terbuka

- Reuse actuator desktop Codex di mesin ini: **tertutup dengan hasil negatif**. Actuator X11/EWMH, desktop Wayland, tidak ada sesi Xorg. Buka kembali hanya bila sesi X11 benar-benar tersedia atau paket Codex kelak membawa backend Wayland.
- Yang masih perlu diukur: distribusi waktu jalur portal sekarang (inferensi versus observasi/tool). Ini gate sebenarnya untuk keluhan kecepatan, dan belum dijalankan.
- Kesiapan helper Sky pada workstation ini (library, permission, SELinux, perilaku restart) tidak perlu diuji lebih jauh selama jalur A/B ditutup.
- Model/provider ZCode tetap harus mendukung vision dan tool calling; mengganti actuator tidak menambah kemampuan model.
- Lisensi: paket RPM berlisensi proprietary dan manifest SDK tidak mencantumkan lisensi. Opsi paling aman tetap memakai instalasi lokal sebagai prerequisite, bukan menyalin atau mem-package ulang.
- Rollback: `runtime/backups/current` (lima resource) tetap berlaku untuk setiap perubahan resource yang nanti dipromosikan.

Kesimpulan yang harus dipegang: penggantian total backend desktop tidak bisa dijanjikan pada konfigurasi mesin ini, dan tidak ada perbaikan kecepatan yang boleh diklaim sebelum pengukuran jalur E selesai. Backend lama tetap satu-satunya jalur desktop yang berfungsi, jadi ia tidak boleh dihapus.
