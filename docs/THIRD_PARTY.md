# Third-party dan provenance

Workspace ini menggabungkan patch lokal dengan runtime/dependency dari beberapa sumber. Tidak ada lisensi tunggal yang diberikan untuk seluruh aplikasi bundled.

Berkas lisensi proyek ada di root: `LICENSE` (Apache-2.0 verbatim) dan `NOTICE.md` (atribusi upstream, ringkasan modifikasi CCode, pernyataan tanpa afiliasi). **Status lisensi upstream (diverifikasi 2026-10-13).** Source ZCode publik di https://github.com/zai-org/ZCode dengan lisensi **Apache-2.0** (`Copyright 2026 Z.AI Co., Ltd`; root `package.json` `"license": "Apache-2.0"`), memuat monorepo lengkap termasuk `packages/desktop`, `NOTICE.md`, dan `THIRD-PARTY-NOTICES.md`. Artinya forking dan redistribusi diizinkan, **dengan kewajiban**: sertakan salinan `LICENSE`, sertakan isi `NOTICE.md`/`THIRD-PARTY-NOTICES.md`, tandai file yang diubah, dan pertahankan atribusi. Apache-2.0 §6 **tidak** memberi izin memakai nama/merek ZCode, jadi rilis CCode wajib memakai identitas sendiri (rebrand CCode). Rinciannya di [releaseplan.md](../releaseplan.md) §3.

- Repositori: upstream https://github.com/zai-org/ZCode (Apache-2.0) · fork rilis https://github.com/0xMinomus/CCode · workspace patch ini https://github.com/0xMinomus/CCode-archive.
- ZCode packaged baseline 3.14.5: identitas dan SHA256 di project.json. Build binary ini belum diverifikasi setara dengan build dari commit upstream (tag rilis terakhir upstream saat pencatatan: `v3.14.3`; `main` = 3.15.1), jadi perlakukan binary sebagai artefak vendor, bukan salinan repo.  Backend agent di luar ASAR (`app/resources/glm/zcode.cjs`) dipin terpisah sebagai `baselines/zcode-3.14.5-original-agent.cjs` dengan hash `agent_baseline_sha256`. Binary Electron/Chromium membawa LICENSE.electron.txt dan LICENSES.chromium.html di app/. AppImage asli tidak dimodifikasi.
- Varian standalone memakai identitas `ccode` (package name, launcher, WM class) dan namespace data sendiri. Perubahan identitas ini tidak mengubah lisensi upstream; tetap tidak ada lisensi tunggal untuk seluruh aplikasi bundled.
- screen-mcp: commit `14b88dee70db3a72281b566494e94ccf87258c28`, dari https://github.com/88plug/screen-mcp. Lisensi upstream FSL-1.1-ALv2 disimpan di services/desktop/LICENSE. Metadata Git asli dipertahankan di vendor-metadata dan tidak untuk commit source project.
- faster-whisper dan dependency: versi yang bekerja pada migrasi tercatat pada services/voice/requirements.txt. Model lokal berasal dari Systran/faster-whisper-small di Hugging Face. Periksa terms masing-masing sebelum redistribusi, bukan hanya lisensi patch lokal.
- Metadata reasoning: snapshot OpenCode/models.dev melalui URL yang tercatat di services/model-sync/sync.py.

Jangan menyertakan credentials, portal restore tokens, task history, rekaman pribadi, atau config backup pengguna dalam distribusi/project commit.

## MCP bawaan dan opsional

Katalog MCP menggunakan package upstream berikut. Dependency transitif dan teks lisensi ikut dipertahankan di payload runtime; lockfile menjadi sumber versi build.

| Integrasi | Sumber | Lisensi package |
|---|---|---|
| Context7 | [`@upstash/context7-mcp`](https://www.npmjs.com/package/@upstash/context7-mcp) | MIT |
| Codegraph | [`@sdsrs/code-graph`](https://www.npmjs.com/package/@sdsrs/code-graph) | MIT |
| LSP | [`lsp-mcp-server`](https://www.npmjs.com/package/lsp-mcp-server) | MIT |
| Ripgrep | [`mcp-ripgrep`](https://www.npmjs.com/package/mcp-ripgrep) | MIT |

Context7 membutuhkan jaringan ketika tool dokumentasi dipanggil dan dapat terkena rate limit. Codegraph mengindeks proyek lokal. Ripgrep memakai binary pencarian native `@vscode/ripgrep-linux-x64`.

Websearch, Obsidian, n8n, dan GitHub tidak ikut dibundel.

Installer npm yang dibundel menggunakan Artistic-2.0. Dukungan TypeScript opsional (`typescript` dan `typescript-language-server`) menggunakan Apache-2.0. Package Codegraph dipakai melalui engine native; hook, prompt, dan installer plugin Claude tidak dimasukkan ke runtime CCode.

## Default skills yang dibundel (`src/skills`)

32 skill ikut dipaketkan ke aplikasi lewat `glm/packages/bundled-skills/skills` (dipromosikan oleh `make apply`; lihat ARCHITECTURE bagian **Default skills**). Tiga kelompok, dengan status lisensi berbeda:

| Kelompok | Skill | Sumber | Lisensi |
|---|---|---|---|
| Antislop (4) | `antislop`, `antislop-code`, `antislop-copywriting`, `antislop-human` | plugin marketplace `anti-slop` v3.2.20 (Oh My Pi) | **MIT**, Copyright (c) 2026 Miqdad Badjuber — teks lengkap di bawah |
| GSAP (8) | `gsap-core`, `gsap-frameworks`, `gsap-performance`, `gsap-plugins`, `gsap-react`, `gsap-scrolltrigger`, `gsap-timeline`, `gsap-utils` | skill resmi GSAP dari library skill Oh My Pi | **MIT** (dinyatakan di frontmatter `license: MIT` tiap SKILL.md) |
| UI/desain (3) | `impeccable`, `design-taste-frontend`, `emil-design-eng` | library skill Oh My Pi | `impeccable`: **Apache-2.0** (frontmatter); dua lainnya tidak menyatakan lisensi di berkasnya |
| Workflow (17) | `code-review`, `diagnosing-bugs`, `investigate-first`, `lean-build`, `migration`, `prototype`, `full-output-enforcement`, `safe-refactor`, `surgical-patch`, `tdd`, `verify-and-stop`, `resolving-merge-conflicts`, `pr`, `research`, `wizard`, `find-skills`, `handoff` | library skill Oh My Pi milik operator (`~/.omp/agent/skills`) | tidak ada lisensi yang dinyatakan di berkas sumber; `pr` mencantumkan kredit `show-me` (Dex Horthy, Humanlayer) di frontmatter |

Catatan: skill tanpa pernyataan lisensi dibundel atas keputusan pemilik workspace untuk pemakaian pribadi. Karena tidak ada lisensi eksplisit, **jangan mengklaim lisensi apa pun untuk berkas itu** dan jangan mempublikasikannya sebagai bagian rilis publik tanpa menanyakan pemiliknya dulu. Frontmatter tiap skill disesuaikan ke format yang diterima aplikasi (`name`, `description`, `when_to_use`, `license`, `metadata`): kunci Claude-Code seperti `allowed-tools`, `argument-hint`, `user-invocable`, `disable-model-invocation`, dan `version` dipindahkan ke dalam `metadata` supaya tidak memicu peringatan `skill_invalid_frontmatter`.

```text
MIT License

Copyright (c) 2026 Miqdad Badjuber (antislop)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
