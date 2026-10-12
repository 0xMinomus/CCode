# Model Vansrouter dan reasoning

Live provider config varian standalone berada di `~/.local/share/zcode-on-steroids/data/.zcode/v2/provider_config.json` (root dapat dipindah lewat `ZCODE_STANDALONE_ROOT`). Instalasi lama di `~/.zcode/v2/provider_config.json` tetap ada dan tidak diubah. Source sinkronisasi berada di `services/model-sync/sync.py`; cache/state merupakan runtime, bukan source yang perlu di-commit.

Timer `zcode-on-steroids-model-sync.timer` menjalankan sync untuk namespace standalone dengan env `ZCODE_MODEL_SYNC_CONFIG` dan `ZCODE_MODEL_SYNC_STATE`. Tanpa env tersebut, `sync.py` tetap memakai jalur lama (`~/.zcode/v2/provider_config.json`) supaya timer instalasi lama tidak berubah perilakunya.

`oc/` dipetakan ke katalog OpenCode. Hanya model yang sudah didaftarkan di provider Vansrouter ZCode yang dilengkapi. Level `effort` berasal dari `reasoning_options.values`; pilihan dikirim melalui `reasoning_effort`. Toggle membutuhkan wire format yang diketahui, misalnya `reasoning.enabled` untuk Ling dan `thinking.type` untuk LongCat. Nama model saja tidak membuktikan dukungan semua level.

Pemetaan ZCode berupa expression string, contoh:

```json
{"values":["low","medium","high","xhigh","max"],"map":"{\"reasoning_effort\": reasoningLevel}"}
```

Simpan di `config.optionSpecs.reasoningLevel` pada manualProviderModelRules model terkait. Objek `optionSpecs` wajib ada pada manual rule; menghilangkannya pernah membuat ZCode menolak seluruh personal provider config. Gunakan backup dan validasi parser ketika mengubah schema.

Pemetaan yang secara eksplisit diubah pengguna tidak ditimpa. Model tak dikenal, routing suffix effort, dan combo dilewati. Combo bisa mengunci effort masing-masing anggotanya; jangan membuat pilihan Low di UI bila rute upstream tetap memaksa Max.

Tes acceptance API dan pemeriksaan payload membuktikan parameter terkirim/diterima, bukan mengukur jumlah reasoning internal model. Availability upstream tetap dapat berubah walaupun metadata model benar.
