# Third-party dan provenance

Workspace ini menggabungkan patch lokal dengan runtime/dependency dari beberapa sumber. Tidak ada lisensi tunggal yang diberikan untuk seluruh aplikasi bundled.

**Status lisensi upstream (diverifikasi 2026-10-13).** Source ZCode publik di https://github.com/zai-org/ZCode dengan lisensi **Apache-2.0** (`Copyright 2026 Z.AI Co., Ltd`; root `package.json` `"license": "Apache-2.0"`), memuat monorepo lengkap termasuk `packages/desktop`, `NOTICE.md`, dan `THIRD-PARTY-NOTICES.md`. Artinya forking dan redistribusi diizinkan, **dengan kewajiban**: sertakan salinan `LICENSE`, sertakan isi `NOTICE.md`/`THIRD-PARTY-NOTICES.md`, tandai file yang diubah, dan pertahankan atribusi. Apache-2.0 §6 **tidak** memberi izin memakai nama/merek ZCode, jadi rilis CCode wajib memakai identitas sendiri (rebrand CCode). Rinciannya di [releaseplan.md](../releaseplan.md) §3.

- Repositori: upstream https://github.com/zai-org/ZCode (Apache-2.0) · fork rilis https://github.com/0xMinomus/CCode · workspace patch ini https://github.com/0xMinomus/CCode-archive.
- ZCode packaged baseline 3.14.5: identitas dan SHA256 di project.json. Build binary ini belum diverifikasi setara dengan build dari commit upstream (tag rilis terakhir upstream saat pencatatan: `v3.14.3`; `main` = 3.15.1), jadi perlakukan binary sebagai artefak vendor, bukan salinan repo.  Backend agent di luar ASAR (`app/resources/glm/zcode.cjs`) dipin terpisah sebagai `baselines/zcode-3.14.5-original-agent.cjs` dengan hash `agent_baseline_sha256`. Binary Electron/Chromium membawa LICENSE.electron.txt dan LICENSES.chromium.html di app/. AppImage asli tidak dimodifikasi.
- Varian standalone memakai identitas `ccode` (package name, launcher, WM class) dan namespace data sendiri. Perubahan identitas ini tidak mengubah lisensi upstream; tetap tidak ada lisensi tunggal untuk seluruh aplikasi bundled.
- screen-mcp: commit `14b88dee70db3a72281b566494e94ccf87258c28`, dari https://github.com/88plug/screen-mcp. Lisensi upstream FSL-1.1-ALv2 disimpan di services/desktop/LICENSE. Metadata Git asli dipertahankan di vendor-metadata dan tidak untuk commit source project.
- faster-whisper dan dependency: versi yang bekerja pada migrasi tercatat pada services/voice/requirements.txt. Model lokal berasal dari Systran/faster-whisper-small di Hugging Face. Periksa terms masing-masing sebelum redistribusi, bukan hanya lisensi patch lokal.
- Metadata reasoning: snapshot OpenCode/models.dev melalui URL yang tercatat di services/model-sync/sync.py.

Jangan menyertakan credentials, portal restore tokens, task history, rekaman pribadi, atau config backup pengguna dalam distribusi/project commit.
