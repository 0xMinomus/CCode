# Uji tanpa login — 2026-10-12

> Catatan historis. Uji ini memakai salinan aplikasi terpisah dan mencatat bahwa produksi **belum** diubah ke mode local-only. Sejak cutover standalone, jalur akun/cloud sudah dihapus dari aplikasi; lihat CHANGELOG dan ARCHITECTURE untuk keadaan saat ini.

## Kesimpulan

ZCode packaged 3.14.5 dapat membuka workspace dan menggunakan provider mandiri tanpa kredensial akun ZCode. Jalur bawaan `Use API key → Skip for now` sudah mendukung ini. Menghapus login wajib tidak memerlukan penulisan ulang harness dasar.

Belum ada perubahan login pada aplikasi produksi. Eksperimen ada di `runtime/no-login`, dan script persiapannya di `scripts/experiments`.

## Metode

- Salinan app dibuat terpisah dengan direktori Electron/data tersendiri.
- Tidak menyalin kredensial akun, tidak membuat JWT palsu, dan tidak mengubah entitlement layanan.
- Konfigurasi Vansrouter pribadi dimasukkan hanya pada config runtime yang diabaikan Git, dengan izin 0600. API key tidak dicetak.
- Backend akun diarahkan ke loopback `127.0.0.1:28081`, yang selalu mengembalikan 503. Endpoint UI `https://zcode.z.ai` pada enam asset eksperimen juga diarahkan ke backend ini.
- Memakai jalur Skip bawaan; tidak memalsukan status authenticated.
- Mengirim satu prompt sederhana ke `oc/space-bunny-free` melalui Vansrouter dengan reasoning Low: `Reply exactly LOCAL_PROVIDER_TEST_OK. Do not use tools, browse, or read files.`
- Menutup dan merestart app tes, lalu membuka chat tersimpan kembali.

## Hasil

| Pemeriksaan | Hasil |
|---|---|
| Halaman awal tanpa credentials | Menampilkan welcome/login dengan API-key flow |
| Skip login | Workspace terbuka; sidebar masih menampilkan Connect |
| Agent via provider mandiri | Balasan `LOCAL_PROVIDER_TEST_OK`, sekitar 4 detik |
| Kredensial akun | `credentials.json` tidak dibuat pada profil tes |
| Penyimpanan lokal | SQLite tasks-index menyimpan task pada workspace runtime/no-login |
| Restart | Task dan balasan dapat dibuka lagi; tetap signed out |
| Backend akun | Selalu 503; keberhasilan provider tidak bergantung pada backend akun |

## Batas dan pekerjaan berikutnya

1. Ini bukan audit semua trafik internet. Backend akun utama dibuat tidak tersedia, tetapi telemetry/CDN/updater atau domain hardcoded lain belum diaudit secara menyeluruh. Jangan menyebutnya aplikasi yang seluruh koneksi ZCode-nya sudah dihapus.
2. Aplikasi masih mencoba `/api/v1/client/configs`, `/api/v1/client/scenes`, `/api/v1/event/report`, dan `/api/v1/marketing/touch`. Mode local-only seharusnya tidak memanggil jalur ini.
3. Environment direktori data tidak menjadi sandbox filesystem penuh. Legacy scanner memasukkan 14 metadata task dari instalasi pengguna ke indeks tes, walaupun task tes memakai workspace tersendiri. Indeks utama berisi 14 task saat pemeriksaan; task tes tersimpan di indeks eksperimen. Sebelum fork mandiri, pisahkan namespace data dan nonaktifkan/minta opt-in untuk migrasi lintas instalasi.
4. Yang diuji adalah teks/chat/provider dasar. Seluruh plugin, remote/cloud features, updater, dan deployment distribusi belum dibuktikan bekerja tanpa layanan akun.
5. Hasil teknis ini tidak menyelesaikan lisensi redistribusi paket installer atau third-party.

## Rekomendasi implementasi minimal

- Mode local-only bersifat eksplisit dan default bagi pengguna provider mandiri.
- Gunakan jalur account-skip yang sudah ada, lalu hapus welcome/login wajib dari pengalaman local-only tanpa menganggap pengguna sudah authenticated.
- Account services, analytics, marketing, client-scenes/config polls, serta cloud-only features dihentikan/dinonaktifkan dalam mode tersebut.
- Provider membawa autentikasinya sendiri. Jangan memberi entitlement Z.ai/BigModel pada pengguna yang tidak login.
- Gunakan app identity dan direktori data khusus agar tidak berbagi/mengimpor data ZCode asli tanpa pilihan pengguna.
- Uji lagi cold start, restart, streaming, tool permission, MCP, dan backup setelah perubahan.

## Artefak

Screenshot dan log pengujian ada di runtime/no-login (ignored). Backend stub mencatat hanya method/path, tanpa header, body, atau API keys. Launcher pengguna dicadangkan sebelum eksperimen dan dipulihkan setelah tes.
