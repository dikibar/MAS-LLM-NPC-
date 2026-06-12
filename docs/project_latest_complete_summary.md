# Ringkasan Lengkap Project Multi-Agent VR Cultural Guide

Dokumen ini merangkum kondisi terbaru project `my-project` setelah perubahan Context Agent, Dialogue Agent, orchestrator, evaluasi, mock model, schema, dan Postman collection.

Tanggal dokumen: 2026-06-01
Commit terbaru yang menjadi acuan: `2d4bcdc Refine context and dialogue agent evaluation flow`
Lokasi project: `/Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project`

## 1. Executive Summary

Project ini adalah backend Python untuk sistem Multi-Agent System (MAS) di aplikasi VR museum budaya. Sistem menerima snapshot runtime dari Unity, menentukan objek budaya yang paling relevan untuk direkomendasikan, mengirim target navigasi ke Unity NavMesh, lalu menghasilkan dialog NPC pemandu budaya dalam bahasa Indonesia.

Sistem saat ini memakai dua agent utama:

| Agent | Peran utama | Output utama | Konsumen output |
|---|---|---|---|
| Context Agent | Context reasoning dan penyusunan `ContextOutput` dari snapshot Unity | Rekomendasi top-3, `nav_target`, ringkasan konteks, alasan rekomendasi, intent dialog | Dialogue Agent, NavMesh, API response |
| Dialogue Agent | Sintesis dialog NPC dan opsi UI berdasarkan context | `spoken_output`, `subtitle_output`, `recommendation_dialogue`, `recommendation_options` | Unity TTS/lip-sync, HUD subtitle, UI pilihan |

Poin penting versi terbaru:

| Area | Kondisi terbaru |
|---|---|
| Bahasa prompt Context Agent | Sudah menggunakan bahasa Indonesia dengan struktur ReAct tetap dipertahankan |
| Peran Context Agent | Bukan hanya summary. Ia menjadi bounded context reasoning layer yang menghasilkan field interpretatif untuk Dialogue Agent |
| Ranking rekomendasi | Deterministik di backend berdasarkan Euclidean distance dan status `visited=false` |
| Guardrail context | Backend tetap memaksa `timestamp`, `scene`, `recommendations`, dan `nav_target` sesuai request dan ranking otoritatif |
| Dialogue Agent | Few-shot prompting dipertahankan dan diperkuat agar memakai semua field penting Context Agent |
| Alur utama API | `/context/run` -> `/dialogue/run` -> `/recommendation/select` |
| Mode test lokal | Menggunakan `USE_MOCK_MODEL=true` agar bisa berjalan tanpa network/API LLM |
| Evaluasi | Sudah ada runner evaluasi per agent dan end-to-end |
| Hasil evaluasi terakhir | 7 skenario, check pass rate 100%, end-to-end success rate 100% |

## 2. Tujuan Project

Tujuan utama project ini adalah membangun backend untuk NPC pemandu budaya dalam lingkungan VR. Backend ini membantu Unity melakukan tiga hal:

1. Mengambil snapshot posisi pemain, scene, dan daftar objek budaya.
2. Menentukan objek budaya belum dikunjungi yang paling relevan untuk dituju.
3. Menghasilkan dialog NPC yang natural, ringkas, dan selaras dengan rekomendasi.

Project ini tidak menyimpan state kunjungan sebagai source of truth utama. Unity tetap menjadi sumber kebenaran untuk:

| Data | Source of truth |
|---|---|
| `timestamp` | Unity request payload |
| `scene` | Unity request payload |
| `playerPosition` | Unity request payload |
| `visited` setiap objek budaya | Unity request payload |
| Objek yang sudah benar-benar dikunjungi | Unity |

Backend memproses snapshot yang diterima saat request. Jadi jika Unity ingin status kunjungan berubah, Unity harus mengirim `visited=true` pada request `/context/run` berikutnya.

## 3. Stack Teknologi

| Komponen | Teknologi |
|---|---|
| Bahasa utama | Python >= 3.11 |
| Web backend utama | Flask |
| Sample server tambahan | FastAPI di `server.py`, saat ini bukan entrypoint utama |
| Data validation | Pydantic |
| Env management | pydantic-settings dan `.env` |
| Agent framework | Strands Agents |
| Model provider real | OpenRouter compatible OpenAI API |
| Model default real | `openai/gpt-4.1` melalui OpenRouter |
| Mode offline/mock | `MockModel` di `src/core/mock_model.py` |
| Evaluasi | Python script deterministic/rule-based |
| API testing | Postman collection |

Dependencies dari `pyproject.toml`:

```toml
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.97.0",
    "strands-agents[openai]>=1.36.0",
    "strands-agents-builder>=0.1.10",
    "strands-agents-tools>=0.5.0",
]
```

Catatan:

| File | Kondisi |
|---|---|
| `README.md` | Saat dokumen ini dibuat, file masih kosong |
| `.env.example` | Berisi contoh API key dan `USE_MOCK_MODEL=true` |
| `.env` | Ada di lokal, sebaiknya dianggap private dan tidak didokumentasikan isinya |

## 4. Struktur File Project

File dan folder penting:

| Path | Fungsi |
|---|---|
| `main.py` | Entrypoint Flask utama. Menyediakan endpoint API runtime |
| `server.py` | Contoh FastAPI minimal. Bukan server utama untuk MAS saat ini |
| `pyproject.toml` | Metadata project dan dependencies |
| `uv.lock` | Lockfile dependency dari uv |
| `.env.example` | Template environment variable |
| `.python-version` | Versi Python lokal |
| `Multi Agent.postman_collection.json` | Collection Postman final untuk test API |
| `data/cultural_sites.json` | Registry mock cultural sites untuk endpoint admin/mock |
| `src/schema/models.py` | Semua Pydantic model request, output agent, session, dan message pool |
| `src/orchestration/coordinator.py` | Orchestrator utama, ranking, session, fallback, dispatch NavMesh/subtitle |
| `src/agents/context_agent.py` | Context Agent, prompt ReAct Indonesia, bounded tools runtime |
| `src/agents/dialogue_agent.py` | Dialogue Agent, persona NPC, few-shot prompt, subtitle tool |
| `src/core/config.py` | Konfigurasi project, env var, fallback mock model |
| `src/core/mock_model.py` | Mock LLM provider untuk test lokal tanpa API |
| `src/vr_tools/unity_api.py` | Mock bridge ke Unity API dan registry cultural sites |
| `src/vr_tools/vr_actions.py` | Action wrapper untuk NavMesh dan subtitle HUD |
| `src/vr_tools/vr_perception.py` | Perception wrapper untuk environment, user status, cultural sites |
| `evals/run_agent_evaluation.py` | Runner evaluasi context, dialogue, e2e, all |
| `evals/scenarios.json` | Dataset skenario evaluasi |
| `evals/README.md` | Cara menjalankan evaluasi |
| `evals/dialogue_llm_judge_rubric.md` | Rubrik tambahan untuk LLM-as-a-judge Dialogue Agent |
| `docs/context_agent_explanation.md` | Dokumentasi khusus Context Agent |
| `docs/evaluation_methodology.md` | Dokumentasi metodologi evaluasi |
| `docs/project_full_documentation.md` | Dokumentasi project versi sebelumnya yang sangat panjang |
| `docs/project_summary_for_llm_evaluation_research.md` | Summary khusus untuk riset evaluasi LLM oleh model lain |
| `docs/project_latest_complete_summary.md` | Dokumen ini |

File/folder generated atau pendukung:

| Path | Catatan |
|---|---|
| `.venv/` | Virtual environment lokal |
| `__pycache__/` | Cache Python generated |
| `.DS_Store` | Metadata macOS |
| `Python-3.11.15.tgz.sigstore` | File signature Python, bukan source utama MAS |
| `test.tsx` | File tambahan di root, tidak menjadi bagian alur backend Python utama |

## 5. Konfigurasi Environment

Contoh dari `.env.example`:

```env
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4.1
USE_MOCK_MODEL=true

PROJECT_NAME=MultiAgentSystem
LOG_LEVEL=INFO
```

Makna environment penting:

| Variable | Fungsi |
|---|---|
| `OPENROUTER_API_KEY` | API key untuk real LLM via OpenRouter |
| `OPENROUTER_BASE_URL` | Base URL OpenRouter compatible OpenAI API |
| `OPENROUTER_MODEL` | Model yang dipakai Context Agent dan Dialogue Agent |
| `USE_MOCK_MODEL` | Jika `true`, sistem memakai mock LLM lokal |
| `PROJECT_NAME` | Nama project |
| `LOG_LEVEL` | Level logging |

Fallback model:

| Kondisi | Model yang dipakai |
|---|---|
| `USE_MOCK_MODEL=true` | `MockModel` |
| `USE_MOCK_MODEL=false`, tetapi `OPENROUTER_API_KEY` kosong/placeholder | `MockModel` |
| `USE_MOCK_MODEL=false` dan API key valid | OpenRouter model dari `OPENROUTER_MODEL` |

## 6. Cara Menjalankan Project

Masuk ke folder project:

```bash
cd /Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project
```

Mode mock yang disarankan untuk test lokal:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python main.py
```

Jika berhasil, Flask berjalan di:

```text
http://127.0.0.1:8080
```

Mode real LLM:

```bash
env USE_MOCK_MODEL=false PYTHONPATH=src .venv/bin/python main.py
```

Syarat mode real LLM:

| Syarat | Keterangan |
|---|---|
| `OPENROUTER_API_KEY` valid | Wajib agar tidak fallback ke mock |
| Network tersedia | Diperlukan untuk memanggil model real |
| Prompt menghasilkan JSON valid | Orchestrator punya fallback, tetapi kualitas real tetap bergantung output model |

## 7. Arsitektur Sistem

Arsitektur saat ini paling tepat disebut:

```text
Hybrid hierarchical-orchestrated multi-agent workflow
```

Penjelasan:

| Aspek | Kondisi aktual |
|---|---|
| Multi-agent | Ada dua agent LLM: Context Agent dan Dialogue Agent |
| Hierarchical | Dialogue Agent berperan sebagai parent/synthesiser yang memakai output Context Agent |
| Orchestrated | `HierarchicalOrchestrator` mengatur urutan eksekusi dan guardrail |
| Hybrid deterministic + LLM | Ranking dan field kritis dijaga backend, field interpretatif dibantu LLM |
| Parallel fan-out terbatas | Setelah ContextOutput tersedia, NavMesh dan Dialogue sama-sama mengonsumsi context |

Penting:

Sistem ini bukan parallel workflow murni karena Context Agent harus berjalan lebih dulu sebelum Dialogue Agent. Namun setelah context tersedia, output context dapat dipakai oleh beberapa downstream consumer, yaitu NavMesh dan Dialogue Agent.

Diagram alur konseptual:

```text
Unity Runtime Snapshot
        |
        v
POST /context/run
        |
        v
Pydantic Validation + Alias Normalization
        |
        v
Backend Ranking of Unvisited Sites
        |
        v
Context Agent Reasoning
        |
        v
ContextOutput
        |
        +---------------------> Unity NavMesh target dispatch
        |
        v
Saved Session by simulation_id
        |
        v
POST /dialogue/run
        |
        v
Dialogue Agent Few-Shot Synthesis
        |
        v
DialogueOutput
        |
        +---------------------> Unity HUD subtitle
        +---------------------> Unity UI options
        |
        v
POST /recommendation/select
        |
        v
Selected option validation + NavMesh retarget + selection dialogue
```

## 8. API Endpoint Utama

Backend utama berada di `main.py` dan berjalan dengan Flask pada port `8080`.

### 8.1 `GET /user/status`

Fungsi:

Mengambil posisi player dari mock/backend status endpoint.

Response mock:

```json
{
  "player_position": "13.67265, 1.291507, 17.12134"
}
```

Catatan:

Endpoint ini berguna untuk mock/admin. Dalam flow live terbaru, Unity mengirim `playerPosition` langsung pada `/context/run`.

### 8.2 `GET /world/cultural_sites`

Fungsi:

Mengambil registry cultural sites dari `data/cultural_sites.json`.

Data saat dokumen ini dibuat:

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

Endpoint ini bukan source utama flow live Unity. Source utama flow live adalah body request `/context/run`.

### 8.3 `PUT /world/cultural_sites`

Fungsi:

Memperbarui registry mock cultural sites backend.

Body:

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

Validasi:

| Kondisi | Response |
|---|---|
| Body bukan JSON valid | HTTP 400 |
| `sites` bukan array | HTTP 422 |
| Item dalam `sites` bukan object | HTTP 422 |
| Payload valid | HTTP 200 |

### 8.4 `POST /context/run`

Fungsi:

Flow utama tahap 1. Unity mengirim snapshot runtime. Backend menjalankan Context Agent, menentukan rekomendasi, mengirim target NavMesh, dan menyimpan session.

Request canonical:

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
    },
    {
      "id": "Kujang",
      "name": "Kujang",
      "cultural_position": "8.99, 3, 13.65",
      "visited": false
    },
    {
      "id": "Surabi",
      "name": "Surabi",
      "cultural_position": "5.448, 3, 16.256",
      "visited": false
    }
  ]
}
```

Alias request yang diterima:

| Alias | Dinormalisasi menjadi |
|---|---|
| `cultural_sites` | `culturalSites` |
| `culturalObject` | `culturalSites` |
| `culturalObjects` | `culturalSites` |
| `coordinate` | `cultural_position` |
| `isObjectVisited` | `visited` |

Response sukses:

```json
{
  "status": "success",
  "message": "Context agent executed successfully",
  "data": {
    "simulation_id": "...",
    "context": {
      "timestamp": "2026-05-01T12:30:00Z",
      "scene": "Heritage_Museum_Wing_A",
      "user_action": "Pemain berada di area dengan beberapa tujuan budaya yang belum dikunjungi.",
      "context_summary": "Pemain berada di Heritage_Museum_Wing_A dengan 3 objek budaya belum dikunjungi yang dapat direkomendasikan.",
      "situation_type": "multiple_recommendations",
      "recommendation_reason": "Julang Ngapak diprioritaskan sebagai tujuan utama karena menjadi kandidat terdekat yang belum dikunjungi. Alternatif yang tersedia: Kujang, Surabi.",
      "dialogue_intent": "guide_to_primary_with_alternatives",
      "recommendations": [
        {
          "rank": 1,
          "id": "Julang Ngapak",
          "name": "Julang Ngapak",
          "cultural_position": "7.21, 2, 8.7"
        }
      ],
      "nav_target": "Julang Ngapak"
    },
    "navmesh_ack": true
  }
}
```

### 8.5 `POST /dialogue/run`

Fungsi:

Flow utama tahap 2. Unity mengirim `simulationId` dari `/context/run`. Backend mengambil context dari session dan menjalankan Dialogue Agent.

Request:

```json
{
  "simulationId": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e"
}
```

Response sukses:

```json
{
  "status": "success",
  "message": "Dialogue agent executed successfully",
  "data": {
    "simulation_id": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e",
    "dialogue": {
      "spoken_output": "Ada beberapa tujuan budaya yang masih bisa kita jelajahi. Mari mulai dari Julang Ngapak sebagai tujuan utama berikutnya. Jika ingin memilih jalur lain, Anda juga dapat memilih Kujang, Surabi.",
      "subtitle_output": "Mari menuju Julang Ngapak.",
      "recommendation_dialogue": "Pemain berada di Heritage_Museum_Wing_A dengan 3 objek budaya belum dikunjungi yang dapat direkomendasikan.",
      "recommendation_options": [
        "Julang Ngapak",
        "Kujang",
        "Surabi"
      ]
    }
  }
}
```

Error penting:

| Kondisi | Response |
|---|---|
| `simulationId` kosong | HTTP 422 |
| `simulationId` tidak ditemukan | HTTP 400 dengan pesan jalankan `/context/run` terlebih dahulu |

### 8.6 `POST /recommendation/select`

Fungsi:

Flow utama tahap 3. Unity mengirim opsi rekomendasi yang dipilih pemain. Backend memvalidasi opsi, mengubah `nav_target` session ke pilihan tersebut, dispatch NavMesh, dan menghasilkan dialog konfirmasi.

Request:

```json
{
  "simulationId": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e",
  "selectedOption": "Kujang"
}
```

Aturan:

| Field | Aturan |
|---|---|
| `simulationId` | Harus berasal dari `/context/run` |
| `selectedOption` | Harus sama persis dengan salah satu item `dialogue.recommendation_options` |
| `visited` | Tidak diubah backend. Unity tetap source of truth |

Response sukses:

```json
{
  "status": "success",
  "message": "Recommendation option selected successfully",
  "data": {
    "selected_option": "Kujang",
    "selected_site_id": "Kujang",
    "navmesh_ack": true,
    "spoken_output": "Baik, saya akan memandu Anda menuju Kujang. Objek budaya ini menjadi tujuan berikutnya, dan saya akan menemani perjalanan Anda sampai tiba.",
    "subtitle_output": "Mari menuju Kujang."
  }
}
```

### 8.7 `POST /run-simulation`

Fungsi:

Endpoint kompatibilitas lama. Menjalankan context dan dialogue sekaligus.

Status terbaru:

| Aspek | Status |
|---|---|
| Masih tersedia | Ya |
| Direkomendasikan untuk integrasi baru | Tidak |
| Flow baru yang disarankan | `/context/run` -> `/dialogue/run` -> `/recommendation/select` |

## 9. Data Model dan Schema

Semua schema utama berada di `src/schema/models.py`.

### 9.1 `SimulationRequest`

Request utama untuk `/context/run` dan `/run-simulation`.

Field:

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `timestamp` | `str` | Ya | Timestamp dari Unity |
| `scene` | `str` | Ya | Nama scene Unity |
| `playerPosition` | `str` | Ya | Format `"x, y, z"` |
| `culturalSites` | `List[CulturalSite]` | Ya | Daftar objek budaya live |

Validasi:

| Field | Validasi |
|---|---|
| `timestamp` | Tidak boleh kosong |
| `scene` | Tidak boleh kosong |
| `playerPosition` | Harus 3 angka dipisah koma |
| `culturalSites` | Harus list model `CulturalSite` |

Normalisasi alias:

Jika input memakai `culturalObject`, `culturalObjects`, atau `cultural_sites`, model akan mengubahnya ke `culturalSites`.

### 9.2 `CulturalSite`

Field:

| Field | Tipe | Keterangan |
|---|---|---|
| `id` | `str` | ID Unity/GameObject atau identitas objek |
| `name` | `str` | Nama display untuk UI/dialog |
| `cultural_position` | `str` | Koordinat world-space format `"x, y, z"` |
| `visited` | `bool` | Status apakah objek sudah dikunjungi |

Validasi:

| Field | Validasi |
|---|---|
| `id` | Tidak boleh kosong |
| `name` | Tidak boleh kosong |
| `cultural_position` | Harus 3 angka dipisah koma |

### 9.3 `SiteRecommendation`

Output rekomendasi satu objek budaya.

| Field | Tipe | Keterangan |
|---|---|---|
| `rank` | `int` | 1 untuk target utama, 2-3 alternatif |
| `id` | `str` | ID objek untuk NavMesh |
| `name` | `str` | Nama yang boleh ditampilkan ke user |
| `cultural_position` | `str` | Koordinat internal, tidak boleh dibocorkan di dialog |

### 9.4 `ContextOutput`

Output final Context Agent yang sudah divalidasi dan dijaga backend.

| Field | Sumber utama | Fungsi |
|---|---|---|
| `timestamp` | Request Unity, dipaksa backend | Grounding waktu runtime |
| `scene` | Request Unity, dipaksa backend | Grounding lokasi scene |
| `user_action` | LLM atau fallback backend | Interpretasi singkat keadaan pemain |
| `context_summary` | Fallback backend otoritatif | Ringkasan konteks untuk Dialogue Agent |
| `situation_type` | LLM divalidasi terhadap fallback backend | Kategori situasi |
| `recommendation_reason` | LLM jika grounded, fallback backend jika tidak | Alasan singkat rekomendasi utama |
| `dialogue_intent` | LLM divalidasi terhadap fallback backend | Arah respons Dialogue Agent |
| `recommendations` | Backend ranking otoritatif | Top-3 objek belum dikunjungi |
| `nav_target` | Backend dari rank-1 | Target NavMesh aktif |

Nilai `situation_type` yang didukung:

| Nilai | Arti |
|---|---|
| `multiple_recommendations` | Ada lebih dari satu rekomendasi |
| `single_recommendation` | Hanya ada satu rekomendasi |
| `all_sites_visited` | Tidak ada objek baru yang belum dikunjungi |
| `exploration_context` | Konteks eksplorasi ringan |

Nilai `dialogue_intent` yang didukung:

| Nilai | Arti |
|---|---|
| `guide_to_primary_with_alternatives` | Arahkan ke target utama sambil menawarkan alternatif |
| `guide_to_single_primary` | Arahkan ke satu target saja |
| `no_new_destination` | Tidak ada destinasi baru |
| `encourage_exploration` | Dorong eksplorasi tanpa tujuan spesifik |

### 9.5 `DialogueOutput`

Output final Dialogue Agent.

| Field | Fungsi |
|---|---|
| `spoken_output` | Ucapan NPC untuk TTS/lip-sync |
| `subtitle_output` | Subtitle singkat untuk HUD, target <= 15 kata |
| `recommendation_dialogue` | Teks UI untuk menjelaskan pilihan rekomendasi |
| `recommendation_options` | Tombol opsi yang bisa dipilih user |

### 9.6 `RecommendationSelectionResponse`

Output saat user memilih salah satu rekomendasi.

| Field | Fungsi |
|---|---|
| `selected_option` | Nama opsi yang dipilih user |
| `selected_site_id` | ID site yang dipilih |
| `navmesh_ack` | Status ack dari dispatch NavMesh |
| `spoken_output` | Dialog konfirmasi |
| `subtitle_output` | Subtitle konfirmasi |

### 9.7 `SimulationSessionState`

Session in-memory per `simulation_id`.

| Field | Fungsi |
|---|---|
| `simulation_id` | ID session UUID |
| `player_position` | Posisi pemain pada context run |
| `cultural_sites` | Payload cultural sites saat context run |
| `context` | ContextOutput tersimpan |
| `dialogue` | DialogueOutput terakhir, optional |

### 9.8 `MessagePoolState`

Blackboard sederhana antar agent.

| Field | Fungsi |
|---|---|
| `latest_context` | ContextOutput terakhir |
| `latest_dialogue` | DialogueOutput terakhir |
| `history` | Daftar `AgentMessage` |

## 10. Context Agent

File: `src/agents/context_agent.py`

### 10.1 Peran Context Agent

Context Agent adalah bounded context reasoning agent. Ia membaca snapshot runtime yang sudah disiapkan backend dan menghasilkan context terstruktur untuk downstream.

Tugas Context Agent saat ini:

| Tugas | Dilakukan oleh |
|---|---|
| Membaca status user dari snapshot runtime | Context Agent via bounded tool |
| Membaca cultural sites dari snapshot runtime | Context Agent via bounded tool |
| Membaca rekomendasi precomputed backend | Context Agent via bounded tool |
| Menyusun `user_action` | Context Agent, dengan fallback backend |
| Menyusun `context_summary` | Backend fallback otoritatif saat merge |
| Menentukan `situation_type` | Context Agent, tetapi harus cocok dengan default backend |
| Menyusun `recommendation_reason` | Context Agent jika grounded, fallback backend jika tidak |
| Menentukan `dialogue_intent` | Context Agent, tetapi harus cocok dengan default backend |
| Menentukan ranking top-3 | Backend, bukan LLM |
| Menentukan `nav_target` final | Backend, bukan LLM |

Jadi Context Agent tidak hanya melakukan summary. Ia memberi interpretasi kontekstual yang dipakai Dialogue Agent. Namun field kritis untuk navigasi dan ranking tetap dikunci oleh backend.

### 10.2 Prompt Context Agent

Prompt Context Agent sudah menggunakan bahasa Indonesia.

Struktur teknik prompting ReAct tetap dipertahankan:

| Tahap ReAct | Implementasi |
|---|---|
| Reasoning 1 | Memahami semua info valid berasal dari bounded tools |
| Action 1 | Memanggil `tool_get_runtime_user_status` |
| Observation 1 | Membaca posisi pemain |
| Reasoning 2 | Memeriksa state pendukung tanpa membuat ranking baru |
| Action 2 | Memanggil `tool_get_runtime_cultural_sites` dan `tool_get_runtime_recommendations` |
| Observation 2 | Membaca visited flags dan precomputed ranking |
| Reasoning 3 | Menyimpulkan field interpretatif tanpa mengarang fakta |
| Action final | Output satu JSON `ContextOutput` |
| Observation downstream | NavMesh dan Dialogue Agent memakai JSON tersebut |

### 10.3 Bounded Tools Context Agent

| Tool | Fungsi |
|---|---|
| `tool_get_runtime_user_status()` | Membaca `user_status` dari `_RUNTIME_SNAPSHOT` |
| `tool_get_runtime_cultural_sites()` | Membaca `cultural_sites` dari `_RUNTIME_SNAPSHOT` |
| `tool_get_runtime_recommendations()` | Membaca `precomputed_recommendations` dari `_RUNTIME_SNAPSHOT` |

Karakteristik tools:

| Aspek | Keterangan |
|---|---|
| Sumber data | Hanya snapshot request yang disiapkan backend |
| Akses eksternal | Tidak ada |
| File access | Tidak ada |
| Unity direct call | Tidak ada |
| Fungsi utama | Membatasi agent agar tidak mengarang sumber kebenaran lain |

### 10.4 Output Context Agent

Schema wajib:

```json
{
  "timestamp": "<timestamp>",
  "scene": "<scene_name>",
  "user_action": "<apa yang sedang dilakukan pengguna>",
  "context_summary": "<ringkasan situasi runtime>",
  "situation_type": "<multiple_recommendations|single_recommendation|all_sites_visited|exploration_context>",
  "recommendation_reason": "<alasan rekomendasi utama>",
  "dialogue_intent": "<guide_to_primary_with_alternatives|guide_to_single_primary|no_new_destination|encourage_exploration>",
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

### 10.5 Guardrail Context Agent

Guardrail utama berada di `src/orchestration/coordinator.py`.

| Function | Guardrail |
|---|---|
| `_rank_unvisited_sites` | Memfilter `visited=true`, ranking berdasarkan jarak, maksimal 3 |
| `_default_context_interpretation` | Membuat fallback field interpretatif yang aman |
| `_merge_context_interpretation` | Mengambil interpretasi LLM hanya jika sesuai dan grounded |
| `_build_context_output` | Membangun ContextOutput final jika parsing LLM gagal |
| `_run_context_agent` | Menimpa field kritis dengan versi backend otoritatif |

Field yang dipaksa backend:

| Field | Alasan |
|---|---|
| `timestamp` | Harus sama dengan request Unity |
| `scene` | Harus sama dengan request Unity |
| `context_summary` | Agar grounded ke jumlah rekomendasi dan scene |
| `situation_type` | Harus sesuai kondisi rekomendasi |
| `dialogue_intent` | Harus sesuai kondisi rekomendasi |
| `recommendations` | Harus sesuai ranking backend |
| `nav_target` | Harus sama dengan rank-1 atau kosong |

Field yang boleh dipengaruhi LLM jika aman:

| Field | Kondisi diterima |
|---|---|
| `user_action` | Non-empty |
| `recommendation_reason` | Menyebut primary site dan tidak mengandung nama tidak grounded |

### 10.6 Ranking Rekomendasi

Ranking dilakukan oleh backend, bukan LLM.

Formula:

```text
distance = sqrt((player_x - site_x)^2 + (player_y - site_y)^2 + (player_z - site_z)^2)
```

Aturan ranking:

| Aturan | Keterangan |
|---|---|
| Filter visited | Hanya `visited=false` yang bisa direkomendasikan |
| Sort utama | Euclidean distance dari `playerPosition` |
| Tie-breaker | `site.name.lower()` |
| Limit | Maksimal 3 rekomendasi |
| `nav_target` | ID dari rekomendasi rank-1 |
| Jika tidak ada rekomendasi | `recommendations=[]`, `nav_target=""` |

## 11. Dialogue Agent

File: `src/agents/dialogue_agent.py`

### 11.1 Peran Dialogue Agent

Dialogue Agent adalah NPC persona dan synthesiser. Ia mengubah `ContextOutput` menjadi dialog NPC dan opsi UI.

NPC persona:

| Atribut | Nilai |
|---|---|
| Nama | Arif |
| Identitas | Pemandu budaya yang bijaksana dan hangat |
| Gaya bicara | Ramah, meyakinkan, ringkas, bahasa Indonesia natural |
| Domain | Arsitektur warisan, artefak, tradisi seremonial, konteks ruang budaya |

### 11.2 Input Dialogue Agent

Dialogue Agent menerima dua shape input.

Shape A: recommendation synthesis.

Digunakan oleh `/dialogue/run`.

```json
{
  "timestamp": "...",
  "scene": "...",
  "user_action": "...",
  "context_summary": "...",
  "situation_type": "...",
  "recommendation_reason": "...",
  "dialogue_intent": "...",
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

Shape B: selection confirmation.

Digunakan oleh `/recommendation/select`.

```json
{
  "mode": "selection_confirmation",
  "selected_option": "...",
  "selected_site_id": "...",
  "context": {
    "timestamp": "...",
    "scene": "...",
    "user_action": "...",
    "context_summary": "...",
    "situation_type": "...",
    "recommendation_reason": "...",
    "dialogue_intent": "...",
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

### 11.3 Field Context yang Dipakai Dialogue Agent

| Field Context | Dipakai untuk |
|---|---|
| `recommendations` | Nama opsi, urutan opsi, tujuan utama |
| `nav_target` | Validasi tujuan aktif |
| `situation_type` | Menentukan pola dialog |
| `dialogue_intent` | Menentukan intensi respons |
| `recommendation_reason` | Bahan alasan singkat dalam `spoken_output` |
| `context_summary` | Bahan `recommendation_dialogue` UI |
| `user_action` | Sinyal kondisi pemain jika membantu |
| `scene` | Konteks lokasi jika perlu |

Mapping `situation_type`:

| `situation_type` | Pola dialog |
|---|---|
| `multiple_recommendations` | Arahkan ke rank-1 dan sebut alternatif |
| `single_recommendation` | Fokus pada satu tujuan |
| `all_sites_visited` | Tidak memaksa navigasi, ajak menikmati area |
| `exploration_context` | Dorong eksplorasi ringan |

Mapping `dialogue_intent`:

| `dialogue_intent` | Respons |
|---|---|
| `guide_to_primary_with_alternatives` | Pemanduan tujuan utama + opsi alternatif |
| `guide_to_single_primary` | Pemanduan satu tujuan |
| `no_new_destination` | Tidak ada rekomendasi baru |
| `encourage_exploration` | Dorongan eksplorasi |

### 11.4 Few-Shot Prompting

Teknik prompting Dialogue Agent tetap menggunakan few-shot.

Few-shot examples yang tersedia:

| Example | Kondisi |
|---|---|
| Example 1 | Shape A dengan `multiple_recommendations` |
| Example 2 | Shape A dengan `single_recommendation` |
| Example 3 | Shape A dengan `all_sites_visited` |
| Example 4 | Shape B untuk konfirmasi pilihan user |

Tujuan few-shot:

| Tujuan | Penjelasan |
|---|---|
| Konsistensi format | Output harus JSON valid |
| Konsistensi persona | Arif harus hangat dan ringkas |
| Konsistensi UI | Opsi harus mengikuti rekomendasi context |
| Grounding | Tidak mengarang detail budaya yang tidak ada |
| Mode handling | Agent memahami rekomendasi awal vs konfirmasi pilihan |

### 11.5 Tool Dialogue Agent

| Tool | Fungsi |
|---|---|
| `tool_show_subtitle(text)` | Mengirim `subtitle_output` ke Unity HUD |

Tool ini memanggil `show_subtitle` dari `src/vr_tools/vr_actions.py`.

### 11.6 Constraint Dialogue Agent

Constraint utama:

| Constraint | Alasan |
|---|---|
| Output hanya JSON | Agar mudah diparse |
| Semua teks user-facing bahasa Indonesia | Konsistensi pengalaman user |
| Jangan tampilkan ID mentah | ID untuk sistem, bukan user |
| Jangan tampilkan koordinat | Koordinat internal |
| Jangan tampilkan istilah backend/NavMesh/tool | Hindari technical leak |
| `subtitle_output` <= 15 kata | Cocok untuk HUD |
| `recommendation_options` hanya nama objek | Cocok untuk tombol UI |
| Mode selection wajib menyebut selected option | User butuh konfirmasi jelas |

### 11.7 Guardrail Dialogue Agent

Guardrail berada di `HierarchicalOrchestrator.run_dialogue_cycle`.

Aturan:

| Guardrail | Perilaku |
|---|---|
| Parse JSON gagal | Pakai fallback deterministic |
| Output tidak menyebut primary recommendation | Pakai fallback deterministic |
| `recommendation_options` | Dipaksa sama dengan context recommendations |
| Subtitle dispatch | Subtitle tetap dikirim via `_dispatch_subtitle` |

Fallback deterministic:

| Kondisi | Output |
|---|---|
| Tidak ada rekomendasi | Dialog aman bahwa belum ada tujuan baru |
| Ada satu rekomendasi | Mengajak menuju primary |
| Ada beberapa rekomendasi | Mengajak menuju primary dan menyebut alternatif |

Guardrail selection:

| Guardrail | Perilaku |
|---|---|
| `selectedOption` tidak ada di context recommendations | Raise `ValueError` |
| Dialog selection tidak menyebut selected site | Pakai fallback deterministic |
| `recommendation_options` | Dipaksa tetap mengikuti context recommendations |

## 12. Orchestrator

File: `src/orchestration/coordinator.py`

Class utama: `HierarchicalOrchestrator`

### 12.1 Fungsi Orchestrator

Orchestrator bertugas:

| Tugas | Detail |
|---|---|
| Membaca request API | Melalui `SimulationRequest` |
| Membentuk runtime context | Environment, user status, cultural sites, precomputed recommendations |
| Ranking rekomendasi | Deterministic Euclidean distance |
| Menjalankan Context Agent | Dengan bounded runtime snapshot |
| Validasi dan merge context | Menggabungkan output LLM dengan fallback backend |
| Dispatch NavMesh | Mengirim `nav_target` ke Unity |
| Menyimpan session | Berdasarkan `simulation_id` |
| Menjalankan Dialogue Agent | Menggunakan context dari session |
| Dispatch subtitle | Mengirim subtitle ke Unity HUD |
| Menangani pilihan user | Validasi pilihan dan retarget NavMesh |

### 12.2 InMemoryMessagePool

`InMemoryMessagePool` menyimpan:

| Data | Fungsi |
|---|---|
| `latest_context` | Context terakhir |
| `latest_dialogue` | Dialogue terakhir |
| `history` | Riwayat message |
| `sessions` | Map `simulation_id` ke `SimulationSessionState` |

Keterbatasan:

| Keterbatasan | Dampak |
|---|---|
| In-memory | Hilang saat server restart |
| Belum persistent DB | Belum cocok untuk production multi-instance |
| Belum TTL/session cleanup | Session bisa bertambah selama proses hidup |

### 12.3 Run Context Cycle

Function: `run_context_cycle(sim_request)`

Alur:

1. Print header context workflow.
2. Build runtime context dari request.
3. Rank unvisited cultural sites.
4. Run Context Agent.
5. Publish context ke message pool.
6. Dispatch `nav_target` ke Unity NavMesh.
7. Generate `simulation_id`.
8. Save session.
9. Return `ContextCycleResponse`.

### 12.4 Run Dialogue Cycle

Function: `run_dialogue_cycle(simulation_id)`

Alur:

1. Ambil session berdasarkan `simulation_id`.
2. Jika tidak ada, raise `ValueError`.
3. Dump context menjadi JSON.
4. Run Dialogue Agent.
5. Validasi primary recommendation disebut.
6. Jika gagal, fallback deterministic.
7. Paksa `recommendation_options` mengikuti context.
8. Dispatch subtitle.
9. Publish dialogue ke message pool.
10. Update session.
11. Return `DialogueCycleResponse`.

### 12.5 Handle Recommendation Selection

Function: `handle_recommendation_selection(simulation_id, selected_option)`

Alur:

1. Ambil session.
2. Validasi selected option ada di recommendations.
3. Update context `nav_target` ke selected site.
4. Dispatch NavMesh ke selected site.
5. Build selection confirmation payload untuk Dialogue Agent.
6. Run Dialogue Agent.
7. Validasi dialog menyebut selected site.
8. Jika gagal, fallback deterministic.
9. Dispatch subtitle.
10. Publish dialogue.
11. Save updated session.
12. Return `RecommendationSelectionResponse`.

## 13. Unity Tools dan Mock Bridge

### 13.1 `src/vr_tools/unity_api.py`

Class: `UnityAPIClient`

Fungsi:

| Method | Fungsi |
|---|---|
| `_load_cultural_sites` | Membaca `data/cultural_sites.json` |
| `update_cultural_sites` | Menulis registry mock cultural sites |
| `mark_site_visited` | Menandai site visited pada registry mock |
| `get` | Simulasi GET ke Unity |
| `post` | Simulasi POST ke Unity, selalu return `True` |

Mock endpoint internal:

| Endpoint | Response |
|---|---|
| `environment/delta` | Timestamp, scene, events, user_position mock |
| `user/status` | Player position mock |
| `world/cultural_sites` | Isi `data/cultural_sites.json` |
| `npc/navmesh` | Simulasi ack true via `post` |
| `npc/ui` | Simulasi ack true via `post` |

### 13.2 `src/vr_tools/vr_actions.py`

| Function | Payload ke Unity mock |
|---|---|
| `set_nav_target(target_id)` | `{"command": "NAV_TO_TARGET", "target_id": target_id}` |
| `show_subtitle(text, duration=5.0)` | `{"command": "DISPLAY_SUBTITLE", "text": text, "duration": duration}` |

### 13.3 `src/vr_tools/vr_perception.py`

| Function | Endpoint yang dipakai |
|---|---|
| `get_environment_data()` | `environment/delta` |
| `get_user_status()` | `user/status` |
| `get_cultural_sites()` | `world/cultural_sites` |

Catatan:

Perception functions masih ada, tetapi flow live terbaru lebih mengandalkan request body `/context/run` dari Unity.

## 14. Mock Model

File: `src/core/mock_model.py`

Tujuan:

Memungkinkan project berjalan dan dievaluasi tanpa API LLM real.

### 14.1 Routing MockModel

| `model_id` | Output |
|---|---|
| `mock-context` | JSON context mock |
| `mock-dialogue` | JSON dialogue dinamis |
| lainnya | `{"status": "mock_response"}` |

### 14.2 Dynamic Dialogue Mock

`MockModel` untuk dialogue sekarang membaca payload context dan menghasilkan output dinamis:

| Kondisi | Output mock |
|---|---|
| `mode=selection_confirmation` | Dialog konfirmasi selected option |
| `recommendations=[]` | Dialog tidak ada tujuan baru |
| `single_recommendation` | Dialog fokus satu tujuan |
| `multiple_recommendations` | Dialog tujuan utama + alternatif |

Ini penting karena evaluasi mock tidak lagi hanya mengembalikan output statis, tetapi mencerminkan variasi input context.

## 15. Postman Collection

File: `Multi Agent.postman_collection.json`

Nama collection: `Multi Agent`

Deskripsi collection:

```text
Koleksi Postman final untuk backend Multi Agent VR Simulation.
Flow utama: /context/run -> /dialogue/run -> /recommendation/select.
```

Items:

| Nama item | Method | URL |
|---|---|---|
| GET User Status | GET | `http://127.0.0.1:8080/user/status` |
| GET Cultural Sites | GET | `http://127.0.0.1:8080/world/cultural_sites` |
| PUT Cultural Sites | PUT | `http://127.0.0.1:8080/world/cultural_sites` |
| POST Context Run | POST | `http://127.0.0.1:8080/context/run` |
| POST Dialogue Run | POST | `http://127.0.0.1:8080/dialogue/run` |
| POST Recommendation Select | POST | `http://127.0.0.1:8080/recommendation/select` |
| POST Run Simulation Legacy | POST | `http://127.0.0.1:8080/run-simulation` |

Status collection versi terbaru:

| Aspek | Status |
|---|---|
| Field Context Agent terbaru | Sudah masuk contoh response `/context/run` |
| Flow `/dialogue/run` | Tetap hanya butuh `simulationId` |
| Field context sebagai input dialogue | Tidak perlu dikirim ulang manual karena diambil dari session |
| JSON collection | Valid |

## 16. Evaluasi

Folder: `evals/`

### 16.1 Cara Menjalankan Evaluasi

Dari root project:

```bash
cd /Users/dicky/Documents/University/Skripsi/MultiAgent/AgentFinal/my-project
```

Semua evaluasi:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all
```

Context Agent saja:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
```

Dialogue Agent saja:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue
```

End-to-end saja:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent e2e
```

Output JSON:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all --json
```

### 16.2 Skenario Evaluasi

File: `evals/scenarios.json`

Jumlah skenario: 7.

| ID skenario | Tujuan |
|---|---|
| `three_unvisited_nearest_order` | Mengecek 3 objek belum dikunjungi diranking berdasarkan jarak |
| `visited_site_filtered_out` | Mengecek objek visited tidak muncul meskipun paling dekat |
| `single_remaining_site` | Mengecek hanya satu rekomendasi dan satu opsi UI |
| `all_sites_visited` | Mengecek tidak ada rekomendasi, `nav_target=""`, opsi kosong |
| `tie_distance_uses_name_sort` | Mengecek tie distance disortir berdasarkan nama lowercase |
| `compatibility_alias_cultural_objects` | Mengecek payload alias `culturalObject/coordinate/isObjectVisited` |
| `invalid_selected_option` | Mengecek pilihan rekomendasi invalid ditolak |

### 16.3 Metrik Context Agent

| Check/Metrik | Fungsi |
|---|---|
| `context.schema_valid` | Output valid sebagai `ContextOutput` |
| `context.timestamp_matches_request` | Timestamp sama dengan request |
| `context.scene_matches_request` | Scene sama dengan request |
| `context.no_visited_sites_recommended` | Tidak merekomendasikan visited site |
| `context.ranking_exact_match` | Ranking sama dengan gold ranking deterministic |
| `context.nav_target_matches_rank_1` | `nav_target` sama dengan rank-1 |
| `context.max_three_recommendations` | Maksimal tiga rekomendasi |
| `context.context_summary_present` | Summary context tidak kosong |
| `context.recommendation_reason_present` | Alasan rekomendasi tidak kosong |
| `context.situation_type_supported` | Situation type masuk daftar valid |
| `context.dialogue_intent_supported` | Dialogue intent masuk daftar valid |
| `context.no_coordinates_in_interpretive_fields` | Field interpretatif tidak bocor koordinat/token teknis |
| `Precision@3` | Proporsi top-3 prediksi yang relevan |
| `Recall@3` | Proporsi item relevan yang berhasil muncul di top-3 |
| `MRR` | Reciprocal rank item relevan pertama |
| `NDCG@3` | Kualitas urutan ranking top-3 |

Catatan penting:

Evaluasi Context Agent saat ini lebih tepat disebut evaluasi hybrid context layer, karena ranking final dikunci backend. Untuk riset lebih lanjut, evaluasi khusus LLM Context Agent bisa ditambah dengan membandingkan field interpretatif seperti `context_summary`, `recommendation_reason`, `situation_type`, dan `dialogue_intent` terhadap rubric human/LLM judge.

### 16.4 Metrik Dialogue Agent

| Check/Metrik | Fungsi |
|---|---|
| `dialogue.schema_valid` | Output valid sebagai `DialogueOutput` |
| `dialogue.options_match_context_order` | Opsi UI sama dengan urutan context |
| `dialogue.subtitle_max_15_words` | Subtitle sesuai constraint HUD |
| `dialogue.no_internal_tokens_or_coordinates` | Tidak membocorkan koordinat, backend, NavMesh, tool |
| `dialogue.primary_option_mentioned` | Dialog/subtitle menyebut primary option |
| `dialogue.empty_recommendations_handled` | Kondisi kosong ditangani dengan opsi kosong |
| `dialogue.selected_option_mentioned` | Mode selection menyebut pilihan user |
| `subtitle_word_count` | Jumlah kata subtitle |
| `option_count` | Jumlah opsi rekomendasi |
| `has_leak` | Ada/tidak technical leak |

### 16.5 Metrik End-to-End

| Check/Metrik | Fungsi |
|---|---|
| `request.valid_simulation_request` | Request valid |
| context checks | Context layer valid |
| dialogue checks | Dialogue layer valid |
| selection checks | Selection behavior valid |
| `end_to_end_success` | Semua check wajib lulus |
| `end_to_end_success_rate` | Rasio skenario e2e sukses |

### 16.6 Hasil Evaluasi Terakhir

Command yang dijalankan:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent all
```

Ringkasan hasil:

| Metrik | Nilai |
|---|---|
| Scenarios | 7 |
| Check pass rate | 100.00% |
| Context Precision@3 | 1.000 |
| Context Recall@3 | 1.000 |
| Context MRR | 0.857 |
| Context NDCG@3 | 1.000 |
| Dialogue subtitle words avg | 3.29 |
| Dialogue options avg | 1.71 |
| Dialogue technical leak rate | 0.00% |
| End-to-end success rate | 100.00% |

Status tiap skenario:

| Skenario | Status |
|---|---|
| `three_unvisited_nearest_order` | PASS |
| `visited_site_filtered_out` | PASS |
| `single_remaining_site` | PASS |
| `all_sites_visited` | PASS |
| `tie_distance_uses_name_sort` | PASS |
| `compatibility_alias_cultural_objects` | PASS |
| `invalid_selected_option` | PASS |

## 17. Rubrik LLM-as-a-Judge untuk Dialogue Agent

File: `evals/dialogue_llm_judge_rubric.md`

Rubrik ini bersifat pelengkap untuk evaluasi deterministic. Dimensi yang disarankan:

| Dimensi | Makna |
|---|---|
| `context_relevance` | Dialog relevan dengan context aktual |
| `faithfulness` | Tidak mengarang fakta di luar context |
| `navigation_clarity` | Arah tujuan jelas |
| `persona_alignment` | Sesuai persona Arif |
| `language_quality` | Bahasa Indonesia natural |
| `ui_usefulness` | UI text dan opsi membantu |
| `technical_leak_safety` | Tidak ada bocoran teknis |

Ambang batas disarankan:

| Aturan | Ambang |
|---|---|
| Pass umum | `overall_score >= 4.0` |
| Technical leak | Harus 5 |
| Faithfulness | Minimal 4 |
| Selection mode | Selected option wajib disebut |

## 18. Cara Kerja Lengkap per Use Case

### 18.1 Normal: Banyak Rekomendasi

Input:

```json
{
  "playerPosition": "8.0, 2.0, 10.0",
  "culturalSites": [
    {"name": "Julang Ngapak", "cultural_position": "7.21, 2, 8.7", "visited": false},
    {"name": "Kujang", "cultural_position": "8.99, 3, 13.65", "visited": false},
    {"name": "Surabi", "cultural_position": "5.448, 3, 16.256", "visited": false}
  ]
}
```

Expected behavior:

| Tahap | Output |
|---|---|
| Ranking | Top-3 berdasarkan jarak |
| Context | `situation_type=multiple_recommendations` |
| NavMesh | Target rank-1 |
| Dialogue | Mengajak ke rank-1 dan menyebut alternatif |
| UI | Menampilkan 3 opsi sesuai urutan ranking |

### 18.2 Ada Objek Visited yang Paling Dekat

Expected behavior:

| Tahap | Output |
|---|---|
| Filter | Objek `visited=true` dibuang |
| Ranking | Hanya objek `visited=false` |
| Context | Tidak boleh memuat visited site |
| Dialogue | Tidak boleh menawarkan visited site |

### 18.3 Satu Objek Tersisa

Expected behavior:

| Tahap | Output |
|---|---|
| Context | `situation_type=single_recommendation` |
| Dialogue | Fokus satu tujuan, tidak seolah ada banyak opsi |
| UI | Satu opsi |

### 18.4 Semua Objek Sudah Dikunjungi

Expected behavior:

| Tahap | Output |
|---|---|
| Context | `recommendations=[]` |
| Context | `nav_target=""` |
| NavMesh | Tidak ada target aktif |
| Dialogue | Tidak memaksa navigasi |
| UI | `recommendation_options=[]` |

### 18.5 User Memilih Alternatif

Contoh:

Rank-1 adalah `Julang Ngapak`, tetapi user memilih `Kujang`.

Expected behavior:

| Tahap | Output |
|---|---|
| `/recommendation/select` | Menerima `selectedOption="Kujang"` |
| Validasi | `Kujang` harus ada di recommendations aktif |
| Context session | `nav_target` diubah ke ID `Kujang` |
| NavMesh | Dispatch target `Kujang` |
| Dialogue | Mengonfirmasi `Kujang` secara eksplisit |

Catatan:

`recommendation_reason` dari `/context/run` awal tetap menjelaskan kenapa rank-1 diprioritaskan. Saat user memilih alternatif, dialog konfirmasi selection lebih relevan daripada alasan rank-1 awal.

## 19. Hubungan Context Agent dan Dialogue Agent

Hubungan field terbaru:

| Context field | Dialogue effect |
|---|---|
| `context_summary` | Diparafrasekan menjadi `recommendation_dialogue` |
| `situation_type` | Menentukan struktur dialog |
| `recommendation_reason` | Dipakai sebagai alasan natural dalam `spoken_output` |
| `dialogue_intent` | Menentukan intensi respons |
| `recommendations` | Menjadi `recommendation_options` |
| `nav_target` | Menentukan tujuan aktif |
| `user_action` | Memberi sinyal keadaan pemain |

Kesimpulan:

Field penting Context Agent sudah terhubung ke Dialogue Agent. Dialogue Agent tidak lagi sekadar membaca `nav_target`, tetapi memakai context yang lebih kaya untuk menghasilkan output yang dinamis.

## 20. Status Context Agent Saat Ini

Context Agent bisa dianggap selesai untuk scope implementasi saat ini karena:

| Kriteria | Status |
|---|---|
| Prompt Indonesia | Selesai |
| ReAct structure | Dipertahankan |
| Bounded tools | Ada |
| Field interpretatif | Ada |
| Ranking grounded | Dijaga backend |
| Output schema | Validated Pydantic |
| Guardrail fallback | Ada |
| Evaluasi dasar | Ada |
| Integrasi ke Dialogue Agent | Ada |

Namun untuk penelitian/evaluasi skripsi, masih ada ruang evaluasi yang lebih spesifik:

| Evaluasi tambahan | Tujuan |
|---|---|
| Human judgement untuk `context_summary` | Menilai apakah summary membantu user/dialogue |
| LLM-as-a-judge untuk groundedness | Menilai apakah reason tidak mengarang |
| Ablation study tanpa field interpretatif | Mengukur dampak context kaya ke Dialogue Agent |
| Real LLM robustness test | Menguji output saat bukan mock |
| Unity live integration test | Menguji dengan data VR asli |

## 21. Status Dialogue Agent Saat Ini

Dialogue Agent versi terbaru:

| Kriteria | Status |
|---|---|
| Persona Arif | Ada |
| Bahasa Indonesia | Ada |
| Few-shot prompting | Ada dan diperkuat |
| Multiple recommendations | Didukung |
| Single recommendation | Didukung |
| All visited/no destination | Didukung |
| Selection confirmation | Didukung |
| Subtitle HUD | Didukung |
| UI options | Didukung |
| Technical leak guardrail | Dievaluasi |
| Mock dynamic output | Ada |

Area yang masih bisa ditingkatkan:

| Area | Rekomendasi |
|---|---|
| Lore budaya | Tambahkan knowledge base terstruktur jika ingin dialog lebih informatif |
| Persona richness | Tambahkan style guide lebih rinci |
| Memory percakapan | Tambahkan riwayat percakapan jika NPC harus ingat interaksi |
| Multiturn dialogue | Saat ini lebih berfokus pada satu cycle rekomendasi |
| Real LLM evaluation | Jalankan evaluasi dengan API real dan judge/human |

## 22. Keputusan Desain Penting

### 22.1 Ranking di Backend, Bukan Full LLM

Alasan:

| Alasan | Dampak |
|---|---|
| Navigasi perlu deterministik | Mengurangi risiko target salah |
| Unity butuh target stabil | `nav_target` tidak boleh halusinasi |
| Evaluasi lebih jelas | Gold ranking bisa dihitung |
| LLM lebih cocok untuk interpretasi | LLM fokus pada summary/reason/intent |

### 22.2 Context Agent Tetap Dipertahankan

Alasan:

| Alasan | Dampak |
|---|---|
| Memberi semantic bridge ke Dialogue Agent | Dialogue lebih kaya |
| Memisahkan perception/context dari persona dialogue | Arsitektur lebih modular |
| Bisa dievaluasi sendiri | Cocok untuk laporan MAS |
| Bisa dikembangkan menjadi reasoning layer | Future-proof |

### 22.3 Dialogue Agent Memakai Few-Shot

Alasan:

| Alasan | Dampak |
|---|---|
| Format JSON lebih konsisten | Lebih mudah diparse |
| Mode berbeda lebih jelas | Multiple/single/all visited/selection |
| Gaya bahasa lebih stabil | Persona Arif lebih konsisten |
| Risiko technical leak berkurang | Contoh mengajarkan output aman |

### 22.4 Unity Tetap Source of Truth

Alasan:

| Alasan | Dampak |
|---|---|
| Unity tahu state real VR | Backend tidak perlu menebak |
| Status visited akurat | Dikirim setiap `/context/run` |
| Backend stateless terhadap world state | Lebih sederhana |
| Selection tidak otomatis visited | Menghindari state salah sebelum player benar-benar tiba |

## 23. Known Limitations

| Area | Limitasi |
|---|---|
| Session storage | Masih in-memory |
| Persistence | Belum ada database |
| Concurrency | Belum ada locking/session cleanup |
| Unity bridge | Masih mock `post` yang selalu return `True` |
| Lore budaya | Belum ada retrieval/knowledge base budaya |
| LLM real robustness | Belum didokumentasikan hasil evaluasi real model |
| Prompt injection | Belum ada layer khusus anti prompt injection dari payload |
| Monitoring | Belum ada logging observability production |
| Security | Belum ada auth/API key untuk endpoint Flask |
| Deployment | Belum ada Docker/deployment config |
| README | Masih kosong |
| `server.py` | FastAPI sample belum terintegrasi ke alur utama |

## 24. Rekomendasi Next Step

Prioritas teknis:

| Prioritas | Aksi |
|---|---|
| 1 | Tambahkan README singkat untuk run, endpoint, evaluasi |
| 2 | Tambahkan persistent session store jika server akan dipakai lama |
| 3 | Ganti mock Unity `post` dengan HTTP call real ke Unity jika integrasi sudah siap |
| 4 | Tambahkan logging structured untuk tiap `simulation_id` |
| 5 | Tambahkan test real LLM dengan sampling beberapa seed/request |

Prioritas evaluasi:

| Prioritas | Aksi |
|---|---|
| 1 | Buat evaluasi Context Agent khusus field interpretatif |
| 2 | Tambahkan LLM-as-a-judge untuk Dialogue Agent berdasarkan rubric |
| 3 | Buat ablation study: Dialogue dengan vs tanpa `context_summary/reason/intent` |
| 4 | Tambahkan human evaluation untuk naturalness dan usefulness |
| 5 | Tambahkan Unity integration test dengan scene asli |

Prioritas akademik/skripsi:

| Prioritas | Aksi |
|---|---|
| 1 | Jelaskan bahwa sistem adalah hybrid MAS, bukan LLM-only |
| 2 | Jelaskan Context Agent sebagai bounded context reasoning agent |
| 3 | Jelaskan Dialogue Agent sebagai persona-based interaction agent |
| 4 | Jelaskan evaluasi deterministic untuk safety dan task success |
| 5 | Jelaskan LLM/human judge untuk aspek subjektif bahasa |

## 25. Glossary

| Istilah | Definisi |
|---|---|
| MAS | Multi-Agent System |
| Context Agent | Agent yang mengubah snapshot runtime menjadi context terstruktur |
| Dialogue Agent | Agent yang mengubah context menjadi dialog NPC dan opsi UI |
| Orchestrator | Komponen yang mengatur alur agent, guardrail, session, dan dispatch |
| Message Pool | Blackboard in-memory untuk latest context/dialogue dan history |
| `simulation_id` | ID session yang menghubungkan `/context/run`, `/dialogue/run`, dan `/recommendation/select` |
| `nav_target` | ID objek budaya tujuan aktif untuk Unity NavMesh |
| `recommendations` | Daftar top-3 objek budaya belum dikunjungi |
| `situation_type` | Klasifikasi situasi context |
| `dialogue_intent` | Arahan respons untuk Dialogue Agent |
| `recommendation_reason` | Alasan grounded kenapa target utama direkomendasikan |
| `recommendation_options` | Daftar nama objek untuk tombol UI |
| Technical leak | Bocornya koordinat, tool name, backend token, atau istilah internal ke user |
| ReAct | Pola prompting Reasoning, Action, Observation |
| Few-shot | Prompting dengan contoh input-output |
| MockModel | Provider LLM palsu untuk test lokal |

## 26. Ringkasan Final

Project ini saat ini adalah backend MAS dua agent untuk VR cultural guide dengan alur utama:

```text
Unity snapshot -> Context Agent -> NavMesh + saved context -> Dialogue Agent -> HUD/UI -> Selection -> NavMesh retarget
```

Context Agent berperan sebagai bounded context reasoning layer. Ia menghasilkan context kaya seperti `context_summary`, `situation_type`, `recommendation_reason`, dan `dialogue_intent`, tetapi ranking dan target navigasi tetap dijaga deterministik oleh backend.

Dialogue Agent berperan sebagai persona NPC bernama Arif. Ia memakai few-shot prompting dan seluruh field penting Context Agent untuk menghasilkan dialog yang lebih dinamis, aman, natural, dan sesuai konteks.

Evaluasi terbaru menunjukkan semua 7 skenario lulus dengan check pass rate 100% dalam mode mock. Ini berarti flow deterministic, schema, ranking, dialogue guardrail, selection behavior, dan end-to-end workflow sudah stabil untuk pengembangan lokal dan siap menjadi dasar integrasi lebih lanjut dengan Unity serta evaluasi akademik yang lebih mendalam.
