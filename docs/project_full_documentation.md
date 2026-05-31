# Dokumentasi Lengkap Project Multi-Agent VR Cultural Guide

Dokumen ini menjelaskan keseluruhan project secara menyeluruh: tujuan sistem, struktur folder, alur runtime, API, schema data, agent, orchestrator, integrasi Unity, mock model, evaluasi, cara menjalankan, serta limitasi yang perlu diperhatikan.

Project ini berada di:

```text
/Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project
```

---

## 1. Gambaran Umum Project

Project ini adalah backend Python untuk sistem **multi-agent NPC guide** di lingkungan **VR museum / heritage cultural simulation**.

Sistem ini dirancang agar sebuah NPC pemandu budaya dapat:

1. Menerima snapshot runtime dari Unity.
2. Membaca posisi pemain.
3. Membaca daftar objek atau situs budaya.
4. Melihat status apakah objek sudah dikunjungi atau belum.
5. Memilih rekomendasi objek budaya yang belum dikunjungi.
6. Menentukan target navigasi untuk NPC melalui NavMesh.
7. Menghasilkan dialog NPC dalam bahasa Indonesia.
8. Menampilkan subtitle di HUD Unity.
9. Menampilkan opsi rekomendasi pada UI.
10. Menangani pilihan pemain terhadap salah satu rekomendasi.

Sistem memakai dua agent utama:

```text
Context Agent  -> memahami state lingkungan dan rekomendasi objek budaya
Dialogue Agent -> membuat dialog NPC, subtitle, dan opsi UI
```

Secara arsitektur, sistem ini bisa disebut sebagai:

```text
Unity/VR Snapshot
  -> Flask Backend
  -> Hierarchical Orchestrator
  -> Context Agent
  -> NavMesh Dispatch
  -> Dialogue Agent
  -> HUD/Subtitle/UI Options
  -> Player Selection
```

---

## 2. Stack Teknologi

Runtime utama:

```text
Python >= 3.11
Flask
Pydantic
Pydantic Settings
Strands Agents
OpenAI-compatible model provider via OpenRouter
MockModel untuk local/offline testing
```

File `pyproject.toml` saat ini mencatat dependencies berikut:

```toml
dependencies = [
    "anthropic>=0.97.0",
    "strands-agents[openai]>=1.36.0",
    "strands-agents-builder>=0.1.10",
    "strands-agents-tools>=0.5.0",
]
```

Catatan penting:

- Runtime utama memakai Flask, tetapi `flask` belum terlihat eksplisit di `pyproject.toml`.
- `pydantic-settings` juga dipakai di kode, tetapi tidak terlihat eksplisit di `pyproject.toml`.
- Dependency tersebut kemungkinan sudah tersedia di `.venv` dan/atau `uv.lock`.
- Jika setup ulang dari nol, dependency runtime perlu diverifikasi ulang.

---

## 3. Struktur Folder dan File

Struktur file utama:

```text
my-project/
  main.py
  server.py
  pyproject.toml
  uv.lock
  README.md
  Multi Agent.postman_collection.json
  Python-3.11.15.tgz.sigstore
  test.tsx
  data/
    cultural_sites.json
  src/
    __init__.py
    agents/
      __init__.py
      context_agent.py
      dialogue_agent.py
    core/
      __init__.py
      config.py
      mock_model.py
    orchestration/
      __init__.py
      coordinator.py
    schema/
      __init__.py
      models.py
    vr_tools/
      __init__.py
      unity_api.py
      vr_actions.py
      vr_perception.py
  evals/
    README.md
    scenarios.json
    run_agent_evaluation.py
    dialogue_llm_judge_rubric.md
  docs/
    evaluation_methodology.md
    project_summary_for_llm_evaluation_research.md
    project_full_documentation.md
```

Penjelasan singkat tiap bagian:

| Path | Fungsi |
|---|---|
| `main.py` | Entry point Flask utama untuk API backend multi-agent. |
| `server.py` | Contoh FastAPI minimal; bukan runtime utama project saat ini. |
| `pyproject.toml` | Metadata project dan dependency utama. |
| `uv.lock` | Lock file dependency untuk environment berbasis `uv`. |
| `README.md` | Masih kosong pada saat dokumentasi ini dibuat. |
| `Multi Agent.postman_collection.json` | Koleksi Postman untuk mengetes endpoint backend. |
| `Python-3.11.15.tgz.sigstore` | File signature terkait Python archive; tidak dipakai langsung oleh runtime project. |
| `test.tsx` | File TypeScript/React yang belum terlihat terintegrasi dengan backend Python. |
| `data/cultural_sites.json` | Registry mock cultural sites untuk endpoint admin/mock. |
| `src/agents/context_agent.py` | Definisi Context Agent, bounded tools, dan system prompt ReAct. |
| `src/agents/dialogue_agent.py` | Definisi Dialogue Agent, persona NPC, subtitle tool, dan system prompt. |
| `src/core/config.py` | Konfigurasi project, env vars, OpenRouter, mock mode. |
| `src/core/mock_model.py` | Mock model untuk menjalankan sistem tanpa LLM API. |
| `src/orchestration/coordinator.py` | Orchestrator utama yang menghubungkan request, agent, NavMesh, session, dan dialogue. |
| `src/schema/models.py` | Semua Pydantic schema request, response, session, dan agent output. |
| `src/vr_tools/unity_api.py` | Mock Unity API client. |
| `src/vr_tools/vr_actions.py` | Action tools untuk NavMesh dan subtitle. |
| `src/vr_tools/vr_perception.py` | Perception wrappers untuk membaca environment, user status, dan cultural sites. |
| `evals/` | Sistem evaluasi offline yang dibuat untuk Context Agent, Dialogue Agent, dan end-to-end. |
| `docs/` | Dokumentasi metodologi dan summary project. |

---

## 4. Entry Point Runtime

### 4.1 `main.py`

`main.py` adalah entry point utama project.

Framework:

```python
from flask import Flask, jsonify, request
```

Sebelum import module dari `src`, file ini menambahkan path `src` ke `sys.path`:

```python
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
```

Ini berarti module seperti `orchestration.coordinator`, `schema.models`, dan `vr_tools.unity_api` dapat di-import tanpa prefix `src`.

Flask app:

```python
app = Flask(__name__)
```

Server dijalankan dengan:

```python
app.run(debug=True, host="0.0.0.0", port=8080)
```

### 4.2 `server.py`

`server.py` berisi FastAPI minimal:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}
```

File ini tampaknya hanya template awal dan **bukan backend utama** untuk flow multi-agent.

---

## 5. API Endpoint

Semua endpoint utama ada di `main.py`.

### 5.1 `GET /user/status`

Mengambil status posisi player dari `unity_client`.

Implementation:

```python
@app.route('/user/status', methods=['GET'])
def get_user_status():
    return jsonify(unity_client.get("user/status")), 200
```

Mock response:

```json
{
  "player_position": "13.67265, 1.291507, 17.12134"
}
```

### 5.2 `GET /world/cultural_sites`

Mengambil registry cultural sites dari mock data lokal.

Implementation:

```python
@app.route('/world/cultural_sites', methods=['GET'])
def get_cultural_sites():
    return jsonify(unity_client.get("world/cultural_sites")), 200
```

Data berasal dari:

```text
data/cultural_sites.json
```

### 5.3 `PUT /world/cultural_sites`

Memperbarui registry mock cultural sites.

Payload harus memiliki field:

```json
{
  "sites": [
    {
      "id": "Surabi",
      "name": "Surabi",
      "cultural_position": "-1.34956, 1.52654, 23.7432",
      "visited": false
    }
  ]
}
```

Validasi awal di endpoint:

- body harus JSON valid;
- `sites` harus array/list;
- setiap item dalam `sites` harus object/dict.

Setelah itu validasi lanjut dilakukan oleh Pydantic melalui `CulturalSitesPayload`.

### 5.4 `POST /context/run`

Endpoint utama tahap pertama.

Fungsi:

1. Menerima snapshot runtime dari Unity.
2. Validasi request menjadi `SimulationRequest`.
3. Menjalankan `orchestrator.run_context_cycle`.
4. Mengembalikan `simulation_id`, `context`, dan `navmesh_ack`.

Canonical request:

```json
{
  "timestamp": "2026-05-01T12:30:00Z",
  "scene": "Heritage_Museum_Wing_A",
  "playerPosition": "12.0, 0.0, 35.0",
  "culturalSites": [
    {
      "id": "Surabi",
      "name": "Surabi",
      "cultural_position": "-1.34956, 1.52654, 23.7432",
      "visited": false
    }
  ]
}
```

Compatibility aliases:

```text
culturalObject
culturalObjects
cultural_sites
coordinate -> cultural_position
isObjectVisited -> visited
```

Important design note:

```text
Unity adalah source of truth untuk timestamp, scene, playerPosition, dan visited status.
```

Response success:

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

Error:

- `400` jika body bukan JSON valid.
- `422` jika schema request tidak valid.
- `500` jika terjadi exception tidak terduga.

### 5.5 `POST /dialogue/run`

Endpoint utama tahap kedua.

Fungsi:

1. Menerima `simulationId`.
2. Mengambil session context yang sudah disimpan dari `/context/run`.
3. Menjalankan Dialogue Agent.
4. Mengembalikan dialog NPC dan opsi rekomendasi.

Request:

```json
{
  "simulationId": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e"
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

Error:

- `400` jika `simulationId` tidak ditemukan.
- `422` jika request tidak valid.
- `500` jika terjadi exception tidak terduga.

### 5.6 `POST /run-simulation`

Endpoint legacy compatibility.

Fungsi:

```text
context + dialogue sekaligus
```

Untuk integrasi baru, flow yang disarankan tetap:

```text
/context/run -> /dialogue/run -> /recommendation/select
```

### 5.7 `POST /recommendation/select`

Endpoint tahap ketiga.

Fungsi:

1. Menerima `simulationId`.
2. Menerima `selectedOption`.
3. Mengecek apakah opsi tersebut ada dalam rekomendasi aktif.
4. Mengubah `nav_target` ke situs yang dipilih.
5. Dispatch target ke NavMesh.
6. Menghasilkan confirmation dialogue.
7. Dispatch subtitle.
8. Menyimpan session terbaru.

Request:

```json
{
  "simulationId": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e",
  "selectedOption": "Julang Ngapak"
}
```

Response:

```json
{
  "status": "success",
  "message": "Recommendation option selected successfully",
  "data": {
    "selected_option": "Julang Ngapak",
    "selected_site_id": "Julang Ngapak",
    "navmesh_ack": true,
    "spoken_output": "Baik, saya akan memandu Anda menuju Julang Ngapak...",
    "subtitle_output": "Mari menuju Julang Ngapak."
  }
}
```

Important design note:

```text
Backend tidak mengubah field visited.
Unity tetap source of truth untuk visited.
Unity harus mengirim status visited terbaru pada request /context/run berikutnya.
```

---

## 6. Schema dan Model Data

Semua schema utama ada di:

```text
src/schema/models.py
```

### 6.1 `AgentRole`

Enum:

```python
class AgentRole(str, Enum):
    CONTEXT  = "context_agent"
    DIALOGUE = "dialogue_agent"
```

Saat ini enum ini lebih bersifat deklaratif/dokumentatif.

### 6.2 `SimulationRequest`

Request body untuk `/context/run` dan `/run-simulation`.

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
- Semua komponen `playerPosition` harus numerik.
- Output `playerPosition` dinormalisasi menjadi string dengan spasi: `"x, y, z"`.

Compatibility normalizer:

- Jika request punya `cultural_sites`, maka dipindahkan ke `culturalSites`.
- Jika request punya `culturalObject`, maka setiap item dikonversi ke canonical structure.
- Jika request punya `culturalObjects`, berlaku sama.
- `id` diambil dari `item.id` atau fallback ke `item.name`.
- `cultural_position` diambil dari `item.cultural_position` atau fallback ke `item.coordinate`.
- `visited` diambil dari `item.visited` atau fallback ke `item.isObjectVisited`.

### 6.3 `RecommendationSelectionRequest`

Request untuk `/recommendation/select`.

Field:

```text
simulationId: str
selectedOption: str
```

Keduanya wajib non-empty.

### 6.4 `DialogueCycleRequest`

Request untuk `/dialogue/run`.

Field:

```text
simulationId: str
```

Wajib non-empty.

### 6.5 `CulturalSite`

Canonical cultural site object.

Field:

```text
id: str
name: str
cultural_position: str
visited: bool = False
```

Validasi:

- `id` non-empty.
- `name` non-empty.
- `cultural_position` non-empty.
- `cultural_position` harus format `"x, y, z"`.
- Semua komponen koordinat harus numerik.

### 6.6 `CulturalSitesPayload`

Wrapper:

```text
sites: List[CulturalSite]
```

Dipakai untuk registry `data/cultural_sites.json` dan runtime payload internal.

### 6.7 `AgentMessage`

Satu item history Message Pool.

Field:

```text
role: str
content: str
timestamp: datetime = now
metadata: Dict[str, Any] = {}
```

### 6.8 `SiteRecommendation`

Satu rekomendasi situs budaya.

Field:

```text
rank: int
id: str
name: str
cultural_position: str
```

Makna:

- `rank=1` adalah target utama NavMesh.
- `rank=2` dan `rank=3` adalah alternatif.

### 6.9 `EnvironmentSnapshot`

State lingkungan runtime.

Field:

```text
timestamp: str
scene: str
user_position: Dict[str, float]
```

### 6.10 `UserStatusSnapshot`

Status player.

Field:

```text
player_position: str
```

### 6.11 `ContextAgentInput`

Payload internal yang diberikan ke Context Agent melalui runtime snapshot.

Field:

```text
player_position: str
environment: EnvironmentSnapshot
user_status: UserStatusSnapshot
cultural_sites: CulturalSitesPayload
precomputed_recommendations: List[SiteRecommendation]
```

### 6.12 `ContextOutput`

Output Context Agent.

Field:

```text
timestamp: str
scene: str
user_action: str
recommendations: List[SiteRecommendation]
nav_target: str
```

Kontrak:

- `recommendations` harus ordered by rank ascending.
- `nav_target` harus sama dengan `id` dari rank-1.
- Jika tidak ada recommendation, `nav_target=""`.

### 6.13 `DialogueOutput`

Output Dialogue Agent.

Field:

```text
spoken_output: str
subtitle_output: str
recommendation_dialogue: str
recommendation_options: List[str]
```

Kontrak:

- `spoken_output`: dialog NPC 2-4 kalimat.
- `subtitle_output`: subtitle HUD maksimal 15 kata.
- `recommendation_dialogue`: kalimat pendek untuk UI.
- `recommendation_options`: 0-3 nama objek budaya untuk tombol pilihan.

### 6.14 `RecommendationSelectionResponse`

Response untuk selection.

Field:

```text
selected_option: str
selected_site_id: str
navmesh_ack: bool
spoken_output: str
subtitle_output: str
```

### 6.15 `SimulationCycleResponse`

Response legacy `/run-simulation`.

Field:

```text
simulation_id: str
context: ContextOutput
navmesh_ack: bool
dialogue: DialogueOutput
```

### 6.16 `ContextCycleResponse`

Response `/context/run`.

Field:

```text
simulation_id: str
context: ContextOutput
navmesh_ack: bool
```

### 6.17 `DialogueCycleResponse`

Response `/dialogue/run`.

Field:

```text
simulation_id: str
dialogue: DialogueOutput
```

### 6.18 `SimulationSessionState`

State session in-memory.

Field:

```text
simulation_id: str
player_position: str
cultural_sites: CulturalSitesPayload
context: ContextOutput
dialogue: Optional[DialogueOutput] = None
```

### 6.19 `MessagePoolState`

State shared blackboard.

Field:

```text
latest_context: Optional[ContextOutput]
latest_dialogue: Optional[DialogueOutput]
history: List[AgentMessage]
```

---

## 7. Orchestrator

File:

```text
src/orchestration/coordinator.py
```

Class utama:

```text
HierarchicalOrchestrator
```

Singleton:

```python
orchestrator = HierarchicalOrchestrator()
```

### 7.1 InMemoryMessagePool

Class:

```text
InMemoryMessagePool
```

Fungsi:

- menyimpan latest context;
- menyimpan latest dialogue;
- menyimpan history message;
- menyimpan session berdasarkan `simulation_id`;
- menyediakan context JSON untuk Dialogue Agent.

Method:

```text
publish_context(output)
publish_dialogue(output)
save_session(session)
get_session(simulation_id)
get_context_json_for_dialogue()
```

### 7.2 JSON Parsing Helpers

Function:

```text
_parse_context(raw: str) -> ContextOutput
_parse_dialogue(raw: str) -> DialogueOutput
_clean_json_text(raw: str) -> str
```

Fungsi:

- membersihkan code fence seperti ```json;
- parse JSON;
- validasi ke Pydantic model.

### 7.3 Coordinate Helpers

Function:

```text
_parse_vector3(position: str) -> tuple[float, float, float]
_distance_between(position_a: str, position_b: str) -> float
```

Fungsi:

- parsing string koordinat `"x, y, z"`;
- menghitung Euclidean distance.

### 7.4 Ranking Recommendation

Function:

```text
_rank_unvisited_sites(player_position, payload) -> list[SiteRecommendation]
```

Logic:

1. Ambil hanya site dengan `visited=False`.
2. Urutkan berdasarkan:
   - jarak Euclidean dari player ke site;
   - `site.name.lower()` sebagai tie-breaker.
3. Ambil top-3.
4. Convert ke `SiteRecommendation`.

Pseudo-code:

```text
unvisited_sites = [site for site in payload.sites if not site.visited]
ranked_sites = sorted(
  unvisited_sites,
  key=lambda site: (distance(player_position, site.cultural_position), site.name.lower())
)
return ranked_sites[:3]
```

### 7.5 Context Fallback Builder

Function:

```text
_build_context_output(raw, environment_snapshot, ranked_recommendations)
```

Dipakai ketika output Context Agent gagal diparse.

Behavior:

- jika raw berisi `status` seperti `NO_DELTA` atau `ALL_VISITED`, pakai sebagai `user_action`;
- jika ada `user_action`, pakai itu;
- kalau tidak ada, fallback ke `"Menunggu interaksi pemain"`;
- recommendations tetap memakai `ranked_recommendations`;
- nav target tetap rank-1.

### 7.6 Dialogue Fallback Builder

Function:

```text
_build_dialogue_output(recommendations)
```

Dipakai ketika Dialogue Agent gagal diparse.

Jika tidak ada rekomendasi:

```text
spoken_output: belum ada tujuan budaya baru
subtitle_output: Belum ada tujuan baru saat ini.
recommendation_options: []
```

Jika ada rekomendasi:

- rank-1 menjadi tujuan utama;
- rank-2/rank-3 menjadi alternatif;
- output dibuat dalam bahasa Indonesia.

### 7.7 Selection Dialogue Fallback Builder

Function:

```text
_build_selection_dialogue_output(selected_site, recommendations)
```

Dipakai ketika selection dialogue gagal dibuat oleh Dialogue Agent atau tidak menyebut selected site.

Output menyebut:

```text
Baik, saya akan memandu Anda menuju {selected_site.name}.
```

### 7.8 Initialization

Saat `HierarchicalOrchestrator` dibuat:

1. Membuat `InMemoryMessagePool`.
2. Mengambil singleton Context Agent.
3. Mengambil singleton Dialogue Agent.
4. Mengecek apakah harus pakai MockModel.

MockModel dipakai jika:

```text
settings.USE_MOCK_MODEL == True
atau
OpenRouter credentials tidak tersedia
```

Jika mock aktif:

```python
self.context_agent.model = MockModel("mock-context")
self.dialogue_agent.model = MockModel("mock-dialogue")
```

Jika mock tidak aktif:

```text
agent memakai OpenRouter model dari settings.OPENROUTER_MODEL
```

### 7.9 `_build_runtime_context`

Input:

```text
SimulationRequest
```

Output:

```text
EnvironmentSnapshot
CulturalSitesPayload
ranked_recommendations
context_agent_input.model_dump()
```

Fungsi:

- parse posisi player;
- build environment snapshot;
- build user status snapshot;
- build cultural sites payload;
- compute ranked recommendations;
- package semua untuk Context Agent tools.

### 7.10 `_run_context_agent`

Flow:

1. Set runtime snapshot untuk bounded tools.
2. Kirim instruksi singkat ke Context Agent.
3. Parse raw output menjadi `ContextOutput`.
4. Override field penting:
   - `timestamp`;
   - `scene`;
   - `recommendations`;
   - `nav_target`.
5. Jika parse gagal, pakai fallback `_build_context_output`.

Important:

```text
Ranking akhir tidak diserahkan penuh ke LLM.
Backend tetap source of truth untuk recommendations dan nav_target.
```

### 7.11 `run_context_cycle`

Dipakai oleh `/context/run`.

Flow:

1. Build runtime context.
2. Run Context Agent.
3. Publish context ke Message Pool.
4. Dispatch nav target ke Unity.
5. Generate `simulation_id`.
6. Save session.
7. Return `ContextCycleResponse`.

### 7.12 `run_dialogue_cycle`

Dipakai oleh `/dialogue/run`.

Flow:

1. Ambil session berdasarkan `simulation_id`.
2. Jika tidak ada, raise `ValueError`.
3. Convert context ke JSON.
4. Run Dialogue Agent.
5. Jika gagal, pakai fallback `_build_dialogue_output`.
6. Override `recommendation_options` agar sesuai context recommendations.
7. Dispatch subtitle.
8. Publish dialogue.
9. Update session.
10. Return `DialogueCycleResponse`.

Important:

```text
recommendation_options selalu dipaksa sinkron dengan context.recommendations.
```

### 7.13 `handle_recommendation_selection`

Dipakai oleh `/recommendation/select`.

Flow:

1. Ambil session.
2. Cari selected option pada `latest_context.recommendations`.
3. Jika tidak ditemukan, raise `ValueError`.
4. Update context `nav_target` menjadi selected site id.
5. Dispatch NavMesh ke selected site.
6. Build selection payload.
7. Run Dialogue Agent.
8. Jika output tidak menyebut selected site, pakai fallback.
9. Override recommendation options.
10. Dispatch subtitle.
11. Publish dialogue.
12. Save updated session.
13. Return `RecommendationSelectionResponse`.

### 7.14 `run_cycle`

Legacy combined flow:

```text
run_context_cycle -> run_dialogue_cycle
```

Dipakai oleh `/run-simulation`.

---

## 8. Context Agent

File:

```text
src/agents/context_agent.py
```

### 8.1 Peran

Context Agent adalah agent yang bertanggung jawab terhadap:

```text
environmental state awareness
runtime perception summarization
spatial cultural-site recommendation context
structured ContextOutput JSON
```

Dalam arsitektur hierarchy:

```text
Context Agent = child node / publisher
```

### 8.2 Five-Module Mapping

Di docstring, Context Agent dipetakan ke lima modul:

| Module | Peran |
|---|---|
| Profile | Specialist dalam environmental awareness dan spatial recommendation. |
| Perception | Membaca runtime payload dari backend. |
| Self-Action | Menyaring raw signals menjadi JSON state summary dan mempertahankan backend-ranked recommendation. |
| Mutual Interaction | Publisher ke Message Pool untuk Dialogue Agent dan NavMesh dispatcher. |
| Evolution | Audit akurasi state, missed events, wrong recommendations. |

### 8.3 Runtime Snapshot

Global variable:

```python
_RUNTIME_SNAPSHOT: dict = {}
```

Setter:

```python
set_context_runtime_snapshot(payload: dict)
```

Fungsi:

- menyimpan snapshot request aktif;
- membuat bounded tools hanya bisa membaca request aktif;
- menghindari tool membaca file eksternal atau sistem lain.

### 8.4 Bounded Tools

Context Agent punya 3 tool:

```text
tool_get_runtime_user_status()
tool_get_runtime_cultural_sites()
tool_get_runtime_recommendations()
```

Detail:

#### `tool_get_runtime_user_status`

Mengembalikan:

```text
_RUNTIME_SNAPSHOT["user_status"]
```

#### `tool_get_runtime_cultural_sites`

Mengembalikan:

```text
_RUNTIME_SNAPSHOT["cultural_sites"]
```

#### `tool_get_runtime_recommendations`

Mengembalikan:

```json
{
  "precomputed_recommendations": [...]
}
```

### 8.5 System Prompt

Prompt sudah diterjemahkan ke bahasa Indonesia.

Bagian utama:

```text
Peran
Tujuan
PROFILE
BOUNDED TOOLS
RUNTIME INPUT
PROCEDURE (ReAct Paradigm)
OUTPUT FORMAT
EXAMPLE
CONSTRAINTS
EVOLUTION
```

Struktur ReAct tetap dipertahankan:

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

### 8.6 Constraint Prompt

Context Agent harus:

- output hanya JSON;
- tidak pakai markdown;
- hanya gunakan bounded runtime tools;
- tidak refer hidden state;
- tidak asumsi data di luar snapshot;
- hanya include site `visited=false`;
- selalu output full schema;
- jika semua visited, output recommendations kosong dan nav_target kosong;
- tidak output status-only object;
- preserve order dari `precomputed_recommendations`;
- nav_target harus sama dengan rank-1 id.

### 8.7 Model

Default model object:

```python
OpenAIModel(
  client_args={
    "api_key": settings.OPENROUTER_API_KEY or "",
    "base_url": settings.OPENROUTER_BASE_URL,
  },
  model_id=settings.OPENROUTER_MODEL,
  params={
    "max_tokens": 800,
    "temperature": 0.7,
  },
)
```

Namun saat `USE_MOCK_MODEL=true`, orchestrator mengganti model agent menjadi `MockModel("mock-context")`.

---

## 9. Dialogue Agent

File:

```text
src/agents/dialogue_agent.py
```

### 9.1 Peran

Dialogue Agent bertanggung jawab terhadap:

```text
NPC persona
dialogue generation
subtitle generation
recommendation UI text
recommendation options
selection confirmation
```

Dalam arsitektur hierarchy:

```text
Dialogue Agent = parent node / subscriber / synthesiser
```

### 9.2 Five-Module Mapping

| Module | Peran |
|---|---|
| Profile | Persona sosial NPC dengan cultural lore dan traits. |
| Perception | Membaca ContextOutput JSON dari Message Pool. |
| Self-Action | Mengubah structured recommendations menjadi immersive NPC dialogue. |
| Mutual Interaction | Memanggil subtitle tool dan publish DialogueOutput. |
| Evolution | Audit persona alignment dan recommendation clarity. |

### 9.3 Persona NPC

Nama:

```text
Arif
```

Kepribadian:

```text
Pemandu budaya yang bijaksana dan hangat di museum warisan budaya VR.
```

Speech style:

```text
Ramah, meyakinkan, ringkas, natural dalam bahasa Indonesia,
menyisipkan konteks budaya singkat tanpa berlebihan.
```

### 9.4 Tool

Tool:

```python
tool_show_subtitle(text: str) -> bool
```

Fungsi:

- mengirim subtitle ke Unity HUD;
- wrapper ke `show_subtitle(text)`.

### 9.5 Input Shape A

Recommendation synthesis:

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

Rules:

- rank-1 adalah tujuan utama;
- rank-2/rank-3 adalah alternatif;
- options harus mengikuti order recommendations;
- spoken output harus mengarahkan player ke tujuan utama;
- subtitle harus singkat dan fokus ke tujuan utama.

### 9.6 Input Shape B

Selection confirmation:

```json
{
  "mode": "selection_confirmation",
  "selected_option": "...",
  "selected_site_id": "...",
  "context": {
    "timestamp": "...",
    "scene": "...",
    "user_action": "...",
    "recommendations": [...],
    "nav_target": "..."
  }
}
```

Rules:

- fokus pada konfirmasi pilihan player;
- spoken output dan subtitle wajib menyebut selected option;
- recommendation dialogue menyatakan pilihan diterima.

### 9.7 Output Format

Dialogue Agent harus output:

```json
{
  "spoken_output": "<ucapan NPC 2-4 kalimat dalam bahasa Indonesia>",
  "subtitle_output": "<satu kalimat <= 15 kata untuk HUD>",
  "recommendation_dialogue": "<kalimat singkat bahasa Indonesia untuk UI>",
  "recommendation_options": ["<option_1>", "<option_2>", "<option_3>"]
}
```

### 9.8 Constraint Prompt

Dialogue Agent harus:

- output hanya JSON;
- semua teks user-facing bahasa Indonesia;
- tidak menampilkan ID mentah jika ID teknis;
- tidak menampilkan koordinat;
- tidak menampilkan angka jarak;
- tidak menampilkan token sistem;
- tidak menampilkan istilah backend;
- tidak mengarang detail budaya yang tidak ada di input;
- menjaga persona hangat, membantu, dan relevan;
- subtitle maksimal 15 kata;
- options hanya nama objek;
- opsi pertama sama dengan rank-1/nav_target;
- jika recommendations kosong, options kosong;
- untuk selection confirmation, selected option disebut eksplisit.

### 9.9 Model

Default:

```python
OpenAIModel(
  client_args={
    "api_key": settings.OPENROUTER_API_KEY or "",
    "base_url": settings.OPENROUTER_BASE_URL,
  },
  model_id=settings.OPENROUTER_MODEL,
  params={
    "max_tokens": 500,
    "temperature": 0.7,
  },
)
```

Saat mock aktif, orchestrator mengganti model menjadi:

```text
MockModel("mock-dialogue")
```

---

## 10. Agents Public Exports

File:

```text
src/agents/__init__.py
```

Exports:

```python
from .context_agent import context_agent, get_context_agent, set_context_runtime_snapshot
from .dialogue_agent import dialogue_agent, get_dialogue_agent
```

`__all__`:

```text
context_agent
dialogue_agent
get_context_agent
get_dialogue_agent
set_context_runtime_snapshot
```

Catatan:

```text
Guidance Agent sudah retired dan diganti Unity NavMesh pathfinding.
```

---

## 11. Core Configuration

File:

```text
src/core/config.py
```

Class:

```python
class Settings(BaseSettings)
```

Field:

```text
PROJECT_NAME = "MultiAgentSystem"
VERSION = "0.1.0"
OPENAI_API_KEY
ANTHROPIC_API_KEY
OPENROUTER_API_KEY
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-4.1"
USE_MOCK_MODEL = True
BASE_DIR
```

Env file:

```text
.env
```

Config:

```python
SettingsConfigDict(
  env_file=".env",
  env_file_encoding="utf-8",
  extra="ignore"
)
```

Property:

```python
has_openrouter_credentials
```

Return `True` jika:

- `OPENROUTER_API_KEY` ada;
- tidak kosong;
- bukan placeholder `"your_openrouter_api_key_here"`.

Global instance:

```python
settings = Settings()
```

---

## 12. Mock Model

File:

```text
src/core/mock_model.py
```

Class:

```text
MockModel(Model)
```

Fungsi:

- memungkinkan testing lokal tanpa LLM API;
- mengembalikan strict JSON string;
- mengikuti interface Strands `Model`.

### 12.1 Mock Context Response

`MOCK_CONTEXT_RESPONSE` berisi:

```json
{
  "timestamp": "12:30:00",
  "scene": "Heritage_Museum_Wing_A",
  "user_action": "Examining_Artifact_ID_7",
  "recommendations": [
    {
      "rank": 1,
      "id": "Kujang",
      "name": "Kujang",
      "cultural_position": "6.211527, -1.27006, 7.544006"
    }
  ],
  "nav_target": "Kujang"
}
```

Important:

```text
Output mock context tidak sepenuhnya menentukan output final,
karena orchestrator mengoverride recommendation dan nav_target.
```

### 12.2 Mock Dialogue Response

`MOCK_DIALOGUE_RESPONSE` berisi dialog generik:

```text
Saya sudah menyiapkan beberapa rekomendasi objek budaya di sekitar Anda.
Silakan pilih tujuan yang paling ingin Anda kunjungi...
```

Known issue:

```text
Dialog awal mock tidak menyebut primary option/rank-1,
sehingga beberapa evaluasi Dialogue Agent gagal.
```

### 12.3 Selection Dialogue Response

Function:

```text
_build_selection_dialogue_response(payload_text)
```

Jika input mode:

```json
{
  "mode": "selection_confirmation"
}
```

Maka mock dapat menghasilkan dialog yang menyebut selected option.

### 12.4 Stream Interface

MockModel mengimplementasikan:

```text
stream(messages, tool_specs, system_prompt, **kwargs)
```

Menghasilkan event sequence:

```text
messageStart
contentBlockStart
contentBlockDelta
contentBlockStop
messageStop
metadata
```

---

## 13. Unity / VR Tools

Folder:

```text
src/vr_tools/
```

### 13.1 `unity_api.py`

Class:

```text
UnityAPIClient
```

Constructor:

```python
def __init__(self, base_url: str = "http://localhost:8080")
```

Field:

```text
base_url
logger
cultural_sites_path = settings.BASE_DIR / "data" / "cultural_sites.json"
```

#### `_load_cultural_sites`

Membaca:

```text
data/cultural_sites.json
```

Lalu validasi:

```python
CulturalSitesPayload.model_validate(payload)
```

#### `update_cultural_sites`

Validasi payload dan menulis ulang JSON ke:

```text
data/cultural_sites.json
```

#### `mark_site_visited`

Mencari site berdasarkan:

```text
site.name == site_name
atau
site.id == site_name
```

Jika ditemukan, set:

```text
visited = True
```

Catatan:

```text
Function ini ada tetapi flow /recommendation/select saat ini tidak mengubah visited.
```

#### `get(endpoint)`

Mock GET.

Supported endpoints:

```text
environment/delta
user/status
world/cultural_sites
```

`environment/delta` mock:

```json
{
  "timestamp": "2026-05-01T12:30:00Z",
  "scene": "Heritage_Museum_Wing_A",
  "events": ["Main_Gate:OPEN", "Chandelier:ON", "Spotlight_Altar:ON"],
  "user_position": {"x": 12.0, "y": 0.0, "z": 35.0}
}
```

`user/status` mock:

```json
{
  "player_position": "13.67265, 1.291507, 17.12134"
}
```

`world/cultural_sites`:

```text
membaca data/cultural_sites.json
```

#### `post(endpoint, data)`

Mock POST.

Saat ini:

```text
logging request
return True
```

Belum melakukan real:

```python
requests.post(f"{self.base_url}/{endpoint}", json=data)
```

Singleton:

```python
unity_client = UnityAPIClient()
```

### 13.2 `vr_actions.py`

Functions:

```text
set_nav_target(target_id: str) -> bool
show_subtitle(text: str, duration: float = 5.0)
```

#### `set_nav_target`

Payload:

```json
{
  "command": "NAV_TO_TARGET",
  "target_id": "..."
}
```

Endpoint mock:

```text
npc/navmesh
```

#### `show_subtitle`

Payload:

```json
{
  "command": "DISPLAY_SUBTITLE",
  "text": "...",
  "duration": 5.0
}
```

Endpoint mock:

```text
npc/ui
```

### 13.3 `vr_perception.py`

Functions:

```text
get_environment_data()
get_user_status()
get_cultural_sites()
```

Semua wrapper ke:

```python
unity_client.get(...)
```

### 13.4 `vr_tools/__init__.py`

Exports:

```text
get_environment_data
get_user_status
get_cultural_sites
set_nav_target
show_subtitle
```

---

## 14. Data Cultural Sites

File:

```text
data/cultural_sites.json
```

Contoh isi saat dibaca sebelumnya:

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
    }
  ]
}
```

Catatan:

- File ini dipakai oleh endpoint mock/admin `/world/cultural_sites`.
- Flow live `/context/run` lebih mengandalkan request body dari Unity.
- Evaluasi offline di `evals/scenarios.json` tidak membaca file ini.

---

## 15. Postman Collection

File:

```text
Multi Agent.postman_collection.json
```

Berisi koleksi request untuk:

```text
GET User Status
GET Cultural Sites
PUT Cultural Sites
POST Context Run
POST Dialogue Run
POST Recommendation Select
POST Run Simulation (Legacy)
```

Deskripsi collection menyatakan flow utama:

```text
/context/run -> /dialogue/run -> /recommendation/select
```

Postman collection juga menyediakan sample payload dan sample response untuk success/error cases.

---

## 16. Evaluation System

Folder:

```text
evals/
```

Sistem evaluasi ini dibuat untuk menjalankan evaluasi offline terhadap:

```text
Context Agent
Dialogue Agent
End-to-End pipeline
```

### 16.1 `evals/scenarios.json`

Berisi 7 skenario synthetic:

1. `three_unvisited_nearest_order`
2. `visited_site_filtered_out`
3. `single_remaining_site`
4. `all_sites_visited`
5. `tie_distance_uses_name_sort`
6. `compatibility_alias_cultural_objects`
7. `invalid_selected_option`

Important:

- Skenario ini tidak membaca `data/cultural_sites.json`.
- Skenario ini tidak memakai Unity live data.
- Objek seperti `Wayang`, `Batik`, `Visited Mask`, `Alpha`, `Beta`, `Zeta` adalah dummy untuk edge-case testing.

### 16.2 `evals/run_agent_evaluation.py`

Runner evaluasi.

Command:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py
```

Mode per agent:

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

### 16.3 Context Evaluation Metrics

Checks:

```text
request.valid_simulation_request
context.schema_valid
context.timestamp_matches_request
context.scene_matches_request
context.no_visited_sites_recommended
context.ranking_exact_match
context.nav_target_matches_rank_1
context.max_three_recommendations
```

Metrics:

```text
precision_at_3
recall_at_3
mrr
ndcg_at_3
recommendation_count
expected_count
```

### 16.4 Dialogue Evaluation Metrics

Checks:

```text
request.valid_simulation_request
dialogue.schema_valid
dialogue.options_match_context_order
dialogue.subtitle_max_15_words
dialogue.no_internal_tokens_or_coordinates
dialogue.primary_option_mentioned
dialogue.empty_recommendations_handled
dialogue.selected_option_mentioned
```

Metrics:

```text
subtitle_word_count
option_count
has_leak
```

### 16.5 End-to-End Evaluation

Checks combined:

```text
request checks
context checks
dialogue checks
selection checks
```

Selection checks:

```text
selection.accepted_valid_option
selection.nav_target_matches_selected_option
selection.expected_error
```

### 16.6 Current Evaluation Result

Hasil terakhir dengan `USE_MOCK_MODEL=true`:

#### Context Agent

```text
Scenarios: 7
Check pass rate: 100.00%
Context Precision@3: 1.000
Context Recall@3: 1.000
Context MRR: 0.857
Context NDCG@3: 1.000
```

#### Dialogue Agent

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

Artinya dialog awal sering tidak menyebut nama tujuan utama.

#### End-to-End

```text
Scenarios: 7
Check pass rate: 92.42%
End-to-end success rate: 14.29%
```

End-to-end rendah terutama karena Dialogue Agent mock terlalu generik.

### 16.7 `evals/dialogue_llm_judge_rubric.md`

Rubrik awal untuk LLM-as-a-judge Dialogue Agent.

Dimensi:

```text
context_relevance
faithfulness
navigation_clarity
persona_alignment
language_quality
ui_usefulness
technical_leak_safety
```

Skor:

```text
1-5
```

Pass suggestion:

```text
overall_score >= 4.0
technical_leak_safety harus 5
faithfulness minimal 4
selection mode wajib menyebut selected option
```

---

## 17. Documentation Files

Folder:

```text
docs/
```

### 17.1 `docs/evaluation_methodology.md`

Berisi metodologi evaluasi agent:

- apakah evaluasi sudah ada;
- dasar literatur;
- evaluasi Context Agent;
- evaluasi Dialogue Agent;
- evaluasi end-to-end;
- interpretasi hasil;
- rekomendasi untuk skripsi.

### 17.2 `docs/project_summary_for_llm_evaluation_research.md`

Briefing detail untuk meminta Claude/model lain melakukan research evaluasi LLM yang cocok untuk Context Agent dan Dialogue Agent.

Isi:

- project overview;
- struktur file;
- API flow;
- schema;
- Context Agent detail;
- Dialogue Agent detail;
- evaluation yang sudah ada;
- pertanyaan riset untuk Claude;
- output riset yang diharapkan.

### 17.3 `docs/project_full_documentation.md`

Dokumen ini.

Fungsi:

```text
menjelaskan keseluruhan project tanpa fokus hanya pada evaluasi.
```

---

## 18. Cara Menjalankan Backend

Dari folder project:

```bash
cd /Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project
```

Jalankan Flask app:

```bash
.venv/bin/python main.py
```

Atau jika perlu path eksplisit:

```bash
PYTHONPATH=src .venv/bin/python main.py
```

Server akan berjalan di:

```text
http://0.0.0.0:8080
```

Local request biasanya:

```text
http://127.0.0.1:8080
```

---

## 19. Cara Menjalankan Evaluasi

Dari folder project:

```bash
cd /Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project
```

Context Agent:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
```

Dialogue Agent:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue
```

End-to-end:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent e2e
```

Combined/default:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py
```

JSON output:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context --json
```

---

## 20. Cara Menggunakan API Secara Manual

### 20.1 Context Run

```bash
curl -X POST http://127.0.0.1:8080/context/run \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-01T12:30:00Z",
    "scene": "Heritage_Museum_Wing_A",
    "playerPosition": "8.0, 2.0, 10.0",
    "culturalSites": [
      {
        "id": "Julang Ngapak",
        "name": "Julang Ngapak",
        "cultural_position": "7.21, 2, 8.7",
        "visited": false
      },
      {
        "id": "Kujang",
        "name": "Kujang",
        "cultural_position": "8.99, 3, 13.65",
        "visited": false
      }
    ]
  }'
```

Ambil `simulation_id` dari response.

### 20.2 Dialogue Run

```bash
curl -X POST http://127.0.0.1:8080/dialogue/run \
  -H "Content-Type: application/json" \
  -d '{
    "simulationId": "<simulation_id_dari_context_run>"
  }'
```

### 20.3 Recommendation Select

```bash
curl -X POST http://127.0.0.1:8080/recommendation/select \
  -H "Content-Type: application/json" \
  -d '{
    "simulationId": "<simulation_id_dari_context_run>",
    "selectedOption": "Kujang"
  }'
```

---

## 21. Error Handling

### 21.1 Invalid JSON

Response:

```json
{
  "status": "error",
  "message": "Request body must be valid JSON with Content-Type: application/json"
}
```

Status:

```text
400
```

### 21.2 Invalid Request Body

Response:

```json
{
  "status": "error",
  "message": "Invalid request body",
  "details": [...]
}
```

Status:

```text
422
```

### 21.3 Simulation ID Tidak Ditemukan

Response:

```json
{
  "status": "error",
  "message": "simulationId tidak ditemukan. Jalankan /context/run terlebih dahulu."
}
```

Status:

```text
400
```

### 21.4 Invalid Selected Option

Response:

```json
{
  "status": "error",
  "message": "Opsi yang dipilih tidak ada dalam rekomendasi aktif."
}
```

Status:

```text
400
```

---

## 22. Known Limitations

### 22.1 Unity Integration Masih Mock

`unity_client.post` belum melakukan HTTP request real.

Saat ini:

```text
log payload
return True
```

Konsekuensi:

- `navmesh_ack=True` belum berarti Unity benar-benar menerima target.
- `subtitle_ack=True` belum berarti HUD Unity benar-benar menampilkan subtitle.

### 22.2 Session In-Memory

Session disimpan di memory:

```text
self.sessions: dict[str, SimulationSessionState] = {}
```

Konsekuensi:

- hilang jika server restart;
- tidak cocok untuk multi-process deployment tanpa shared store;
- tidak persistent.

### 22.3 `visited` Tidak Diubah Backend Saat Selection

Saat pemain memilih rekomendasi:

```text
backend hanya mengubah nav_target
backend tidak menandai site visited
```

Desain saat ini:

```text
Unity tetap source of truth untuk visited.
```

### 22.4 Dialogue Mock Terlalu Generik

Mock dialogue output tidak menyebut primary option pada dialog awal.

Ini menyebabkan:

```text
dialogue.primary_option_mentioned gagal
end-to-end success rendah
```

### 22.5 Dependencies Tidak Sepenuhnya Tercatat di `pyproject.toml`

Kode memakai:

```text
flask
pydantic-settings
```

Namun tidak terlihat eksplisit di `pyproject.toml`.

### 22.6 `README.md` Kosong

Project belum punya README utama.

Dokumen ini bisa menjadi dasar untuk mengisi README.

### 22.7 `server.py` Tidak Konsisten Dengan Runtime Utama

`server.py` memakai FastAPI minimal.

`main.py` memakai Flask dan berisi flow nyata.

Potential confusion:

```text
developer baru bisa mengira server.py adalah entry point utama.
```

### 22.8 Evaluasi Masih Offline Synthetic

Skenario evaluasi saat ini:

- synthetic;
- tidak memakai real Unity logs;
- tidak memakai user study;
- tidak mengukur latency real;
- tidak mengukur keberhasilan navigasi real di scene VR.

---

## 23. Current Git/Workspace Notes

Pada saat dokumentasi ini dibuat, worktree memiliki beberapa perubahan lokal:

```text
M .DS_Store
M data/cultural_sites.json
M src/agents/context_agent.py
M src/vr_tools/unity_api.py
?? docs/
?? evals/
?? test.tsx
```

Catatan:

- `context_agent.py` sudah diubah system prompt-nya ke bahasa Indonesia.
- `docs/` dan `evals/` adalah folder dokumentasi/evaluasi yang ditambahkan.
- `test.tsx` muncul sebagai untracked dan belum diketahui perannya dalam backend Python.
- `.DS_Store` adalah file metadata macOS.

---

## 24. Rekomendasi Pengembangan Berikutnya

### 24.1 Perbaiki Dialogue Agent atau MockModel

Karena evaluasi menunjukkan Dialogue Agent mock gagal menyebut primary option, perbaikan bisa dilakukan pada:

```text
src/core/mock_model.py
atau
src/agents/dialogue_agent.py prompt
atau
orchestrator fallback logic
```

Tujuan:

```text
spoken_output dan subtitle_output menyebut rank-1/rekomendasi utama.
```

Contoh expected:

```text
Mari menuju Julang Ngapak sebagai tujuan berikutnya.
```

### 24.2 Tambahkan Real Unity HTTP Client

Ubah `unity_api.py` agar `post` benar-benar melakukan request:

```python
requests.post(f"{self.base_url}/{endpoint}", json=data)
```

Perlu:

- timeout;
- error handling;
- retry policy;
- response validation;
- logging response.

### 24.3 Tambahkan Persistent Session Store

Pilihan:

```text
SQLite
Redis
PostgreSQL
file-based session
```

### 24.4 Lengkapi `pyproject.toml`

Tambahkan dependency eksplisit:

```text
flask
pydantic
pydantic-settings
requests
```

Jika ingin mempertahankan `server.py`:

```text
fastapi
uvicorn
```

### 24.5 Isi `README.md`

README sebaiknya mencakup:

- project overview;
- setup;
- env variables;
- run backend;
- endpoint list;
- run evaluation;
- known limitations.

### 24.6 Pakai Real Cultural Sites Dari Unity

Skenario evaluasi sebaiknya nanti diganti/ditambah dari:

```text
real Unity scene object names
real coordinates
real visited status logs
```

### 24.7 Tambahkan LLM-as-a-Judge Untuk Dialogue Agent

Gunakan rubric:

```text
context relevance
faithfulness
navigation clarity
persona alignment
language quality
UI usefulness
technical leak safety
```

Namun tetap perlu:

- deterministic checks;
- sample human evaluation;
- bias mitigation.

### 24.8 Tambahkan User Study VR

Metrik potensial:

```text
task completion rate
time to target
wrong navigation count
user satisfaction
perceived helpfulness
dialog clarity
trust in NPC guide
motion/navigation comfort
```

---

## 25. Ringkasan Satu Paragraf

Project ini adalah backend Flask untuk sistem NPC pemandu budaya berbasis multi-agent di VR. Unity mengirim snapshot runtime berupa posisi player, scene, timestamp, dan daftar cultural sites. Backend memvalidasi payload dengan Pydantic, menghitung rekomendasi objek budaya belum dikunjungi berdasarkan jarak Euclidean, lalu menjalankan Context Agent untuk membentuk `ContextOutput`. Target rank-1 dikirim ke Unity NavMesh melalui mock tool. Dialogue Agent kemudian membaca context dan menghasilkan `DialogueOutput` berupa ucapan NPC, subtitle HUD, teks UI, dan opsi rekomendasi. Pemain dapat memilih salah satu opsi melalui `/recommendation/select`, dan backend mengubah target navigasi sesuai pilihan. Sistem sudah memiliki evaluator offline untuk Context Agent, Dialogue Agent, dan end-to-end pipeline, dengan hasil awal menunjukkan Context Agent sangat kuat pada skenario synthetic, sementara Dialogue Agent/mock masih perlu diperbaiki karena dialog awal terlalu generik dan sering tidak menyebut tujuan utama.

---

## 26. Mental Model Project

Cara paling sederhana memahami project:

```text
Unity memberi data:
  "Player ada di posisi X, scene Y, objek A/B/C sudah atau belum dikunjungi."

Backend menghitung:
  "Objek terdekat yang belum dikunjungi adalah A, lalu B, lalu C."

Context Agent merapikan:
  "Ini context JSON yang valid untuk downstream."

NavMesh menerima:
  "NPC, pergi ke A."

Dialogue Agent berkata:
  "Mari menuju A. Kalau mau, B dan C juga bisa dipilih."

Player memilih:
  "Saya pilih B."

Backend merespons:
  "Baik, target diganti ke B. NPC akan memandu ke sana."
```

---

## 27. File Yang Paling Penting Untuk Dipahami Lebih Dulu

Urutan belajar yang disarankan:

1. `main.py`
2. `src/schema/models.py`
3. `src/orchestration/coordinator.py`
4. `src/agents/context_agent.py`
5. `src/agents/dialogue_agent.py`
6. `src/vr_tools/unity_api.py`
7. `src/core/config.py`
8. `src/core/mock_model.py`
9. `evals/run_agent_evaluation.py`
10. `evals/scenarios.json`

Jika memahami 10 file ini, hampir seluruh behavior project akan terbaca.
