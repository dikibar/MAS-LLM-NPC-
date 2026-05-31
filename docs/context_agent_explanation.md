# Penjelasan Context Agent Saat Ini

Dokumen ini menjelaskan posisi, fungsi, dan batasan **Context Agent** pada project Multi-Agent VR Cultural Guide saat ini. Dokumen ini dibuat agar Context Agent dapat dijelaskan secara jelas, jujur, dan akademik, terutama karena sebagian proses rekomendasi spasial saat ini dikerjakan oleh backend/orchestrator secara deterministic, bukan sepenuhnya oleh LLM.

---

## 1. Ringkasan Singkat

Context Agent pada project ini **bukan sekadar summarizer biasa**, tetapi juga **bukan agent yang mengambil seluruh keputusan rekomendasi secara mandiri**.

Peran paling tepat untuk Context Agent saat ini adalah:

```text
LLM-based bounded context-synthesis agent
```

atau dalam bahasa Indonesia:

```text
agen kontekstual berbasis LLM yang menggunakan tool terbatas untuk menyintesis snapshot lingkungan Unity menjadi representasi state terstruktur bagi sistem downstream.
```

Context Agent tetap dapat disebut sebagai agent karena memiliki:

1. role/profile khusus;
2. system prompt;
3. struktur ReAct;
4. bounded tools;
5. input runtime;
6. proses reasoning berbasis observasi tool;
7. output/action berupa `ContextOutput`;
8. hubungan downstream ke Dialogue Agent dan NavMesh dispatcher melalui orchestrator.

Namun, untuk menjaga reliabilitas sistem VR real-time, beberapa bagian objektif seperti ranking jarak dan `nav_target` dikunci oleh backend.

---

## 2. Lokasi File

Context Agent didefinisikan di:

```text
src/agents/context_agent.py
```

Orchestrator yang menjalankan dan mengontrol hasil Context Agent berada di:

```text
src/orchestration/coordinator.py
```

Schema output Context Agent berada di:

```text
src/schema/models.py
```

---

## 3. Peran Context Agent Dalam Sistem

Dalam arsitektur sistem, Context Agent berperan sebagai:

```text
Environmental State Engine
Context Synthesizer
Structured State Publisher
Recommendation Context Agent
```

Tugas utamanya adalah menyusun konteks lingkungan menjadi format JSON yang dapat dipakai oleh komponen lain.

Komponen downstream yang memakai hasil Context Agent:

1. **NavMesh Dispatcher**
   - menggunakan `nav_target`;
   - mengarahkan NPC ke objek budaya tujuan.

2. **Dialogue Agent**
   - membaca `ContextOutput`;
   - membuat dialog NPC;
   - membuat subtitle;
   - membuat opsi UI rekomendasi.

3. **Message Pool / Session State**
   - menyimpan context terbaru;
   - menyimpan session berdasarkan `simulation_id`.

---

## 4. Apa Yang Dikerjakan Context Agent?

Context Agent saat ini mengerjakan:

1. Membaca runtime snapshot melalui bounded tools.
2. Memahami bahwa semua informasi valid berasal dari snapshot request.
3. Membaca status posisi player.
4. Membaca daftar cultural sites.
5. Membaca rekomendasi yang sudah dihitung backend.
6. Menyusun output JSON sesuai schema `ContextOutput`.
7. Menghasilkan atau mempertahankan `user_action`.
8. Menjadi publisher context untuk workflow downstream.

Secara konseptual, Context Agent melakukan:

```text
runtime perception -> context synthesis -> structured state publication
```

---

## 5. Apa Yang Tidak Sepenuhnya Dikerjakan Context Agent?

Context Agent saat ini **tidak sepenuhnya menentukan ranking rekomendasi secara mandiri**.

Ranking rekomendasi dihitung oleh backend/orchestrator menggunakan logic deterministic:

1. Ambil cultural site dengan `visited=false`.
2. Hitung jarak Euclidean dari `playerPosition` ke `cultural_position`.
3. Urutkan berdasarkan jarak terdekat.
4. Jika jarak sama, gunakan `site.name.lower()` sebagai tie-breaker.
5. Ambil maksimal 3 rekomendasi.
6. Jadikan rank-1 sebagai `nav_target`.

Dengan kata lain:

```text
Backend menentukan kandidat rekomendasi dan target navigasi.
Context Agent menyintesis dan mempublikasikan konteks terstruktur.
```

---

## 6. Mengapa Ranking Dikerjakan Backend?

Ranking dikerjakan backend karena tugas tersebut bersifat:

```text
objektif
numerik
deterministic
harus akurat
harus reproducible
berdampak langsung pada navigasi Unity
```

Dalam sistem VR real-time, kesalahan pada ranking atau `nav_target` dapat menyebabkan:

1. NPC bergerak ke objek yang salah.
2. Pemain diarahkan ke lokasi yang tidak relevan.
3. Objek yang sudah dikunjungi direkomendasikan ulang.
4. State Unity dan backend tidak sinkron.
5. Pengalaman pengguna menjadi membingungkan.

Karena itu, ranking spasial lebih aman dihitung oleh backend deterministic daripada diserahkan sepenuhnya ke LLM.

Desain ini dapat dijelaskan sebagai:

```text
hybrid agentic architecture
```

Yaitu pemisahan antara:

```text
deterministic computation layer
LLM-based context synthesis layer
natural language dialogue layer
```

---

## 7. Apakah Context Agent Tetap Bisa Disebut Agent?

Ya, Context Agent tetap bisa disebut agent.

Alasannya, agent tidak harus selalu mengambil seluruh keputusan secara otonom. Dalam banyak sistem agentic, agent dapat dibatasi oleh:

1. tool tertentu;
2. schema output tertentu;
3. policy tertentu;
4. deterministic guardrail;
5. external state;
6. backend-computed input.

Context Agent pada project ini tetap agent karena ia:

1. memiliki persona/peran sebagai environmental state engine;
2. memiliki prompt instruksi;
3. menggunakan tools;
4. mengikuti prosedur ReAct;
5. membaca observasi dari tool;
6. menghasilkan output untuk komponen lain;
7. menjadi bagian dari koordinasi multi-agent;
8. bekerja dalam workflow yang melibatkan Dialogue Agent dan Unity tools.

Istilah yang paling aman:

```text
bounded LLM agent
```

atau:

```text
context-synthesis agent
```

atau:

```text
environment state representation agent
```

---

## 8. Struktur ReAct Pada Context Agent

System prompt Context Agent menggunakan struktur ReAct:

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

Maknanya:

| Tahap | Fungsi |
|---|---|
| Reasoning 1 | Memahami bahwa data valid berasal dari bounded tools. |
| Action 1 | Memanggil `tool_get_runtime_user_status`. |
| Observation 1 | Membaca posisi player. |
| Reasoning 2 | Memahami state pendukung tanpa membuat ranking baru. |
| Action 2 | Memanggil `tool_get_runtime_cultural_sites` dan `tool_get_runtime_recommendations`. |
| Observation 2 | Membaca visited flags dan precomputed recommendations. |
| Reasoning 3 | Menjaga urutan rekomendasi dan menyimpulkan `user_action`. |
| Action | Menghasilkan JSON `ContextOutput`. |
| Observation | Output dipakai downstream untuk NavMesh dan Dialogue Agent. |

Struktur ini penting karena Context Agent tidak hanya menerima input pasif, tetapi mengikuti pola:

```text
reason -> act with tool -> observe -> synthesize output
```

---

## 9. Bounded Tools

Context Agent memiliki tiga bounded tools.

### 9.1 `tool_get_runtime_user_status`

Fungsi:

```text
membaca user status dari runtime snapshot
```

Output biasanya berisi:

```json
{
  "player_position": "8.0, 2.0, 10.0"
}
```

### 9.2 `tool_get_runtime_cultural_sites`

Fungsi:

```text
membaca daftar cultural sites dari runtime snapshot
```

Output berisi daftar objek budaya:

```json
{
  "sites": [
    {
      "id": "Kujang",
      "name": "Kujang",
      "cultural_position": "8.99, 3, 13.65",
      "visited": false
    }
  ]
}
```

### 9.3 `tool_get_runtime_recommendations`

Fungsi:

```text
membaca rekomendasi yang sudah dihitung backend
```

Output:

```json
{
  "precomputed_recommendations": [
    {
      "rank": 1,
      "id": "Julang Ngapak",
      "name": "Julang Ngapak",
      "cultural_position": "7.21, 2, 8.7"
    }
  ]
}
```

### 9.4 Mengapa Tool Disebut Bounded?

Tool disebut bounded karena hanya membaca:

```text
_RUNTIME_SNAPSHOT
```

Tool tidak membaca:

1. internet;
2. file eksternal;
3. database;
4. Unity secara langsung;
5. sumber data lain di luar request aktif.

Ini membuat Context Agent lebih aman dan grounded.

---

## 10. Input Context Agent

Input Context Agent berasal dari orchestrator.

Orchestrator membentuk `ContextAgentInput` yang berisi:

```text
player_position
environment
user_status
cultural_sites
precomputed_recommendations
```

Contoh secara konseptual:

```json
{
  "player_position": "8.0, 2.0, 10.0",
  "environment": {
    "timestamp": "2026-05-01T12:30:00Z",
    "scene": "Heritage_Museum_Wing_A",
    "user_position": {
      "x": 8.0,
      "y": 2.0,
      "z": 10.0
    }
  },
  "user_status": {
    "player_position": "8.0, 2.0, 10.0"
  },
  "cultural_sites": {
    "sites": [
      {
        "id": "Julang Ngapak",
        "name": "Julang Ngapak",
        "cultural_position": "7.21, 2, 8.7",
        "visited": false
      }
    ]
  },
  "precomputed_recommendations": [
    {
      "rank": 1,
      "id": "Julang Ngapak",
      "name": "Julang Ngapak",
      "cultural_position": "7.21, 2, 8.7"
    }
  ]
}
```

Namun Context Agent tidak menerima semua ini sebagai raw prompt panjang. Data ini disimpan sebagai runtime snapshot dan dibaca lewat bounded tools.

---

## 11. Output Context Agent

Output Context Agent harus mengikuti schema:

```text
ContextOutput
```

Field:

```text
timestamp
scene
user_action
recommendations
nav_target
```

Contoh:

```json
{
  "timestamp": "2026-05-01T12:30:00Z",
  "scene": "Heritage_Museum_Wing_A",
  "user_action": "Menunggu interaksi pemain",
  "recommendations": [
    {
      "rank": 1,
      "id": "Julang Ngapak",
      "name": "Julang Ngapak",
      "cultural_position": "7.21, 2, 8.7"
    },
    {
      "rank": 2,
      "id": "Kujang",
      "name": "Kujang",
      "cultural_position": "8.99, 3, 13.65"
    }
  ],
  "nav_target": "Julang Ngapak"
}
```

Jika semua objek sudah dikunjungi:

```json
{
  "timestamp": "2026-05-01T12:40:00Z",
  "scene": "Heritage_Museum_Wing_C",
  "user_action": "Menunggu interaksi pemain",
  "recommendations": [],
  "nav_target": ""
}
```

---

## 12. Field Mana Yang Dikunci Oleh Backend?

Saat Context Agent menghasilkan output, orchestrator mencoba parse output tersebut. Jika valid, orchestrator tetap melakukan override pada beberapa field:

```text
timestamp
scene
recommendations
nav_target
```

Artinya:

```text
LLM boleh menghasilkan ContextOutput,
tetapi field kritikal tetap disesuaikan dengan data deterministic backend.
```

Tujuannya:

1. menjaga `timestamp` sama dengan request Unity;
2. menjaga `scene` sama dengan request Unity;
3. menjaga rekomendasi sesuai ranking backend;
4. menjaga `nav_target` sama dengan rank-1;
5. menghindari hallucination;
6. memastikan NavMesh menerima target yang valid.

Field yang masih dapat mencerminkan kontribusi LLM secara lebih langsung:

```text
user_action
struktur/sintesis context
formatting awal sebelum override
```

---

## 13. Alur Teknis Context Agent

Alur dari request sampai output:

```text
Unity / Client
  -> POST /context/run
  -> SimulationRequest validation
  -> _build_runtime_context()
  -> _rank_unvisited_sites()
  -> set_context_runtime_snapshot()
  -> Context Agent runs with ReAct prompt
  -> Context Agent calls bounded tools
  -> Context Agent outputs JSON
  -> _parse_context()
  -> orchestrator overrides critical fields
  -> publish_context()
  -> set_nav_target(nav_target)
  -> save_session(simulation_id)
  -> return ContextCycleResponse
```

Dalam bentuk ringkas:

```text
Request Unity -> Backend ranking -> Context Agent synthesis -> Safe ContextOutput -> NavMesh + Dialogue Agent
```

---

## 14. Hubungan Context Agent Dengan Dialogue Agent

Dialogue Agent tidak membaca langsung request Unity.

Dialogue Agent membaca output Context Agent:

```text
ContextOutput JSON
```

Dialogue Agent menggunakan:

```text
recommendations
nav_target
scene
user_action
```

Untuk menghasilkan:

```text
spoken_output
subtitle_output
recommendation_dialogue
recommendation_options
```

Jadi Context Agent berfungsi sebagai jembatan antara:

```text
raw Unity snapshot
dan
natural language NPC response
```

---

## 15. Hubungan Context Agent Dengan NavMesh

NavMesh tidak membaca dialog.

NavMesh hanya membutuhkan target:

```text
nav_target
```

Context Agent menghasilkan output yang mengandung `nav_target`, tetapi value final `nav_target` dijaga oleh backend agar sama dengan rekomendasi rank-1.

Lalu orchestrator memanggil:

```python
set_nav_target(context_output.nav_target)
```

Payload ke Unity mock:

```json
{
  "command": "NAV_TO_TARGET",
  "target_id": "Julang Ngapak"
}
```

---

## 16. Apakah Desain Ini Bermasalah?

Tidak otomatis bermasalah.

Desain ini justru dapat dianggap kuat untuk sistem VR real-time karena:

1. Perhitungan numerik dilakukan deterministic.
2. LLM tidak diberi wewenang penuh untuk target navigasi.
3. Unity tetap source of truth untuk visited state.
4. Backend menjaga schema dan field kritikal.
5. Dialogue Agent tetap mendapat context yang rapi.
6. Sistem lebih stabil dan aman dari hallucination.

Yang harus dihindari adalah klaim yang terlalu besar seperti:

```text
Context Agent secara mandiri menghitung rekomendasi.
```

Kalimat yang lebih tepat:

```text
Context Agent menggunakan rekomendasi yang telah dihitung backend sebagai grounded input,
kemudian menyintesis snapshot lingkungan menjadi ContextOutput terstruktur untuk koordinasi sistem.
```

---

## 17. Framing Akademik Yang Disarankan

Untuk laporan atau skripsi, Context Agent dapat dijelaskan seperti ini:

> Context Agent merupakan agen berbasis LLM dengan tool terbatas yang bertugas membaca snapshot lingkungan dari Unity melalui bounded runtime tools dan menyintesisnya menjadi representasi state terstruktur. Untuk menjaga reliabilitas navigasi dalam lingkungan VR real-time, proses filtering objek yang telah dikunjungi, perhitungan jarak, ranking rekomendasi, dan pemilihan `nav_target` dilakukan secara deterministic oleh backend. Hasil deterministic tersebut kemudian digunakan sebagai grounded input oleh Context Agent, sehingga output yang dikirim ke Dialogue Agent dan NavMesh tetap konsisten dengan state Unity.

Atau versi lebih singkat:

> Context Agent adalah bounded LLM agent yang berfungsi sebagai context synthesis dan state representation layer. Ia tidak mengambil seluruh keputusan spasial secara mandiri, melainkan menggunakan backend-precomputed recommendations untuk menghasilkan ContextOutput yang aman, terstruktur, dan grounded.

---

## 18. Istilah Yang Cocok Untuk Context Agent

Istilah yang cocok:

```text
Bounded Context Agent
Context Synthesis Agent
Environment State Representation Agent
Environmental State Engine
Grounded Context Publisher
LLM-based Context Formatter
Hybrid Context Agent
```

Istilah yang kurang tepat jika dipakai sendiri:

```text
Recommendation Agent penuh
Autonomous Navigation Agent
Independent Decision-Making Agent
Pure Recommender Agent
```

Karena ranking dan nav target saat ini masih dikontrol backend.

---

## 19. Evaluasi Context Agent Saat Ini

Evaluasi Context Agent dapat dijalankan dengan:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
```

Metrik yang digunakan:

```text
context.schema_valid
context.timestamp_matches_request
context.scene_matches_request
context.no_visited_sites_recommended
context.ranking_exact_match
context.nav_target_matches_rank_1
context.max_three_recommendations
Precision@3
Recall@3
MRR
NDCG@3
```

Hasil evaluasi terakhir:

```text
Scenarios: 7
Check pass rate: 100.00%
Context Precision@3: 1.000
Context Recall@3: 1.000
Context MRR: 0.857
Context NDCG@3: 1.000
```

Interpretasi:

```text
Context output final saat ini sangat stabil pada skenario synthetic.
```

Namun perlu dicatat:

```text
Skor tinggi sebagian besar karena field kritikal dikunci oleh backend.
```

Jadi evaluasi Context Agent sebaiknya dijelaskan sebagai evaluasi:

```text
Context Agent + backend guardrail untuk structured context publication
```

atau pisahkan menjadi:

1. evaluasi deterministic backend ranking;
2. evaluasi Context Agent output validity dan grounding;
3. evaluasi tool-use/trajectory jika ingin menilai ReAct behavior.

---

## 20. Risiko Jika Context Agent Dibuat Full LLM

Jika ranking dan nav target diserahkan sepenuhnya ke LLM, risiko yang muncul:

1. LLM salah menghitung jarak.
2. LLM merekomendasikan objek yang sudah visited.
3. LLM mengubah urutan rekomendasi tanpa alasan.
4. LLM mengarang objek yang tidak ada.
5. LLM memilih `nav_target` yang tidak valid.
6. LLM tidak konsisten antar request.
7. Unity NavMesh menerima target yang salah.

Karena itu, desain hybrid saat ini lebih aman untuk sistem yang sudah berjalan di Unity asli.

---

## 21. Kapan Context Agent Perlu Diperluas?

Context Agent dapat diperluas jika nanti dibutuhkan:

1. Interpretasi event lingkungan yang lebih kompleks.
2. Multi-turn state tracking.
3. Deteksi perubahan signifikan antar tick.
4. Penalaran terhadap aktivitas player.
5. Penilaian konteks non-spasial.
6. Prioritasi berbasis pedagogical objective.
7. Adaptasi rekomendasi berdasarkan history player.
8. Integrasi preference model.
9. Reflection/evolution terhadap output sebelumnya.

Contoh perluasan:

```text
Jika player sudah terlalu lama diam di area tertentu,
Context Agent dapat menyimpulkan user_action sebagai "menunggu arahan"
dan memicu Dialogue Agent untuk memberi bantuan.
```

Namun untuk ranking jarak dasar, backend deterministic tetap lebih aman.

---

## 22. Saran Evaluasi Lebih Lanjut

Untuk menilai Context Agent secara lebih adil, evaluasi bisa dibagi:

### 22.1 Backend Deterministic Evaluation

Menguji:

```text
visited filtering
distance calculation
ranking exact match
nav_target correctness
tie-break behavior
```

### 22.2 Context Agent Structured Output Evaluation

Menguji:

```text
schema validity
JSON validity
field completeness
grounding to snapshot
no hallucinated site
valid user_action
```

### 22.3 ReAct / Tool-Use Evaluation

Menguji:

```text
apakah tool dipanggil
apakah tool yang benar dipanggil
apakah urutan tool sesuai prompt
apakah output menggunakan hasil tool
apakah agent tidak memakai sumber eksternal
```

### 22.4 Downstream Utility Evaluation

Menguji:

```text
apakah Dialogue Agent bisa memakai ContextOutput
apakah NavMesh mendapat target valid
apakah UI options sinkron
apakah player berhasil diarahkan
```

---

## 23. Jawaban Singkat Untuk Pertanyaan Umum

### Apakah Context Agent hanya summary?

Tidak hanya summary. Ia menyintesis context dan menerbitkan structured state, tetapi ranking spasialnya dibantu backend.

### Apakah Context Agent tetap agent?

Ya. Ia adalah bounded LLM agent dengan tools, prompt, ReAct flow, dan output/action terstruktur.

### Apakah bermasalah jika backend mengerjakan sebagian tugas?

Tidak. Untuk sistem VR real-time, ini justru meningkatkan reliability dan safety.

### Apakah boleh disebut Multi-Agent System?

Ya, selama dijelaskan bahwa sistem memiliki beberapa agent/komponen dengan peran berbeda:

```text
Context Agent
Dialogue Agent
orchestrator
Unity tools
```

Namun jangan mengklaim semua keputusan dilakukan otonom oleh LLM.

### Apa kontribusi utama Context Agent?

Kontribusi utamanya adalah:

```text
mengubah snapshot Unity menjadi ContextOutput terstruktur yang grounded dan siap dipakai Dialogue Agent serta NavMesh.
```

---

## 24. Diagram Alur Context Agent

```text
POST /context/run
  |
  v
SimulationRequest validation
  |
  v
Backend parses playerPosition
  |
  v
Backend filters visited=false sites
  |
  v
Backend ranks sites by Euclidean distance
  |
  v
Runtime snapshot prepared
  |
  v
Context Agent uses bounded tools
  |
  v
Context Agent outputs ContextOutput JSON
  |
  v
Orchestrator validates and overrides critical fields
  |
  v
Message Pool stores context
  |
  +--> NavMesh receives nav_target
  |
  +--> Dialogue Agent receives context JSON
```

---

## 25. Kesimpulan

Context Agent saat ini adalah **bounded LLM-based context synthesis agent**. Ia bukan hanya summarizer, tetapi juga bukan autonomous recommender penuh. Perannya berada di tengah: membaca runtime snapshot melalui bounded tools, mengikuti rekomendasi yang telah dihitung backend, lalu menghasilkan representasi context terstruktur untuk downstream system.

Pembagian tugas antara backend dan Context Agent bukan kelemahan selama dijelaskan dengan tepat. Dalam konteks Unity/VR yang sudah berjalan secara nyata, desain ini justru kuat karena menjaga akurasi ranking, mencegah hallucination, dan memastikan target navigasi tetap valid.

Kalimat final yang paling aman:

> Context Agent pada sistem ini berfungsi sebagai bounded LLM agent untuk sintesis konteks lingkungan. Agent membaca snapshot Unity melalui tool terbatas dan menghasilkan `ContextOutput` terstruktur, sementara perhitungan spasial yang bersifat objektif seperti filtering visited, ranking jarak, dan `nav_target` dilakukan secara deterministic oleh backend untuk menjaga reliabilitas navigasi VR.
