# Agent Evaluation

Folder ini berisi evaluasi offline untuk sistem multi-agent VR:

- `scenarios.json`: kumpulan skenario input Unity dan pilihan rekomendasi.
- `run_agent_evaluation.py`: runner evaluasi deterministic/rule-based.

Jalankan dari root project:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py
```

Perintah default menjalankan LLM judge pada seluruh skenario terpilih dan bersifat
fail-closed. Untuk evaluasi struktural tanpa API judge, gunakan:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python \
  evals/run_agent_evaluation.py --skip-llm-judge
```

Evaluasi per agent:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent e2e
```

Output JSON untuk analisis lanjutan:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --json
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context --json
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue --json
```

## Metrik Utama

Context Agent:

- `schema_valid`: output valid sesuai `ContextOutput`.
- `timestamp_matches_request` dan `scene_matches_request`: output grounded ke request Unity.
- `no_visited_sites_recommended`: objek `visited=true` tidak boleh muncul.
- `ranking_exact_match`: urutan rekomendasi sama dengan ranking Euclidean distance backend.
- `nav_target_matches_rank_1`: target NavMesh sama dengan rekomendasi rank-1.
- `Precision@3`, `Recall@3`, `MRR`, `NDCG@3`: kualitas ranking top-3.

Dialogue Agent:

- `schema_valid`: output valid sesuai `DialogueOutput`.
- `options_match_context_order`: opsi UI sama dengan rekomendasi context.
- `subtitle_max_15_words`: subtitle sesuai constraint HUD.
- `no_internal_tokens_or_coordinates`: teks user-facing tidak membocorkan koordinat, tool, backend, atau NavMesh.
- `primary_option_mentioned`: dialog/subtitle mengarahkan pemain ke rank-1.
- `selected_option_mentioned`: mode selection wajib menyebut pilihan pemain.

End-to-end:

- `end_to_end_success`: request valid, context valid, dialogue valid, dan selection behavior sesuai skenario.

## LLM-as-a-Judge

LLM-as-a-Judge hanya menilai output Dialogue Agent, yaitu dialog yang benar-benar
didengar/dibaca pemain (`spoken_output`, `subtitle_output`, `recommendation_dialogue`,
`recommendation_options`). Context Agent tidak pernah menjadi candidate under test;
kualitasnya diverifikasi lewat deterministic checks dan UQ metrics di atas, bukan lewat
skor subjektif LLM judge. Ini berlaku untuk seluruh skenario, termasuk skenario yang
`focus`-nya `context_agent` — context_output dari skenario tersebut hanya dipakai sebagai
`grounding_reference` (sumber fakta pembanding), bukan yang dinilai.

Evaluator judge menggunakan satu panggilan batch per skenario untuk seluruh dimensi
yang relevan. Secara default, semua skenario yang dipilih dinilai:

```bash
env USE_MOCK_MODEL=false PYTHONPATH=src .venv/bin/python \
  evals/run_agent_evaluation.py --judge-coverage all
```

Pilihan coverage:

- `all`: nilai seluruh skenario terpilih;
- `configured`: hanya skenario dengan `llm_judge=true`;
- `none`: evaluasi deterministic saja.

Konfigurasi judge dipisahkan dari model agent:

```dotenv
OPENROUTER_MODEL=gpt-5-mini
JUDGE_MODEL=gpt-5.4
JUDGE_MAX_RETRIES=3
```

Judge menerima request dan expected output sebagai reference, menggunakan output
JSON terstruktur, memvalidasi skor 1-5, menyimpan reasoning dan raw response, serta
melakukan retry untuk respons invalid. Status `skipped` atau `error` tidak dianggap
lulus ketika judge diwajibkan.

Kelulusan judge membutuhkan:

- weighted overall score minimal 4.0;
- `grounded_response_correctness >= 4`;
- `faithfulness >= 4`;
- `technical_leak_safety = 5`.

Ringkasan `judge_execution` melaporkan coverage skenario/dimensi, status error, dan
pass rate. Jika model agent dan judge sama, hasil memuat warning self-preference.

### Validasi Diskriminatif Judge

Jalankan benchmark output bersih versus output yang sengaja dirusak:

```bash
PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py \
  --judge-validation-only --json
```

Dataset `judge_validation_cases.json` mencakup clean controls, target yang salah,
hallucination, technical leak, dan prompt injection. Benchmark melaporkan accuracy,
clean-pass sensitivity, corruption-rejection specificity, dan confusion matrix.

### Kalibrasi Dengan Penilai Manusia

Gunakan format pada `human_annotations.example.json`, lalu jalankan:

```bash
PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py \
  --human-annotations evals/human_annotations.json
```

Output menghitung exact agreement, within-one agreement, quadratic weighted Cohen's
kappa, dan korelasi Spearman. Agreement hanya dilaporkan jika anotasi benar-benar
tersedia; evaluator tidak mengklaim kalibrasi manusia secara otomatis.

## Validasi UQ Dengan Kasus Gagal

Lima puluh skenario utama dapat seluruhnya benar sehingga error-detection AUROC
tidak bisa dihitung. Gunakan benchmark terpisah berikut untuk menghasilkan kelas
benar dan salah secara terkontrol:

```bash
env USE_MOCK_MODEL=false \
  CONTEXT_UQ_SAMPLES=3 \
  DIALOGUE_UQ_SAMPLES=3 \
  PYTHONPATH=src \
  .venv/bin/python evals/run_agent_evaluation.py \
  --uq-failure-validation \
  --agent all \
  --skip-llm-judge
```

Benchmark berada di `evals/uq_failure_scenarios.json` dan terdiri dari:

- 5 clean controls untuk Context Agent;
- 5 controlled failures untuk Context Agent;
- 5 clean controls untuk Dialogue Agent;
- 5 controlled failures untuk Dialogue Agent.

Controlled failure diterapkan hanya di evaluator, sebelum perhitungan CDeg/UDeg.
Kode produksi dan 50 skenario utama tidak dimodifikasi. Gangguan mencakup respons
antarsampel yang menyimpang, kebocoran koordinat/istilah internal, subtitle terlalu
panjang, dan HUD output yang tidak aman.

Output penting:

- `error_detection_auroc`: kemampuan UDeg memisahkan output benar dan salah;
- `mean_udeg_correct` dan `mean_udeg_incorrect`;
- `mean_udeg_gap`: selisih rata-rata UDeg salah terhadap benar;
- `mann_whitney_greater_p`: pengujian apakah UDeg output salah lebih tinggi;
- `benchmark_threshold`: ambang UDeg dengan balanced accuracy terbaik pada
  benchmark, beserta sensitivity dan specificity;
- `expected_label_agreement`: memastikan injeksi menghasilkan label yang dirancang;
- `validation_confirmed`: true jika kedua kelas tersedia, AUROC minimal 0.70,
  UDeg error lebih tinggi, dan label benchmark konsisten.

Gambar disimpan sebagai:

```text
evals/figures/09_uq_error_detection.png
```

Catatan metodologis: controlled corruption membuktikan sensitivitas UQ terhadap
gangguan yang diketahui. Hasil ini perlu dilengkapi dengan natural-error benchmark
dari beberapa run model nyata; controlled failure tidak boleh diklaim sebagai bukti
tunggal bahwa seluruh kegagalan alami akan selalu terdeteksi. Nilai
`benchmark_threshold` juga diturunkan dari benchmark yang sama, sehingga belum
merupakan threshold produksi yang telah dikalibrasi pada data independen.
