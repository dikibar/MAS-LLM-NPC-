# Metodologi Evaluasi Agent

Dokumen ini menjelaskan rancangan evaluasi untuk sistem multi-agent VR museum:

- Context Agent: membaca snapshot Unity dan menghasilkan context rekomendasi.
- Dialogue Agent: mengubah context menjadi dialog NPC, subtitle, dan opsi UI.
- Orchestrator: menghubungkan Context Agent, NavMesh dispatch, Dialogue Agent, dan selection flow.

## Apakah Evaluasi Sudah Ada?

Sebelum rancangan ini, project belum memiliki evaluasi operasional untuk masing-masing agent. Di prompt agent memang ada bagian `EVOLUTION`, tetapi itu hanya instruksi refleksi, belum berupa evaluator, dataset skenario, metrik, atau runner otomatis.

Evaluasi yang ditambahkan berada di folder `evals/`:

- `evals/scenarios.json` sebagai test collection.
- `evals/run_agent_evaluation.py` sebagai runner evaluasi offline.
- `evals/README.md` sebagai panduan eksekusi.

## Dasar Literatur

1. ReAct: Synergizing Reasoning and Acting in Language Models

   ReAct menggabungkan reasoning trace dan action/tool use secara berselang-seling. Karena agent tidak hanya menghasilkan teks akhir, evaluasi perlu memperhatikan apakah agent menggunakan informasi dan aksi dengan benar, bukan sekadar melihat output akhir.

2. TRAJECT-Bench: A Trajectory-Aware Benchmark for Evaluating Agentic Tool Use

   TRAJECT-Bench menekankan bahwa evaluasi agent tool-use sebaiknya memeriksa trajectory: pemilihan tool, parameter/argument correctness, serta urutan/dependency. Ini relevan untuk Context Agent karena prompt mewajibkan penggunaan bounded tools dalam pola ReAct.

3. Evaluating Recommender Systems: Survey and Framework

   Literatur recommender system menggunakan metrik seperti Precision@k, Recall@k, MRR, dan NDCG untuk menilai kualitas ranking. Context Agent menghasilkan ranking top-3 cultural sites, sehingga metrik ranking ini cocok sebagai pengukuran objektif.

4. Evaluating Conversational Recommender Systems: A Landscape of Research

   Sistem conversational recommender bersifat multi-komponen. Evaluasinya tidak cukup hanya recommendation accuracy; perlu mengukur kualitas komponen, kualitas percakapan, usability, dan persepsi pengguna. Ini cocok dengan sistem VR Anda karena rekomendasi disampaikan melalui NPC dan UI.

5. G-Eval dan LLM-as-a-Judge/MT-Bench

   G-Eval mendukung rubric-based evaluation untuk natural language generation, sedangkan MT-Bench menunjukkan strong LLM judge dapat mendekati human preference pada konteks dialog terbuka. Namun keduanya juga punya risiko bias, sehingga di project ini LLM judge disarankan sebagai pelengkap, bukan satu-satunya dasar evaluasi.

6. USR dan FED untuk evaluasi dialog

   USR dan FED menunjukkan bahwa metrik overlap seperti BLEU/ROUGE kurang cocok untuk dialog. Evaluasi dialog sebaiknya melihat relevansi, naturalness, coherence, consistency, dan kualitas fine-grained lain.

## Prinsip Desain Evaluasi

Rancangan ini menggunakan hybrid evaluation:

- Bagian objektif dinilai deterministic.
- Bagian bahasa/dialog dinilai dengan rule-based checks dan dapat diperluas dengan LLM-as-a-judge.
- Sistem keseluruhan dinilai melalui scenario-based end-to-end evaluation.
- Evaluasi pengguna tetap disarankan untuk validasi VR karena kualitas pengalaman tidak bisa sepenuhnya diwakili metrik offline.

## Evaluasi Context Agent

Context Agent paling cocok dievaluasi dengan metrik objektif karena output yang benar dapat dihitung dari request Unity.

Input yang digunakan:

- `timestamp`
- `scene`
- `playerPosition`
- `culturalSites`
- `visited`

Gold answer dihitung dengan langkah berikut:

1. Ambil semua cultural site dengan `visited=false`.
2. Hitung Euclidean distance dari `playerPosition` ke `cultural_position`.
3. Urutkan berdasarkan jarak terdekat.
4. Jika jarak sama, gunakan tie-breaker nama lowercase, sesuai implementasi backend saat ini.
5. Ambil maksimal 3 item.
6. `nav_target` harus sama dengan `id` rank-1.

Metrik:

- `Schema Validity Rate`: output harus valid terhadap `ContextOutput`.
- `Grounding Accuracy`: `timestamp` dan `scene` harus sama dengan request.
- `Visited Filter Accuracy`: rekomendasi tidak boleh mengandung item `visited=true`.
- `Ranking Exact Match`: urutan `id` output harus sama dengan gold ranking.
- `Top-1/Nav Target Accuracy`: `nav_target` harus sama dengan rank-1.
- `Precision@3`: proporsi rekomendasi top-3 yang benar.
- `Recall@3`: proporsi gold relevant top-3 yang ditemukan.
- `MRR`: posisi relevant pertama; penting karena rank-1 dipakai NavMesh.
- `NDCG@3`: kualitas urutan ranking dengan discount untuk posisi lebih rendah.

Alasan:

Context Agent bukan agent kreatif. Ia bertugas menjaga akurasi state dan rekomendasi spasial. Karena itu, evaluasi deterministic lebih valid dibanding meminta LLM judge menilai benar/salah.

## Evaluasi Dialogue Agent

Dialogue Agent menghasilkan bahasa natural, jadi evaluasinya perlu menggabungkan checks objektif dan rubric-based judgement.

Checks objektif yang sudah diimplementasikan:

- Output valid terhadap `DialogueOutput`.
- `recommendation_options` sama persis dengan urutan `context.recommendations.name`.
- `subtitle_output` maksimal 15 kata.
- Teks user-facing tidak membocorkan koordinat, nama tool, istilah backend, atau NavMesh.
- Jika ada rekomendasi, rank-1 harus disebut di spoken output atau subtitle.
- Dalam mode selection, selected option harus disebut di spoken output dan subtitle.

Rubrik LLM-as-a-judge yang disarankan:

Berikan input berupa context JSON dan dialogue output. Nilai setiap dimensi 1-5.

- Relevansi terhadap context: dialog membahas rekomendasi aktual.
- Faithfulness: tidak mengarang detail budaya yang tidak tersedia.
- Clarity: pemain paham tujuan berikutnya.
- Persona alignment: gaya Arif hangat, ringkas, dan membantu.
- Bahasa Indonesia: natural, tidak kaku, tidak campur Inggris.
- UI usefulness: `recommendation_dialogue` membantu pemain memilih.
- Safety/Privacy: tidak menampilkan koordinat, ID teknis, tool, atau token sistem.

Alasan:

Dialog NPC tidak memiliki satu jawaban referensi tunggal. Dua dialog yang berbeda bisa sama-sama baik. Karena itu, BLEU/ROUGE tidak cocok; rubric-based evaluation lebih sesuai.

## Evaluasi End-to-End

End-to-end evaluation menguji apakah satu skenario berhasil melewati flow:

1. Request Unity valid.
2. Context Agent menghasilkan rekomendasi benar.
3. NavMesh target sesuai rank-1 atau kosong jika tidak ada rekomendasi.
4. Dialogue Agent menghasilkan opsi UI sesuai context.
5. Selection flow menerima opsi valid dan menolak opsi invalid.

Metrik:

- `end_to_end_success_rate`
- total check pass rate
- failure categories per scenario
- latency, jika nanti ditambahkan instrumentation runtime

Alasan:

Sistem Anda adalah pipeline interaktif. Komponen yang terlihat benar secara terpisah bisa tetap gagal saat digabungkan, misalnya context benar tetapi opsi dialogue tidak sinkron, atau selection menerima pilihan yang tidak aktif.

## Skenario Yang Disediakan

`evals/scenarios.json` mencakup:

- tiga situs belum dikunjungi dengan ranking jarak normal;
- situs terdekat tetapi sudah visited;
- hanya satu situs tersisa;
- semua situs sudah visited;
- tie distance dengan tie-break nama;
- payload compatibility `culturalObject`, `coordinate`, dan `isObjectVisited`;
- selected option invalid.

Skenario ini dapat diperluas dengan:

- scene berbeda;
- koordinat negatif;
- posisi player sangat dekat target;
- cultural site dengan nama mirip;
- jumlah site lebih dari 3;
- data Unity yang tidak valid;
- simulasi beberapa tick berturut-turut.

## Interpretasi Hasil

Context score rendah biasanya berarti masalah serius karena gold answer objektif. Contoh:

- `visited=true` masih muncul berarti filter gagal.
- `nav_target` tidak sama rank-1 berarti NPC bisa berjalan ke objek salah.
- `ranking_exact_match` gagal berarti rekomendasi spasial tidak sesuai kontrak.

Dialogue score rendah perlu dibaca lebih kualitatif. Contoh:

- `primary_option_mentioned` gagal berarti dialog tidak cukup mengarahkan pemain.
- `options_match_context_order` gagal berarti UI bisa tidak sinkron dengan navigasi.
- `no_internal_tokens_or_coordinates` gagal berarti ada kebocoran detail teknis ke pemain.

End-to-end failure berarti skenario perlu dicek sebagai alur, bukan hanya satu agent.

## Rekomendasi Untuk Skripsi

Gunakan tiga lapis evaluasi:

1. Offline deterministic evaluation untuk membuktikan akurasi Context Agent.
2. Rule-based + rubric LLM-as-a-judge untuk menilai Dialogue Agent.
3. User study kecil di Unity/VR untuk menilai usability, clarity, dan pengalaman navigasi.

Untuk laporan, pisahkan hasil per agent:

- Context Agent: laporkan Precision@3, Recall@3, MRR, NDCG@3, nav_target accuracy, visited filter accuracy.
- Dialogue Agent: laporkan format validity, option consistency, subtitle compliance, no-leak rate, dan skor rubrik.
- System: laporkan end-to-end success rate, selection success/rejection, dan observasi user study.

Dengan struktur ini, evaluasi menjadi lebih kuat karena setiap agent dinilai sesuai tugasnya: Context Agent dinilai secara objektif, Dialogue Agent dinilai berdasarkan kualitas komunikasi, dan sistem VR dinilai berdasarkan keberhasilan interaksi.
