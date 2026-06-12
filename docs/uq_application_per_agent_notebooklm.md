# Ringkasan Penerapan Uncertainty Quantification per Agent

Dokumen ini merangkum penerapan **Uncertainty Quantification (UQ)** pada sistem Multi-Agent VR Museum Guide. File ini dibuat singkat agar mudah dimasukkan ke NotebookLM dan disesuaikan dengan paper rujukan.

## 1. Ruang Lingkup Penerapan UQ

UQ diterapkan hanya pada dua agent:

| Agent | Status UQ | Alasan |
|---|---|---|
| Context Agent | Digunakan | Agent menghasilkan interpretasi konteks yang bersifat generatif. |
| Dialogue Agent | Digunakan | Agent menghasilkan dialog NPC, subtitle, dan opsi rekomendasi yang rawan variasi/hallucination. |
| Agent / blok lain | Tidak digunakan | Ranking, NavMesh, dan dispatch command bersifat deterministic atau rule-based. |

UQ tidak diterapkan pada semua agent karena tidak semua bagian sistem membutuhkan estimasi ketidakpastian. Bagian seperti ranking rekomendasi dan `nav_target` sudah dihitung secara deterministic oleh backend, sehingga lebih tepat dijaga dengan rule dan validasi, bukan dengan UQ berbasis sampling.

## 2. Paper Rujukan

Paper utama yang digunakan sebagai dasar konsep:

1. **Generating with Confidence: Uncertainty Quantification for Black-box Large Language Models**
   - Digunakan sebagai rujukan utama untuk pendekatan **black-box UQ**.
   - Prinsip yang diambil: model dijalankan beberapa kali, output dibandingkan satu sama lain, lalu tingkat konsistensi digunakan sebagai confidence/uncertainty.

2. **A Survey of Uncertainty Estimation Methods on Large Language Models**
   - Digunakan untuk mengklasifikasikan metode yang dipakai.
   - Metode pada project ini masuk kategori **consistency-based uncertainty estimation** dan **semantic/response similarity-based uncertainty estimation**.

Catatan: project ini tidak menggunakan token-level entropy karena model dipakai melalui OpenRouter/API black-box, sehingga akses ke logit atau probabilitas token tidak selalu tersedia.

## 2.1 Istilah UQ yang Dipakai Secara Konsisten

Dokumen ini memakai istilah berikut agar selaras dengan paper dan implementasi:

| Istilah | Makna dalam project |
|---|---|
| **black-box consistency-based UQ** | UQ berbasis beberapa output model tanpa akses logit; output dibandingkan untuk melihat konsistensi. |
| **black-box response similarity UQ** | UQ pada Dialogue Agent dengan membandingkan kemiripan beberapa kandidat respons. |
| **CDeg** | Confidence Degree, yaitu skor keyakinan/stabilitas kandidat berdasarkan kemiripan terhadap kandidat lain. |
| **UDeg** | Uncertainty Degree, yaitu skor ketidakpastian keseluruhan; makin tinggi berarti output makin bervariasi. |
| **grounding score** | Skor tambahan pada Dialogue Agent untuk mengecek apakah dialog sesuai dengan Context Agent. |

## 3. Context Agent

### 3.1 Peran Context Agent

Context Agent bertugas mengubah snapshot runtime dari Unity/backend menjadi `ContextOutput`, yang berisi:

- ringkasan situasi pemain,
- status scene,
- alasan rekomendasi,
- tipe situasi,
- intent dialog,
- daftar rekomendasi objek budaya,
- target navigasi.

Namun, UQ hanya diterapkan pada field interpretatif, bukan pada ranking utama.

### 3.2 Metode UQ yang Dipakai

Metode yang digunakan:

```text
black-box consistency-based UQ over interpretive fields
```

Kategori:

```text
black-box uncertainty estimation
consistency-based uncertainty estimation
```

Context Agent menghasilkan beberapa kandidat output untuk input yang sama. Setelah itu, output-output tersebut dibandingkan untuk melihat apakah interpretasinya konsisten.

### 3.3 Field yang Dihitung UQ

Field yang dihitung:

- `user_action`
- `context_summary`
- `recommendation_reason`
- `situation_type`
- `dialogue_intent`

Field yang tidak dihitung UQ:

- `recommendations`
- `nav_target`
- `cultural_position`

Alasannya: `recommendations` dan `nav_target` sudah dijaga oleh backend melalui ranking deterministic berdasarkan posisi player, status `visited`, dan jarak Euclidean.

### 3.4 Rumus Context Agent

Untuk dua sample output ke-i dan ke-j, dihitung skor kemiripan:

```text
a_ij = similarity(output_i, output_j)
```

Untuk field teks, similarity dihitung dengan kemiripan token/Jaccard:

```text
sim(A, B) = |tokens(A) ∩ tokens(B)| / |tokens(A) ∪ tokens(B)|
```

Untuk field kategori:

```text
sim(A, B) = 1 jika sama
sim(A, B) = 0 jika berbeda
```

CDeg atau Confidence Degree kandidat ke-i:

```text
CDeg_i = sum(a_ij) / (m - 1)
```

UDeg atau Uncertainty Degree keseluruhan:

```text
UDeg = 1 - mean(CDeg_i)
```

Keterangan:

- `m` = jumlah sample.
- `a_ij` = kemiripan sample i terhadap sample j.
- `CDeg_i` = Confidence Degree kandidat ke-i; dalam implementasi dihitung dari konsistensi terhadap sample lain.
- `UDeg` = Uncertainty Degree keseluruhan.

Output yang dipilih:

```text
selected_output = sample dengan CDeg tertinggi
```

### 3.5 Makna Skor pada Context Agent

| Skor | Makna |
|---|---|
| `CDeg` tinggi | Output mirip dengan mayoritas sample, sehingga lebih stabil. |
| `CDeg` rendah | Output menyimpang dari sample lain. |
| `UDeg` rendah | Ketidakpastian rendah. |
| `UDeg` tinggi | Ketidakpastian tinggi karena output bervariasi. |

## 4. Dialogue Agent

### 4.1 Peran Dialogue Agent

Dialogue Agent bertugas mengubah `ContextOutput` menjadi:

- `spoken_output`,
- `subtitle_output`,
- `recommendation_dialogue`,
- `recommendation_options`.

Pada implementasi Unity saat ini, data yang benar-benar tampil di HUD adalah
`recommendation_dialogue`, `subtitle_output`, dan `recommendation_options`.
`spoken_output` tetap berada dalam kontrak API untuk kompatibilitas, tetapi tidak
digunakan untuk audio/TTS dan tidak dihitung dalam UQ.

Agent ini lebih rawan uncertainty karena menghasilkan bahasa natural untuk NPC. Risiko utamanya adalah:

- dialog menyebut objek yang salah,
- opsi tidak sesuai urutan Context Agent,
- hallucination fakta budaya,
- persona drift,
- subtitle terlalu panjang,
- muncul istilah teknis seperti koordinat atau backend.

### 4.2 Metode UQ yang Dipakai

Metode yang digunakan:

```text
black-box response similarity UQ + grounding score
```

Kategori:

```text
black-box uncertainty estimation
response similarity-based uncertainty estimation
grounding-based confidence scoring
```

Dialogue Agent menghasilkan beberapa kandidat dialog. Kandidat-kandidat tersebut dibandingkan berdasarkan kemiripan respons dan kesesuaiannya dengan `ContextOutput`.

### 4.3 Rumus Response Similarity Dialogue

Kemiripan dua kandidat dialog dihitung dengan bobot:

```text
a_ij =
0.50 * sim(recommendation_dialogue_i, recommendation_dialogue_j)
+ 0.30 * sim(subtitle_output_i, subtitle_output_j)
+ 0.20 * sim(recommendation_options_i, recommendation_options_j)
```

Alasan bobot:

| Komponen | Bobot | Alasan |
|---|---:|---|
| `recommendation_dialogue` | 0.50 | Teks utama panel rekomendasi pada HUD. |
| `subtitle_output` | 0.30 | Konfirmasi singkat yang tampil setelah pemain memilih. |
| `recommendation_options` | 0.20 | Tombol pilihan harus mengikuti Context Agent. |
| `spoken_output` | 0.00 | Dipertahankan untuk kompatibilitas API, tetapi tidak digunakan VR/UQ. |

Confidence degree kandidat:

```text
CDeg_i = sum(a_ij) / (m - 1)
```

Uncertainty degree:

```text
UDeg = 1 - mean(CDeg_i)
```

### 4.4 Rumus grounding score

Dialogue Agent tidak cukup hanya memilih output yang konsisten, karena beberapa output bisa sama-sama konsisten tetapi tetap salah target. Karena itu digunakan **grounding score**.

```text
grounding_score =
0.50 * option_score
+ 0.35 * primary_score
+ 0.15 * subtitle_score
```

Keterangan:

- `option_score`: apakah `recommendation_options` sama dengan urutan rekomendasi dari Context Agent.
- `primary_score`: apakah objek rank-1 / tujuan utama disebut dalam dialog.
- `subtitle_score`: apakah subtitle valid dan cukup singkat.

### 4.5 Rumus Final Selection Score

Kandidat dialog dipilih berdasarkan kombinasi `CDeg` dan `grounding score`:

```text
FinalScore_i =
0.45 * CDeg_i
+ 0.55 * grounding_score_i
```

`grounding score` diberi bobot lebih besar karena dialog yang benar harus mengikuti hasil Context Agent. Konsistensi saja belum cukup jika output konsisten tetapi menyebut objek yang salah.

Output yang dipilih:

```text
selected_dialogue = sample dengan FinalScore tertinggi
```

## 5. Groundtruth pada Project

Groundtruth pada project ini bukan angka uncertainty tertentu. Groundtruth adalah expected behavior dari skenario evaluasi.

Untuk Context Agent, groundtruth dihitung dari:

```text
objek budaya dengan visited = false
+ jarak Euclidean dari posisi player
+ sorting berdasarkan jarak terdekat
+ tie-break berdasarkan nama
```

Maka expected output:

```text
recommendations = top-3 objek budaya belum dikunjungi terdekat
nav_target = objek rank-1
```

Untuk Dialogue Agent, groundtruth berupa aturan:

- `recommendation_options` harus sama dengan urutan Context Agent.
- Objek rank-1 harus disebut.
- Subtitle maksimal 15 kata.
- Tidak boleh menyebut koordinat.
- Tidak boleh menyebut istilah teknis seperti backend/token/system.
- Tidak boleh hallucinate nama objek di luar daftar.

## 6. Hasil Penerapan UQ

Hasil evaluasi 50 skenario:

| Kondisi | Passed | Pass Rate | Faithfulness |
|---|---:|---:|---:|
| Baseline tanpa UQ | 48/50 | 96% | 0.992 |
| Dengan UQ | 49/50 | 98% | 1.000 |

Interpretasi:

- UQ meningkatkan stabilitas output generatif.
- Ranking rekomendasi tetap stabil karena dihitung deterministic.
- Perbaikan paling terlihat pada output interpretatif dan dialog.
- UQ tidak menggantikan groundtruth, tetapi membantu memilih kandidat output yang lebih stabil dan grounded.

## 7. Kalimat Ringkas untuk Seminar

Penelitian ini menerapkan Uncertainty Quantification secara selektif pada Context Agent dan Dialogue Agent. Context Agent menggunakan black-box consistency-based UQ untuk memilih interpretasi konteks yang paling stabil, sedangkan Dialogue Agent menggunakan black-box response similarity UQ yang dikombinasikan dengan grounding score untuk memilih dialog yang paling konsisten dan tetap sesuai dengan ContextOutput. Groundtruth pada evaluasi bukan berupa nilai uncertainty, melainkan expected behavior dari 50 skenario terkontrol, seperti urutan rekomendasi objek, target navigasi, kesesuaian opsi dialog, dan larangan hallucination. Hasil evaluasi menunjukkan peningkatan pass rate dari 96% pada baseline tanpa UQ menjadi 98% setelah UQ diterapkan.

## 7. Penyempurnaan Validasi UQ

Evaluator terbaru menambahkan validasi selective prediction yang mengikuti prinsip
evaluasi pada paper *Generating with Confidence*:

1. Skenario diurutkan dari `UDeg` paling rendah ke paling tinggi.
2. Skenario dengan `UDeg` tertinggi ditolak secara bertahap.
3. Akurasi dihitung kembali pada skenario yang masih dipertahankan.
4. Luas kurva tersebut dilaporkan sebagai `AUARC`.
5. Jika terdapat output benar dan salah, `error_detection_auroc` juga dihitung untuk
   mengukur kemampuan `UDeg` membedakan output benar dan salah.

Hasil disimpan dalam:

```text
summary.uncertainty_validation.context_agent
summary.uncertainty_validation.dialogue_agent
summary.uq_group_summary
```

Diagram disimpan sebagai:

```text
evals/figures/08_uq_accuracy_rejection_curve.png
```

### Interpretasi yang Benar

Jika semua skenario lulus, `AUARC` dapat bernilai `1.0`, tetapi
`error_detection_auroc` akan bernilai `null` dengan status
`no_error_variation`. Kondisi ini berarti akurasi selective prediction sempurna
pada benchmark tersebut, tetapi kemampuan UQ untuk membedakan output benar dan
salah belum dapat dibuktikan karena tidak tersedia contoh output salah.

Karena itu, klaim yang aman adalah:

> UQ mempertahankan akurasi pada seluruh tingkat rejection dalam benchmark
> terkontrol. Namun validitas `UDeg` sebagai pendeteksi kesalahan membutuhkan
> variasi output benar dan salah, misalnya melalui repeated real-model runs,
> stress test, atau controlled perturbation.

Run menggunakan MockModel hanya memvalidasi pipeline dan biasanya menghasilkan
`UDeg = 0` karena semua kandidat identik. Nilai UQ yang digunakan untuk analisis
penelitian harus berasal dari model asli.
