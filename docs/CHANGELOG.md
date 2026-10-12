# Changelog

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
