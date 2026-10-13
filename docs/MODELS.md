# Model Vansrouter dan reasoning

Live provider config varian standalone berada di `~/.local/share/zcode-on-steroids/data/.zcode/v2/provider_config.json` (root dapat dipindah lewat `ZCODE_STANDALONE_ROOT`). Instalasi lama di `~/.zcode/v2/provider_config.json` tetap ada dan tidak diubah. Source sinkronisasi berada di `services/model-sync/sync.py`; cache/state merupakan runtime, bukan source yang perlu di-commit.

## Discovery 9Router (otomatis, terkelompok)

Gateway 9Router di `http://127.0.0.1:20128/v1` menerbitkan daftar modelnya di `GET /v1/models` (440 model, tanpa auth untuk pemakaian lokal). `sync.py` memakai daftar itu untuk mengisi provider keluarga **9Router** di `provider_config.json`:

- **Pengelompokan**: `combo/*` menjadi provider `9Router` (ditampilkan paling atas); namespace dengan ≥10 model menjadi provider sendiri (`9Router · kios`, `9Router · kioc`, `9Router · cmc`, …); sisanya digabung ke `9Router · lainnya`. Ambang 10 = `DISCOVERY_GROUP_MIN`.
- **Metadata**: `capabilities` gateway (`contextWindow`, `maxOutput`, `vision`, `pdf`, `videoInput`, `search`, `reasoning`, `thinkingEffortSupported`, `thinkingCanDisable`) mengisi rule model. Bila gateway tidak menyebutkan limit (mis. tier gratis `oc/*`), snapshot OpenCode/models.dev dipakai sebagai fallback. Model yang tidak dikenal kedua sumber dibiarkan keluar dari daftar dan dicatat di `state.json` (`discovery.skipped`), bukan diisi angka karangan.
- **Kontrol reasoning**: level hanya ditawarkan bila gateway menyatakan dukungan effort; nilainya diambil dari himpunan yang benar-benar divalidasi gateway (`off|low|medium|high|xhigh|max`, error validasi gateway memuat daftar ini) dan dipetakan ke `reasoning_effort`. Model tanpa dukungan effort terverifikasi memakai placeholder inert `{"values":["disabled"],"map":"{}"}` — schema host mewajibkan `optionSpecs.reasoningLevel` ada, dan placeholder ini tidak mengirim parameter apa pun.
- **Satu rule per model**: model yang sudah punya rule katalog (smart) tidak boleh juga punya rule manual — host menolak config dengan pesan "同一 Provider/Model 不能同时声明智能和手动配置". Rule manual yang sebelumnya kita tulis untuk model seperti itu dihapus otomatis. Sebaliknya, smart rule yang tersisa untuk model yang **tidak lagi** didefinisikan katalog (mis. `combo/coding-harian` pada provider yang dibuat sebelum template dibersihkan) bersifat inert — host tidak merendernya — sehingga discovery menghapus rule basi itu dan menulis manual rule sebagai gantinya, supaya model tetap bisa dipakai.
- **Toggle on/off milik pengguna**: host menyimpan switch per model sebagai `config.enabled` pada rule manual. Refresh metadata mempertahankan field itu; model yang dimatikan pengguna tetap **tampil** sebagai baris dengan switch off (id-nya kembali ke `personalModelIds`, flag `enabled:false` dipertahankan) sehingga bisa dinyalakan lagi kapan saja, model yang dihapus tidak dihidupkan kembali (dicatat di `discovery.removed`), dan rule yang diedit tangan tidak ditimpa.
- **Satu API key untuk satu keluarga**: key yang ditempel di salah satu provider keluarga disebar ke provider keluarga lain yang masih memakai placeholder `DISCOVERY_API_KEY_PLACEHOLDER` (`local-gateway`; gateway lokal tidak memerlukan key).
- **Kapan jalan**: provider keluarga 9Router dibuat dari template katalog yang **tidak menyemai model apa pun**, jadi model list-nya mulai dengan `No models are configured`. Tiga pemicu mengisinya: (1) **tombol Auto Detect** di header Model list (sebelah kiri `+ Add model`) — pengguna mengisi API key lalu menekan tombol ini, yang menjalankan discovery + pembuatan grup sekarang juga via IPC lokal `zcode-detect:run` dan menampilkan hasilnya (mis. `Added 12 providers · 433 models`); (2) unit systemd path `zcode-on-steroids-model-sync.path` yang memantau `provider_config.json` sehingga write dari app (provider dibuat atau API key diubah) menjalankan sync; (3) timer 60 detik + TTL 12 jam (`DISCOVERY_TTL_SECONDS`) sebagai jaring rutin, plus kondisi `needs_fill` untuk provider yang masih kosong atau belum dikelompokkan. Gateway mati → no-op dengan backoff 15 menit, config pengguna tidak disentuh. Untuk memaksa dari terminal: `make models` (atau `python3 services/model-sync/sync.py --discover --bootstrap`).
- **Penghapusan milik pengguna dihormati, tanpa heuristik**: run otomatis (timer/path unit) **hanya mengisi grup yang sudah ada** dan tidak pernah membuat grup baru; pemulihan/pembuatan keluarga provider adalah aksi eksplisit — tombol **Auto Detect** atau `make models` (keduanya `--bootstrap`). Jadi grup yang kamu hapus tetap terhapus, dan sekali klik Auto Detect membangunnya kembali. Aturan lama (`removedProviders` + ambang penghapusan massal) dibuang karena tidak bisa membedakan "user menghapus 11 grup satu per satu" dari "file ditulis ulang" — dengan kontrak ini tidak ada lagi sync yang melawan pengguna maupun yang membangkitkan grup diam-diam. Di level model: penghapusan hanya diingat bila jumlahnya kecil (≤5 per run) dan provider-nya tidak jadi kosong; daftar yang dikosongkan/ditulis ulang diisi ulang, dan model yang dikenal host tetapi tidak terdaftar didaftarkan kembali dengan switch mengikuti flag rule-nya.
- **Pengaman data**: `sync.py` hanya menambah model, sehingga `commit()` menolak menulis config yang mengurangi jumlah model aktif (≥5 model). Backup pra-tulis tetap disimpan maksimal 10 di `<namespace>/model-sync/backups/`.

Timer `zcode-on-steroids-model-sync.timer` menjalankan sync untuk namespace standalone dengan env `ZCODE_MODEL_SYNC_CONFIG` dan `ZCODE_MODEL_SYNC_STATE`. Tanpa env tersebut, `sync.py` tetap memakai jalur lama (`~/.zcode/v2/provider_config.json`) supaya timer instalasi lama tidak berubah perilakunya.

Status **Auto Detect** (proses, sukses, atau gagal) tampil di kiri tombol. Label dan ukuran tombol tetap selama deteksi; pesan panjang dipotong sesuai ruang header, dengan pesan lengkap pada tooltip dan status yang diumumkan melalui `role="status"`.

## Reasoning Vansrouter

`oc/` dipetakan ke katalog OpenCode. Hanya model yang sudah didaftarkan di provider Vansrouter ZCode yang dilengkapi. Level `effort` berasal dari `reasoning_options.values`; pilihan dikirim melalui `reasoning_effort`. Toggle membutuhkan wire format yang diketahui, misalnya `reasoning.enabled` untuk Ling dan `thinking.type` untuk LongCat. Nama model saja tidak membuktikan dukungan semua level.

Pemetaan ZCode berupa expression string, contoh:

```json
{"values":["low","medium","high","xhigh","max"],"map":"{\"reasoning_effort\": reasoningLevel}"}
```

Simpan di `config.optionSpecs.reasoningLevel` pada manualProviderModelRules model terkait. Objek `optionSpecs` wajib ada pada manual rule; menghilangkannya pernah membuat ZCode menolak seluruh personal provider config. Gunakan backup dan validasi parser ketika mengubah schema.

Pemetaan yang secara eksplisit diubah pengguna tidak ditimpa. Model tak dikenal, routing suffix effort, dan combo dilewati. Combo bisa mengunci effort masing-masing anggotanya; jangan membuat pilihan Low di UI bila rute upstream tetap memaksa Max.

Tes acceptance API dan pemeriksaan payload membuktikan parameter terkirim/diterima, bukan mengukur jumlah reasoning internal model. Availability upstream tetap dapat berubah walaupun metadata model benar.
