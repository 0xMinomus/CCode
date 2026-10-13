# Third-party dan provenance

Workspace ini menggabungkan patch lokal dengan runtime/dependency dari beberapa sumber. Tidak ada lisensi tunggal yang diberikan untuk seluruh aplikasi bundled.

- ZCode packaged baseline 3.14.5: identitas dan SHA256 di project.json. Backend agent di luar ASAR (`app/resources/glm/zcode.cjs`) dipin terpisah sebagai `baselines/zcode-3.14.5-original-agent.cjs` dengan hash `agent_baseline_sha256`. Binary Electron/Chromium membawa LICENSE.electron.txt dan LICENSES.chromium.html di app/. AppImage asli tidak dimodifikasi.
- Varian standalone memakai identitas `zcode-on-steroids` (package name, launcher, WM class) dan namespace data sendiri. Perubahan identitas ini tidak mengubah lisensi upstream; tetap tidak ada lisensi tunggal untuk seluruh aplikasi bundled.
- screen-mcp: commit `14b88dee70db3a72281b566494e94ccf87258c28`, dari https://github.com/88plug/screen-mcp. Lisensi upstream FSL-1.1-ALv2 disimpan di services/desktop/LICENSE. Metadata Git asli dipertahankan di vendor-metadata dan tidak untuk commit source project.
- faster-whisper dan dependency: versi yang bekerja pada migrasi tercatat pada services/voice/requirements.txt. Model lokal berasal dari Systran/faster-whisper-small di Hugging Face. Periksa terms masing-masing sebelum redistribusi, bukan hanya lisensi patch lokal.
- Metadata reasoning: snapshot OpenCode/models.dev melalui URL yang tercatat di services/model-sync/sync.py.
- Riset Codex lokal (`chatgpt-26.930.61225`, `codex-cli 0.160.1`): [CLI/app-server terbuka](https://learn.chatgpt.com/docs/open-source), tetapi paket RPM desktop berlisensi `Proprietary` dan manifest SDK `@oai/sky`/`@oai/cua-repl` tidak mencantumkan field lisensi. Rencana reuse di [COMPUTER_USE_PLAN.md](COMPUTER_USE_PLAN.md) memakai instalasi lokal sebagai prerequisite; tidak menyalin binary/SDK/plugin ke source tracked, tidak mem-package ulang, dan tidak mengasumsikan izin redistribusi.

Jangan menyertakan credentials, portal restore tokens, task history, rekaman pribadi, atau config backup pengguna dalam distribusi/project commit.
