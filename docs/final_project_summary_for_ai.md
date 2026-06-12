# Final Project Summary for AI Review

Dokumen ini adalah ringkasan final project `my-project` agar dapat dipahami oleh AI lain, reviewer, atau evaluator eksternal tanpa harus membaca seluruh codebase dari awal.

Tanggal ringkasan: 2026-06-02
Project root: `/Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project`
Commit terbaru yang relevan: `fe6fc19 Implement comprehensive agent evaluation suite`
Commit agent redesign: `2d4bcdc Refine context and dialogue agent evaluation flow`

## 1. Ringkasan Singkat

Project ini adalah backend Python untuk sistem **Multi-Agent VR Museum Guide**. Sistem menerima snapshot runtime dari Unity, memilih objek budaya yang belum dikunjungi, mengirim target navigasi ke Unity NavMesh, dan menghasilkan dialog NPC pemandu budaya berbahasa Indonesia.

Arsitektur saat ini adalah **hybrid deterministic + LLM multi-agent system**:

| Komponen | Peran |
|---|---|
| Backend deterministic | Validasi payload, ranking Euclidean, filtering `visited`, session, guardrail, NavMesh dispatch |
| Context Agent | Bounded ReAct context reasoning layer |
| Dialogue Agent | Few-shot persona-based NPC dialogue generator |
| Orchestrator | Mengatur workflow, session, fallback, dan koneksi antar komponen |
| Evaluation suite | Structural checks, LLM judge, faithfulness, reliability, ablation, visualisasi |

Kesimpulan paling penting:

1. Ranking rekomendasi dan `nav_target` **bukan keputusan bebas LLM**. Backend mengunci field kritis tersebut.
2. Context Agent tetap disebut agent karena memakai LLM, ReAct prompting, bounded tools, dan menghasilkan interpretive context fields.
3. Dialogue Agent memakai few-shot prompting dan persona NPC bernama **Arif**.
4. Evaluasi terbaru menunjukkan backend/structural layer kuat, tetapi kualitas persona dan alasan rekomendasi LLM masih perlu ditingkatkan.

## 2. Tujuan Sistem

Sistem dibuat untuk integrasi Unity VR museum budaya. Target runtime:

1. Unity mengirim posisi pemain, scene, timestamp, dan daftar objek budaya.
2. Backend menentukan objek budaya belum dikunjungi yang paling relevan.
3. NPC diarahkan ke target via NavMesh.
4. Dialogue Agent menghasilkan dialog dan UI options.
5. Jika player memilih opsi alternatif, backend mengubah target navigasi ke opsi tersebut.

Unity tetap menjadi **source of truth** untuk:

| Data | Source of truth |
|---|---|
| `timestamp` | Unity request payload |
| `scene` | Unity request payload |
| `playerPosition` | Unity request payload |
| status `visited` | Unity request payload |
| apakah player benar-benar sudah mengunjungi objek | Unity |

Backend tidak otomatis mengubah `visited=true` ketika user memilih rekomendasi. Unity harus mengirim status terbaru pada request `/context/run` berikutnya.

## 3. Stack dan Dependencies

Bahasa dan framework:

| Area | Teknologi |
|---|---|
| Backend | Flask |
| Agent framework | Strands Agents |
| Validation | Pydantic |
| Config | pydantic-settings + `.env` |
| Real LLM provider | OpenRouter-compatible OpenAI API |
| Default model | `openai/gpt-4.1` |
| Mock mode | Custom `MockModel` |
| Evaluation | Python, OpenAI SDK, scikit-learn, matplotlib, numpy, scipy |

Dependencies utama di `pyproject.toml`:

```toml
dependencies = [
    "anthropic>=0.97.0",
    "strands-agents[openai]>=1.36.0",
    "strands-agents-builder>=0.1.10",
    "strands-agents-tools>=0.5.0",
    "openai>=2.33.0",
    "scikit-learn>=1.8.0",
    "matplotlib>=3.10.9",
    "numpy>=2.4.6",
    "scipy>=1.17.1",
]
```

Environment variables penting:

| Variable | Keterangan |
|---|---|
| `USE_MOCK_MODEL` | `true` untuk test lokal tanpa API LLM, `false` untuk real LLM |
| `OPENROUTER_API_KEY` | API key real LLM dan LLM judge |
| `OPENROUTER_BASE_URL` | Default `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Default `openai/gpt-4.1` |
| `PYTHONPATH` | Umumnya diset ke `src` |

## 4. Struktur File Penting

| Path | Fungsi |
|---|---|
| `main.py` | Flask API entrypoint utama |
| `server.py` | FastAPI sample minimal, bukan entrypoint MAS utama |
| `src/schema/models.py` | Pydantic schema request/response/session |
| `src/orchestration/coordinator.py` | Orchestrator, ranking, session, guardrail, fallback |
| `src/agents/context_agent.py` | Context Agent ReAct prompt dan bounded tools |
| `src/agents/dialogue_agent.py` | Dialogue Agent persona Arif, few-shot prompt, subtitle tool |
| `src/core/config.py` | Env config dan fallback mock detection |
| `src/core/mock_model.py` | Mock LLM provider untuk offline testing |
| `src/vr_tools/unity_api.py` | Mock Unity bridge |
| `src/vr_tools/vr_actions.py` | `set_nav_target` dan `show_subtitle` |
| `src/vr_tools/vr_perception.py` | Perception wrappers |
| `data/cultural_sites.json` | Mock registry cultural sites |
| `Multi Agent.postman_collection.json` | Postman collection untuk API |
| `evals/scenarios.json` | 20 skenario evaluasi terbaru |
| `evals/run_agent_evaluation.py` | Evaluation runner terbaru |
| `evals/figures/` | PNG output evaluasi |
| `evals/results/` | JSON output evaluasi |
| `docs/` | Dokumentasi tambahan |

## 5. API Endpoints

Entrypoint: `main.py`
Default server: `http://127.0.0.1:8080`

Run backend mock:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python main.py
```

Run backend real LLM:

```bash
env USE_MOCK_MODEL=false PYTHONPATH=src .venv/bin/python main.py
```

Jika muncul `Address already in use`, port 8080 sedang dipakai proses lain.

### 5.1 `POST /context/run`

Flow utama tahap 1. Unity mengirim runtime snapshot.

Request:

```json
{
  "timestamp": "2026-05-01T12:30:00Z",
  "scene": "Heritage_Museum_Wing_A",
  "playerPosition": "8.0, 2.0, 10.0",
  "culturalSites": [
    {
      "id": "Julang Ngapak",
      "name": "Julang Ngapak",
      "cultural_position": "7.21, 2, 8.7",
      "visited": false
    }
  ]
}
```

Response berisi:

| Field | Keterangan |
|---|---|
| `simulation_id` | Session ID untuk `/dialogue/run` dan `/recommendation/select` |
| `context` | `ContextOutput` final |
| `navmesh_ack` | Ack mock/Unity dispatch |

### 5.2 `POST /dialogue/run`

Flow utama tahap 2. Unity mengirim `simulationId`. Backend mengambil context dari session dan menjalankan Dialogue Agent.

Request:

```json
{
  "simulationId": "..."
}
```

Response berisi:

| Field | Keterangan |
|---|---|
| `spoken_output` | Dialog NPC untuk TTS/lip-sync |
| `subtitle_output` | Subtitle HUD |
| `recommendation_dialogue` | Teks pendek UI |
| `recommendation_options` | Nama objek sebagai tombol UI |

### 5.3 `POST /recommendation/select`

Flow utama tahap 3. User memilih salah satu opsi rekomendasi.

Request:

```json
{
  "simulationId": "...",
  "selectedOption": "Kujang"
}
```

Behavior:

1. Backend memastikan `selectedOption` ada di rekomendasi aktif.
2. Backend mengubah `nav_target` session ke objek terpilih.
3. Backend dispatch NavMesh ke objek terpilih.
4. Dialogue Agent membuat dialog konfirmasi.

### 5.4 Endpoint Tambahan

| Endpoint | Fungsi |
|---|---|
| `GET /user/status` | Mock player status |
| `GET /world/cultural_sites` | Membaca mock registry `data/cultural_sites.json` |
| `PUT /world/cultural_sites` | Mengubah mock registry |
| `POST /run-simulation` | Legacy endpoint context + dialogue sekaligus |

## 6. Schema Utama

### 6.1 `SimulationRequest`

Field:

| Field | Tipe | Keterangan |
|---|---|---|
| `timestamp` | string | Waktu runtime dari Unity |
| `scene` | string | Nama scene Unity |
| `playerPosition` | string | Format `"x, y, z"` |
| `culturalSites` | list | Daftar cultural site live |

Compatibility aliases:

| Alias | Normalized to |
|---|---|
| `cultural_sites` | `culturalSites` |
| `culturalObject` | `culturalSites` |
| `culturalObjects` | `culturalSites` |
| `coordinate` | `cultural_position` |
| `isObjectVisited` | `visited` |

### 6.2 `ContextOutput`

Field final Context Agent:

| Field | Sumber final | Fungsi |
|---|---|---|
| `timestamp` | Backend override dari request | Grounding waktu |
| `scene` | Backend override dari request | Grounding scene |
| `user_action` | LLM jika valid, fallback backend | Interpretasi keadaan pemain |
| `context_summary` | Backend default/override | Ringkasan runtime untuk Dialogue Agent |
| `situation_type` | LLM divalidasi enum/fallback backend | Klasifikasi kondisi |
| `recommendation_reason` | LLM jika grounded, fallback backend | Alasan rekomendasi utama |
| `dialogue_intent` | LLM divalidasi enum/fallback backend | Arahan dialog |
| `recommendations` | Backend ranking otoritatif | Top-3 objek belum dikunjungi |
| `nav_target` | Backend dari rank-1 | Target NavMesh |

Allowed `situation_type`:

```text
multiple_recommendations
single_recommendation
all_sites_visited
exploration_context
```

Allowed `dialogue_intent`:

```text
guide_to_primary_with_alternatives
guide_to_single_primary
no_new_destination
encourage_exploration
```

### 6.3 `DialogueOutput`

Field:

| Field | Fungsi |
|---|---|
| `spoken_output` | Dialog NPC, 2-4 kalimat |
| `subtitle_output` | Subtitle HUD, maksimal 15 kata |
| `recommendation_dialogue` | Teks pendek UI |
| `recommendation_options` | List nama objek budaya |

## 7. Ranking dan Guardrail

Ranking dilakukan di backend, bukan LLM.

Algorithm:

1. Ambil semua site dengan `visited=false`.
2. Hitung Euclidean distance dari `playerPosition` ke `cultural_position`.
3. Sort berdasarkan `(distance, site.name.lower())`.
4. Ambil maksimal 3.
5. Set `nav_target = recommendations[0].id`, atau `""` jika kosong.

Formula jarak:

```text
sqrt((player_x - site_x)^2 + (player_y - site_y)^2 + (player_z - site_z)^2)
```

Guardrail penting:

| Guardrail | Tujuan |
|---|---|
| Backend override `timestamp` dan `scene` | Mencegah LLM mengubah fakta runtime |
| Backend override `recommendations` | Mencegah rekomendasi hallucinated |
| Backend override `nav_target` | Menjaga target navigasi valid |
| Fallback context interpretation | Jika LLM output rusak/tidak grounded |
| Dialogue fallback | Jika output Dialogue Agent gagal parse atau tidak menyebut target utama |
| Selection validation | User hanya boleh memilih opsi yang ada di context |

## 8. Context Agent

File: `src/agents/context_agent.py`

Context Agent adalah bounded ReAct agent. Prompt sudah menggunakan bahasa Indonesia dan tetap mempertahankan teknik ReAct.

Bounded tools:

| Tool | Fungsi |
|---|---|
| `tool_get_runtime_user_status` | Membaca posisi user dari runtime snapshot |
| `tool_get_runtime_cultural_sites` | Membaca daftar cultural sites dari runtime snapshot |
| `tool_get_runtime_recommendations` | Membaca precomputed backend recommendations |

Peran Context Agent:

1. Membaca bounded runtime snapshot.
2. Menghasilkan interpretasi keadaan pemain.
3. Menghasilkan `recommendation_reason`.
4. Menghasilkan `situation_type`.
5. Menghasilkan `dialogue_intent`.
6. Output JSON lengkap sesuai `ContextOutput`.

Namun field kritis tetap dikunci backend.

Catatan penting untuk AI evaluator:

Context Agent tidak boleh dinilai sebagai recommender bebas penuh, karena ranking sudah deterministic. Evaluasi LLM Context Agent harus fokus pada kualitas interpretatif:

| Field | Dimensi evaluasi |
|---|---|
| `user_action` | Natural, spesifik, tidak generik |
| `recommendation_reason` | Grounded, menyebut rank-1, memberi alasan logis |
| `situation_type` | Konsisten dengan jumlah rekomendasi |
| `dialogue_intent` | Konsisten dengan `situation_type` |

## 9. Dialogue Agent

File: `src/agents/dialogue_agent.py`

Dialogue Agent adalah persona NPC bernama **Arif**.

Persona:

| Attribute | Value |
|---|---|
| Name | Arif |
| Role | Pemandu budaya VR |
| Tone | Hangat, ramah, ringkas, meyakinkan |
| Language | Bahasa Indonesia natural |
| Domain | Arsitektur warisan, artefak, tradisi, ruang budaya |

Prompting:

| Teknik | Status |
|---|---|
| Few-shot prompting | Aktif |
| Mode A recommendation synthesis | Aktif |
| Mode B selection confirmation | Aktif |
| JSON-only output | Diinstruksikan |
| Subtitle <= 15 kata | Diinstruksikan dan dievaluasi |

Dialogue Agent memakai field Context Agent berikut:

| Context field | Digunakan untuk |
|---|---|
| `recommendations` | Opsi UI dan target utama |
| `nav_target` | Konsistensi target |
| `situation_type` | Pola dialog |
| `dialogue_intent` | Intensi dialog |
| `recommendation_reason` | Alasan natural dalam `spoken_output` |
| `context_summary` | Teks UI / pengantar |
| `user_action` | Konteks keadaan pemain |

Known weakness dari evaluasi real LLM:

Dialogue Agent sering terlalu netral seperti sistem navigasi. Persona Arif perlu dibuat lebih hangat, apresiatif, dan terasa sebagai pemandu budaya, bukan hanya berkata "mari menuju X".

## 10. Orchestrator

File: `src/orchestration/coordinator.py`

Class utama: `HierarchicalOrchestrator`.

Fungsi:

| Function | Peran |
|---|---|
| `_rank_unvisited_sites` | Ranking deterministic |
| `_default_context_interpretation` | Fallback interpretive context |
| `_merge_context_interpretation` | Menerima LLM interpretation jika grounded |
| `_run_context_agent` | Menjalankan Context Agent |
| `run_context_cycle` | Menjalankan flow `/context/run` |
| `run_dialogue_cycle` | Menjalankan flow `/dialogue/run` |
| `handle_recommendation_selection` | Menangani pilihan user |
| `run_cycle` | Legacy context + dialogue sekaligus |

Session disimpan in-memory di `InMemoryMessagePool.sessions`.

Limitasi:

| Limitasi | Dampak |
|---|---|
| Session in-memory | Hilang jika server restart |
| Belum persistent database | Belum production-ready multi-instance |
| Mock Unity post selalu true | Integrasi real Unity masih perlu adapter HTTP/Unity bridge |

## 11. Mock Model

File: `src/core/mock_model.py`

MockModel digunakan ketika:

```text
USE_MOCK_MODEL=true
```

atau ketika OpenRouter API key tidak valid.

MockModel routing:

| Model ID | Output |
|---|---|
| `mock-context` | ContextOutput JSON |
| `mock-dialogue` | DialogueOutput JSON dinamis |

Mock Dialogue Agent sudah membaca context dan menghasilkan respons berbeda untuk:

| Kondisi | Behavior |
|---|---|
| multiple recommendations | Menyebut target utama dan alternatif |
| single recommendation | Fokus satu target |
| no recommendations | Empty-state dialogue |
| selection confirmation | Konfirmasi selected option |

## 12. Evaluasi Final

Evaluation suite terbaru berada di:

```text
evals/run_agent_evaluation.py
evals/scenarios.json
```

Jumlah skenario dasar: 20.
Expanded total run saat `--agent all`: 25, karena `sc19` reliability dijalankan 5 kali dan `sc20` ablation memiliki 2 run.

Metode evaluasi:

| Layer | Metode |
|---|---|
| Structural correctness | Rule-based deterministic checks |
| Ranking verification | Precision@3, Recall@3, MRR, NDCG@3 |
| Context quality | G-Eval style LLM judge + faithfulness |
| Dialogue quality | G-Eval style LLM judge |
| Safety | Regex technical leak + judge |
| Reliability | pass^k |
| Ablation | Full context vs stripped `recommendation_reason` |
| Visualization | Matplotlib PNG |

Run mock structural:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all --skip-llm-judge
```

Hasil mock structural:

| Metric | Value |
|---|---|
| Total expanded runs | 25 |
| Passed | 25 |
| Overall pass rate | 100% |
| Check pass rate | 100% |
| Reliability pass^5 | 1.0 |

Run real LLM penuh:

```bash
env USE_MOCK_MODEL=false PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all
```

Hasil real LLM terbaru:

| Metric | Value |
|---|---|
| Total expanded runs | 25 |
| Passed | 14 |
| Overall pass rate | 56% |
| Check pass rate | 100% |
| Faithfulness avg | 1.0 |
| Precision@3 | 1.0 |
| Recall@3 | 0.9729 |
| MRR | 0.9583 |
| NDCG@3 | 0.9167 |
| Reliability pass^5 | 1.0 |

Important interpretation:

1. `Check pass rate = 100%` berarti backend, schema, ranking, options order, subtitle length, dan technical leak structural checks stabil.
2. `Overall pass rate = 56%` turun karena LLM judge menilai kualitas generatif belum cukup pada beberapa dimensi.
3. `Faithfulness = 1.0` berarti agent tidak banyak hallucinate nama/site.
4. Kelemahan terbesar adalah `persona_alignment` dan `recommendation_reason_quality`.

LLM judge summary real LLM:

| Dimension | Mean | Interpretation |
|---|---:|---|
| `faithfulness` | 5.0 | Sangat baik |
| `navigation_clarity` | 5.0 | Sangat jelas |
| `technical_leak_safety` | 5.0 | Aman |
| `language_quality` | 4.0 | Baik |
| `context_relevance` | 4.2 | Cukup baik |
| `persona_alignment` | 3.2 | Lemah |
| `recommendation_reason_quality` | 2.33 | Lemah |
| `tool_call_validity` | 1.0 | Metrik perlu trace instrumentation |

Evaluation artifacts:

| Path | Isi |
|---|---|
| `evals/results/eval_results_20260601_153838.json` | Hasil real LLM full eval terbaru |
| `evals/figures/01_deterministic_check_pass_rate.png` | Pass rate structural checks |
| `evals/figures/02_dialogue_agent_radar.png` | Radar Dialogue Agent |
| `evals/figures/03_context_agent_radar.png` | Radar Context Agent |
| `evals/figures/04_scenario_metric_heatmap.png` | Heatmap scenario vs metrics |
| `evals/figures/05_reliability_boxplot.png` | Reliability score boxplot |
| `evals/figures/06_ablation_delta.png` | Ablation delta |
| `evals/figures/07_ir_metrics_summary.png` | IR ranking metrics |

## 13. Failed Real-LLM Evaluation Patterns

Skenario yang gagal bukan karena backend rusak. Penyebab utamanya:

| Pattern | Detail |
|---|---|
| Context reason terlalu generik | `recommendation_reason` sering hanya menyebut "kandidat teratas", bukan alasan natural |
| Persona Arif kurang kuat | Dialog terdengar seperti sistem navigasi, bukan pemandu budaya hangat |
| Near-end exploration kurang apresiatif | Saat 4 dari 5 site sudah visited, dialog belum mengakui progres player |
| Tool trajectory check belum punya trace asli | Runner belum mengakses trace Strands tool call asli, sehingga `tool_call_validity` rendah |
| Ablation hypothesis tidak confirmed | `recommendation_reason` belum cukup kuat untuk menaikkan semua kualitas dialog |

Secara akademik, ini justru berguna: evaluasi baru berhasil membedakan antara **system correctness** dan **LLM quality**.

## 14. Rekomendasi Perbaikan Berikutnya

Prioritas 1: perbaiki Dialogue Agent persona.

Target:

| Masalah | Perbaikan |
|---|---|
| Dialog terlalu netral | Tambahkan instruksi warmth dan contoh few-shot yang lebih ekspresif |
| Tidak terasa sebagai Arif | Tambahkan signature style tanpa berlebihan |
| Near-end exploration gagal | Tambahkan aturan: jika banyak visited dan hanya satu tersisa, apresiasi progres |

Prioritas 2: perbaiki `recommendation_reason`.

Target:

| Masalah | Perbaikan |
|---|---|
| Alasan terlalu generik | Ubah fallback backend agar menyebut alasan proximity/top candidate secara natural |
| Tidak membantu Dialogue Agent | Buat reason lebih user-facing dan tidak teknis |
| Ablation tidak confirmed | Pastikan reason membawa informasi yang benar-benar dipakai dialogue |

Prioritas 3: instrument ReAct tool trace.

Target:

| Masalah | Perbaikan |
|---|---|
| `tool_call_validity=1` | Tambahkan logging trace tool calls dari Context Agent |
| Evaluasi trajectory best-effort | Simpan trace di result atau MessagePool metadata |
| Skripsi butuh bukti ReAct | Export tool call sequence untuk `sc18` |

## 15. Cara Cepat untuk AI Lain Memahami Project

Jika AI lain hanya punya waktu singkat, baca file ini dan file berikut:

| File | Mengapa penting |
|---|---|
| `src/schema/models.py` | Kontrak data semua agent/API |
| `src/orchestration/coordinator.py` | Alur sebenarnya dan guardrail |
| `src/agents/context_agent.py` | Prompt dan tools Context Agent |
| `src/agents/dialogue_agent.py` | Prompt dan persona Dialogue Agent |
| `evals/run_agent_evaluation.py` | Evaluasi final |
| `evals/scenarios.json` | Dataset evaluasi |
| `evals/results/eval_results_20260601_153838.json` | Hasil evaluasi real LLM terbaru |

## 16. Key Claims yang Aman Dipakai

Claim yang didukung code dan evaluasi:

1. Sistem adalah hybrid MAS dengan dua LLM agents dan deterministic orchestrator.
2. Context Agent adalah bounded ReAct context reasoning agent, bukan recommender bebas penuh.
3. Dialogue Agent adalah few-shot persona NPC generator.
4. Ranking dan navigation target dikunci backend.
5. Structural correctness sudah lulus 100% pada evaluation suite terbaru.
6. Real LLM evaluation menunjukkan faithfulness dan navigation clarity kuat.
7. Real LLM evaluation menunjukkan persona alignment dan recommendation reason quality masih perlu diperbaiki.
8. IR metrics mengukur deterministic backend correctness, bukan kualitas LLM.

Claim yang tidak boleh dibuat:

1. Jangan klaim LLM menentukan ranking akhir secara bebas.
2. Jangan klaim sistem production-ready multi-instance.
3. Jangan klaim ReAct trajectory sudah tervalidasi penuh tanpa trace instrumentation.
4. Jangan klaim persona Arif sudah optimal, karena judge menilai masih lemah.
5. Jangan klaim ablation membuktikan `recommendation_reason` selalu meningkatkan dialogue, karena hypothesis belum confirmed.

## 17. Final Mental Model

Sistem ini paling akurat dipahami sebagai:

```text
Unity runtime snapshot
  -> Flask API
  -> deterministic validation + Euclidean recommendation ranking
  -> Context Agent for grounded interpretive context
  -> backend guardrail/override for critical fields
  -> NavMesh target dispatch
  -> Dialogue Agent for persona-based Indonesian NPC speech
  -> subtitle/UI output
  -> optional recommendation selection retargeting
  -> evaluation suite separating backend correctness from LLM quality
```

Project saat ini sudah kuat sebagai prototype akademik untuk menunjukkan MAS berbasis agent di VR museum guide. Bagian yang paling matang adalah backend correctness dan integrasi workflow. Bagian yang paling perlu ditingkatkan untuk kualitas akhir adalah persona Dialogue Agent, richness `recommendation_reason`, dan ReAct tool trajectory instrumentation.
