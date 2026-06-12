# Panduan Seminar: Uncertainty Quantification (UQ) pada Context Agent dan Dialogue Agent

Dokumen ini adalah bahan belajar dan pegangan seminar untuk menjelaskan penerapan **Uncertainty Quantification (UQ)** pada sistem **Multi-Agent VR Museum Guide**. Bahasa dibuat sengaja lebih mudah dipahami, tetapi tetap cukup teknis untuk dipertanggungjawabkan secara akademik.

---

## 1. Gambaran Singkat Sistem

Project ini adalah backend Python untuk sistem **NPC pemandu budaya di lingkungan VR museum**. NPC bernama **Arif** berperan sebagai pemandu yang membantu pemain memilih dan menuju objek budaya.

Alur utama sistem:

```text
Unity snapshot
-> Context Agent
-> NavMesh/session
-> Dialogue Agent
-> HUD/UI
-> Player selection
```

Sistem saat ini memiliki dua agent utama:

1. **Context Agent**
   - Membaca snapshot runtime dari Unity.
   - Menghasilkan konteks terstruktur.
   - Menentukan `context_summary`, `situation_type`, `recommendation_reason`, dan `dialogue_intent`.
   - Ranking objek budaya tetap dihitung secara deterministic oleh backend berdasarkan jarak dan status `visited`.

2. **Dialogue Agent**
   - Membaca output Context Agent.
   - Menghasilkan ucapan NPC Arif.
   - Menghasilkan subtitle.
   - Menghasilkan opsi rekomendasi untuk UI.

Komponen deterministic seperti perhitungan jarak, filtering `visited`, `nav_target`, dan validasi schema tidak diberi UQ LLM karena komponen ini sudah bisa diuji secara objektif.

---

## 2. Masalah Yang Ingin Diatasi

LLM bisa menghasilkan jawaban yang terdengar yakin, tetapi sebenarnya:

- tidak konsisten,
- tidak grounded pada input,
- mengarang fakta,
- salah menyebut target,
- atau berbeda hasil ketika dijalankan ulang.

Dalam sistem VR museum, masalah ini penting karena NPC pemandu harus terasa natural, tetapi juga tidak boleh sembarangan memberi arahan atau informasi.

Contoh risiko:

```text
Context mengatakan target utama adalah "Kujang",
tetapi Dialogue Agent menyuruh pemain menuju "Angklung".
```

Atau:

```text
Dialogue Agent menyebut sejarah objek budaya yang tidak ada di input.
```

Karena itu, sistem perlu mekanisme untuk mengukur:

```text
Seberapa stabil output agent?
Seberapa percaya sistem terhadap output yang dipilih?
Kapan output perlu diganti dengan fallback yang lebih aman?
```

Di sinilah **Uncertainty Quantification (UQ)** digunakan.

---

## 3. Apa Itu Uncertainty Quantification?

**Uncertainty Quantification (UQ)** adalah metode untuk mengukur ketidakpastian model terhadap output yang dihasilkan.

Dalam konteks LLM, UQ membantu menjawab pertanyaan:

```text
Apakah model benar-benar stabil dengan jawabannya?
Atau model menghasilkan jawaban yang berubah-ubah?
```

UQ berbeda dari sekadar meminta model berkata:

```text
"Saya yakin 90%."
```

Alasan: LLM sering **overconfident**, yaitu tampak yakin meskipun salah. Karena itu, penelitian UQ modern tidak hanya mengandalkan pengakuan confidence dari LLM, tetapi melihat **perilaku output ketika model dijalankan beberapa kali**.

---

## 4. Perbedaan Uncertainty dan Confidence

Dalam paper *Generating with Confidence: Uncertainty Quantification for Black-box Large Language Models*, terdapat perbedaan penting:

### 4.1 Uncertainty

**Uncertainty** adalah ketidakpastian terhadap satu input secara keseluruhan.

Pertanyaannya:

```text
Untuk input yang sama, apakah model menghasilkan banyak jawaban berbeda?
```

Jika output sangat bervariasi, uncertainty tinggi.

### 4.2 Confidence

**Confidence** adalah tingkat kepercayaan terhadap satu output tertentu.

Pertanyaannya:

```text
Dari beberapa output yang muncul, output mana yang paling stabil dan paling representatif?
```

Dalam sistem ini:

- `UDeg` dipakai sebagai ukuran uncertainty keseluruhan.
- `CDeg` dipakai sebagai ukuran confidence dari satu sample output.

---

## 5. Kenapa UQ Hanya Diterapkan Pada Context Agent dan Dialogue Agent?

Tidak semua bagian sistem perlu UQ.

UQ cocok untuk bagian yang bersifat **generatif** atau **interpretatif**, yaitu bagian yang hasilnya bisa bervariasi jika LLM dijalankan ulang.

### 5.1 Komponen Yang Diberi UQ

| Komponen | Alasan Diberi UQ |
|---|---|
| Context Agent | Menghasilkan interpretasi situasi, seperti `situation_type`, `dialogue_intent`, dan `recommendation_reason`. |
| Dialogue Agent | Menghasilkan bahasa natural, subtitle, dan opsi UI yang rawan variasi atau hallucination. |

### 5.2 Komponen Yang Tidak Diberi UQ

| Komponen | Alasan Tidak Diberi UQ |
|---|---|
| Ranking jarak | Bisa dihitung deterministic dengan rumus Euclidean distance. |
| Filtering visited | Cukup cek boolean `visited`. |
| NavMesh target | Harus mengikuti rank-1 recommendation. |
| Selection handler | Cukup exact/fuzzy match terhadap opsi aktif. |
| Schema validation | Sudah bisa diuji dengan Pydantic. |

Jadi posisi akademiknya:

```text
UQ diterapkan secara selektif pada agent yang menghasilkan output berbasis interpretasi dan bahasa natural, bukan pada seluruh sistem.
```

Ini lebih kuat daripada memasang UQ di semua komponen tanpa alasan.

---

## 6. Data Objek Budaya

Saat ini sistem menggunakan 8 objek budaya.

Empat objek awal:

1. Surabi
2. Angklung
3. Julang Ngapak
4. Kujang

Empat objek tambahan:

1. Badak Heuay
2. Tagog Anjing
3. Tari Jaipong
4. Suling Sunda

Data yang digunakan:

```json
{
  "sites": [
    {
      "id": "Surabi",
      "name": "Surabi",
      "cultural_position": "-1.34956, 1.52654, 23.7432",
      "visited": false
    },
    {
      "id": "Angklung",
      "name": "Angklung",
      "cultural_position": "14.62413, 1.37554, 18.67057",
      "visited": true
    },
    {
      "id": "Julang Ngapak",
      "name": "Julang Ngapak",
      "cultural_position": "21.48713, 2.18983, 17.03246",
      "visited": false
    },
    {
      "id": "Kujang",
      "name": "Kujang",
      "cultural_position": "19.72784, 0.30118, 21.86564",
      "visited": false
    },
    {
      "id": "Badak Heuay",
      "name": "Badak Heuay",
      "cultural_position": "6.84231, 1.18492, 28.41675",
      "visited": false
    },
    {
      "id": "Tagog Anjing",
      "name": "Tagog Anjing",
      "cultural_position": "24.31892, 1.04735, 10.59284",
      "visited": false
    },
    {
      "id": "Tari Jaipong",
      "name": "Tari Jaipong",
      "cultural_position": "11.27364, 1.66247, 6.73451",
      "visited": false
    },
    {
      "id": "Suling Sunda",
      "name": "Suling Sunda",
      "cultural_position": "27.95618, 1.23804, 24.37192",
      "visited": false
    }
  ]
}
```

Catatan penting:

```text
Koordinat untuk Badak Heuay, Tagog Anjing, Tari Jaipong, dan Suling Sunda adalah placeholder terkontrol untuk evaluasi.
Koordinat ini perlu diganti jika tim Unity sudah memberikan posisi final.
```

---

## 7. Desain 50 Skenario Evaluasi

Skenario evaluasi dibuat sebagai **controlled benchmark**, bukan sebagai pengganti penuh Unity live test.

Artinya:

```text
Skenario ini digunakan untuk menguji perilaku agent secara sistematis.
Unity live test tetap diperlukan untuk validasi integrasi nyata.
```

Komposisi skenario:

| Kelompok | Jumlah | Tujuan |
|---|---:|---|
| Context Agent normal | 15 | Menguji kondisi umum dengan variasi posisi player dan visited flag. |
| Context Agent edge/ambigu | 10 | Menguji kondisi sulit seperti all visited, single remaining, banyak objek visited, dan alias payload. |
| Dialogue Agent normal | 15 | Menguji apakah dialog, subtitle, dan opsi UI sesuai dengan context. |
| Dialogue Agent risk/persona drift | 10 | Menguji kondisi rawan hallucination, salah target, atau persona drift. |

Semua skenario memakai 8 objek budaya yang sama, tetapi divariasikan:

- posisi player,
- status `visited`,
- jumlah objek yang belum dikunjungi,
- payload alias dari Unity,
- pilihan user valid,
- pilihan user invalid,
- dan kasus semua objek sudah dikunjungi.

---

## 8. UQ pada Context Agent

### 8.1 Tujuan

Context Agent diberi UQ untuk mengukur stabilitas field interpretatif.

Field interpretatif adalah field yang merupakan hasil penafsiran LLM, bukan hasil hitungan langsung.

Contoh field interpretatif:

```json
{
  "user_action": "...",
  "context_summary": "...",
  "situation_type": "...",
  "recommendation_reason": "...",
  "dialogue_intent": "..."
}
```

Field yang tidak dihitung UQ:

```json
{
  "recommendations": [...],
  "nav_target": "..."
}
```

Alasannya: `recommendations` dan `nav_target` sudah dikunci oleh backend berdasarkan ranking deterministic.

### 8.2 Metode Yang Digunakan

Kategori metode:

```text
black-box consistency-based UQ
```

Black-box artinya metode ini tidak membutuhkan token logits atau akses internal model. Sistem cukup melihat output teks yang dihasilkan. Consistency-based artinya beberapa output untuk input yang sama dibandingkan untuk melihat stabilitasnya.

Langkah:

1. Jalankan Context Agent sebanyak `m` kali.
2. Ambil beberapa kandidat `ContextOutput`.
3. Bandingkan field interpretatif antar-sample.
4. Hitung skor kemiripan.
5. Pilih sample yang paling stabil.

Saat ini:

```text
m = 3
```

### 8.3 Rumus Similarity Context Agent

Untuk dua sample, misalnya sample ke-i dan sample ke-j, dihitung similarity:

```text
a_ij = rata-rata similarity field interpretatif antara sample i dan sample j
```

Untuk field kategorikal:

```text
similarity = 1 jika nilainya sama
similarity = 0 jika nilainya berbeda
```

Contoh:

```text
situation_type sample 1 = multiple_recommendations
situation_type sample 2 = multiple_recommendations
similarity = 1
```

Jika berbeda:

```text
situation_type sample 1 = multiple_recommendations
situation_type sample 2 = exploration_context
similarity = 0
```

Untuk field teks, digunakan **Jaccard Similarity**:

```text
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Penjelasan sederhana:

- `A ∩ B` = kata yang sama-sama muncul di dua teks.
- `A ∪ B` = semua kata unik dari dua teks.

Contoh:

```text
Teks A = "Pemain berada dekat Kujang"
Teks B = "Pemain berada dekat Surabi"

Kata sama = {Pemain, berada, dekat}
Semua kata unik = {Pemain, berada, dekat, Kujang, Surabi}

Jaccard = 3 / 5 = 0.6
```

### 8.4 Rumus CDeg Context Agent

`CDeg` adalah singkatan dari **Confidence Degree**.

Rumus:

```text
CDeg_i = Σ a_ij / (m - 1)
```

Artinya:

```text
CDeg sample ke-i = rata-rata kemiripan sample ke-i terhadap semua sample lain.
```

Jika `CDeg` tinggi, berarti sample tersebut mirip dengan sample lain dan dianggap stabil.

### 8.5 Rumus UDeg Context Agent

`UDeg` adalah singkatan dari **Uncertainty Degree**.

Rumus:

```text
UDeg = 1 - mean(CDeg_i)
```

Interpretasi:

| Nilai UDeg | Arti |
|---:|---|
| Mendekati 0 | Output agent stabil, uncertainty rendah. |
| Mendekati 1 | Output agent bervariasi, uncertainty tinggi. |

### 8.6 Apa Yang Diambil Dari Hasil UQ?

Context Agent memilih:

```text
sample dengan CDeg tertinggi
```

Karena sample tersebut dianggap paling representatif dari kumpulan output.

---

## 9. UQ pada Dialogue Agent

### 9.1 Tujuan

Dialogue Agent menghasilkan bahasa natural. Karena itu, risikonya berbeda dari Context Agent.

Risiko Dialogue Agent:

- salah menyebut target utama,
- opsi UI tidak sesuai context,
- subtitle terlalu panjang,
- mengarang fakta budaya,
- gaya bahasa tidak sesuai persona Arif,
- atau menyebut istilah teknis backend.

### 9.2 Metode Yang Digunakan

Kategori metode:

```text
black-box response similarity UQ + grounding score
```

Maknanya:

- Agent dijalankan beberapa kali.
- Setiap output dianggap sebagai sample.
- Sample dibandingkan satu sama lain.
- Output yang paling stabil dan paling grounded dipilih.

### 9.3 Rumus Similarity Dialogue Agent

Dialogue Agent membandingkan empat bagian output:

1. `recommendation_dialogue`
2. `subtitle_output`
3. `recommendation_options`

`spoken_output` masih ada pada kontrak API untuk kompatibilitas, tetapi VR saat
ini tidak memakai audio/TTS sehingga field tersebut tidak dihitung dalam UQ.

Rumus:

```text
a_ij =
0.50 * sim(recommendation_dialogue_i, recommendation_dialogue_j)
+ 0.30 * sim(subtitle_output_i, subtitle_output_j)
+ 0.20 * sim(recommendation_options_i, recommendation_options_j)
```

Kenapa bobot `recommendation_dialogue` paling besar?

Karena `recommendation_dialogue` adalah teks utama yang benar-benar tampil pada
panel HUD dan menjadi dasar pemain memahami rekomendasi.

Kenapa `subtitle_output` diberi bobot kedua terbesar?

Karena `subtitle_output` menjadi konfirmasi visual singkat setelah pemain memilih tujuan.

Kenapa `recommendation_options` tetap dihitung?

Karena opsi UI harus konsisten dengan `recommendations` dari Context Agent.

### 9.4 Rumus CDeg Dialogue Agent

Sama seperti Context Agent:

```text
CDeg_i = Σ a_ij / (m - 1)
```

Artinya:

```text
Dialog dengan CDeg tinggi adalah dialog yang paling mirip dengan dialog-dialog lain.
```

Namun, ada masalah penting:

```text
Dialog yang konsisten belum tentu benar.
```

Contoh:

Jika tiga sample sama-sama menyebut target yang salah, `CDeg` bisa tinggi, tetapi output tetap salah.

Karena itu, Dialogue Agent juga memakai **grounding score**.

### 9.5 grounding score

`grounding score` mengukur apakah dialog sesuai dengan ContextOutput.

Yang dicek:

1. Apakah `recommendation_options` sama dengan context?
2. Apakah target utama disebut?
3. Apakah subtitle tidak lebih dari 15 kata?

Rumus:

```text
grounding_score =
0.50 * option_score
+ 0.35 * primary_score
+ 0.15 * subtitle_score
```

Penjelasan:

| Komponen | Arti |
|---|---|
| `option_score` | Apakah opsi UI sama dengan recommendations dari Context Agent. |
| `primary_score` | Apakah target utama disebut di dialog/subtitle/UI. |
| `subtitle_score` | Apakah subtitle valid dan maksimal 15 kata. |

### 9.6 Final Score Dialogue Agent

Dialogue Agent memilih output berdasarkan kombinasi `CDeg` dan `grounding score`.

Rumus:

```text
FinalScore_i =
0.45 * CDeg_i
+ 0.55 * grounding_score_i
```

Kenapa `grounding score` lebih besar dari `CDeg`?

Karena dalam sistem pemandu VR, output yang stabil tetapi salah tetap berbahaya.

Contoh:

```text
Tiga sample sama-sama menyebut "Angklung",
padahal target utama adalah "Kujang".
```

Secara `CDeg`, output bisa terlihat stabil. Tetapi secara `grounding score`, output itu salah.

Karena itu, `grounding score` diberi bobot lebih besar.

### 9.7 Fallback

Jika output terlalu tidak stabil dan grounding lemah, sistem menggunakan safe fallback.

Contoh fallback:

```text
"Ada beberapa tujuan budaya yang bisa kita jelajahi. Mari mulai dari tujuan utama berikutnya."
```

Fallback ini lebih aman karena tidak mengarang informasi budaya yang tidak ada di input.

---

## 10. Hasil Pengujian Terakhir

Pengujian dilakukan dengan:

```bash
USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all --skip-llm-judge --json
```

Hasil:

```text
Total scenarios : 50
Passed          : 50
Overall pass    : 100%
Check pass rate : 100%
Faithfulness avg: 1.0
Precision@3     : 1.0
Recall@3        : 0.6252
MRR             : 0.96
NDCG@3          : 0.94
```

Makna umum:

```text
Sistem berhasil melewati 50 skenario terkontrol berbasis 8 objek budaya.
```

---

## 11. Penjelasan Terminologi Hasil Evaluasi

### 11.1 Total Scenarios

Jumlah seluruh skenario yang diuji.

```text
Total scenarios = 50
```

### 11.2 Passed

Jumlah skenario yang lulus semua check wajib.

```text
Passed = 50
```

### 11.3 Overall Pass Rate

Persentase skenario yang lulus.

Rumus:

```text
Overall Pass Rate = jumlah skenario lulus / total skenario
```

Hasil:

```text
50 / 50 = 1.0 = 100%
```

### 11.4 Check Pass Rate

Persentase semua butir check yang berhasil.

Contoh check:

- schema valid,
- ranking sesuai,
- nav target sesuai rank-1,
- tidak merekomendasikan objek visited,
- subtitle maksimal 15 kata,
- tidak bocor koordinat,
- opsi UI sesuai context.

Rumus:

```text
Check Pass Rate = jumlah check lulus / total check yang dijalankan
```

### 11.5 Faithfulness Average

Faithfulness mengukur apakah output tetap setia pada input.

Dalam project ini, faithfulness terutama mengecek:

- tidak menyebut nama objek yang tidak ada di input,
- tidak mengarang nama objek,
- recommendation reason tetap grounded.

Nilai:

```text
Faithfulness avg = 1.0
```

Artinya:

```text
Output yang dicek tidak melakukan hallucination nama objek.
```

---

## 12. Penjelasan Metrik Ranking

Context Agent menghasilkan maksimal 3 rekomendasi. Karena itu digunakan metrik ranking top-3.

### 12.1 Precision@3

Precision@3 menjawab:

```text
Dari rekomendasi yang diberikan, berapa yang benar/relevan?
```

Rumus:

```text
Precision@3 = jumlah item relevan di top-3 / jumlah item yang direkomendasikan
```

Hasil:

```text
Precision@3 = 1.0
```

Artinya:

```text
Semua rekomendasi yang muncul adalah objek yang valid dan belum dikunjungi.
```

### 12.2 Recall@3

Recall@3 menjawab:

```text
Dari semua objek yang seharusnya bisa direkomendasikan, berapa yang masuk top-3?
```

Rumus:

```text
Recall@3 = jumlah item relevan di top-3 / total item relevan
```

Contoh:

```text
Ada 8 objek belum dikunjungi.
Sistem hanya menampilkan 3 rekomendasi.

Recall@3 = 3 / 8 = 0.375
```

Jadi Recall@3 tidak harus 1 karena sistem memang membatasi output maksimal 3 rekomendasi.

Hasil:

```text
Recall@3 = 0.6252
```

Maknanya:

```text
Secara rata-rata, top-3 rekomendasi mencakup sebagian besar objek relevan yang tersedia, tetapi tidak semuanya karena ada batas maksimal 3 rekomendasi.
```

### 12.3 MRR

MRR adalah **Mean Reciprocal Rank**.

MRR menjawab:

```text
Seberapa cepat item relevan muncul di ranking?
```

Rumus per skenario:

```text
Reciprocal Rank = 1 / posisi item relevan pertama
```

Contoh:

```text
Item relevan pertama ada di rank 1:
RR = 1 / 1 = 1.0

Item relevan pertama ada di rank 2:
RR = 1 / 2 = 0.5
```

Rumus total:

```text
MRR = rata-rata Reciprocal Rank seluruh skenario
```

Hasil:

```text
MRR = 0.96
```

Maknanya:

```text
Rekomendasi relevan hampir selalu muncul di posisi paling atas.
```

### 12.4 NDCG@3

NDCG adalah **Normalized Discounted Cumulative Gain**.

NDCG@3 menjawab:

```text
Apakah urutan top-3 mendekati ranking ideal?
```

Rumus DCG@3:

```text
DCG@3 = Σ relevance_i / log2(i + 1)
```

Lalu dinormalisasi:

```text
NDCG@3 = DCG@3 / IDCG@3
```

`IDCG@3` adalah nilai DCG ideal jika ranking sempurna.

Hasil:

```text
NDCG@3 = 0.94
```

Maknanya:

```text
Urutan rekomendasi sangat dekat dengan ranking ideal.
```

---

## 13. Hasil UQ Sample Run

Pada sample run mock model, hasil UQ adalah:

```text
Context Agent:
UDeg = 0.00
Selected CDeg = 1.00
Situation Agreement = 1.00
Intent Agreement = 1.00

Dialogue Agent:
UDeg = 0.00
Selected CDeg = 1.00
grounding_score = 1.00
Final Score = 1.00
```

Interpretasi:

```text
Output sangat stabil karena mock model menghasilkan output yang konsisten.
```

Catatan penting:

```text
Hasil mock model tidak membuktikan bahwa UQ meningkatkan akurasi pada LLM asli.
Hasil ini membuktikan bahwa pipeline UQ dan evaluasi berjalan dengan benar secara struktural.
```

Untuk membuktikan manfaat UQ secara ilmiah, perlu pengujian dengan LLM asli dan perbandingan baseline.

---

## 14. Cara Mengevaluasi UQ Dengan Benar

Evaluasi UQ yang benar bukan hanya melaporkan:

```text
UDeg = 0.12
CDeg = 0.88
```

Yang harus diuji adalah:

```text
Apakah uncertainty tinggi benar-benar berkorelasi dengan output yang salah?
Apakah confidence tinggi benar-benar berkorelasi dengan output yang benar?
Apakah menolak output uncertain membuat akurasi meningkat?
```

### 14.1 Selective Generation

Selective generation adalah strategi:

1. Hitung uncertainty/confidence setiap output.
2. Urutkan output dari paling uncertain ke paling confident.
3. Tolak sebagian output paling uncertain.
4. Hitung akurasi output yang tersisa.

Contoh:

| Rejection Rate | Output Dipakai | Accuracy |
|---:|---:|---:|
| 0% | semua output | 75% |
| 20% | buang 20% paling uncertain | 82% |
| 40% | buang 40% paling uncertain | 90% |

Jika akurasi naik ketika output uncertain dibuang, berarti UQ berguna.

### 14.2 AUARC

AUARC adalah **Area Under Accuracy-Rejection Curve**.

Maknanya:

```text
Semakin tinggi AUARC, semakin baik UQ dalam memilah output benar dan salah.
```

Untuk seminar, cukup jelaskan:

```text
AUARC mengukur apakah strategi menolak output yang uncertain dapat meningkatkan akurasi sistem.
```

---

## 15. Baseline Yang Perlu Dibandingkan

Agar kontribusi UQ kuat, perlu dibandingkan dengan baseline.

Baseline yang cocok:

| Metode | Penjelasan |
|---|---|
| Single generation | Agent hanya dijalankan sekali tanpa UQ. |
| Random sample | Memilih salah satu sample secara acak. |
| Majority vote | Memilih output berdasarkan mayoritas sederhana. |
| CDeg only | Memilih output dengan `CDeg` tertinggi. |
| grounding score only | Memilih output berdasarkan rule grounding saja. |
| CDeg + grounding score | Metode yang digunakan pada Dialogue Agent saat ini. |

Yang ingin dibuktikan:

```text
CDeg + grounding score lebih stabil dan lebih aman daripada single generation.
```

---

## 16. Keterbatasan Saat Ini

Beberapa batasan yang harus dijelaskan saat seminar:

1. **Koordinat 4 objek baru masih placeholder**
   - Badak Heuay, Tagog Anjing, Tari Jaipong, dan Suling Sunda belum memiliki koordinat final dari tim Unity.

2. **Evaluasi masih controlled benchmark**
   - 50 skenario ini kuat untuk menguji sistem secara terkontrol.
   - Namun, tetap perlu Unity live test untuk validasi integrasi nyata.

3. **Mock model menghasilkan output stabil**
   - Karena mock model deterministic, nilai UQ cenderung rendah.
   - Uji dengan LLM asli diperlukan untuk melihat variasi output yang sebenarnya.

4. **Similarity masih lexical/Jaccard**
   - Implementasi saat ini memakai similarity sederhana.
   - Paper *Generating with Confidence* menyarankan NLI entailment untuk semantic similarity yang lebih kuat.

5. **Belum ada AUARC final**
   - Saat ini evaluasi sudah structural dan UQ-ready.
   - Untuk membuktikan manfaat UQ sepenuhnya, perlu selective generation evaluation dan AUARC.

---

## 17. Kalimat Yang Bisa Dipakai Saat Seminar

Berikut beberapa kalimat yang bisa digunakan saat presentasi.

### 17.1 Menjelaskan Kenapa UQ Dipakai

```text
UQ digunakan karena LLM dapat menghasilkan output yang terlihat meyakinkan tetapi tidak stabil. Dengan menjalankan agent beberapa kali dan membandingkan konsistensi outputnya, sistem dapat memilih respons yang paling representatif dan menghindari output yang terlalu uncertain.
```

### 17.2 Menjelaskan Kenapa Hanya Dua Agent

```text
UQ tidak diterapkan ke seluruh sistem, melainkan hanya pada Context Agent dan Dialogue Agent karena dua komponen ini menghasilkan output interpretatif dan generatif. Komponen seperti ranking jarak, filtering visited, dan nav_target tetap deterministic sehingga cukup divalidasi dengan rule-based checks.
```

### 17.3 Menjelaskan CDeg

```text
CDeg atau Confidence Degree mengukur seberapa mirip satu output dengan output lainnya. Jika sebuah output mirip dengan mayoritas sample lain, maka output tersebut dianggap lebih stabil dan lebih layak dipilih.
```

### 17.4 Menjelaskan UDeg

```text
UDeg atau Uncertainty Degree mengukur ketidakpastian keseluruhan. Jika output-output dari beberapa sampling sangat berbeda, maka UDeg meningkat. Jika output-output konsisten, maka UDeg rendah.
```

### 17.5 Menjelaskan grounding score

```text
grounding score digunakan khusus pada Dialogue Agent untuk memastikan dialog tidak hanya stabil, tetapi juga sesuai dengan ContextOutput. Skor ini mengecek apakah opsi UI sesuai, target utama disebut, dan subtitle tetap valid.
```

### 17.6 Menjelaskan Hasil 50 Skenario

```text
Hasil evaluasi menunjukkan bahwa sistem berhasil melewati 50 skenario terkontrol dengan pass rate 100%. Ini menunjukkan bahwa setelah penambahan 8 objek budaya dan integrasi UQ, struktur output, ranking rekomendasi, filtering visited, dan konsistensi dialog tetap berjalan dengan baik.
```

### 17.7 Menjelaskan Batasan

```text
Evaluasi ini belum menggantikan Unity live test. Skenario yang digunakan adalah controlled benchmark untuk menguji reliability dan uncertainty behavior secara sistematis. Validasi akhir tetap perlu dilakukan dengan data runtime Unity.
```

---

## 18. Ringkasan Satu Paragraf

Penelitian ini menerapkan Uncertainty Quantification secara selektif pada Context Agent dan Dialogue Agent dalam sistem Multi-Agent VR Museum Guide. Context Agent menggunakan black-box consistency-based UQ untuk mengukur stabilitas field interpretatif, sedangkan Dialogue Agent menggunakan black-box response similarity UQ, CDeg, dan grounding score untuk memilih dialog yang paling stabil serta tetap sesuai dengan ContextOutput. Evaluasi dilakukan pada 50 skenario terkontrol berbasis 8 objek budaya, dengan variasi posisi player, status visited, dan edge case. Hasil evaluasi menunjukkan pass rate 100%, Precision@3 1.0, MRR 0.96, dan NDCG@3 0.94, yang menunjukkan bahwa sistem tetap reliabel secara struktural setelah penambahan data dan mekanisme UQ. Namun, evaluasi lebih lanjut dengan LLM asli, AUARC, dan Unity live test tetap diperlukan untuk membuktikan peningkatan akurasi akibat UQ secara penuh.

---

## 19. Checklist Belajar Sebelum Seminar

Pastikan bisa menjawab pertanyaan berikut:

- Apa bedanya uncertainty dan confidence?
- Kenapa UQ hanya dipasang pada Context Agent dan Dialogue Agent?
- Apa itu field interpretatif?
- Apa itu `CDeg`?
- Apa itu `UDeg`?
- Apa itu grounding score?
- Kenapa Dialogue Agent tidak cukup hanya memakai CDeg?
- Apa arti pass rate 100%?
- Kenapa Recall@3 tidak harus 1?
- Apa batasan evaluasi 50 skenario?
- Kenapa Unity live test tetap diperlukan?
- Apa langkah berikutnya untuk membuktikan manfaat UQ?

---

## 20. File Penting Dalam Project

File implementasi UQ:

```text
src/agents/context_agent.py
src/agents/dialogue_agent.py
```

File data objek budaya:

```text
data/cultural_sites.json
```

File 50 skenario evaluasi:

```text
evals/scenarios.json
```

File hasil evaluasi terbaru:

```text
evals/results/eval_results_20260602_125029.json
```

Diagram hasil UQ:

```text
docs/figures/uq_result_context_dialogue_agents.png
```

Diagram metodologi UQ:

```text
docs/figures/uq_context_dialogue_agents.png
```
