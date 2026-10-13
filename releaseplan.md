# Rencana rilis CCode

Tujuan: CCode bisa **diunduh dan langsung dipakai** sebagai aplikasi mandiri (bukan patch atas binary orang lain), terbuka sebagai open source, dan mengakui secara eksplisit bahwa ini turunan dari ZCode.

Dokumen ini rencana; status hari ini ada di [README.md](README.md) dan [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
5. **Activity lokal** (`src/main/activity.cjs` + `src/renderer/activity-panel.js`), **Voice** (`src/main/voice.cjs` + `services/voice`), **Computer Use Linux** (`src/renderer/linux-computer-use.js` + `services/desktop`).
6. **Model sync** (`services/model-sync`), penjadwalan: systemd timer di Linux, padanan per OS saat F4.
7. **Deep-link/desktop self-install**: `sl="zcode.desktop"` + `iconName:"zcode"` harus jadi `ccode.*` (kalau tidak, aplikasi akan menulis entri `zcode.desktop` bernama CCode dengan ikon lama).
8. Opsional: standarisasi env internal jadi `CCODE_*` (sekarang masih `ZCODE_*` demi kompatibilitas binary) dan skema URL sendiri.
Kriteria selesai: build dari sumber setara dengan hasil patch sekarang pada daftar uji perilaku di `docs/NO_LOGIN_TEST.md` + smoke test di `docs/DEVELOPMENT.md`.

### F3 — Packaging per platform
- Linux: `.AppImage` (appimagetool) + `.deb`/`.rpm` (electron-builder), ikon hicolor, `.desktop`, unit systemd opsional, `update-desktop-database` + `gtk-update-icon-cache`.
- Windows: installer NSIS/portable ZIP, `icon_windows.png`, shortcut, Task Scheduler untuk sync, ganti `run.sh` dengan `.cmd`/bootstrap internal.
- macOS: `.dmg` (butuh signing/notarization atau instruksi bypass Gatekeeper) — opsional, evaluasi terpisah.
- Artefak pendukung: tar portable, checksum SHA256, catatan verifikasi, uninstaller/instruksi hapus data (`~/.local/share/ccode`).
Kriteria selesai: satu perintah/unduhan → aplikasi jalan di mesin bersih tanpa ZCode terpasang.

### F4 — Rilis pertama
- Tag `v<ccode>+upstream.<x.y.z>` (contoh `v1.0.0+upstream.3.15.1`) + GitHub Release berisi artifact, checksum, NOTICE, dan riwayat perubahan.
- Release notes: versi upstream, SHA commit upstream, daftar perubahan kita, kewajiban lisensi, batasan yang jujur (Computer Use Fedora-only pada rilis pertama, Voice butuh PipeWire, dsb.).
- Uji asap rilis di VM/container bersih (Fedora + satu distro lain).
Kriteria selesai: orang lain bisa download → pakai tanpa menghubungi pemilik repo.

### F5 — Pemeliharaan
- Kebijakan versi: ikuti rilis upstream; setiap bump = rebase + jalankan daftar uji perilaku.
- Jadwal: evaluasi upstream tiap rilis minor; keamanan (dependency) bulanan; changelog tiap rilis.
- Migrasi data antar versi CCode: namespace stabil, skema SQLite dari upstream, backup lewat `scripts/data_backup.py`.
- Rencana depan: Windows/macOS, alternate recorder untuk Voice di luar PipeWire, penjadwal lintas OS.

## 6. Checklist pra-rilis

- [ ] `make test` hijau (patch workspace) **dan** `pnpm test` hijau (fork sumber).
- [ ] Smoke test root terisolasi: judul CCode, tanpa layar login, 0 `Unknown channel`, 0 `No handler registered`, 0 `ReferenceError`/`TypeError`.
- [ ] Tidak ada sisa mark/nama lama di UI: 0 `ZCode` di luar daftar yang sengaja dipertahankan (protokol/transport, env internal, layout `.zcode`, skema URL).
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
- Menjanjikan fitur yang belum diuji (Computer Use di luar Linux, Voice tanpa PipeWire, dsb.).
