# Peningkatan Computer Use Linux

Status: tahap 1 dikerjakan 2026-10-13. Ruang lingkup: backend `services/desktop` yang dipakai varian standalone, bukan penggantian engine.

## Tujuan

Lima target yang diminta: cepat, ringan, akurat, pinter, dan bisa mengerjakan task apa saja. Empat yang pertama punya tuas konkret di backend; yang kelima tidak bisa dijanjikan mutlak dan batasnya dicatat di bawah.

## Diagnosis yang memandu perubahan

- Backend server sebenarnya sudah punya jalur murah dan akurat, tetapi profil `ccode-fast` memotong permukaan tool menjadi 10 tool screenshot-lalu-tebak dan menulis ulang deskripsi screenshot tanpa menyebut `annotate` maupun `use_cache`.
- `screen_click` menerima `element=<id>` dan server menyelesaikan koordinat tepatnya, tetapi model tidak pernah diberi tahu bahwa jalur itu ada.
- Setiap aksi mengembalikan gambar. Biayanya tetap per gambar (sekitar 1.300 token pada batas 1280 px), dan aksi yang tidak mengubah apa pun tetap membayar biaya itu plus mengundang model mengulang klik yang sama.
- Guard takeover hanya membandingkan posisi kursor dengan posisi terakhir yang kita perintahkan (ambang 40 px). Gerakan menyenggol mouse karena itu membatalkan aksi, walaupun pengguna tidak sedang mengendalikan apa pun.

## Perubahan yang dikerjakan (tahap 1)

Semua di `services/desktop/ccode_fast_profile.py`, dimuat oleh server saat `MCP_SCREEN_PROFILE=ccode-fast`. File vendor `server.py`, `capture.py`, dan `input.py` tidak disentuh.

| Perubahan | Efek |
|---|---|
| Permukaan tool ditambah `screen_read_text`, `screen_wait_text`, `screen_verify`, `screen_sense`, `screen_focus` | Model bisa memeriksa keadaan sebagai teks, menunggu label muncul, dan memastikan fokus sebelum mengetik, bukan menebak dari gambar |
| Deskripsi `screen_screenshot` mengajarkan Set-of-Marks (`annotate=true`), cache elemen (`use_cache`), dan crop `region` untuk teks kecil | Nama/ikon bernomor bisa diklik langsung; OCR layar yang sudah dikenal dilewati |
| Deskripsi `screen_click` mengarahkan ke `element=<id>` dan menyebut `verify=true` | Klik memakai koordinat hasil deteksi, bukan hasil terkaan, dan salah klik yang senyap bisa diketahui |
| Gambar pasca-aksi dilewati saat SENSE menyatakan tidak ada perubahan | Aksi no-op tidak lagi membayar token gambar; model tetap diberi tahu bahwa aksinya gagal |
| Mode tunggu perubahan diubah ke `hybrid` (event damage dengan lantai poll) | Deteksi perubahan frame lebih cepat daripada polling tiap 60 ms |
| Kebijakan pointer: hysteresis berbasis jendela sampel | Gerakan menyenggol tidak lagi menghentikan task; hanya pengendalian yang berkelanjutan yang dialihkan ke pengguna |

### Kebijakan pointer

Guard bawaan diganti pembungkusnya, bukan dihapus:

- Divergensi kursor dinilai atas jendela sampel. Kursor yang berhenti di tempat lain (diparkir) dianggap idle, dan aksi tetap jalan.
- Kursor yang terus bergerak sepanjang jendela `CCODE_CUA_TAKEOVER_MS` dianggap pengambilalihan nyata: aksi dibatalkan dengan pesan `STOPPED` yang sama seperti sebelumnya.
- Pointer yang tidak terbaca tetap gagal-terbuka, sama seperti guard bawaan.
- `force=true` tetap menerobos kebijakan ini, dan instruksi model tetap melarang memakainya untuk melawan pengambilalihan.
- Kanal berhenti yang tersisa: pengendalian kursor berkelanjutan oleh pengguna, dan tombol stop task di UI CCode.

Yang tidak dilakukan: membiarkan agent terus mengklik sementara pengguna aktif memakai desktop. Satu pointer berarti input agent mendarat di jendela yang baru difokuskan pengguna; karena itu pengambilalihan nyata tetap menghentikan aksi.

## Konfigurasi

| Env | Default | Arti |
|---|---|---|
| `CCODE_CUA_IDLE_MS` | 600 | Lama kursor harus diam sebelum dianggap idle |
| `CCODE_CUA_IDLE_PX` | 8 | Ambang gerak antar sampel yang dianggap "masih bergerak" |
| `CCODE_CUA_TAKEOVER_MS` | 2500 | Lama pengendalian berkelanjutan sebelum dianggap pengambilalihan |
| `CCODE_CUA_POLL_S` | 0.1 | Jeda antar sampel kursor saat divergensi |
| `CCODE_CUA_SKIP_UNCHANGED_SHOT` | 1 | Set `0` untuk selalu mengirim gambar pasca-aksi |
| `CCODE_CUA_WARMUP` | (kosong) | Set `1` untuk memuat model OCR/OmniParser saat MCP start lagi (~60 MB prefetch) |
| `MCP_SCREEN_WAIT_MODE` | (profil menetapkan `hybrid`) | Setel `poll` untuk kembali ke perilaku lama |

Perubahan ini berlaku saat MCP desktop dimuat ulang (chat baru atau CCode dibuka ulang). Env di atas dibaca oleh profil, jadi tidak perlu `make install`.

## Berikutnya (belum dikerjakan)

1. **Pengukuran**: jumlah giliran, jumlah gambar, token konteks, dan waktu per fase pada satu task nyata. Tanpa angka ini, klaim kecepatan hanya dugaan.
2. **AT-SPI sebagai sumber utama** saat pohon elemen tersedia (`atspi_tree.elements()` sudah ada dan dipakai `_perceive`), dengan vision sebagai cadangan.
3. **Anotasi sebagai default** untuk screenshot pertama pada layar baru, kalau hasil pengukuran menunjukkan biaya OCR-nya terbayar.
4. **Crop ke jendela fokus** sebagai default observasi, bukan seluruh desktop.
5. **Pemeriksaan elemen basi** untuk id yang berasal dari `screen_read_text`, karena jalur itu tidak menandai view seperti jalur `annotate`.

## Batas jujur

- Perubahan ini belum diuji pada desktop nyata. Tes yang ada menutup logika profil (permukaan tool, default, kebijakan pointer, aturan lewati gambar); capture, OCR, dan portal baru terbukti saat aplikasi benar-benar dipakai.
- Cakupan AT-SPI tidak merata: aplikasi GTK dan Qt bagus, Electron sebagian, canvas/game tidak ada. Vision tetap wajib sebagai cadangan.
- Aplikasi tanpa teks yang terbaca tetap lambat dan rawan salah klik, apa pun modelnya.
- Empat tool menulis ke desktop (`screen_read_page`, `screen_read_selection`, `screen_tour`, `screen_reload`) sengaja tetap tidak diekspos.
