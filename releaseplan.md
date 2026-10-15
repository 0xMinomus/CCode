# Rencana rilis CCode

Tujuan: CCode bisa **diunduh dan langsung dipakai** sebagai aplikasi mandiri (bukan patch atas binary orang lain), terbuka sebagai open source, dan mengakui secara eksplisit bahwa ini turunan dari ZCode.

Dokumen ini rencana; status hari ini ada di [README.md](README.md) dan [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Target rilis yang disepakati

Target rilis pertama adalah **Linux x64** (`.AppImage`, `.deb`, `.rpm`) dan **Windows x64** (installer `.exe`). ARM64 dan macOS di luar scope rilis ini. Jalur resmi tetap fork source; workspace patch Linux menjadi acuan perilaku, bukan installer lintas OS.

Build dan verifikasi Linux dikerjakan di lingkungan Linux. Installer Windows disiapkan dari source beserta dependency x64 yang sesuai; bila build memerlukan toolchain Windows, gunakan runner Windows. Pengguna menguji `.exe` di mesin Windows miliknya. Build berhasil tidak membuktikan aplikasi berjalan: artifact Windows belum layak dinyatakan siap rilis sebelum hasil pengujian pengguna lolos dan dicatat.

Computer Use dan model-sync tetap masuk scope porting Windows. Implementasi portal dan systemd Linux tidak dapat dipakai langsung di Windows; masing-masing memerlukan backend atau integrasi OS yang sesuai. Voice dihapus dari seluruh platform sesuai keputusan 2026-10-15 di `linuxrelease.md`. n8n dipasang pengguna dari Plugin Marketplace, dengan dependency lengkap di zip release asset publik. Fitur lain yang belum berfungsi harus dilaporkan sebagai penghambat, bukan dihilangkan diam-diam atau diklaim setara.

## 1. Fakta yang menentukan rencana

Diverifikasi 2026-10-13:

| Fakta | Nilai |
|---|---|
| Repo upstream | `github.com/zai-org/ZCode` — publik, monorepo lengkap (bukan cuma harness) |
| Lisensi upstream | **Apache-2.0**, `Copyright 2026 Z.AI Co., Ltd` (root `package.json`: `"license": "Apache-2.0"`) |
| Paket di upstream | `packages/desktop` (Electron + e2e wdio), `packages/{rpc,provider,provider-node,shared,services,client,server,zcode-server-cli,ui,web}`, `apps/zcode-cli` |
| Toolchain upstream | Node **>= 24**, `pnpm@10.33.2`, TypeScript 6, vitest; skrip `bootstrap`, `build:zcode`, `bundle:desktop`, `build:sea`, `docker` e2e |
| Versi | `main` = 3.15.1; tag rilis terakhir = `v3.14.3` (2026-09-24); baseline binary yang dipakai workspace ini = 3.14.5 |
| Notice wajib | `NOTICE.md`, `THIRD-PARTY-NOTICES.md`, `LICENSE` (ketiganya ada di root upstream) |
| Trademark | tidak ada `TRADEMARK.md` → Apache-2.0 §6 tetap berlaku: **tidak ada** izin memakai nama/merek ZCode |

**Konsekuensi:** forking dan redistribusi **diizinkan** oleh lisensinya, jadi target "user tinggal download dan pakai" realistis. Tapi "tidak memegang lisensi apa pun" tidak tepat: kamu **mewarisi kewajiban Apache-2.0** (ringan, bukan copyleft) dan **tidak boleh memakai merek ZCode** — yang justru sudah sejalan dengan rebrand CCode.

## 2. Keputusan arsitektur

| Jalur | Cara kerja | Kelebihan | Kekurangan |
|---|---|---|---|
| **A. Source fork** (rekomendasi untuk rilis) | Fork `zai-org/ZCode` → port perilaku CCode ke TypeScript → build sendiri per platform | Rilis nyata per OS; patch tidak rapuh; lisensi bersih; bisa naik versi upstream dengan rebase | Butuh Node 24 + pnpm + toolchain Electron; kerja awal besar (port patch) |
| B. Binary patch (kondisi sekarang) | Patch `app.asar` + agent lewat anchor, `make apply` | Cepat, tanpa toolchain, sudah jalan | Rapuh per bump (nama chunk/simbol/hash berubah), Linux-only, distribusi harus "bawa binary upstream sendiri" |
| C. Commit binary | — | — | Tidak mungkin (binary 196 MB > batas GitHub) + legalnya sama dengan B tanpa kontrol build |

**Rencana:** A sebagai jalur rilis resmi; B tetap dipakai sebagai *stopgap* yang sudah terpasang hari ini dan sebagai *spesifikasi perilaku* yang diport.

## 3. Kewajiban lisensi (checklist, harus benar sebelum rilis apa pun)

Status 2026-10-13: `LICENSE` (Apache-2.0, verbatim dari upstream) dan `NOTICE.md` (atribusi + ringkasan modifikasi + pernyataan tanpa afiliasi) sudah ada di root repo. Item di bawah diverifikasi ulang setiap rilis.

- [ ] Sertakan `LICENSE` (Apache-2.0, Copyright 2026 Z.AI Co., Ltd) apa adanya di repo dan di setiap artifact.
- [ ] Sertakan `NOTICE.md` dan `THIRD-PARTY-NOTICES.md` dari upstream; tambahkan bagian CCode sendiri (tidak menghapus milik upstream).
- [ ] File yang diubah diberi penanda perubahan: header komentar pada file sumber yang disentuh, plus catatan di `docs/CHANGELOG.md`/release notes.
- [ ] `docs/THIRD_PARTY.md` menyatakan: CCode = fork tidak resmi, tanpa afiliasi Z.ai/Zhipu, merek tidak dipakai, perubahan dicatat.
- [ ] Jangan pakai nama/merek/kemasan ZCode pada artifact rilis (binari, installer, ikon, iklan rilis). Penyebutan seperti "fork ZCode 3.14.x" untuk deskripsi asal diperbolehkan §6.
- [ ] Simpan pembukuan provenance: kode sumber CCode berasal dari commit/tag upstream mana (catat SHA commit di release notes).
- [ ] Jangan menaruh kredensial pengguna, snapshot data, atau jalur pribadi (`/home/<user>/…`) di repo/artifact.

## 4. Repo dan strategi sinkronisasi

Status per 2026-10-13: sudah dibuat — workspace patch lama di-rename jadi **`0xMinomus/CCode-archive`**, dan **`0xMinomus/CCode`** dibuat sebagai fork dari `zai-org/ZCode` (history upstream ikut, `0` star/issue karena repo baru). Snapshot workspace ini didorong ke branch `ccode-workspace` di fork itu.

1. Fork: `0xMinomus/CCode`, dibuat lewat `gh repo fork zai-org/ZCode --fork-name CCode`. Jangan ubah `main` supaya rebase tetap murah.
2. Remote: `origin` = workspace (`0xMinomus/CCode-archive`), `upstream` = `zai-org/ZCode`, `fork` = `0xMinomus/CCode`.
3. Branch di fork: `main` mengikuti upstream bersih, `ccode` memuat perubahan kita (commit terpisah per fitur, bukan satu commit raksasa), `ccode-workspace` = snapshot patch workspace ini untuk rujukan spesifikasi perilaku — dan **default branch** fork saat ini, supaya halaman depan menampilkan README CCode sementara `main` tetap identik dengan upstream. Ganti default ke `ccode` begitu porting pertama mendarat. Catatan: tombol **Sync fork** GitHub bekerja pada default branch, jadi setelah default bukan `main`, sinkronisasi upstream dilakukan lokal (`git fetch upstream && git rebase upstream/main` di `main`).
4. Catatan URL: karena nama `0xMinomus/CCode` dipakai ulang oleh fork, redirect URL lama dari repo workspace tidak lagi mengarah ke arsip. Pakai selalu URL eksplisit (`CCode-archive` untuk workspace, `CCode` untuk fork).
5. Visibilitas: fork `CCode` publik; workspace `CCode-archive` masih privat. Sebelum workspace dibuka ke publik, jalankan F0 (buang `compatibility_links` di `project.json` dan jalur `/home/<user>/…` di dokumen) karena history-nya ikut terlihat.
6. Alternatif bila tidak mau memuat history upstream: repo patch + direktori `patches/*.patch` yang bisa diterapkan ke checkout upstream, dan skrip `make upstream-apply`. Ini cadangan, bukan jalur utama.

## 5. Fase

### F0 — Higiene repo rilis
Deliverable: repo publik bersih + lisensi + CI dasar.
- `LICENSE`, `NOTICE.md`, `THIRD-PARTY-NOTICES.md`, `docs/THIRD_PARTY.md` final.
- Buang data machine-specific: `project.json.compatibility_links` (berisi `/home/andikaputra/...`), cek `grep -rn "/home/andikaputra" .` = 0 sebelum publik.
- README: prasyarat OS (Fedora/Ubuntu/Arch), langkah install 3 baris, uninstall, rollback; seksi "Turunan dari ZCode" dengan tautan upstream + lisensi.
- CI (GitHub Actions) untuk bagian *patch/source* kita: unit test, lint, `node --check`. Build Electron penuh tidak di CI (butuh artifact besar) — build manual per rilis.
Kriteria selesai: `make test` hijau di runner bersih; tidak ada path/secret pribadi; LICENSE+NOTICE ada.

### F1 — Bangun dari sumber (validasi jalur A)
- Checkout upstream pada tag/commit yang dipilih (mis. 3.15.1), `pnpm install`, `pnpm run bootstrap`, `pnpm --filter @zcode/desktop build`/`bundle:desktop`.
- Catat hasil build bersih (baseline) sebagai pembanding perilaku.
- Pastikan toolchain terpenuhi lokal: Node ≥ 24, pnpm 10.33.x, Electron native deps (libnss3, libatk, libgbm, libasound), `postject` untuk build SEA.
Kriteria selesai: aplikasi hasil build dari sumber jalan di Fedora tanpa patch apa pun.

### F2 — Port perilaku CCode ke sumber (inti)
Port daftar patch yang sekarang hidup di `src/local_only/` + `src/main/` + `src/renderer/` menjadi perubahan TypeScript di fork:
1. **Standalone storage** (`storage.py`): namespace data sendiri, env sendiri, tanpa scan/impor instalasi lama.
2. **Tanpa akun/cloud** (`cloud.py`): registry service akun dimatikan, gerbang login renderer dihapus, channel yatim dijawab lokal, refresh katalog built-in dimatikan.
3. **Branding** (`branding.py` + `ccode-logo.svg`): mark CCode di onboarding/title bar/startup/About/ikon paket, nama produk `CCode`, `make icons` tetap dipakai untuk aset.
4. **Katalog provider** (`catalog.py`): tanpa keluarga Zhipu, plus template **9Router**.
5. **Activity lokal** (`src/main/activity.cjs` + `src/renderer/activity-panel.js`) dan **Computer Use Linux** (`src/renderer/linux-computer-use.js` + `services/desktop`).
6. **Model sync** (`services/model-sync`): pertahankan penjadwalan systemd Linux; port integrasi Windows ke Task Scheduler atau mekanisme native yang diverifikasi sebelum packaging.
7. ✅ **Selesai 2026-10-14 — Deep-link/desktop self-install**: `sl`/`iconName` dan seluruh nama file kini ditulis ulang `rebrand.apply()` menjadi `ccode.*`, dan `make apply`/`make install` mengganti nama identitas AppDir/launcher/unit yang sudah terpasang.
8. ✅ **Selesai 2026-10-14 — Standarisasi env internal dan skema URL**: env (`CCODE_*`), kanal IPC (`ccode-*`), skema `ccode://`, layout `.ccode`, id/direktori plugin, dan judul proses memakai ejaan CCode (lihat `docs/CHANGELOG.md` 2026-10-14); `rebrand.previous()` menyediakan ejaan lama untuk kode migrasi.
9. **Token savers**: port RTK, Caveman, Ponytail, pengaturan level/toggle, persistensi, dan analytics lokal; paketkan runtime yang sesuai per OS.
10. **Skills dan subagents default**: port pack skill, katalog role, inheritance model, serta toggle built-in dan agent plugin.
11. **Slash commands**: port 12 prompt, kategori Settings, enablement, seeding yang melindungi perubahan user, serta scanner dan resolver agent pada namespace yang sama. Verifikasi ekspansi argumen, bukan hanya kemunculan picker.
12. **Plugin Marketplace dan katalog MCP**: port kompatibilitas manifest, instalasi/enablement plugin, katalog server, bootstrap dependency per OS, dan integrasi n8n; jangan membawa credential atau konfigurasi live ke artifact.
Kriteria selesai: build dari sumber setara dengan hasil patch sekarang pada daftar uji perilaku di `docs/NO_LOGIN_TEST.md` + smoke test di `docs/DEVELOPMENT.md`.

### F3 — Packaging per platform
- **Selesai 2026-10-15 — Linux x64**: `scripts/pack_linux.py` (`make pack-linux`) menghasilkan AppImage (329,15 MiB), deb (260,62 MiB), dan rpm (274,24 MiB), setelah Voice dihapus dan n8n dipisahkan ke Marketplace. Nama artifact tetap memakai `1.0.0+upstream.3.14.5`; `SHA256SUMS` dan `release-notes.md` menyertai ketiganya. Payload layanan hanya `model-sync,desktop`.
  Verifikasi akhir: ketiga checksum lulus; AppImage dijalankan lewat `--appimage-extract-and-run` pada root terisolasi; RPM dipasang ke root sementara dan launchernya dijalankan. Keduanya membuka workspace tanpa login, 12 command, tanpa kontrol Voice dan tanpa error renderer/IPC yatim. Deb diekstrak; 13.612 berkas reguler per payload RPM/deb dan hash inti ASAR/agent/launcher/metadata/NOTICE cocok. n8n dipasang dari asset publik melalui UI native, 15 skill aktif lalu hilang saat disable, dan MCP `get_node` membaca database terpaket. Artifact unsigned; dependency/scriptlet pada distro bersih belum diuji. Computer Use masih bergantung pada Python dan paket desktop sistem. Ini distribusi stopgap AppDir hasil patch, bukan build source fork; batas lisensi pihak ketiga tetap dicatat di `docs/THIRD_PARTY.md`.
- Windows x64: installer `.exe` (NSIS), ikon Windows dan shortcut CCode, namespace data mandiri, dependency native x64, serta bootstrap tanpa ketergantungan pada shell Linux. Portable ZIP bukan deliverable wajib. Rancangan kerja konkret ada di [windowsrelease.md](windowsrelease.md).
- ARM64 dan macOS tidak dibuat atau dijanjikan pada rilis ini.
- Sertakan checksum SHA256, LICENSE/NOTICE, catatan verifikasi, serta instruksi uninstall dan penghapusan data sesuai OS.
Kriteria selesai: artifact setiap format dapat dipasang dan dibuka pada mesin target bersih tanpa instalasi upstream atau dependency pengembang yang tidak didokumentasikan.

### F4 — Rilis pertama
- ✅ **Selesai sebagian 2026-10-15 — Linux x64**: [prerelease `v1.0.0+upstream.3.14.5`](https://github.com/0xMinomus/CCode/releases/tag/v1.0.0%2Bupstream.3.14.5) publik di fork, berisi AppImage/deb/rpm, `SHA256SUMS`, `LICENSE`, dan `NOTICE.md`; digest asset GitHub cocok dengan checksum lokal. Source: commit `e1af2ee` (`origin/main`, snapshot publik `fork/ccode-workspace`). Label prerelease dipakai karena artifact unsigned dan belum diuji di distro bersih lain. Windows belum dibangun, jadi gate Windows di bawah masih terbuka.
- Tag `v<ccode>+upstream.<x.y.z>` (contoh `v1.0.0+upstream.3.15.1`) + GitHub Release berisi artifact, checksum, NOTICE, dan riwayat perubahan.
- Release notes: versi dan SHA upstream, perubahan CCode, kewajiban lisensi, status signing, serta batasan per OS berdasarkan hasil pengujian. Jangan mengklaim Computer Use/model-sync Windows siap sebelum terverifikasi.
- Verifikasi Linux: instalasi, startup, fungsi utama, uninstall, dan upgrade/rollback pada Fedora serta satu distro lain. Gunakan VM/desktop nyata untuk fitur yang memerlukan sesi grafis; container saja tidak membuktikan Computer Use.
- Verifikasi Windows oleh pengguna: jalankan installer `.exe` pada Windows x64, lalu periksa startup tanpa akun, provider/chat, persistensi data, skills, subagents, slash commands, plugin/MCP, token savers, Computer Use, model-sync, dan uninstall. Catat versi Windows, artifact/checksum, hasil, serta log yang sudah disensor.
Kriteria selesai: Linux lolos verifikasi dan pengguna mengonfirmasi pengujian Windows lolos; installer berhasil dibangun saja bukan bukti kesiapan rilis Windows.

### F5 — Pemeliharaan
- Kebijakan versi: ikuti rilis upstream; setiap bump = rebase + jalankan daftar uji perilaku.
- Jadwal: evaluasi upstream tiap rilis minor; keamanan (dependency) bulanan; changelog tiap rilis.
- Migrasi data antar versi CCode: namespace stabil, skema SQLite dari upstream, backup lewat `scripts/data_backup.py`.
- Rencana depan di luar rilis ini: ARM64 dan macOS. Pelihara integrasi Linux/Windows serta kesetaraan fitur yang sudah dirilis.

## 6. Checklist pra-rilis

- [ ] `make test` hijau (patch workspace) **dan** `pnpm test` hijau (fork sumber).
- [ ] Smoke test root terisolasi: judul CCode, tanpa layar login, 0 `Unknown channel`, 0 `No handler registered`, 0 `ReferenceError`/`TypeError`.
- [ ] Linux x64: `.AppImage`, `.deb`, `.rpm` lolos uji instalasi/startup di mesin target bersih.
- [ ] Windows x64: `.exe` berhasil dibangun; pengujian pengguna di Windows lolos dan hasilnya dicatat.
- [ ] Computer Use dan model-sync diverifikasi per OS; tidak ada fitur scope rilis lain yang dihapus tanpa persetujuan.
- [x] Tidak ada sisa mark/nama lama di UI (**selesai 2026-10-14**): `rebrand.assert_clean()`/`branding.guard()` menolak build bila sisa ejaan/mark upstream ada di asset yang dikirim; ejaan lama hanya tersisa di artifact upstream yang dipin dan di kode migrasi (`rebrand.PREVIOUS_*`).
- [ ] Ikon: `Icon=ccode` resolve di tema user (ugrep + Gtk.IconTheme), cache ikon disegarkan installer.
- [ ] Data terpisah: rilis tidak membaca/menulis `~/.zcode`, `~/.config/ZCode`.
- [ ] LICENSE + NOTICE.md + THIRD-PARTY-NOTICES.md + provenance commit upstream tercatat.
- [ ] Checksum artifact + instruksi verifikasi; uninstall + rollback didokumentasikan.
- [ ] Repository hygiene: tanpa secret, tanpa snapshot data, tanpa path pribadi, `.gitignore` benar.
- [ ] Release notes memuat batasan yang jujur dan pernyataan tanpa afiliasi.

## 7. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Bump upstream mengubah banyak hal | Patch besar, rebase berat | Fork berbasis commit per-fitur + daftar uji perilaku otomatis |
| Kebijakan merek Z.ai berubah | Rilis terpaksa ganti nama lagi | Sudah rebrand penuh ke CCode; hindari penggunaan merek di artifact |
| Upstream berhenti merilis / berubah lisensi | Fork harus mandiri | Kode fork tetap Apache-2.0 pada commit terakhir yang aman; simpan `LICENSE`/`NOTICE` historis |
| Klaim di README (produk, publik) tidak didukung fakta | Kredibilitas | Sejak 2026-10-13 README ditulis umum/profesional tanpa seksi batasan; catatan batasan tetap hidup di `docs/` (ARCHITECTURE, NO_LOGIN_TEST, THIRD_PARTY, releaseplan) dan di release notes |
| Artefak besar per rilis (Electron 200+ MB) | Biaya hosting | AppImage/NSIS terkompres, hindari menyimpan semua platform di repo |

## 8. Yang tidak boleh dilakukan

- Menyebarkan binary tanpa `LICENSE`/`NOTICE` atau tanpa menandai file yang diubah.
- Memakai nama, logo, atau merek ZCode pada rilis CCode.
- Mengklaim afiliasi/dukungan Z.ai atau Zhipu.
- Meng-commit `app/`, `baselines/`, model, venv, snapshot data, kredensial, atau jalur pribadi.
- Melemahkan assertion anchor/guard supaya build terlihat hijau.
- Menjanjikan fitur yang belum diuji (misalnya Computer Use di luar Linux).
