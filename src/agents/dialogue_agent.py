"""
Dialogue Agent — Character Persona & Interaction Engine
=======================================================
Module  : Profile → Perception → Self-Action → Mutual Interaction → Evolution
Role    : Cultural NPC Persona & Parent Node (Synthesiser)
Layer   : Parent Node (Subscriber / Synthesiser)

Five-module mapping
-------------------
Profile         : NPC's social interface with cultural lore and personality traits.
Perception      : Subscribes to Message Pool — reads ContextOutput JSON from Context Agent.
Self-Action     : Translates structured recommendations into immersive NPC dialogue.
Mutual Interaction: Publishes DialogueOutput JSON; the coordinator sends HUD commands.
Evolution       : Audits dialogue for persona alignment and recommendation clarity.

Hierarchical Interaction
------------------------
  Dialogue Agent (Parent Node / Synthesiser)
    └── Context Agent (Child Node — publishes ContextOutput JSON)
"""

import json
import os
import re
from typing import Any

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from core.config import settings
from vr_tools import show_subtitle


# ---------------------------------------------------------------------------
# Dialogue uncertainty settings
# ---------------------------------------------------------------------------
DIALOGUE_UQ_SAMPLE_COUNT = max(1, int(os.getenv("DIALOGUE_UQ_SAMPLES", "3")))
DIALOGUE_UQ_LOW_CONFIDENCE_THRESHOLD = float(os.getenv("DIALOGUE_UQ_MIN_CDEG", "0.45"))
DIALOGUE_UQ_RECOMMENDATION_WEIGHT = 0.50
DIALOGUE_UQ_SUBTITLE_WEIGHT = 0.30
DIALOGUE_UQ_OPTIONS_WEIGHT = 0.20

# ---------------------------------------------------------------------------
# NPC persona constants
# ---------------------------------------------------------------------------
NPC_NAME         = "Arif"
NPC_PERSONALITY  = "Pemandu budaya yang bijaksana dan hangat di museum warisan budaya VR."
NPC_SPEECH_STYLE = (
    "Ramah, meyakinkan, dan ringkas. Berbicara langsung kepada pemain dengan bahasa Indonesia "
    "yang natural. Menyisipkan konteks budaya singkat ke dalam rekomendasi tanpa berlebihan."
)

# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------

@tool
def tool_show_subtitle(text: str) -> bool:
    """
    Sends the condensed NPC subtitle to the Unity VR HUD display.
    Call this with the subtitle_output value after generating your JSON response.

    Args:
        text: A condensed single sentence (≤ 15 words) for the HUD.
    """
    return show_subtitle(text)


# ---------------------------------------------------------------------------
# HUD-centric black-box response similarity UQ for dialogue generation
# ---------------------------------------------------------------------------
def _clean_json_text(raw: str) -> str:
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def _parse_json_sample(raw: str) -> dict[str, Any]:
    required_fields = {
        "spoken_output",
        "subtitle_output",
        "recommendation_dialogue",
        "recommendation_options",
    }
    try:
        parsed = json.loads(_clean_json_text(raw))
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict) and required_fields.issubset(parsed):
        return parsed

    decoder = json.JSONDecoder()
    for index, character in enumerate(raw):
        if character != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and required_fields.issubset(candidate):
            return candidate
    return {}


def _tokenize_for_similarity(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _text_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize_for_similarity(left)
    right_tokens = _tokenize_for_similarity(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _option_similarity(left: list[Any], right: list[Any]) -> float:
    left_values = [str(value).strip().lower() for value in left if str(value).strip()]
    right_values = [str(value).strip().lower() for value in right if str(value).strip()]
    if not left_values and not right_values:
        return 1.0
    if left_values == right_values:
        return 1.0
    left_set = set(left_values)
    right_set = set(right_values)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _dialogue_pair_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    """
    HUD-centric black-box response-similarity UQ.

    a_ij = 0.50 * sim(recommendation_dialogue_i, recommendation_dialogue_j)
         + 0.30 * sim(subtitle_i, subtitle_j)
         + 0.20 * sim(options_i, options_j)

    spoken_output remains in the API schema for backward compatibility, but is
    deliberately excluded because the current VR experience has no audio/TTS.

    This mirrors the paper's black-box graph idea at the HUD-response level.
    In a production NLI deployment, each text similarity term can be replaced by
    entailment probability p_entail(response_i, response_j).
    """
    recommendation_similarity = _text_similarity(
        str(left.get("recommendation_dialogue", "")),
        str(right.get("recommendation_dialogue", "")),
    )
    subtitle_similarity = _text_similarity(
        str(left.get("subtitle_output", "")),
        str(right.get("subtitle_output", "")),
    )
    options_similarity = _option_similarity(
        left.get("recommendation_options", []),
        right.get("recommendation_options", []),
    )
    return (
        DIALOGUE_UQ_RECOMMENDATION_WEIGHT * recommendation_similarity
        + DIALOGUE_UQ_SUBTITLE_WEIGHT * subtitle_similarity
        + DIALOGUE_UQ_OPTIONS_WEIGHT * options_similarity
    )


def _degree_scores(samples: list[dict[str, Any]]) -> list[float]:
    """
    CDeg_i = sum_{j != i} a_ij / (m - 1)

    Dialogue Agent returns the sample with the highest CDeg, i.e. the most
    semantically central response among sampled generations.
    """
    sample_count = len(samples)
    if sample_count <= 1:
        return [1.0] * sample_count

    scores: list[float] = []
    for left_index, left_sample in enumerate(samples):
        pair_scores = [
            _dialogue_pair_similarity(left_sample, right_sample)
            for right_index, right_sample in enumerate(samples)
            if right_index != left_index
        ]
        scores.append(sum(pair_scores) / len(pair_scores) if pair_scores else 0.0)
    return scores


def _dialogue_uncertainty_report(samples: list[dict[str, Any]], degree_scores: list[float]) -> dict[str, Any]:
    field_weights = {
        "recommendation_dialogue": DIALOGUE_UQ_RECOMMENDATION_WEIGHT,
        "subtitle_output": DIALOGUE_UQ_SUBTITLE_WEIGHT,
        "recommendation_options": DIALOGUE_UQ_OPTIONS_WEIGHT,
    }
    if len(samples) <= 1:
        return {
            "method": "hud_black_box_response_similarity_cdeg",
            "sample_count": len(samples),
            "field_weights": field_weights,
            "degree_scores": [1.0] * len(samples),
            "udeg": 0.0,
            "selected_cdeg": 1.0,
        }
    return {
        "method": "hud_black_box_response_similarity_cdeg",
        "sample_count": len(samples),
        "field_weights": field_weights,
        "degree_scores": degree_scores,
        "udeg": 1.0 - (sum(degree_scores) / len(degree_scores)),
        "selected_cdeg": max(degree_scores) if degree_scores else 0.0,
    }


def _expected_options_from_payload(prompt: str) -> list[str]:
    try:
        parsed = json.loads(prompt)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, dict):
        return []

    context = parsed.get("context") if parsed.get("mode") == "selection_confirmation" else parsed
    if not isinstance(context, dict):
        return []

    recommendations = context.get("recommendations", [])
    if not isinstance(recommendations, list):
        return []

    return [
        item.get("name", "")
        for item in recommendations
        if isinstance(item, dict) and item.get("name")
    ][:3]


def _grounding_score(sample: dict[str, Any], expected_options: list[str]) -> float:
    if not expected_options:
        actual_options = sample.get("recommendation_options", [])
        return 1.0 if actual_options == [] else 0.5

    actual_options = sample.get("recommendation_options", [])
    option_score = _option_similarity(actual_options, expected_options)
    primary = expected_options[0].lower()
    visible_text = " ".join(
        [
            str(sample.get("recommendation_dialogue", "")),
            str(sample.get("subtitle_output", "")),
        ]
    ).lower()
    primary_score = 1.0 if primary in visible_text else 0.0
    subtitle_words = str(sample.get("subtitle_output", "")).split()
    subtitle_score = 1.0 if subtitle_words and len(subtitle_words) <= 15 else 0.0
    return 0.50 * option_score + 0.35 * primary_score + 0.15 * subtitle_score


def _safe_dialogue_from_payload(prompt: str) -> str | None:
    try:
        parsed = json.loads(prompt)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    if parsed.get("mode") == "selection_confirmation":
        selected_option = str(parsed.get("selected_option", "")).strip() or "tujuan yang dipilih"
        context = parsed.get("context", {})
        recommendations = context.get("recommendations", []) if isinstance(context, dict) else []
        options = [
            item.get("name", "")
            for item in recommendations
            if isinstance(item, dict) and item.get("name")
        ][:3]
        return json.dumps(
            {
                "spoken_output": (
                    f"Baik, kita akan menuju {selected_option}. "
                    "Saya akan memandu perjalanan Anda dari sini."
                ),
                "subtitle_output": f"Mari menuju {selected_option}.",
                "recommendation_dialogue": "Pilihan Anda sudah diterima. Saya akan memandu ke tujuan yang dipilih.",
                "recommendation_options": options,
            },
            ensure_ascii=False,
        )

    recommendations = parsed.get("recommendations", [])
    if not isinstance(recommendations, list):
        return None

    options = [
        item.get("name", "")
        for item in recommendations
        if isinstance(item, dict) and item.get("name")
    ][:3]
    if not options:
        return json.dumps(
            {
                "spoken_output": (
                    "Saat ini belum ada tujuan budaya baru yang perlu dipilih. "
                    "Anda bisa menikmati area di sekitar terlebih dahulu."
                ),
                "subtitle_output": "Belum ada tujuan baru saat ini.",
                "recommendation_dialogue": "Saat ini belum ada rekomendasi baru di sekitar Anda.",
                "recommendation_options": [],
            },
            ensure_ascii=False,
        )

    primary = options[0]
    if len(options) == 1:
        spoken_output = (
            f"Saat ini {primary} menjadi tujuan budaya yang paling siap kita kunjungi. "
            "Mari saya pandu ke sana."
        )
        recommendation_dialogue = "Ada satu tujuan budaya yang belum dikunjungi dan siap dipilih."
    else:
        alternatives = ", ".join(options[1:])
        spoken_output = (
            f"Ada beberapa tujuan budaya yang bisa kita jelajahi. "
            f"Mari mulai dari {primary}; alternatifnya adalah {alternatives}."
        )
        recommendation_dialogue = "Pilih salah satu tujuan budaya, dan saya akan memandu perjalanan Anda."

    return json.dumps(
        {
            "spoken_output": spoken_output,
            "subtitle_output": f"Mari menuju {primary}.",
            "recommendation_dialogue": recommendation_dialogue,
            "recommendation_options": options,
        },
        ensure_ascii=False,
    )


class DialogueUncertaintyAgent:
    """
    A transparent wrapper around the Strands Dialogue Agent.

    Category used:
      HUD-centric black-box response similarity UQ + grounding score.

    What it does:
      1. Generate m candidate DialogueOutput JSON strings.
      2. Compute pairwise HUD response similarity a_ij.
      3. Compute CDeg for every candidate.
      4. Combine CDeg with grounding score and return the highest-score response.
      5. If all candidates are too dispersed, return a conservative safe dialogue.
    """

    def __init__(
        self,
        agent: Agent,
        tools: list[Any],
        sample_count: int = DIALOGUE_UQ_SAMPLE_COUNT,
    ):
        self._agent = agent
        self._tools = tools
        self.sample_count = sample_count
        self.last_uq_report: dict[str, Any] = {}

    @property
    def model(self):
        return self._agent.model

    @model.setter
    def model(self, value):
        self._agent.model = value

    def __getattr__(self, name: str):
        return getattr(self._agent, name)

    def _sample_once(self, prompt: str) -> str:
        stateless_agent = Agent(
            model=self._agent.model,
            system_prompt=self._agent.system_prompt,
            tools=self._tools,
        )
        return str(stateless_agent(prompt)).strip()

    def __call__(self, prompt: str) -> str:
        raw_samples = [
            self._sample_once(prompt)
            for _ in range(max(1, self.sample_count))
        ]
        parsed_samples = [_parse_json_sample(raw_sample) for raw_sample in raw_samples]
        degree_scores = _degree_scores(parsed_samples)
        expected_options = _expected_options_from_payload(prompt)
        grounding_scores = [
            _grounding_score(parsed_sample, expected_options)
            for parsed_sample in parsed_samples
        ]
        selection_scores = [
            0.45 * degree_score + 0.55 * grounding_score
            for degree_score, grounding_score in zip(degree_scores, grounding_scores)
        ]
        selected_index = max(range(len(raw_samples)), key=lambda index: selection_scores[index])
        selected_cdeg = degree_scores[selected_index]

        self.last_uq_report = _dialogue_uncertainty_report(parsed_samples, degree_scores)
        self.last_uq_report["selected_index"] = selected_index
        self.last_uq_report["selected_cdeg"] = selected_cdeg
        self.last_uq_report["max_cdeg"] = max(degree_scores) if degree_scores else 0.0
        self.last_uq_report["grounding_scores"] = grounding_scores
        self.last_uq_report["selection_scores"] = selection_scores
        self.last_uq_report["selected_grounding"] = grounding_scores[selected_index]
        self.last_uq_report["selected_score"] = selection_scores[selected_index]

        if (
            selected_cdeg < DIALOGUE_UQ_LOW_CONFIDENCE_THRESHOLD
            and grounding_scores[selected_index] < 1.0
        ):
            safe_dialogue = _safe_dialogue_from_payload(prompt)
            if safe_dialogue:
                self.last_uq_report["fallback"] = "safe_dialogue_low_cdeg"
                return safe_dialogue

        return raw_samples[selected_index]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
DIALOGUE_AGENT_SYSTEM_PROMPT = f"""
Role: Dialogue Agent — Character Persona & Parent Node
Objective: Ubah rekomendasi JSON dari Context Agent menjadi teks HUD dan opsi rekomendasi
           yang jelas untuk pengguna VR. spoken_output tetap dihasilkan hanya untuk
           kompatibilitas kontrak API lama; pengalaman VR saat ini tidak memakai audio/TTS.

PROFILE (Persona):
  Name         : {NPC_NAME}
  Identity     : {NPC_PERSONALITY}
  Speech Style : {NPC_SPEECH_STYLE}
  Cultural Scope: Arsitektur warisan, makna artefak, tradisi seremonial,
                  dan konteks ruang budaya. Ini adalah domain EKSKLUSIF Anda.
  Prioritas    : Kejelasan HUD, ketepatan tujuan, relevansi konteks, dan kestabilan format JSON.

HUD DELIVERY:
  Coordinator akan mengirim subtitle_output ke Unity HUD setelah JSON tervalidasi.
  Jangan menghasilkan tool-call dan jangan membungkus output di dalam nama fungsi/tool.

INPUT:
You may receive one of these two JSON shapes.

Shape A — Context recommendation synthesis:
{{
  "timestamp": "...",
  "scene": "...",
  "user_action": "...",
  "context_summary": "...",
  "situation_type": "...",
  "recommendation_reason": "...",
  "dialogue_intent": "...",
  "recommendations": [
    {{"rank": 1, "id": "...", "name": "...", "cultural_position": "x, y, z"}},
    {{"rank": 2, "id": "...", "name": "...", "cultural_position": "x, y, z"}},
    {{"rank": 3, "id": "...", "name": "...", "cultural_position": "x, y, z"}}
  ],
  "nav_target": "..."
}}

Shape B — Selection confirmation synthesis:
{{
  "mode": "selection_confirmation",
  "selected_option": "...",
  "selected_site_id": "...",
  "context": {{
    "timestamp": "...",
    "scene": "...",
    "user_action": "...",
    "context_summary": "...",
    "situation_type": "...",
    "recommendation_reason": "...",
    "dialogue_intent": "...",
    "recommendations": [
      {{"rank": 1, "id": "...", "name": "...", "cultural_position": "x, y, z"}}
    ],
    "nav_target": "..."
  }}
}}

INSTRUKSI INTI:
  1. Identifikasi mode input:
    • Shape A = rekomendasi awal / pembukaan pilihan.
    • Shape B = konfirmasi pilihan pemain.
  2. Tulis semua teks dalam bahasa Indonesia yang natural, hangat, dan langsung ke pemain.
  3. Jangan pernah menampilkan:
    • ID mentah
    • koordinat
    • angka jarak
    • token sistem
    • istilah teknis backend
  4. cultural_position hanya konteks internal. Jangan ditampilkan ke pengguna.
  5. Jika fakta budaya tidak jelas di input, jangan mengarang detail spesifik.
     Lebih baik gunakan deskripsi aman seperti "objek budaya", "bangunan tradisional",
     atau "tujuan berikutnya".
  6. Gunakan context_summary, recommendation_reason, dan dialogue_intent sebagai arahan
     grounded untuk membuat recommendation_dialogue dan subtitle_output lebih spesifik,
     tetapi jangan menyalinnya mentah-mentah jika terdengar teknis atau terlalu panjang.
  7. Jangan memanggil tool apa pun. Tugas Anda hanya menghasilkan DialogueOutput JSON.
  8. Keluarkan HANYA satu objek JSON valid, tanpa markdown dan tanpa teks tambahan.

FIELD USAGE PRIORITY:
  • recommendations       : sumber nama opsi, urutan opsi, dan tujuan utama.
  • nav_target            : validasi tujuan aktif; harus konsisten dengan rank-1 pada Mode A.
  • situation_type        : menentukan pola dialog:
      - multiple_recommendations → arahkan ke tujuan utama dan tawarkan alternatif.
      - single_recommendation    → fokus pada satu tujuan, jangan seolah ada banyak pilihan.
      - all_sites_visited        → jangan memaksa navigasi; ajak pemain menikmati area.
      - exploration_context      → beri dorongan eksplorasi ringan tanpa klaim spesifik.
  • dialogue_intent       : menentukan intensi respons:
      - guide_to_primary_with_alternatives → pemanduan tujuan utama + opsi alternatif.
      - guide_to_single_primary            → pemanduan satu tujuan.
      - no_new_destination                 → tidak ada rekomendasi baru.
      - encourage_exploration              → dorongan eksplorasi.
  • recommendation_reason : bahan alasan singkat dalam recommendation_dialogue, tanpa koordinat/angka.
  • context_summary       : bahan recommendation_dialogue UI, diparafrasekan agar natural.
  • user_action           : sinyal keadaan pemain; gunakan hanya jika membantu dialog.

ATURAN PER MODE:
  Mode A — Recommendation synthesis:
    • Objek rank-1 adalah tujuan utama aktif.
    • Objek rank-2 dan rank-3 adalah alternatif yang bisa dipilih pemain.
    • recommendation_options harus mengikuti urutan recommendations persis.
    • recommendation_dialogue harus menyebut tujuan utama dan menjadi teks utama HUD.
    • spoken_output harus:
      - mengarahkan pemain ke tujuan utama
      - menyebut alternatif lain dengan wajar
      - memanfaatkan recommendation_reason atau context_summary bila tersedia
      - tetap valid untuk kompatibilitas API, walaupun tidak dipakai oleh Unity saat ini
    • subtitle_output harus singkat, jelas, dan fokus pada tujuan utama.
    • recommendation_dialogue tidak boleh sekadar mengulang subtitle.

  Mode B — Selection confirmation:
    • Fokus utama adalah mengonfirmasi pilihan pemain.
    • subtitle_output wajib menyebut selected_option karena field ini tampil di HUD.
    • spoken_output tetap menyebut selected_option untuk kompatibilitas respons lama.
    • recommendation_dialogue harus menandakan bahwa pilihan pemain telah diterima.
    • recommendation_options boleh tetap mengikuti recommendations pada context.
    • Nada harus terasa meyakinkan, seolah NPC siap memandu perjalanan.

ATURAN GAYA BAHASA:
  • Gunakan kalimat pendek sampai menengah.
  • Hindari bahasa terlalu formal, kaku, atau akademik.
  • Hindari bahasa bercampur Inggris.
  • Hindari pengulangan nama objek terlalu banyak dalam satu output.
  • Hindari janji yang tidak didukung context, seperti menyebut sejarah rinci yang tidak ada di input.
  • Jika ada 3 opsi, prioritaskan penyebutan objek rank-1 terlebih dahulu.
  • Jika hanya ada 1 opsi, jangan seolah-olah masih ada banyak pilihan.

OUTPUT FORMAT — JSON ketat, tanpa code fence, tanpa teks tambahan:
{{
  "spoken_output": "<ucapan NPC 2–4 kalimat dalam bahasa Indonesia>",
  "subtitle_output": "<satu kalimat ≤ 15 kata untuk HUD>",
  "recommendation_dialogue": "<kalimat singkat bahasa Indonesia untuk UI>",
  "recommendation_options": ["<option_1>", "<option_2>", "<option_3>"]
}}

FEW-SHOT EXAMPLES:

Example 1 — Shape A, multiple_recommendations:
Input:
{{
  "timestamp": "2026-05-01T12:30:00Z",
  "scene": "Heritage_Museum_Wing_A",
  "user_action": "Pemain berada di area dengan beberapa tujuan budaya yang belum dikunjungi.",
  "context_summary": "Pemain berada di Heritage_Museum_Wing_A dengan tiga objek budaya belum dikunjungi yang dapat direkomendasikan.",
  "situation_type": "multiple_recommendations",
  "recommendation_reason": "Kujang diprioritaskan sebagai tujuan utama karena menjadi kandidat terdekat yang belum dikunjungi. Alternatif yang tersedia: Angklung, Surabi.",
  "dialogue_intent": "guide_to_primary_with_alternatives",
  "recommendations": [
    {{"rank": 1, "id": "Kujang", "name": "Kujang", "cultural_position": "6.211527, -1.27006, 7.544006"}},
    {{"rank": 2, "id": "Angklung", "name": "Angklung", "cultural_position": "14.62413, 1.37554, 18.67057"}},
    {{"rank": 3, "id": "Surabi", "name": "Surabi", "cultural_position": "-1.34956, 1.52654, 23.7432"}}
  ],
  "nav_target": "Kujang"
}}
Output:
{{
  "spoken_output": "Ada beberapa tujuan budaya yang masih bisa kita jelajahi di area ini. Mari mulai dari Kujang sebagai tujuan utama berikutnya. Jika Anda ingin memilih jalur lain, Angklung dan Surabi juga tersedia.",
  "subtitle_output": "Mari menuju Kujang.",
  "recommendation_dialogue": "Ada tiga tujuan budaya yang belum dikunjungi. Pilih salah satu, dan saya akan memandu Anda.",
  "recommendation_options": ["Kujang", "Angklung", "Surabi"]
}}

Example 2 — Shape A, single_recommendation:
Input:
{{
  "timestamp": "2026-05-01T12:35:00Z",
  "scene": "Heritage_Museum_Wing_B",
  "user_action": "Pemain berada dekat satu tujuan budaya yang belum dikunjungi.",
  "context_summary": "Pemain berada di Heritage_Museum_Wing_B dengan satu objek budaya belum dikunjungi yang siap diarahkan, yaitu Angklung.",
  "situation_type": "single_recommendation",
  "recommendation_reason": "Angklung diprioritaskan karena menjadi satu-satunya objek budaya yang belum dikunjungi pada snapshot saat ini.",
  "dialogue_intent": "guide_to_single_primary",
  "recommendations": [
    {{"rank": 1, "id": "Angklung", "name": "Angklung", "cultural_position": "2, 0, 0"}}
  ],
  "nav_target": "Angklung"
}}
Output:
{{
  "spoken_output": "Saat ini ada satu tujuan budaya yang paling siap kita kunjungi, yaitu Angklung. Mari saya pandu ke sana dengan tenang. Setelah tiba, Anda bisa melanjutkan eksplorasi dari area itu.",
  "subtitle_output": "Mari menuju Angklung.",
  "recommendation_dialogue": "Ada satu tujuan budaya yang belum dikunjungi dan siap dipilih.",
  "recommendation_options": ["Angklung"]
}}

Example 3 — Shape A, all_sites_visited:
Input:
{{
  "timestamp": "2026-05-01T12:40:00Z",
  "scene": "Heritage_Museum_Wing_C",
  "user_action": "Pemain berada di area tanpa tujuan budaya baru yang belum dikunjungi.",
  "context_summary": "Pemain berada di Heritage_Museum_Wing_C, tetapi semua objek budaya pada snapshot saat ini sudah dikunjungi atau tidak ada kandidat baru.",
  "situation_type": "all_sites_visited",
  "recommendation_reason": "Tidak ada rekomendasi baru karena tidak ditemukan objek budaya dengan status belum dikunjungi.",
  "dialogue_intent": "no_new_destination",
  "recommendations": [],
  "nav_target": ""
}}
Output:
{{
  "spoken_output": "Saat ini belum ada tujuan budaya baru yang perlu dipilih. Anda bisa menikmati area di sekitar Anda terlebih dahulu. Jika ada objek baru yang tersedia, saya akan membantu mengarahkan Anda.",
  "subtitle_output": "Belum ada tujuan baru saat ini.",
  "recommendation_dialogue": "Semua tujuan pada area ini sudah dikunjungi atau belum ada kandidat baru.",
  "recommendation_options": []
}}

Example 4 — Shape B, konfirmasi pilihan:
Input:
{{
  "mode": "selection_confirmation",
  "selected_option": "Surabi",
  "selected_site_id": "Surabi",
  "context": {{
    "timestamp": "2026-05-01T12:30:00Z",
    "scene": "Heritage_Museum_Wing_A",
    "user_action": "Pemain berada di area dengan beberapa tujuan budaya yang belum dikunjungi.",
    "context_summary": "Pemain berada di Heritage_Museum_Wing_A dengan tiga objek budaya belum dikunjungi yang dapat direkomendasikan.",
    "situation_type": "multiple_recommendations",
    "recommendation_reason": "Kujang diprioritaskan sebagai tujuan utama karena menjadi kandidat terdekat yang belum dikunjungi. Alternatif yang tersedia: Angklung, Surabi.",
    "dialogue_intent": "guide_to_primary_with_alternatives",
    "recommendations": [
      {{"rank": 1, "id": "Kujang", "name": "Kujang", "cultural_position": "6.211527, -1.27006, 7.544006"}},
      {{"rank": 2, "id": "Angklung", "name": "Angklung", "cultural_position": "14.62413, 1.37554, 18.67057"}},
      {{"rank": 3, "id": "Surabi", "name": "Surabi", "cultural_position": "-1.34956, 1.52654, 23.7432"}}
    ],
    "nav_target": "Surabi"
  }}
}}
Output:
{{
  "spoken_output": "Kita akan menuju Surabi sebagai tujuan berikutnya. Saya akan memandu perjalanan Anda dari sini.",
  "subtitle_output": "Mari menuju Surabi.",
  "recommendation_dialogue": "Pilihan Anda sudah diterima. Saya akan memandu ke tujuan yang dipilih.",
  "recommendation_options": ["Kujang", "Angklung", "Surabi"]
}}

CONSTRAINTS:
  1. Output HANYA objek JSON, tanpa penjelasan dan tanpa markdown fences.
  2. Semua teks yang tampil ke pengguna harus dalam bahasa Indonesia.
  3. Jangan tampilkan ID, angka mentah, koordinat, atau token sistem dalam spoken/subtitle/UI text.
  4. Jaga konsistensi persona: hangat, membantu, dan relevan dengan konteks budaya.
  5. spoken_output maksimal 2–4 kalimat. subtitle_output maksimal 15 kata.
  6. recommendation_options harus berisi nama objek saja, tanpa ID.
  7. recommendation_dialogue dan spoken_output harus relevan dengan rekomendasi aktual pada input.
  8. Opsi pertama pada recommendation_options harus sama dengan objek rank-1 / nav_target aktif.
  9. Jika recommendations kosong, recommendation_options harus berupa array kosong.
  10. Jika hanya ada satu rekomendasi, recommendation_options boleh berisi satu item saja.
  11. Jangan buat subtitle yang berbeda arah dengan spoken_output.
  12. Untuk mode selection_confirmation, selected_option harus disebut secara eksplisit.

EVOLUTION (invoked externally):
  Audit last N outputs for persona drift, exposed tokens, mixed language, or unclear recommendations.
  Output: {{"reflection": "<finding>", "alignment_score": <0-100>}}
"""

# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------
dialogue_model = OpenAIModel(
    client_args={
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    },
    model_id=settings.llm_model,
    params=settings.llm_model_params_for(500),
)

_base_dialogue_agent = Agent(
    model=dialogue_model,
    system_prompt=DIALOGUE_AGENT_SYSTEM_PROMPT,
    tools=[],
)

dialogue_agent = DialogueUncertaintyAgent(_base_dialogue_agent, tools=[])


def get_dialogue_agent() -> DialogueUncertaintyAgent:
    """Return the singleton uncertainty-aware Dialogue Agent (Parent Node)."""
    return dialogue_agent
