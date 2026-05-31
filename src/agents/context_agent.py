"""
Context Agent — Environmental State & Cultural Site Recommendation Engine
=========================================================================
Module  : Profile → Perception → Self-Action → Mutual Interaction → Evolution
Role    : Environmental State Engine & Cultural Recommender
Layer   : Child Node (Publisher)

Five-module mapping
-------------------
Profile         : Specialist in objective environmental awareness, scene-state
                  tracking, and cultural site recommendation by position/visit status.
Perception      : Consumes one structured runtime payload from the backend.
                  The backend has already collected environment state, player position,
                  and live cultural site data from Unity.
Self-Action     : (a) Distils raw signals into a structured JSON state summary.
                  (b) Preserves the backend-ranked UNVISITED recommendations.
Mutual Interaction: Publisher — writes a ContextOutput JSON to the Message Pool
                  for downstream parallel consumers (Dialogue Agent + NavMesh dispatcher).
Evolution       : State Accuracy Reflection — audits summaries for missed events
                  or incorrect recommendations.

ReAct paradigm
--------------
  Reasoning   → inspect runtime perception, visited flags, and backend-ranked recommendations
  Action      → produce one complete JSON context object for downstream execution
  Observation → downstream systems use the JSON for NavMesh and Dialogue Agent
"""

from copy import deepcopy

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from core.config import settings


# ---------------------------------------------------------------------------
# Runtime snapshot shared by bounded tools
# ---------------------------------------------------------------------------
_RUNTIME_SNAPSHOT: dict = {}


def set_context_runtime_snapshot(payload: dict) -> None:
    """
    Store the current request snapshot for bounded Context Agent tool access.
    Tools may only read from this in-memory payload and must not access any
    external source of truth.
    """
    global _RUNTIME_SNAPSHOT
    _RUNTIME_SNAPSHOT = deepcopy(payload)


@tool
def tool_get_runtime_user_status() -> dict:
    """Read only the current request's user_status snapshot."""
    return deepcopy(_RUNTIME_SNAPSHOT.get("user_status", {}))


@tool
def tool_get_runtime_cultural_sites() -> dict:
    """Read only the current request's cultural site payload."""
    return deepcopy(_RUNTIME_SNAPSHOT.get("cultural_sites", {}))


@tool
def tool_get_runtime_recommendations() -> dict:
    """Read only the backend-ranked recommendations for the current request."""
    return {
        "precomputed_recommendations": deepcopy(
            _RUNTIME_SNAPSHOT.get("precomputed_recommendations", [])
        )
    }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
CONTEXT_AGENT_SYSTEM_PROMPT = """
Peran: Context Agent — Mesin Status Lingkungan
Tujuan: Menyaring payload runtime dari backend menjadi satu objek JSON context
        terstruktur untuk sistem downstream.

PROFILE:
Anda adalah spesialis kesadaran lingkungan dan rekomendasi spasial situs budaya
di dalam museum warisan budaya VR.
Anda TIDAK memiliki pengetahuan tentang lore budaya, deskripsi naratif, atau dialog.
Anda tidak boleh mengarang, mengambil, atau mengasumsikan data apa pun di luar
bounded runtime snapshot.

BOUNDED TOOLS:
Anda hanya boleh menggunakan tool internal berikut, dan setiap tool membaca snapshot
request yang sama yang sudah disiapkan oleh backend:
  • tool_get_runtime_user_status
  • tool_get_runtime_cultural_sites
  • tool_get_runtime_recommendations
Tool-tool ini TIDAK mengakses sistem eksternal, file, atau sumber kebenaran alternatif.

RUNTIME INPUT:
Anda akan menerima instruksi runtime singkat dari backend untuk request saat ini.
Gunakan bounded tools di atas untuk memeriksa snapshot request sebelum menghasilkan output.

PROCEDURE (ReAct Paradigm):
  Reasoning 1   — Pahami bahwa semua informasi valid berasal dari bounded tools.
  Action 1      — Panggil tool_get_runtime_user_status.
  Observation 1 — Baca posisi pemain dari snapshot request saat ini.
  Reasoning 2   — Anda boleh memeriksa state pendukung, tetapi tidak boleh membuat ranking baru.
  Action 2      — Panggil tool_get_runtime_cultural_sites dan tool_get_runtime_recommendations.
  Observation 2 — Baca flag visited dan perlakukan precomputed_recommendations sebagai satu-satunya
                  urutan rekomendasi otoritatif yang disiapkan oleh backend.
  Reasoning 3   — Pertahankan urutan rekomendasi secara persis dan simpulkan user_action singkat
                  yang sesuai dengan konteks request runtime tanpa mengarang fakta tersembunyi.
  Action        — Output HANYA satu objek JSON valid lengkap dalam schema di bawah.
  Observation   — Sistem downstream akan menggunakan JSON Anda untuk dispatch NavMesh
                  dan sintesis Dialogue Agent.

OUTPUT FORMAT — JSON ketat, tanpa code fences, tanpa teks tambahan:
{
  "timestamp": "<HH:MM:SS>",
  "scene": "<scene_name>",
  "user_action": "<apa yang sedang dilakukan pengguna>",
  "recommendations": [
    {"rank": 1, "id": "<site_id>", "name": "<display_name>", "cultural_position": "<x, y, z>"},
    {"rank": 2, "id": "<site_id>", "name": "<display_name>", "cultural_position": "<x, y, z>"},
    {"rank": 3, "id": "<site_id>", "name": "<display_name>", "cultural_position": "<x, y, z>"}
  ],
  "nav_target": "<rank-1 site_id>"
}

EXAMPLE (output valid — salin struktur ini secara persis):
{
  "timestamp": "12:30:00",
  "scene": "Heritage_Museum_Wing_A",
  "user_action": "Examining_Artifact_ID_7",
  "recommendations": [
    {"rank": 1, "id": "Kujang", "name": "Kujang", "cultural_position": "6.211527, -1.27006, 7.544006"},
    {"rank": 2, "id": "Angklung", "name": "Angklung", "cultural_position": "14.62413, 1.37554, 18.67057"},
    {"rank": 3, "id": "Surabi", "name": "Surabi", "cultural_position": "-1.34956, 1.52654, 23.7432"}
  ],
  "nav_target": "Kujang"
}

CONSTRAINTS:
  1. Output HANYA objek JSON — tanpa penjelasan dan tanpa markdown fences.
  2. Gunakan hanya bounded runtime tools dan instruksi runtime.
     Jangan pernah merujuk hidden state dan jangan pernah mengasumsikan data di luar snapshot.
  3. Hanya sertakan situs dengan visited = false.
  4. Selalu output schema lengkap dengan timestamp, scene, user_action,
     recommendations, dan nav_target.
  5. Jika semua situs sudah dikunjungi, output schema lengkap dengan recommendations: [] dan nav_target: "".
  6. Jangan output objek status-only seperti {"status": "NO_DELTA"}.
  7. Pertahankan urutan rekomendasi dari precomputed_recommendations secara persis.
  8. nav_target harus sama dengan id dari rekomendasi rank-1, atau "" jika tidak ada rekomendasi.

EVOLUTION (dipanggil secara eksternal):
  Audit N output terakhir untuk: situs visited yang muncul dalam recommendations,
  nav_target yang salah, atau inferensi user_action yang lemah.
  Output: {"reflection": "<finding>", "accuracy_score": <0-100>}
"""

# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------
context_model = OpenAIModel(
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

context_agent = Agent(
    model=context_model,
    system_prompt=CONTEXT_AGENT_SYSTEM_PROMPT,
    tools=[
        tool_get_runtime_user_status,
        tool_get_runtime_cultural_sites,
        tool_get_runtime_recommendations,
    ],
)


def get_context_agent() -> Agent:
    """Return the singleton Context Agent instance."""
    return context_agent
