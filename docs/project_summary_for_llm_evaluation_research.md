# Project Summary Untuk Riset Evaluasi LLM Multi-Agent

Dokumen ini disiapkan sebagai briefing lengkap untuk meminta bantuan riset kepada Claude atau model lain tentang **metode evaluasi LLM/agent yang paling cocok** untuk dua agent dalam project ini: **Context Agent** dan **Dialogue Agent**.

Tujuan utama briefing ini adalah memberi konteks project secara menyeluruh agar rekomendasi evaluasi yang diberikan nanti tidak generik, tetapi sesuai dengan desain sistem, peran masing-masing agent, tipe output, risiko failure, dan kebutuhan penelitian/skripsi.

---

## 1. Identitas Project

Project ini adalah backend Python untuk sistem **multi-agent NPC guide dalam simulasi VR museum/heritage cultural environment**.

Secara konseptual, project ini membuat NPC pemandu budaya yang dapat:

1. Membaca kondisi runtime dari Unity/VR.
2. Mengetahui posisi player.
3. Menerima daftar objek/situs budaya beserta koordinat dan status `visited`.
4. Merekomendasikan objek budaya yang belum dikunjungi berdasarkan jarak.
5. Mengirim target navigasi ke Unity NavMesh.
6. Menghasilkan dialog NPC berbahasa Indonesia untuk pemain.
7. Menampilkan subtitle dan opsi rekomendasi pada UI.
8. Menangani pilihan pemain terhadap salah satu rekomendasi.

Project berada di:

```text
/Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project
```

Runtime utama saat ini memakai:

```text
Python >= 3.11
Flask
Pydantic
Strands Agents
OpenRouter-compatible OpenAIModel
MockModel fallback untuk evaluasi lokal
```

Catatan penting:

- `main.py` adalah entry point Flask utama.
- `server.py` hanya contoh FastAPI minimal dan bukan runtime utama saat ini.
- `README.md` project masih kosong.
- Integrasi Unity saat ini masih mock/local bridge, belum benar-benar HTTP call ke Unity runtime.

---

## 2. Struktur File Penting

```text
my-project/
  main.py
  server.py
  pyproject.toml
  uv.lock
  data/
    cultural_sites.json
  src/
    agents/
      context_agent.py
      dialogue_agent.py
      __init__.py
    orchestration/
      coordinator.py
      __init__.py
    schema/
      models.py
      __init__.py
    core/
      config.py
      mock_model.py
      __init__.py
    vr_tools/
      unity_api.py
      vr_actions.py
      vr_perception.py
      __init__.py
  evals/
    scenarios.json
    run_agent_evaluation.py
    dialogue_llm_judge_rubric.md
    README.md
  docs/
    evaluation_methodology.md
    project_summary_for_llm_evaluation_research.md
```

Peran file utama:

- `main.py`: Flask API endpoint untuk flow live.
- `src/schema/models.py`: definisi Pydantic untuk request, response, context output, dialogue output, session state.
- `src/orchestration/coordinator.py`: orchestrator utama yang menjalankan Context Agent, Dialogue Agent, NavMesh dispatch, dan session management.
- `src/agents/context_agent.py`: definisi Context Agent, bounded tools, dan system prompt ReAct.
- `src/agents/dialogue_agent.py`: definisi Dialogue Agent, persona NPC, tool subtitle, dan system prompt dialog.
- `src/vr_tools/unity_api.py`: mock client untuk Unity bridge.
- `src/core/config.py`: konfigurasi env, OpenRouter, mock mode.
- `src/core/mock_model.py`: model mock agar sistem bisa diuji tanpa LLM API.
- `evals/run_agent_evaluation.py`: evaluator offline yang sudah dibuat untuk per-agent dan end-to-end.
- `evals/scenarios.json`: kumpulan skenario evaluasi offline.
- `evals/dialogue_llm_judge_rubric.md`: template awal rubrik LLM-as-a-judge untuk Dialogue Agent.
- `docs/evaluation_methodology.md`: dokumen metodologi evaluasi awal berdasarkan paper.

---

## 3. Flow API Utama

Runtime utama terdapat di `main.py` dan menggunakan Flask.

Endpoint utama:

### 3.1 `POST /context/run`

Tahap pertama flow. Unity mengirim snapshot runtime:

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

Compatibility aliases yang diterima:

- `cultural_sites` -> `culturalSites`
- `culturalObject` -> `culturalSites`
- `culturalObjects` -> `culturalSites`
- `coordinate` -> `cultural_position`
- `isObjectVisited` -> `visited`

Response:

```json
{
  "status": "success",
  "message": "Context agent executed successfully",
  "data": {
    "simulation_id": "...",
    "context": {
      "timestamp": "...",
      "scene": "...",
      "user_action": "...",
      "recommendations": [
        {
          "rank": 1,
          "id": "...",
          "name": "...",
          "cultural_position": "..."
        }
      ],
      "nav_target": "..."
    },
    "navmesh_ack": true
  }
}
```

### 3.2 `POST /dialogue/run`

Tahap kedua flow. Unity/backend mengirim `simulationId` dari `/context/run`.

Request:

```json
{
  "simulationId": "..."
}
```

Response:

```json
{
  "status": "success",
  "message": "Dialogue agent executed successfully",
  "data": {
    "simulation_id": "...",
    "dialogue": {
      "spoken_output": "...",
      "subtitle_output": "...",
      "recommendation_dialogue": "...",
      "recommendation_options": ["..."]
    }
  }
}
```

### 3.3 `POST /recommendation/select`

Tahap ketiga flow. Pemain memilih salah satu opsi rekomendasi.

Request:

```json
{
  "simulationId": "...",
  "selectedOption": "Kujang"
}
```

Response:

```json
{
  "status": "success",
  "message": "Recommendation option selected successfully",
  "data": {
    "selected_option": "Kujang",
    "selected_site_id": "Kujang",
    "navmesh_ack": true,
    "spoken_output": "Baik, saya akan memandu Anda menuju Kujang...",
    "subtitle_output": "Mari menuju Kujang."
  }
}
```

### 3.4 `POST /run-simulation`

Endpoint legacy yang menjalankan context + dialogue sekaligus. Untuk integrasi baru, flow yang direkomendasikan adalah:

```text
/context/run -> /dialogue/run -> /recommendation/select
```

---

## 4. Model Data dan Schema

Schema ada di `src/schema/models.py`.

### 4.1 `SimulationRequest`

Digunakan oleh `/context/run` dan `/run-simulation`.

Field:

```text
timestamp: str
scene: str
playerPosition: str
culturalSites: List[CulturalSite]
```

Validasi:

- `timestamp` tidak boleh kosong.
- `scene` tidak boleh kosong.
- `playerPosition` harus format `"x, y, z"`.
- `playerPosition` harus numerik.
- Payload legacy/alias dinormalisasi ke `culturalSites`.

### 4.2 `CulturalSite`

Field:

```text
id: str
name: str
cultural_position: str
visited: bool = False
```

Validasi:

- `id`, `name`, `cultural_position` tidak boleh kosong.
- `cultural_position` harus format `"x, y, z"`.
- Koordinat harus numerik.

### 4.3 `SiteRecommendation`

Output rekomendasi yang dipakai Context Agent.

```text
rank: int
id: str
name: str
cultural_position: str
```

### 4.4 `ContextOutput`

Output utama Context Agent.

```text
timestamp: str
scene: str
user_action: str
recommendations: List[SiteRecommendation]
nav_target: str
```

Makna:

- `recommendations` berisi maksimal 3 situs budaya belum dikunjungi.
- `nav_target` harus sama dengan `id` rekomendasi rank-1.
- Jika tidak ada rekomendasi, `recommendations=[]` dan `nav_target=""`.

### 4.5 `DialogueOutput`

Output utama Dialogue Agent.

```text
spoken_output: str
subtitle_output: str
recommendation_dialogue: str
recommendation_options: List[str]
```

Makna:

- `spoken_output`: ucapan NPC 2-4 kalimat.
- `subtitle_output`: subtitle HUD maksimal 15 kata.
- `recommendation_dialogue`: teks pendek untuk UI rekomendasi.
- `recommendation_options`: nama objek budaya yang bisa dipilih pemain, urut sesuai recommendations.

### 4.6 `SimulationSessionState`

Session disimpan in-memory oleh orchestrator.

```text
simulation_id: str
player_position: str
cultural_sites: CulturalSitesPayload
context: ContextOutput
dialogue: Optional[DialogueOutput]
```

Konsekuensi:

- `simulation_id` hanya valid selama proses server hidup.
- Jika server restart, session hilang.
- `/dialogue/run` dan `/recommendation/select` bergantung pada session dari `/context/run`.

---

## 5. Orchestrator dan Algoritma Ranking

File: `src/orchestration/coordinator.py`

Class utama:

```text
HierarchicalOrchestrator
```

Workflow:

1. Terima `SimulationRequest`.
2. Parse `playerPosition`.
3. Bentuk `EnvironmentSnapshot`.
4. Bentuk `UserStatusSnapshot`.
5. Bentuk `CulturalSitesPayload`.
6. Hitung ranking situs yang belum dikunjungi.
7. Jalankan Context Agent.
8. Override output Context Agent agar `timestamp`, `scene`, `recommendations`, dan `nav_target` tetap sesuai backend-computed data.
9. Publish context ke Message Pool.
10. Dispatch `nav_target` ke Unity NavMesh.
11. Simpan session dengan `simulation_id`.
12. Jalankan Dialogue Agent berdasarkan context JSON.
13. Publish dialogue ke Message Pool.
14. Dispatch subtitle ke Unity HUD.
15. Jika pemain memilih rekomendasi, update `nav_target` sesuai pilihan dan generate confirmation dialogue.

### 5.1 Ranking Logic

Ranking dilakukan secara deterministic di backend, bukan sepenuhnya oleh LLM.

Pseudo-code:

```text
unvisited_sites = [site for site in sites if not site.visited]
ranked_sites = sort by:
  1. Euclidean distance from playerPosition to site.cultural_position
  2. site.name.lower() as tie-breaker
take top 3
```

Distance:

```text
sqrt((ax - bx)^2 + (ay - by)^2 + (az - bz)^2)
```

Implikasi untuk evaluasi:

- Context Agent dapat dievaluasi secara objektif.
- Gold answer dapat dihitung dari input.
- Ranking correctness, nav_target accuracy, visited filtering, dan top-k metrics sangat relevan.

---

## 6. Context Agent

File: `src/agents/context_agent.py`

Peran:

```text
Context Agent — Environmental State Engine
```

Tugas utama:

1. Membaca snapshot runtime request yang sudah disiapkan backend.
2. Memahami posisi player.
3. Membaca daftar cultural sites dan flag `visited`.
4. Membaca `precomputed_recommendations` dari backend.
5. Menghasilkan satu objek JSON `ContextOutput`.
6. Tidak membuat ranking baru sendiri.
7. Tidak mengarang data di luar snapshot.
8. Tidak membuat dialog atau lore budaya.

### 6.1 Bounded Tools

Context Agent memiliki bounded tools:

```text
tool_get_runtime_user_status()
tool_get_runtime_cultural_sites()
tool_get_runtime_recommendations()
```

Tool-tool ini hanya membaca `_RUNTIME_SNAPSHOT` dalam memori, bukan file eksternal, bukan Unity langsung, dan bukan sumber data lain.

### 6.2 ReAct Prompt Structure

System prompt Context Agent menggunakan struktur ReAct yang sudah diterjemahkan ke bahasa Indonesia, tetapi label teknis tetap dipertahankan:

```text
Reasoning 1
Action 1
Observation 1
Reasoning 2
Action 2
Observation 2
Reasoning 3
Action
Observation
```

Intent ReAct:

- Reasoning: pahami bahwa semua data valid berasal dari bounded tools.
- Action: panggil tool runtime.
- Observation: baca hasil tool.
- Reasoning lanjutan: pertahankan ranking dari backend.
- Final Action: output JSON valid.

### 6.3 Output Contract

Context Agent harus output JSON strict:

```json
{
  "timestamp": "<HH:MM:SS>",
  "scene": "<scene_name>",
  "user_action": "<apa yang sedang dilakukan pengguna>",
  "recommendations": [
    {
      "rank": 1,
      "id": "<site_id>",
      "name": "<display_name>",
      "cultural_position": "<x, y, z>"
    }
  ],
  "nav_target": "<rank-1 site_id>"
}
```

Constraint penting:

- Output hanya JSON.
- Tidak boleh markdown.
- Tidak boleh explanation.
- Hanya gunakan bounded runtime tools.
- Jangan refer hidden state.
- Jangan asumsi data di luar snapshot.
- Hanya include `visited=false`.
- Jika semua sudah dikunjungi, output `recommendations=[]` dan `nav_target=""`.
- Jangan output status-only seperti `{"status":"NO_DELTA"}`.
- Preserve order dari `precomputed_recommendations`.
- `nav_target` harus sama dengan `id` rank-1.

### 6.4 Risiko Failure Context Agent

Failure yang perlu dievaluasi:

- Output bukan JSON valid.
- Field wajib hilang.
- Rekomendasi memasukkan site `visited=true`.
- Ranking berubah dari backend-computed order.
- `nav_target` tidak sama dengan rank-1.
- Mengarang site yang tidak ada di snapshot.
- Mengubah `timestamp` atau `scene`.
- Menggunakan koordinat salah.
- Menghasilkan lebih dari 3 rekomendasi.
- Menghasilkan status-only object.
- Tidak mengikuti bounded tool instruction.

### 6.5 Catatan Penting

Walaupun Context Agent menjalankan LLM, orchestrator saat ini melakukan override pada beberapa field penting:

```text
timestamp
scene
recommendations
nav_target
```

Artinya, output final context yang dipakai downstream lebih aman karena ranking tetap berasal dari backend deterministic logic.

Namun evaluasi Context Agent tetap penting untuk:

- memastikan output sesuai schema;
- memastikan user_action masuk akal;
- memastikan prompt/tool behavior tidak menyimpang;
- memastikan jika nanti override dikurangi, agent tetap grounded.

---

## 7. Dialogue Agent

File: `src/agents/dialogue_agent.py`

Peran:

```text
Dialogue Agent — Character Persona & Parent Node
```

Nama NPC:

```text
Arif
```

Persona:

```text
Pemandu budaya yang bijaksana dan hangat di museum warisan budaya VR.
```

Speech style:

```text
Ramah, meyakinkan, ringkas, natural dalam bahasa Indonesia.
Menyisipkan konteks budaya singkat tanpa berlebihan.
```

### 7.1 Tugas Utama

Dialogue Agent bertugas:

1. Membaca `ContextOutput`.
2. Menghasilkan dialog NPC dalam bahasa Indonesia.
3. Menghasilkan subtitle pendek untuk HUD.
4. Menghasilkan teks pengantar rekomendasi untuk UI.
5. Menghasilkan opsi rekomendasi berbasis nama objek.
6. Memanggil `tool_show_subtitle`.
7. Menangani dua mode input:
   - recommendation synthesis;
   - selection confirmation.

### 7.2 Tool

Dialogue Agent memiliki tool:

```text
tool_show_subtitle(text: str) -> bool
```

Tool ini memanggil:

```text
show_subtitle(text)
```

yang kemudian mengirim payload mock ke Unity client:

```json
{
  "command": "DISPLAY_SUBTITLE",
  "text": "...",
  "duration": 5.0
}
```

### 7.3 Input Shape A: Recommendation Synthesis

Input berupa `ContextOutput`:

```json
{
  "timestamp": "...",
  "scene": "...",
  "user_action": "...",
  "recommendations": [
    {
      "rank": 1,
      "id": "...",
      "name": "...",
      "cultural_position": "x, y, z"
    }
  ],
  "nav_target": "..."
}
```

Ekspektasi:

- Rank-1 adalah tujuan utama aktif.
- Rank-2 dan rank-3 adalah alternatif.
- `recommendation_options` harus mengikuti urutan `recommendations`.
- `spoken_output` mengarahkan pemain ke tujuan utama.
- `spoken_output` menyebut alternatif jika tersedia.
- `subtitle_output` singkat dan fokus ke tujuan utama.
- `recommendation_dialogue` menjadi teks UI, bukan sekadar pengulangan subtitle.

### 7.4 Input Shape B: Selection Confirmation

Input:

```json
{
  "mode": "selection_confirmation",
  "selected_option": "...",
  "selected_site_id": "...",
  "context": {
    "timestamp": "...",
    "scene": "...",
    "user_action": "...",
    "recommendations": [
      {
        "rank": 1,
        "id": "...",
        "name": "...",
        "cultural_position": "x, y, z"
      }
    ],
    "nav_target": "..."
  }
}
```

Ekspektasi:

- Fokus mengonfirmasi pilihan pemain.
- `spoken_output` dan `subtitle_output` wajib menyebut `selected_option`.
- `recommendation_dialogue` menyatakan pilihan diterima.
- Nada meyakinkan, seperti NPC siap memandu perjalanan.

### 7.5 Output Contract

Dialogue Agent harus output:

```json
{
  "spoken_output": "<ucapan NPC 2-4 kalimat dalam bahasa Indonesia>",
  "subtitle_output": "<satu kalimat <= 15 kata untuk HUD>",
  "recommendation_dialogue": "<kalimat singkat untuk UI>",
  "recommendation_options": ["<option_1>", "<option_2>", "<option_3>"]
}
```

Constraint penting:

- Output hanya JSON.
- Semua teks user-facing dalam bahasa Indonesia.
- Jangan tampilkan ID mentah jika ID bersifat teknis.
- Jangan tampilkan koordinat.
- Jangan tampilkan angka jarak.
- Jangan tampilkan token sistem.
- Jangan tampilkan istilah teknis backend.
- Jangan tampilkan tool name.
- Jangan mengarang fakta budaya detail yang tidak ada pada input.
- Subtitle maksimal 15 kata.
- `recommendation_options` hanya nama objek.
- Opsi pertama harus sama dengan rank-1/nav_target aktif.
- Jika recommendations kosong, options kosong.
- Untuk mode selection, `selected_option` harus disebut eksplisit.

### 7.6 Risiko Failure Dialogue Agent

Failure yang perlu dievaluasi:

- Output bukan JSON valid.
- Tidak mengikuti `DialogueOutput`.
- Subtitle terlalu panjang.
- Dialog tidak menyebut tujuan utama.
- Dialog tidak menyebut selected option saat selection confirmation.
- Recommendation options tidak sinkron dengan context.
- Options berubah urutan.
- Mengarang fakta budaya.
- Terlalu generik dan tidak actionable.
- Membocorkan koordinat.
- Membocorkan ID teknis atau istilah backend.
- Bahasa Indonesia kaku/campur Inggris.
- Persona Arif tidak terasa.
- UI text tidak membantu pemain memilih.
- Tool subtitle tidak dipanggil atau subtitle yang dipanggil tidak konsisten.

---

## 8. Unity/VR Tools

Folder: `src/vr_tools/`

### 8.1 `unity_api.py`

Class:

```text
UnityAPIClient
```

Saat ini masih mock.

Behavior:

- `get("user/status")` mengembalikan posisi player mock.
- `get("world/cultural_sites")` membaca `data/cultural_sites.json`.
- `post(endpoint, data)` hanya logging dan return `True`.
- `update_cultural_sites(payload)` menulis ke `data/cultural_sites.json`.

Catatan:

```text
Real implementation belum aktif:
requests.post(f"{self.base_url}/{endpoint}", json=data)
```

### 8.2 `vr_actions.py`

Fungsi:

```text
set_nav_target(target_id: str) -> bool
show_subtitle(text: str, duration: float = 5.0)
```

Payload NavMesh:

```json
{
  "command": "NAV_TO_TARGET",
  "target_id": "..."
}
```

Payload subtitle:

```json
{
  "command": "DISPLAY_SUBTITLE",
  "text": "...",
  "duration": 5.0
}
```

### 8.3 `vr_perception.py`

Fungsi:

```text
get_environment_data()
get_user_status()
get_cultural_sites()
```

Saat ini hanya wrapper ke `unity_client.get`.

---

## 9. Model Provider dan MockModel

Konfigurasi ada di `src/core/config.py`.

Field penting:

```text
OPENROUTER_API_KEY
OPENROUTER_BASE_URL = https://openrouter.ai/api/v1
OPENROUTER_MODEL = openai/gpt-4.1
USE_MOCK_MODEL = true
```

Behavior:

- Jika `USE_MOCK_MODEL=true`, agent memakai `MockModel`.
- Jika API key OpenRouter kosong atau placeholder, fallback ke `MockModel`.
- Jika API key valid dan `USE_MOCK_MODEL=false`, agent memakai OpenRouter model.

MockModel ada di `src/core/mock_model.py`.

### 9.1 Mock Context Response

MockModel untuk context mengembalikan JSON fixed:

```json
{
  "timestamp": "12:30:00",
  "scene": "Heritage_Museum_Wing_A",
  "user_action": "Examining_Artifact_ID_7",
  "recommendations": [
    {"rank": 1, "id": "Kujang", "name": "Kujang", "...": "..."}
  ],
  "nav_target": "Kujang"
}
```

Namun orchestrator mengoverride `timestamp`, `scene`, `recommendations`, dan `nav_target` dengan hasil request/ranking backend.

### 9.2 Mock Dialogue Response

MockModel untuk dialogue mengembalikan dialog generik:

```text
Saya sudah menyiapkan beberapa rekomendasi objek budaya di sekitar Anda.
Silakan pilih tujuan yang paling ingin Anda kunjungi...
```

Masalah:

- Dialog awal tidak menyebut nama tujuan utama.
- Ini menyebabkan beberapa evaluasi Dialogue Agent gagal pada check `dialogue.primary_option_mentioned`.

Selection confirmation punya fallback logic yang bisa menghasilkan dialog seperti:

```text
Baik, saya akan memandu Anda menuju Kujang...
Mari menuju Kujang.
```

---

## 10. Evaluasi Yang Sudah Dibuat

Folder: `evals/`

### 10.1 Runner

File:

```text
evals/run_agent_evaluation.py
```

Runner mendukung evaluasi:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent e2e
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all
```

Output JSON:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context --json
```

Verbose:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue --verbose
```

### 10.2 Skenario Evaluasi

File:

```text
evals/scenarios.json
```

Berisi 7 skenario:

1. `three_unvisited_nearest_order`
2. `visited_site_filtered_out`
3. `single_remaining_site`
4. `all_sites_visited`
5. `tie_distance_uses_name_sort`
6. `compatibility_alias_cultural_objects`
7. `invalid_selected_option`

Catatan penting:

- Skenario ini adalah synthetic/offline scenarios.
- Tidak membaca `data/cultural_sites.json`.
- Tidak memakai posisi player live Unity.
- Beberapa objek seperti `Wayang`, `Batik`, `Visited Mask`, `Alpha`, `Beta`, `Zeta` adalah dummy untuk menguji edge case.
- Jika ingin evaluasi hanya memakai objek budaya asli project, skenario perlu disesuaikan dengan data Unity sebenarnya.

### 10.3 Context Agent Metrics

Metrik yang sudah diimplementasikan:

```text
context.schema_valid
context.timestamp_matches_request
context.scene_matches_request
context.no_visited_sites_recommended
context.ranking_exact_match
context.nav_target_matches_rank_1
context.max_three_recommendations
precision_at_3
recall_at_3
mrr
ndcg_at_3
```

Interpretasi:

- `schema_valid`: output valid terhadap `ContextOutput`.
- `timestamp_matches_request`: tidak mengubah timestamp Unity.
- `scene_matches_request`: tidak mengubah scene Unity.
- `no_visited_sites_recommended`: objek visited tidak direkomendasikan.
- `ranking_exact_match`: urutan rekomendasi sama dengan gold ranking berbasis Euclidean distance.
- `nav_target_matches_rank_1`: NavMesh target sama dengan rank-1.
- `max_three_recommendations`: output maksimal 3 opsi.
- `Precision@3`: proporsi prediksi top-3 yang relevan.
- `Recall@3`: proporsi gold top-3 yang ditemukan.
- `MRR`: kualitas posisi relevant pertama.
- `NDCG@3`: kualitas ranking dengan discount berdasarkan posisi.

### 10.4 Dialogue Agent Metrics

Metrik/check yang sudah diimplementasikan:

```text
dialogue.schema_valid
dialogue.options_match_context_order
dialogue.subtitle_max_15_words
dialogue.no_internal_tokens_or_coordinates
dialogue.primary_option_mentioned
dialogue.empty_recommendations_handled
dialogue.selected_option_mentioned
subtitle_word_count
option_count
has_leak
```

Interpretasi:

- `schema_valid`: output valid terhadap `DialogueOutput`.
- `options_match_context_order`: UI options sama persis dengan context recommendations.
- `subtitle_max_15_words`: subtitle sesuai constraint HUD.
- `no_internal_tokens_or_coordinates`: tidak bocor koordinat, tool, backend, atau NavMesh.
- `primary_option_mentioned`: dialog/subtitle menyebut tujuan utama rank-1.
- `empty_recommendations_handled`: jika tidak ada rekomendasi, options kosong.
- `selected_option_mentioned`: saat selection confirmation, pilihan pemain disebut eksplisit.

### 10.5 End-to-End Metrics

End-to-end success mengecek:

1. Request valid.
2. Context valid.
3. Dialogue valid.
4. Selection valid/invalid sesuai skenario.
5. Semua required checks lolos.

---

## 11. Hasil Evaluasi Sementara

Hasil terakhir dengan mock model:

### 11.1 Context Agent

Command:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
```

Hasil:

```text
Scenarios: 7
Check pass rate: 100.00%
Context Precision@3: 1.000
Context Recall@3: 1.000
Context MRR: 0.857
Context NDCG@3: 1.000
All scenarios: PASS
```

Interpretasi:

- Context output final sangat kuat pada skenario offline.
- Ranking, filtering visited, nav_target, timestamp, scene, max-three recommendation semua lolos.
- MRR tidak 1.0 karena ada skenario tanpa rekomendasi, sehingga MRR dihitung 0 pada case tersebut.

### 11.2 Dialogue Agent

Command:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue
```

Hasil:

```text
Scenarios: 7
Check pass rate: 86.11%
Dialogue subtitle words avg: 3.57
Dialogue options avg: 1.71
Dialogue technical leak rate: 0.00%
```

Failure utama:

```text
dialogue.primary_option_mentioned
```

Contoh:

```text
primary_option=Julang Ngapak
primary_option=Kujang
primary_option=Angklung
primary_option=Alpha
primary_option=Wayang
```

Interpretasi:

- Dialogue Agent/mock output terlalu generik.
- Dialog awal sering tidak menyebut nama tujuan utama.
- Subtitle awal juga sering generik: "Silakan pilih tujuan budaya berikutnya."
- Namun tidak ada technical leak.
- Options tetap sinkron karena orchestrator mengoverride `recommendation_options` berdasarkan context.

### 11.3 End-to-End

Command:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent e2e
```

Hasil:

```text
Scenarios: 7
Check pass rate: 92.42%
End-to-end success rate: 14.29%
```

Interpretasi:

- End-to-end rendah bukan karena Context Agent.
- Penyebab utama adalah Dialogue Agent gagal menyebut primary option.
- Skenario `all_sites_visited` lolos penuh.

---

## 12. Literatur Yang Sudah Dijadikan Dasar Awal

Dokumen metodologi awal sudah mengacu pada paper berikut:

1. **ReAct: Synergizing Reasoning and Acting in Language Models**
   - Relevansi: Context Agent menggunakan struktur ReAct.
   - Evaluasi agent tidak cukup hanya final output; reasoning/action/tool behavior penting.

2. **TRAJECT-Bench: A Trajectory-Aware Benchmark for Evaluating Agentic Tool Use**
   - Relevansi: agent dengan tool-use perlu dievaluasi dari trajectory, tool selection, argument correctness, dan order/dependency.

3. **Evaluating Recommender Systems: Survey and Framework**
   - Relevansi: Context Agent menghasilkan ranking rekomendasi top-3.
   - Metrik seperti Precision@k, Recall@k, MRR, NDCG relevan.

4. **Evaluating Conversational Recommender Systems: A Landscape of Research**
   - Relevansi: sistem ini bukan hanya recommender biasa, tetapi conversational/interactive recommender via NPC.
   - Perlu evaluasi komponen dan evaluasi user experience.

5. **G-Eval**
   - Relevansi: Dialogue Agent output berupa natural language, cocok dinilai dengan rubric-based LLM-as-a-judge.

6. **Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena**
   - Relevansi: LLM-as-a-judge bisa mendekati human preference, tetapi punya bias.

7. **USR dan FED untuk evaluasi dialog**
   - Relevansi: dialog tidak cocok dinilai hanya dengan BLEU/ROUGE.
   - Perlu menilai relevansi, naturalness, coherence, consistency, dan kualitas dialog lain.

---

## 13. Kebutuhan Riset Yang Ingin Ditanyakan Ke Claude

Tolong lakukan research mendalam untuk menjawab:

### 13.1 Untuk Context Agent

Apa metode evaluasi paling valid untuk Context Agent yang:

- menggunakan ReAct prompting;
- memakai bounded tools;
- membaca runtime snapshot;
- menghasilkan structured JSON;
- melakukan contextual state summarization;
- menerima precomputed ranking dari backend;
- outputnya bisa diverifikasi secara deterministic;
- terhubung dengan NavMesh target;
- berperan sebagai environmental state/recommendation engine?

Pertanyaan spesifik:

1. Apakah metric ranking seperti Precision@3, Recall@3, MRR, NDCG@3 sudah cukup?
2. Apakah perlu trajectory/tool-use evaluation?
3. Apakah perlu faithfulness/grounding evaluation seperti pada RAG atau state tracking?
4. Apakah Context Agent sebaiknya dievaluasi sebagai:
   - recommender system;
   - LLM tool-use agent;
   - state tracker;
   - structured-output generator;
   - atau kombinasi semuanya?
5. Paper apa yang paling tepat dijadikan dasar untuk masing-masing aspek?
6. Bagaimana desain eksperimen yang kuat untuk skripsi?
7. Apakah evaluator deterministic lebih valid daripada LLM-as-a-judge untuk agent ini?
8. Jika memakai LLM-as-a-judge, bagian mana yang boleh/jangan dinilai LLM judge?

### 13.2 Untuk Dialogue Agent

Apa metode evaluasi paling valid untuk Dialogue Agent yang:

- menghasilkan dialog NPC;
- output dalam bahasa Indonesia;
- persona-based;
- bertugas mengarahkan player ke objek budaya;
- menghasilkan subtitle pendek;
- menghasilkan UI recommendation options;
- harus grounded pada ContextOutput;
- tidak boleh mengarang fakta budaya;
- tidak boleh membocorkan koordinat atau istilah teknis;
- punya mode recommendation synthesis dan selection confirmation?

Pertanyaan spesifik:

1. Apakah G-Eval cocok?
2. Apakah LLM-as-a-judge cocok untuk bahasa Indonesia?
3. Bagaimana mengurangi bias LLM judge?
4. Rubrik apa yang paling valid untuk dialogue quality?
5. Apakah perlu human evaluation?
6. Apakah perlu task-based evaluation dari user VR?
7. Apakah metrik seperti coherence, relevance, fluency, persona consistency, instruction clarity, faithfulness, groundedness, dan safety cukup?
8. Bagaimana mengevaluasi subtitle secara spesifik?
9. Bagaimana mengevaluasi recommendation options agar sinkron dengan context?
10. Bagaimana mengevaluasi dialog yang tidak memiliki reference answer tunggal?

### 13.3 Untuk Sistem End-to-End

Apa metode evaluasi paling valid untuk sistem gabungan:

```text
Unity snapshot -> Context Agent -> NavMesh target -> Dialogue Agent -> UI options -> Player selection
```

Pertanyaan spesifik:

1. Apakah cocok memakai task success rate?
2. Apakah perlu user study VR?
3. Apa metrik UX yang cocok?
4. Bagaimana mengukur kualitas bantuan NPC?
5. Bagaimana menghubungkan metrik offline dengan performa real-time di Unity?
6. Apakah perlu latency evaluation?
7. Apakah perlu robustness testing untuk invalid payload?
8. Bagaimana mengevaluasi multi-turn/tick behavior?

---

## 14. Rekomendasi Awal Yang Sudah Dipakai

Evaluasi awal project saat ini menggunakan pendekatan hybrid:

### 14.1 Context Agent

Dominan deterministic evaluation:

- schema validation;
- groundedness to request;
- visited filtering;
- ranking exact match;
- nav target accuracy;
- Precision@3;
- Recall@3;
- MRR;
- NDCG@3.

Alasan:

Context Agent memiliki gold answer objektif yang bisa dihitung dari input.

### 14.2 Dialogue Agent

Rule-based evaluation + rencana LLM-as-a-judge:

- schema validation;
- subtitle length;
- option consistency;
- no technical leakage;
- primary option mentioned;
- selected option mentioned;
- LLM judge rubric untuk relevansi, faithfulness, clarity, persona, language quality, UI usefulness, technical leak safety.

Alasan:

Dialogue Agent tidak punya satu reference answer tunggal. Banyak output bisa benar selama grounded, natural, dan membantu.

### 14.3 End-to-End

Scenario-based evaluation:

- context correctness;
- dialogue correctness;
- selection correctness;
- flow success;
- future: latency dan user-study metrics.

---

## 15. Rubrik LLM Judge Awal Untuk Dialogue Agent

Rubrik awal disimpan di:

```text
evals/dialogue_llm_judge_rubric.md
```

Dimensi yang disarankan:

1. `context_relevance`
2. `faithfulness`
3. `navigation_clarity`
4. `persona_alignment`
5. `language_quality`
6. `ui_usefulness`
7. `technical_leak_safety`

Skor:

```text
1 sampai 5
```

Aturan pass:

- `overall_score >= 4.0`
- tidak boleh pass jika `technical_leak_safety < 5`
- tidak boleh pass jika `faithfulness < 4`
- untuk selection confirmation, tidak boleh pass jika selected option tidak disebut eksplisit

---

## 16. Hal Yang Perlu Diperhatikan Dalam Riset

Tolong jangan memberikan saran evaluasi yang terlalu generik seperti hanya "accuracy" atau "BLEU".

Project ini membutuhkan evaluasi yang membedakan:

1. **Objective structured agent**: Context Agent.
2. **Subjective natural language agent**: Dialogue Agent.
3. **Interactive VR system**: end-to-end pipeline.

Evaluasi yang baik seharusnya:

- berbasis paper;
- menjelaskan kenapa metric cocok;
- menjelaskan keterbatasan metric;
- membedakan evaluasi offline dan online/user study;
- membedakan deterministic evaluator dan LLM-as-a-judge;
- menjelaskan risiko bias LLM judge;
- memberi desain eksperimen konkret;
- memberi format tabel hasil yang bisa dipakai dalam skripsi;
- memberi saran dataset/skenario yang perlu dibuat;
- relevan dengan bahasa Indonesia dan NPC VR guide.

---

## 17. Output Riset Yang Diharapkan Dari Claude

Minta Claude menghasilkan:

1. Rekomendasi metode evaluasi untuk Context Agent.
2. Rekomendasi metode evaluasi untuk Dialogue Agent.
3. Rekomendasi metode evaluasi end-to-end.
4. Tabel mapping:

```text
Agent / Component
Task
Failure Risk
Recommended Metric
Why Suitable
Paper Support
Implementation Plan
```

5. Daftar paper utama dan ringkasan kontribusinya.
6. Desain eksperimen skripsi.
7. Rubrik final untuk LLM-as-a-judge Dialogue Agent.
8. Saran apakah Context Agent perlu LLM judge atau cukup deterministic evaluation.
9. Saran user study VR, termasuk metrik subjektif dan objektif.
10. Kritik terhadap evaluasi yang sudah ada di project ini.

---

## 18. Ringkasan Paling Penting

Project ini memiliki dua agent dengan karakter evaluasi yang berbeda:

### Context Agent

Tipe:

```text
structured, grounded, deterministic-checkable, spatial recommendation/state agent
```

Evaluasi paling cocok kemungkinan:

```text
schema validity + grounding + ranking metrics + tool trajectory compliance
```

### Dialogue Agent

Tipe:

```text
natural language, persona-based, grounded dialogue/UI synthesis agent
```

Evaluasi paling cocok kemungkinan:

```text
rule-based safety/consistency checks + rubric-based LLM-as-a-judge + human/user study
```

### End-to-End System

Tipe:

```text
interactive VR navigation assistant pipeline
```

Evaluasi paling cocok kemungkinan:

```text
scenario task success + selection correctness + latency + user experience study
```

Tujuan riset Claude adalah memvalidasi, memperkuat, atau mengoreksi rancangan ini dengan paper yang paling tepat dan metode evaluasi yang bisa dipertanggungjawabkan secara akademik.
