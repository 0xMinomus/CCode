# Rencana Kerja Update 18 Oktober 2026: Adopsi Fitur T3Code ke CCode

Dokumen perencanaan teknis untuk mengadopsi kapabilitas terpilih dari **T3Code** (`pingdotgg/t3code`, v0.1.0 Beta) ke dalam **CCode** (v1.0.3, basis upstream 3.14.5).

---

## 1. Konteks dan Batasan Arsitektur

### 1.1 Filosofi CCode (Tetap Terkunci)
1. **100% No-Account & Local-First:** Tidak ada akun cloud, tidak ada login gate. Seluruh data hidup di namespace privat (`~/.local/share/ccode` di Linux, `%LOCALAPPDATA%\CCode` di Windows).
2. **Zero Silent Credential Scraping:** Menolak keras komponen seperti `t3-browser-secret` yang membongkar `libsecret`/keyring untuk mencuri session login browser. Di CCode, seluruh otentikasi API/CLI (termasuk GitHub CLI `gh`) dilakukan secara eksplisit dan transparan oleh pengguna.
3. **Ringan & Tanpa Bloat Eksternal:** Menolak dependensi besar seperti `playwright-core` di root runtime dan menolak engine render visual diff eksternal (seperti Pierre Diff) yang rapuh jika disuntikkan ke bundle ASAR upstream. CCode sudah memiliki viewer file-change bawaan dan editor terintegrasi.
4. **Lisensi:** Kode dan binary dari `pingdotgg/t3code` berlisensi **MIT**, kompatibel untuk diserap ke dalam CCode (Apache-2.0) dengan pencatatan atribusi di `NOTICE.md`.

### 1.2 Matriks Platform (Windows vs Linux)

| Rencana Fitur | Linux x64 | Windows x64 | Alasan & Catatan |
|---|---|---|---|
| **Plan 1: Native Compositor Capture** | **Aktif** | **Diabaikan (Ignore)** | Khusus Wayland (Hyprland / KDE). Windows sudah memiliki backend native `.NET` + `SendInput` (`windows-desktop`). |
| **Plan 2: System Resource Monitor Sidecar** | **Aktif** | **Opsional / Evaluasi** | Linux memakai binary sidecar native. Windows memakai provider WMI/PowerShell ringan agar binary Windows tetap ramping. |
| **Plan 3: Full UI Settings → Source Control & PR Workflow** | **Aktif** | **Aktif** | Antarmuka UI penuh di Settings CCode untuk manajemen Git, GitHub CLI `gh`, aturan commit bersih, dan otomasi PR. |

---

## 2. Rencana 1: Native Linux Compositor Capture (Hyprland & KDE)

*Scope: **Linux Saja***

### 2.1 Masalah Saat Ini
Backend Computer Use Linux CCode (`services/desktop/capture.py`) mengandalkan PipeWire via XDG Desktop Portal dan X11 fallback. Pada window manager Wayland non-GNOME seperti **Hyprland** atau **KDE Wayland**, portal PipeWire seringkali:
1. Memunculkan dialog izin interaktif berulang kali ke layar pengguna.
2. Memerlukan setup PipeWire session yang rumit.
3. Terkadang gagal menangkap koordinat toplevel window secara presisi.

### 2.2 Solusi dari T3Code
Menyerap dua binary mandiri (ELF 64-bit, Rust) yang ada di T3Code:
- `resources/hyprland-capture/t3-hyprland-snap-shot` (1.1 MB) — menggunakan protokol Wayland langsung `hyprland-toplevel-export-v1` dan `hyprland-toplevel-mapping-v1`.
- `resources/kde-capture/t3-kde-snap-shot` (2.5 MB) — menggunakan jalur direct KWin DBus scripting.

### 2.3 Rincian Perubahan Kode
1. **Penyimpanan Binary:**
   - Simpan binary di `services/desktop/bin/t3-hyprland-snap-shot` dan `services/desktop/bin/t3-kde-snap-shot`.
   - Pastikan izin eksekusi `0755` dan sertakan dalam manifest verifikasi `scripts/build.py` serta `apply_build.py`.
2. **Modifikasi `services/desktop/capture.py`:**
   - Tambahkan deteksi lingkungan desktop melalui `os.environ.get("XDG_CURRENT_DESKTOP", "").lower()`.
   - **Fast-path Hyprland:** Jika mendeteksi `hyprland` dan binary snapshot tersedia, panggil binary untuk mengambil tangkapan layar langsung ke memori/file sementara tanpa melalui portal PipeWire.
   - **Fast-path KDE:** Jika mendeteksi `kde` / `plasma`, gunakan helper KDE.
   - **Fallback:** Jika binary gagal atau desktop adalah GNOME/X11, fallback tetap ke PipeWire Portal dan X11 yang sudah terbukti stabil.
3. **Takeover Guard:**
   - Mekanisme guard mouse takeover (STOPPED pada pergerakan pointer >16px selama 2500ms) tetap menjadi pengendali mutlak sebelum aksi input dieksekusi.

### 2.4 Kriteria Penerimaan (Acceptance)
- Pada lingkungan Hyprland/KDE, `linux-desktop` MCP dapat mengambil screenshot tanpa memunculkan dialog pop-up portal PipeWire.
- Pada sesi GNOME Fedora default, pipeline PipeWire eksisting tetap berjalan tanpa regresi.

---

## 3. Rencana 2: System Resource Monitor Sidecar

*Scope: **Linux (Utama) & Windows (Ringan)***

### 3.1 Masalah Saat Ini
Saat agen CCode mengeksekusi subagent paralel atau kompilasi kode berat di background, pengguna tidak memiliki indikator visual beban CPU dan RAM proses kerja di antarmuka CCode, selain memantau secara manual lewat terminal (`top`/`htop`).

### 3.2 Solusi dari T3Code
T3Code menyertakan binary sidecar `t3-resource-monitor` (~680 KB) yang menghasilkan stream JSON berkala mengenai statistik proses:
- `cumulativeCpuTime` & `currentCpuPercent`
- `residentMemory` & `virtualMemory`
- `ioBytes`
- `processTree` (melacak proses anak yang di-spawn oleh agen)

### 3.3 Rincian Perubahan Kode
1. **Backend / Sidecar:**
   - **Linux:** Tempatkan binary di `services/monitor/bin/ccode-resource-monitor` (mengadopsi build T3Code).
   - **Windows:** Buat runner kecil berbasis Node.js/PowerShell (memanfaatkan `process.cpuUsage()` dan `process.memoryUsage()` bawaan Electron atau WMI `Win32_PerfFormattedData_PerfProc_Process`) tanpa menambah binary besar baru.
2. **Main IPC:**
   - Buat modul `src/main/resource-monitor.cjs` yang memanage lifecycle sidecar (start saat app aktif, stop saat idle/tutup).
   - Expose channel read-only `window.ccodeResourceMonitor.getStats()`.
3. **UI Display:**
   - Tambahkan widget indikator beban CPU/RAM ringkas pada footer atau header panel Activity di CCode.

### 3.4 Kriteria Penerimaan (Acceptance)
- Sidecar tidak membebani sistem (<1% CPU overhead).
- Data penggunaan resource proses CCode dan child worker dapat dibaca di UI tanpa kebocoran memori.

---

## 4. Rencana 3: Full UI Settings → Source Control & PR Workflow Automation

*Scope: **Linux dan Windows***

### 4.1 Tujuan Fitur
Menghadirkan panel antarmuka visual penuh di **Settings → Source Control** di CCode (sebagaimana tampilan pada T3Code) tanpa memasukkan engine visual diff pihak ketiga yang berat. Seluruh otomasi Git dan GitHub CLI (`gh`) diatur dari panel ini.

### 4.2 Struktur Antarmuka `Settings → Source Control`

Panel UI baru dibangun menggunakan komponen React bundled upstream (`Q1`, `Z1`, `Xx`, switch, input, dropdown) dengan susunan bagian:

```
Settings / Source Control
├── Repositories
│   ├── Automatically pull [Toggle]
│   ├── Remove agent credits when merging [Toggle, default: ON]
│   └── Default merge method [Dropdown: Squash / Merge / Rebase, default: Squash]
├── Version Control CLI
│   ├── Git Status: [Terdeteksi: git version x.y.z / Not Found]
│   └── Jujutsu (jj): [Status / Coming Soon]
├── Source Control Providers
│   ├── GitHub: [Terdeteksi: gh version x.y.z · Authenticated as @user / Login Required]
│   ├── GitLab: [glab status]
│   └── Gitea / Forgejo: [tea status]
└── Text Generation & Workflows
    ├── Worktree branch naming [Dropdown: Static prefix / Task ID / Slug]
    ├── Branch prefix [Text Input, default: "ccode"]
    ├── Follow repository PR templates [Toggle, default: ON]
    ├── Strip AI/Bot Co-Authors from commit messages [Toggle, default: ON]
    └── Generate maintainer review guide [Toggle, default: ON]
```

### 4.3 Rincian Perubahan Kode

#### A. Main Process & IPC (`src/main/source-control.cjs`)
1. **Deteksi CLI:**
   - Jalankan `git --version` dan `gh --version` + `gh auth status`.
   - Kembalikan status keberadaan tool dan username yang terotentikasi.
2. **Penyimpanan Konfigurasi:**
   - Simpan state di `<storage_dir>/v2/source-control.json` di dalam namespace CCode.
   - Konfigurasi mandiri, tidak mencemari global git config `~/.gitconfig`.
3. **Ekspos Preload:**
   - Tambahkan channel aman `window.ccodeSourceControl` di preload IPC bridge:
     - `getStatus()`: memeriksa CLI dan status auth.
     - `getConfig()`: membaca preferensi pengguna.
     - `saveConfig(data)`: menyimpan preferensi.

#### B. Renderer UI (`src/renderer/source-control-panel.js`)
1. Buat komponen `SourceControlPanel` dengan tata letak form native CCode.
2. Tambahkan entri menu di sidebar Settings tepat di bawah **Token savers**:
   - Ikon Lucide `GitBranch` atau `GitPullRequest`.
   - Label: **Source Control**.
3. Hubungkan setiap switch dan text input ke IPC `window.ccodeSourceControl`.

#### C. Build Patcher (`scripts/build.py`)
1. Tambahkan anchor injeksi menu sidebar Settings di `scripts/build.py`.
2. Bundel modul `src/renderer/source-control-panel.js` ke dalam asset renderer ASAR.
3. Daftarkan module di `src/local_only/` dan pastikan anchor integrity lolos.

#### D. Integrasi Workflow Agen (Slash Command `/pr`)
1. **Prompt `/pr` (`src/commands/pr.md`):**
   - Periksa status working tree git saat ini.
   - Baca preferensi dari `source-control.json`.
   - Buat branch baru dengan prefix yang dikonfigurasi (misal `ccode/task-nama`).
   - Format pesan commit bersih: hapus seluruh baris watermark seperti `Co-authored-by: Agent <...>` atau `Generated by ...`.
   - Periksa keberadaan `.github/pull_request_template.md` atau `.github/PULL_REQUEST_TEMPLATE/`.
   - Jika `gh` tersedia: jalankan `gh pr create` dengan judul, isi template yang sudah terisi otomatis, dan opsi merge yang dipilih.
   - Buat rangkuman **Review Guide** ringkas untuk maintainer di output chat: daftar file yang berubah, risiko regresi, dan perintah testing yang sudah dijalankan.

### 4.4 Kriteria Penerimaan (Acceptance)
- Menu **Settings → Source Control** muncul rapi di sidebar Settings Linux dan Windows.
- Menampilkan status deteksi `git` dan `gh` akun GitHub yang sedang login.
- Perubahan toggle (seperti prefix branch dan *Remove agent credits*) tersimpan permanen di `source-control.json` dan bertahan setelah aplikasi di-restart.
- Perintah `/pr` mengeksekusi git branch, commit bersih tanpa watermark bot, dan membuat PR melalui GitHub CLI sesuai template repo.

---

## 5. Rencana Tahapan Eksekusi (Milestones)

1. **Milestone 1 (M1) — Plan 1: Native Compositor Capture (Linux):**
   - Ekstrak binary Hyprland & KDE snapshot dari T3Code.
   - Pasang di `services/desktop/bin/`.
   - Update `services/desktop/capture.py` dan uji tangkapan layar di Linux.
2. **Milestone 2 (M2) — Plan 3: Source Control Backend & UI:**
   - Buat IPC `src/main/source-control.cjs` untuk deteksi `git`/`gh`.
   - Buat komponen `src/renderer/source-control-panel.js`.
   - Patch `scripts/build.py` untuk menyuntikkan menu Settings.
   - Buat slash command `src/commands/pr.md` dan integrasikan skill `pr`.
   - Uji persistensi di namespace terisolasi pada Linux dan Windows.
3. **Milestone 3 (M3) — Plan 2: Resource Monitor Sidecar:**
   - Integrasikan `ccode-resource-monitor` sidecar dan hubungkan ke UI dashboard.
