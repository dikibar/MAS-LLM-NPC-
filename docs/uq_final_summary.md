# Ringkasan Final UQ: Context Agent dan Dialogue Agent

Dokumen ini merangkum keseluruhan penerapan **Uncertainty Quantification (UQ)** pada sistem **Multi-Agent VR Museum Guide**, mulai dari alasan pemilihan agent, metode yang digunakan, rumus, implementasi, evaluasi 50 skenario, baseline tanpa UQ, sampai kesimpulan yang dapat dipakai untuk seminar.

## 1. Tujuan Penerapan UQ

UQ diterapkan untuk menjawab pertanyaan:

> Seberapa stabil output LLM ketika agent dijalankan beberapa kali pada konteks yang sama?

Dalam sistem VR Museum Guide, output LLM tidak boleh hanya terlihat benar secara bahasa. Output juga harus:

- konsisten terhadap data objek budaya,
- tidak mengarang objek baru,
- tidak membocorkan informasi teknis seperti koordinat atau istilah backend,
- tetap mengikuti `nav_target` dari Context Agent,
- menghasilkan dialog yang aman untuk ditampilkan di UI VR.

Karena itu, UQ digunakan sebagai mekanisme untuk **membandingkan beberapa kandidat output**, lalu memilih kandidat yang paling stabil dan paling grounded.

## 2. Agent Yang Diberi UQ

UQ hanya diterapkan pada:

| Agent | Alasan Diberi UQ |
|---|---|
| Context Agent | Menghasilkan field interpretatif seperti `user_action`, `context_summary`, `recommendation_reason`, `situation_type`, dan `dialogue_intent`. Field ini bisa bervariasi karena dipengaruhi LLM. |
| Dialogue Agent | Menghasilkan bahasa natural, subtitle, dan opsi dialog. Output ini rentan variasi, hallucination, dan persona drift. |

UQ tidak diterapkan pada komponen deterministic seperti:

- filtering objek `visited`,
- perhitungan jarak,
- ranking rekomendasi,
- `nav_target`,
- dispatch NavMesh,
- validasi schema.

Alasannya: komponen deterministic sudah memiliki aturan objektif. Jika diberi UQ LLM, justru bisa membuat keputusan teknis yang seharusnya pasti menjadi kabur.

## 3. Peran ReAct Prompting pada Context Agent

Pada Context Agent, **ReAct prompting berpengaruh**, tetapi bukan sebagai penentu akhir ranking atau `nav_target`.

Perannya adalah membantu LLM melakukan reasoning terhadap konteks:

- membaca status pemain,
- membaca objek budaya,
- membaca rekomendasi yang sudah dihitung,
- menyusun ringkasan situasi,
- menentukan tipe situasi,
- menentukan intent dialog untuk Dialogue Agent.

Namun keputusan penting tetap deterministic:

```text
filter visited object
hitung jarak player ke objek
urutkan kandidat
ambil maksimal 3 rekomendasi
nav_target = rekomendasi rank 1
```

Dengan begitu, ReAct membantu agent "memahami situasi", tetapi tidak diberi kebebasan penuh untuk menentukan target navigasi.

Kalimat ringkas untuk seminar:

> ReAct prompting digunakan sebagai mekanisme reasoning interpretatif pada Context Agent, sedangkan keputusan ranking dan nav_target tetap dikendalikan secara deterministic agar tidak bergantung penuh pada LLM.

## 4. Peran Few-Shot Prompting pada Dialogue Agent

Few-shot prompting pada Dialogue Agent berpengaruh terhadap UQ secara tidak langsung.

Few-shot tidak menghitung uncertainty. Yang menghitung uncertainty adalah UQ. Namun few-shot membantu model menghasilkan output yang lebih stabil, misalnya:

- format JSON lebih konsisten,
- subtitle tetap pendek,
- dialog tetap mengikuti persona museum guide,
- opsi dialog mengikuti Context Agent,
- dialog tidak menyebut koordinat,
- dialog tidak keluar dari `nav_target`.

Hubungannya:

```text
Few-shot = memberi contoh respons yang baik
UQ       = mengecek apakah beberapa respons yang dihasilkan stabil
```

Jika few-shot baik, kandidat output yang dihasilkan LLM cenderung berbeda dalam redaksi, tetapi tetap sama dalam maksud. Ini membuat skor konsistensi lebih tinggi.

## 5. Metode UQ pada Context Agent

Kategori metode:

```text
black-box consistency-based UQ over interpretive fields
```

Metode ini disebut black-box karena tidak membutuhkan akses ke logit/token probability model. Sistem hanya melihat output akhir dari beberapa sampling.

Field yang dihitung:

- `user_action`
- `context_summary`
- `recommendation_reason`
- `situation_type`
- `dialogue_intent`

Field yang tidak dihitung:

- `recommendations`
- `nav_target`
- `cultural_position`

Alasannya: `recommendations` dan `nav_target` sudah dijaga oleh deterministic backend logic.

### Bobot Field Context Agent

Pada implementasi saat ini, semua field interpretatif pada Context Agent diberi bobot sama besar. Artinya, tidak ada satu field pun yang didominasi secara khusus; sistem memperlakukan masing-masing field sebagai bagian penting dari interpretasi konteks.

| Field | Bobot | Alasan |
|---|---:|---|
| `user_action` | 0.20 | Menjelaskan tindakan atau keadaan pemain yang sedang berlangsung. |
| `context_summary` | 0.20 | Ringkasan utama yang dibaca agent untuk menyimpulkan situasi. |
| `recommendation_reason` | 0.20 | Alasan rekomendasi yang harus tetap konsisten antar-sample. |
| `situation_type` | 0.20 | Penentu pola konteks, misalnya `multiple_recommendations` atau `single_recommendation`. |
| `dialogue_intent` | 0.20 | Penentu arah dialog yang harus stabil di setiap sample. |

### 5.1 Rumus Context UQ

Agent menghasilkan beberapa kandidat output:

```text
S = {s1, s2, ..., sm}
```

Pada implementasi saat ini:

```text
m = 3
```

Kemiripan antar kandidat dihitung sebagai:

```text
a_ij = similarity(sample_i, sample_j)
```

Untuk field teks, similarity memakai token overlap sederhana:

```text
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Untuk field kategori seperti `situation_type` dan `dialogue_intent`:

```text
similarity = 1 jika sama
similarity = 0 jika berbeda
```

Rumus pairwise similarity Context Agent:

```text
a_ij =
0.20 * sim(user_action_i, user_action_j)
+ 0.20 * sim(context_summary_i, context_summary_j)
+ 0.20 * sim(recommendation_reason_i, recommendation_reason_j)
+ 0.20 * sim(situation_type_i, situation_type_j)
+ 0.20 * sim(dialogue_intent_i, dialogue_intent_j)
```

Skor konsistensi kandidat ke-i:

```text
CDeg_i = sum(a_ij) / (m - 1)
```

Keterangan:

- `CDeg_i` = Confidence Degree kandidat ke-i; pada implementasi dihitung dari konsistensi terhadap kandidat lain.
- `a_ij` = kemiripan kandidat i terhadap kandidat j.
- `m` = jumlah sample.

Uncertainty keseluruhan:

```text
UDeg = 1 - mean(CDeg_i)
```

Interpretasi:

| Nilai | Makna |
|---|---|
| `CDeg` tinggi | Kandidat stabil dan dekat dengan mayoritas output. |
| `CDeg` rendah | Kandidat menyimpang dari kandidat lain. |
| `UDeg` rendah | Output agent stabil, uncertainty rendah. |
| `UDeg` tinggi | Output agent bervariasi, uncertainty tinggi. |

Output yang dipilih:

```text
selected_output = sample dengan CDeg tertinggi
```

## 6. Metode UQ pada Dialogue Agent

Kategori metode:

```text
black-box response similarity UQ + grounding score
```

Dialogue Agent tidak hanya butuh konsistensi antar-output, tetapi juga harus grounded ke Context Agent.

Karena itu, Dialogue Agent memakai dua skor:

1. `CDeg`, yaitu konsistensi antar kandidat dialog.
2. `grounding score`, yaitu kesesuaian dialog terhadap opsi dan target dari Context Agent.

### 6.1 Rumus Pairwise Similarity Dialogue

Kemiripan dua kandidat dialog:

```text
a_ij =
0.05 * sim(spoken_output_i, spoken_output_j)
+ 0.55 * sim(recommendation_dialogue_i, recommendation_dialogue_j)
+ 0.25 * sim(subtitle_output_i, subtitle_output_j)
+ 0.15 * sim(recommendation_options_i, recommendation_options_j)
```

Alasan bobot:

| Komponen | Bobot | Alasan |
|---|---:|---|
| `spoken_output` | 0.05 | Dipertahankan untuk kompatibilitas API, tetapi bobotnya kecil karena Unity live belum memakai audio/TTS. |
| `recommendation_dialogue` | 0.55 | Teks utama panel rekomendasi pada HUD, sehingga menjadi komponen paling dominan. |
| `subtitle_output` | 0.25 | Konfirmasi singkat yang tampil pada HUD. |
| `recommendation_options` | 0.15 | Tombol pilihan harus mengikuti urutan Context Agent. |

### 6.2 Rumus CDeg Dialogue

```text
CDeg_i = sum(a_ij) / (m - 1)
```

Kandidat dengan `CDeg` tinggi berarti responsnya dekat dengan mayoritas respons lain.

### 6.3 Rumus grounding score

`grounding score` mengukur apakah dialog tetap mengikuti Context Agent.

```text
grounding_score =
0.05 * spoken_score
+ 0.55 * recommendation_score
+ 0.20 * subtitle_score
+ 0.20 * option_score
```

Keterangan:

- `spoken_score`: apakah `spoken_output` tetap menyebut target utama, dengan bobot kecil karena belum dipakai Unity live.
- `recommendation_score`: apakah `recommendation_dialogue` menyebut target utama.
- `subtitle_score`: apakah subtitle menyebut target utama, valid, dan tidak terlalu panjang.
- `option_score`: apakah `recommendation_options` sesuai urutan Context Agent.

### 6.4 Rumus Final Selection Score

Dialogue Agent memilih kandidat berdasarkan:

```text
FinalScore_i = 0.45 * CDeg_i + 0.55 * grounding_score_i
```

Alasannya: dialog yang dipilih tidak cukup hanya mirip dengan kandidat lain, tetapi juga harus benar-benar grounded pada Context Agent.

## 7. Contoh Cara Kerja UQ

Misalnya Context Agent memberi rekomendasi:

```text
Rank 1: Angklung
Rank 2: Surabi
Rank 3: Julang Ngapak
```

Dialogue Agent menghasilkan tiga kandidat:

```text
Sample 1:
"Mari menuju Angklung sebagai tujuan utama."

Sample 2:
"Mari kita mulai dari Angklung."

Sample 3:
"Mari menuju Kujang."
```

Sample 1 dan Sample 2 konsisten karena sama-sama mengarah ke Angklung. Sample 3 menyimpang karena menyebut Kujang, padahal Kujang tidak ada pada rekomendasi.

Misalnya skor:

```text
Sample 1:
CDeg = 0.88
grounding_score = 1.00
FinalScore = 0.946

Sample 2:
CDeg = 0.85
grounding_score = 1.00
FinalScore = 0.9325

Sample 3:
CDeg = 0.35
grounding_score = 0.20
FinalScore = 0.2675
```

Maka yang dipilih adalah Sample 1. Sample 3 tidak dipakai karena menyimpang dari konteks.

## 8. Data Objek Budaya

Evaluasi terbaru memakai 8 objek budaya:

| ID | Name | Catatan |
|---|---|---|
| Surabi | Surabi | Objek awal |
| Angklung | Angklung | Objek awal |
| Julang Ngapak | Julang Ngapak | Objek awal |
| Kujang | Kujang | Objek awal |
| Badak Heuay | Badak Heuay | Objek tambahan |
| Tagog Anjing | Tagog Anjing | Objek tambahan |
| Tari Jaipong | Tari Jaipong | Objek tambahan |
| Suling Sunda | Suling Sunda | Objek tambahan |

Empat objek tambahan memiliki koordinat placeholder karena posisi final dari tim Unity belum diberikan.

File data:

```text
data/cultural_sites.json
```

## 9. Desain Evaluasi 50 Skenario

Evaluasi terdiri dari:

```text
15 skenario Context Agent normal
10 skenario Context Agent ambigu/edge case
15 skenario Dialogue Agent normal
10 skenario Dialogue Agent rawan hallucination/persona drift
```

Variasi yang diuji:

- status `visited`,
- posisi player,
- semua objek sudah dikunjungi,
- hanya satu objek tersisa,
- beberapa objek tersedia,
- valid/invalid selection,
- risiko dialog menyimpang,
- risiko hallucination,
- risiko persona drift,
- risiko technical leak.

File skenario:

```text
evals/scenarios.json
```

## 10. Metrik Evaluasi

### 10.1 Overall Pass Rate

```text
overall_pass_rate = jumlah_skenario_lulus / total_skenario
```

### 10.2 Check Pass Rate

```text
check_pass_rate = jumlah_check_lulus / total_check
```

Ini mengukur semua butir pemeriksaan, bukan hanya jumlah skenario.

### 10.3 Faithfulness

Faithfulness mengukur apakah output menyebut objek budaya yang valid dan tidak mengarang nama objek baru.

Nilai:

| Nilai | Makna |
|---|---|
| 1.0 | Tidak ada hallucinated object. |
| < 1.0 | Ada indikasi penyebutan objek tidak valid atau tidak sesuai konteks. |

### 10.4 Precision@3

```text
precision@3 = jumlah rekomendasi top-3 yang relevan / jumlah rekomendasi top-3
```

Jika `precision@3 = 1.0`, semua rekomendasi top-3 valid.

### 10.5 Recall@3

```text
recall@3 = jumlah objek relevan yang masuk top-3 / total objek relevan
```

Recall@3 bisa lebih rendah ketika jumlah objek belum dikunjungi lebih dari 3, karena sistem memang hanya menampilkan maksimal 3 rekomendasi.

### 10.6 MRR

```text
MRR = rata-rata dari 1 / posisi item relevan pertama
```

Jika item relevan terbaik ada di rank 1, skornya 1.0.

### 10.7 NDCG@3

NDCG@3 mengukur kualitas urutan ranking top-3. Semakin dekat ke 1.0, semakin baik urutan rekomendasi.

## 11. Hasil Evaluasi Dengan UQ

Run real OpenRouter dengan UQ:

```text
File hasil:
evals/results/eval_results_20260602_133230.json
```

Ringkasan:

| Metrik | Nilai |
|---|---:|
| Total skenario | 50 |
| Passed | 49 |
| Overall pass rate | 98% |
| Check pass rate | 99.89% |
| Faithfulness avg | 1.000 |
| Precision@3 | 1.000 |
| Recall@3 | 0.6252 |
| MRR | 0.960 |
| NDCG@3 | 0.940 |

Satu skenario gagal:

```text
sc40_dialogue_normal_15
```

Check yang gagal:

```text
no_coordinates_in_interpretive_fields
```

Setelah dicek, kegagalan ini bukan karena ranking atau dialog salah. Penyebabnya adalah field interpretatif menyebut kata teknis `backend`, sehingga evaluator menandainya sebagai technical leak.

## 12. Hasil Baseline Tanpa UQ

Baseline dijalankan dengan single-sample generation:

```bash
USE_MOCK_MODEL=false CONTEXT_UQ_SAMPLES=1 DIALOGUE_UQ_SAMPLES=1 PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all --skip-llm-judge --json
```

File hasil:

```text
evals/results/eval_results_20260602_151534.json
```

Ringkasan:

| Metrik | Nilai |
|---|---:|
| Total skenario | 50 |
| Passed | 48 |
| Overall pass rate | 96% |
| Check pass rate | 99.78% |
| Faithfulness avg | 0.992 |
| Precision@3 | 1.000 |
| Recall@3 | 0.6252 |
| MRR | 0.960 |
| NDCG@3 | 0.940 |

Skenario gagal:

```text
sc05_context_normal_05
sc33_dialogue_normal_08
```

Keduanya gagal pada check:

```text
no_coordinates_in_interpretive_fields
```

Penyebabnya sama: field interpretatif memunculkan istilah teknis `backend`.

## 13. Perbandingan Baseline vs UQ

| Metrik | Baseline Tanpa UQ | Dengan UQ | Perubahan |
|---|---:|---:|---:|
| Passed | 48/50 | 49/50 | +1 skenario |
| Overall pass rate | 96% | 98% | +2% |
| Check pass rate | 99.78% | 99.89% | +0.11% |
| Faithfulness avg | 0.992 | 1.000 | +0.008 |
| Precision@3 | 1.000 | 1.000 | tetap |
| Recall@3 | 0.6252 | 0.6252 | tetap |
| MRR | 0.960 | 0.960 | tetap |
| NDCG@3 | 0.940 | 0.940 | tetap |

Interpretasi:

- UQ tidak mengubah performa ranking karena ranking sudah deterministic.
- UQ membantu pada bagian generatif/interpretatif.
- UQ mengurangi failure technical leak dari 2 kasus menjadi 1 kasus.
- UQ menjaga faithfulness menjadi sempurna.

Diagram perbandingan:

```text
docs/figures/baseline_vs_uq_comparison.png
```

## 14. Hasil Export Metrik UQ Per Skenario

Evaluator sekarang menyimpan metrik UQ per skenario.

Context Agent:

```json
{
  "context_uq": {
    "method": "consistency_based_interpretive_fields",
    "sample_count": 3,
    "degree_scores": [1.0, 1.0, 1.0],
    "udeg": 0.0,
    "selected_cdeg": 1.0,
    "situation_agreement": 1.0,
    "intent_agreement": 1.0,
    "selected_index": 0
  }
}
```

Dialogue Agent:

```json
{
  "dialogue_uq": {
    "method": "black_box_response_similarity_cdeg",
    "sample_count": 3,
    "degree_scores": [1.0, 1.0, 1.0],
    "udeg": 0.0,
    "selected_cdeg": 1.0,
    "selected_index": 0,
    "grounding_scores": [1.0, 1.0, 1.0],
    "selection_scores": [1.0, 1.0, 1.0],
    "selected_grounding": 1.0,
    "selected_score": 1.0
  }
}
```

Ini penting karena membuktikan bahwa UQ tidak hanya diterapkan secara konseptual, tetapi benar-benar dihitung dan disimpan pada hasil evaluasi.

## 15. Diagram Yang Telah Dibuat

Diagram metodologi UQ:

```text
docs/figures/uq_context_dialogue_agents.png
```

Diagram hasil UQ:

```text
docs/figures/uq_result_context_dialogue_agents.png
```

Diagram hasil initial scenario:

```text
docs/figures/initial_run_scenario_results.png
```

Diagram baseline vs UQ:

```text
docs/figures/baseline_vs_uq_comparison.png
```

## 16. File Implementasi Penting

Context Agent UQ:

```text
src/agents/context_agent.py
```

Dialogue Agent UQ:

```text
src/agents/dialogue_agent.py
```

Evaluator:

```text
evals/run_agent_evaluation.py
```

Skenario:

```text
evals/scenarios.json
```

Data objek budaya:

```text
data/cultural_sites.json
```

Hasil evaluasi UQ:

```text
evals/results/eval_results_20260602_133230.json
```

Hasil baseline tanpa UQ:

```text
evals/results/eval_results_20260602_151534.json
```

## 17. Detail Metode UQ Per Agent

Bagian ini menjelaskan secara lebih eksplisit metode UQ yang dipakai pada tiap agent, peran metode tersebut, rumus perhitungannya, dan alasan pemilihannya.

### 17.1 Context Agent

Metode UQ yang dipakai:

```text
black-box consistency-based UQ over interpretive fields
```

Artinya, Context Agent dijalankan beberapa kali untuk menghasilkan beberapa kandidat output. Setelah itu, sistem membandingkan apakah bagian interpretatif dari output tersebut konsisten.

Field yang dihitung UQ:

```text
user_action
context_summary
recommendation_reason
situation_type
dialogue_intent
```

Bobot field Context Agent pada implementasi saat ini:

```text
user_action            = 0.20
context_summary        = 0.20
recommendation_reason   = 0.20
situation_type         = 0.20
dialogue_intent        = 0.20
```

Field yang tidak dihitung UQ:

```text
recommendations
nav_target
cultural_position
```

Alasannya: `recommendations`, `nav_target`, dan `cultural_position` adalah bagian yang sudah dikunci oleh deterministic ranking dan runtime logic. UQ tidak perlu menghitung bagian ini karena ketidakpastian utamanya bukan berasal dari LLM, melainkan sudah diatur oleh perhitungan objektif.

Peran UQ pada Context Agent:

- mengecek apakah interpretasi situasi stabil,
- memilih `context_summary` yang paling konsisten,
- memilih `recommendation_reason` yang tidak menyimpang,
- menjaga `situation_type` tetap sesuai,
- menjaga `dialogue_intent` tidak berubah-ubah.

Contoh:

```text
Sample 1:
situation_type = multiple_recommendations
dialogue_intent = guide_to_primary_with_alternatives

Sample 2:
situation_type = multiple_recommendations
dialogue_intent = guide_to_primary_with_alternatives

Sample 3:
situation_type = exploration_context
dialogue_intent = encourage_exploration
```

Sample 3 dianggap lebih tidak stabil karena berbeda dari mayoritas.

Rumus similarity antar-sample:

```text
a_ij = similarity(sample_i, sample_j)
```

Untuk field teks seperti `context_summary` dan `recommendation_reason`, similarity memakai Jaccard token overlap:

```text
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Rumus pairwise similarity Context Agent:

```text
a_ij =
0.20 * sim(user_action_i, user_action_j)
+ 0.20 * sim(context_summary_i, context_summary_j)
+ 0.20 * sim(recommendation_reason_i, recommendation_reason_j)
+ 0.20 * sim(situation_type_i, situation_type_j)
+ 0.20 * sim(dialogue_intent_i, dialogue_intent_j)
```

Keterangan:

```text
A = kumpulan token dari teks sample i
B = kumpulan token dari teks sample j
```

Untuk field kategori seperti `situation_type` dan `dialogue_intent`:

```text
similarity = 1 jika sama
similarity = 0 jika berbeda
```

Lalu dihitung `CDeg`:

```text
CDeg_i = sum(a_ij) / (m - 1)
```

Keterangan:

```text
CDeg_i = Confidence Degree sample ke-i, dihitung dari konsistensi terhadap sample lain
a_ij   = similarity sample i terhadap sample j
m      = jumlah sample
```

Dalam sistem ini:

```text
m = 3
```

Uncertainty degree:

```text
UDeg = 1 - mean(CDeg_i)
```

Interpretasi:

| Nilai | Makna |
|---|---|
| `CDeg` tinggi | Output kandidat stabil dan dekat dengan mayoritas output. |
| `CDeg` rendah | Output kandidat menyimpang dari kandidat lain. |
| `UDeg` rendah | Uncertainty rendah. |
| `UDeg` tinggi | Uncertainty tinggi. |

Output yang dipakai:

```text
selected_output = sample dengan CDeg tertinggi
```

Alasan metode ini cocok untuk Context Agent:

1. Context Agent memiliki output interpretatif, bukan hanya hasil hitungan.
2. LLM bisa berbeda-beda dalam menjelaskan situasi walaupun data runtime sama.
3. Sistem memakai model black-box melalui OpenRouter, sehingga akses logit/token probability tidak selalu tersedia.
4. Yang perlu diuji adalah stabilitas output level field, bukan token individual.
5. Ranking dan `nav_target` sudah deterministic, jadi UQ cukup difokuskan pada field interpretatif.

### 17.2 Dialogue Agent

Metode UQ yang dipakai:

```text
black-box response similarity UQ + grounding score
```

Artinya, Dialogue Agent menghasilkan beberapa kandidat dialog, lalu sistem memilih dialog yang:

1. paling konsisten dengan kandidat lain,
2. paling grounded terhadap output Context Agent.

Field yang dibandingkan:

```text
recommendation_dialogue
subtitle_output
recommendation_options
```

`spoken_output` tetap dihasilkan untuk kompatibilitas kontrak API lama, tetapi
tidak digunakan oleh Unity dan tidak masuk perhitungan UQ.

Peran UQ pada Dialogue Agent:

- mencegah dialog menyimpang dari `nav_target`,
- mencegah hallucination objek budaya,
- menjaga subtitle tetap pendek,
- menjaga opsi sesuai urutan rekomendasi Context Agent,
- mengurangi persona drift,
- memilih respons yang paling stabil dan grounded.

Contoh:

```text
Context Agent:
recommendation_options = [Angklung, Surabi, Julang Ngapak]
nav_target = Angklung

Sample 1:
Mari menuju Angklung sebagai tujuan utama.

Sample 2:
Mari kita mulai dari Angklung.

Sample 3:
Mari menuju Kujang.
```

Sample 1 dan Sample 2 masih stabil karena sama-sama mengarah ke Angklung. Sample 3 menyimpang karena menyebut Kujang, padahal Kujang tidak ada dalam opsi rekomendasi.

Rumus similarity Dialogue Agent:

```text
a_ij =
0.05 * sim(spoken_output_i, spoken_output_j)
+ 0.55 * sim(recommendation_dialogue_i, recommendation_dialogue_j)
+ 0.25 * sim(subtitle_output_i, subtitle_output_j)
+ 0.15 * sim(recommendation_options_i, recommendation_options_j)
```

Alasan bobot:

| Komponen | Bobot | Alasan |
|---|---:|---|
| `spoken_output` | 0.05 | Hanya kompatibilitas API dan belum dipakai Unity live, sehingga bobotnya kecil. |
| `recommendation_dialogue` | 0.55 | Teks utama yang tampil pada panel HUD, sehingga paling menentukan. |
| `subtitle_output` | 0.25 | Teks konfirmasi singkat yang tampil pada HUD. |
| `recommendation_options` | 0.15 | Tombol pilihan harus mengikuti Context Agent. |

Lalu dihitung `CDeg`:

```text
CDeg_i = sum(a_ij) / (m - 1)
```

grounding score:

```text
grounding_score =
0.05 * spoken_score
+ 0.55 * recommendation_score
+ 0.20 * subtitle_score
+ 0.20 * option_score
```

Keterangan:

| Komponen | Makna |
|---|---|
| `spoken_score` | Mengukur apakah `spoken_output` tetap menyebut target utama, dengan bobot kecil karena belum dipakai Unity live. |
| `recommendation_score` | Mengukur apakah `recommendation_dialogue` menyebut objek rank 1 atau `nav_target`. |
| `subtitle_score` | Mengukur apakah subtitle valid, singkat, cocok untuk UI, dan menyebut target utama. |
| `option_score` | Mengukur apakah `recommendation_options` sesuai dengan Context Agent. |

Skor akhir pemilihan:

```text
FinalScore_i = 0.45 * CDeg_i + 0.55 * grounding_score_i
```

`grounding score` diberi bobot lebih besar daripada `CDeg` karena dialog yang konsisten belum tentu benar. Bisa saja beberapa kandidat sama-sama konsisten, tetapi semuanya menyebut objek yang salah. Karena itu, Dialogue Agent tidak cukup memilih respons yang mirip dengan mayoritas, tetapi harus memilih respons yang paling sesuai dengan Context Agent.

Output yang dipakai:

```text
selected_output = sample dengan FinalScore tertinggi
```

Alasan metode ini cocok untuk Dialogue Agent:

1. Dialogue Agent menghasilkan bahasa natural yang sangat variatif.
2. Risiko hallucination lebih tinggi pada dialog dibanding ranking.
3. Dialog harus mengikuti Context Agent, bukan mengambil keputusan baru sendiri.
4. Subtitle harus pendek dan aman untuk UI VR.
5. Persona museum guide harus stabil.
6. Model yang digunakan bersifat black-box, sehingga metode sampling output lebih realistis daripada token entropy.

### 17.3 Kenapa Bukan Entropy Token?

Token-level entropy relevan dalam literatur UQ, tetapi kurang cocok sebagai metode utama pada sistem ini karena:

1. Model via OpenRouter tidak selalu menyediakan token probability atau logprob lengkap.
2. Sistem membutuhkan evaluasi level output, bukan hanya level token.
3. Kesalahan utama pada museum guide terjadi pada level keputusan, kalimat, opsi, dan grounding.
4. Yang ingin diketahui adalah apakah respons akhir stabil dan sesuai konteks, bukan hanya apakah token tertentu probabilitasnya rendah.

Karena itu, metode yang lebih sesuai adalah:

```text
black-box sampling + response similarity + grounding score
```

### 17.4 Kenapa UQ Tidak Dipasang di Semua Agent?

Tidak semua bagian sistem memiliki ketidakpastian generatif. Komponen seperti:

```text
distance calculation
visited filtering
top-3 recommendation
nav_target dispatch
```

lebih tepat diuji dengan rule-based deterministic checks.

Prinsip desainnya:

```text
UQ untuk bagian yang interpretatif/generatif.
Rule-based deterministic logic untuk bagian yang objektif dan bisa dihitung.
```

Ringkasan:

| Agent | Metode UQ | Fungsi Utama |
|---|---|---|
| Context Agent | black-box consistency-based UQ | Memilih interpretasi konteks paling stabil. |
| Dialogue Agent | black-box response similarity UQ + grounding score | Memilih dialog paling stabil dan paling sesuai Context Agent. |

Kalimat siap pakai:

> Context Agent menggunakan black-box consistency-based UQ untuk mengukur stabilitas field interpretatif seperti user_action, context_summary, recommendation_reason, situation_type, dan dialogue_intent. Dialogue Agent menggunakan black-box response similarity UQ yang dikombinasikan dengan grounding score untuk memilih respons yang bukan hanya konsisten antar-sample, tetapi juga sesuai dengan rekomendasi Context Agent. Pendekatan ini dipilih karena model yang digunakan bersifat black-box dan risiko utama sistem berada pada output interpretatif serta generatif, bukan pada ranking deterministic.

## 18. Kesimpulan Akademik

Penerapan UQ pada sistem Multi-Agent VR Museum Guide dilakukan secara selektif pada Context Agent dan Dialogue Agent. Context Agent menggunakan black-box consistency-based UQ pada field interpretatif, sedangkan Dialogue Agent menggunakan black-box response similarity UQ, CDeg, grounding score, dan final selection score untuk memilih respons yang paling stabil serta paling sesuai dengan Context Agent.

Evaluasi pada 50 skenario berbasis 8 objek budaya menunjukkan bahwa sistem dengan UQ mencapai:

```text
49/50 passed
overall pass rate 98%
faithfulness 1.0
precision@3 1.0
MRR 0.96
NDCG@3 0.94
```

Dibanding baseline tanpa UQ, sistem dengan UQ meningkat dari 48/50 menjadi 49/50 skenario lulus. Peningkatan ini terutama terjadi pada aspek generatif/interpretatif, bukan pada ranking deterministic. Hal ini masuk akal karena ranking, filtering visited, dan nav_target memang sudah dikendalikan oleh deterministic logic.

Dengan demikian, klaim yang aman adalah:

> UQ membantu meningkatkan stabilitas output interpretatif dan dialog pada Context Agent dan Dialogue Agent, sekaligus menjaga faithfulness terhadap data objek budaya. Namun UQ tidak dimaksudkan untuk menggantikan deterministic ranking atau validasi runtime Unity.

## 19. Batasan

Beberapa batasan yang perlu disampaikan:

1. Evaluasi 50 skenario adalah controlled benchmark, bukan pengganti penuh Unity live test.
2. Empat koordinat objek tambahan masih placeholder.
3. LLM Judge tidak aktif pada run baseline vs UQ terbaru, sehingga hasil ini terutama membuktikan stabilitas struktural dan faithfulness, bukan kualitas estetika persona.
4. Failure yang tersisa lebih terkait technical leak wording, yaitu kemunculan kata `backend`, bukan kesalahan navigasi.
5. Untuk evaluasi UQ yang lebih kuat, dapat ditambahkan selective generation curve atau AUARC.

## 20. Kalimat Siap Pakai Untuk Seminar

> Sistem ini menerapkan UQ hanya pada Context Agent dan Dialogue Agent karena keduanya menghasilkan output interpretatif dan generatif. Context Agent memakai black-box consistency-based UQ untuk memilih interpretasi konteks yang paling stabil, sedangkan Dialogue Agent memakai black-box response similarity UQ dan grounding score untuk memilih dialog yang paling konsisten serta tetap sesuai dengan Context Agent. Hasil evaluasi 50 skenario menunjukkan bahwa UQ meningkatkan pass rate dari 96% pada baseline single-generation menjadi 98%, serta meningkatkan faithfulness dari 0.992 menjadi 1.0. Karena ranking rekomendasi sudah deterministic, metrik IR seperti Precision@3, MRR, dan NDCG tetap stabil. Ini menunjukkan bahwa kontribusi UQ berada pada stabilitas bahasa dan interpretasi, bukan pada penggantian logic ranking.

## 21. Langkah Berikutnya Jika Ingin Diperkuat

Langkah tambahan yang bisa dilakukan setelah tahap ini:

1. Perbaiki prompt agar tidak memakai kata teknis `backend` pada `recommendation_reason`.
2. Jalankan ulang 50 skenario dengan UQ setelah perbaikan technical leak.
3. Jalankan LLM Judge khusus untuk kualitas persona dan naturalitas dialog.
4. Lakukan Unity live test setelah koordinat 4 objek tambahan diberikan tim Unity.
5. Tambahkan selective generation evaluation atau AUARC jika ingin klaim UQ lebih kuat secara statistik.
