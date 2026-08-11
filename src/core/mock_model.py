import json
import hashlib
from typing import Any, AsyncGenerator, AsyncIterable, TypeVar
from pydantic import BaseModel
from strands.models.model import Model
from strands.types.streaming import StreamEvent

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Mock JSON responses — mirrors what a real LLM would produce
# ---------------------------------------------------------------------------

MOCK_CONTEXT_RESPONSE = json.dumps({
    "timestamp": "12:30:00",
    "scene": "Heritage_Museum_Wing_A",
    "user_action": "Pemain berada di Heritage_Museum_Wing_A dengan beberapa rekomendasi tujuan.",
    "context_summary": (
        "Tersedia 3 rekomendasi teratas dari objek budaya yang belum dikunjungi "
        "di Heritage_Museum_Wing_A."
    ),
    "situation_type": "multiple_recommendations",
    "recommendation_reason": (
        "Kujang diprioritaskan sebagai tujuan utama karena menjadi kandidat terdekat "
        "yang belum dikunjungi. Alternatif yang tersedia: Angklung, Surabi."
    ),
    "dialogue_intent": "guide_to_primary_with_alternatives",
    "recommendations": [
        {"rank": 1, "id": "Kujang", "name": "Kujang", "cultural_position": "6.211527, -1.27006, 7.544006"},
        {"rank": 2, "id": "Angklung", "name": "Angklung", "cultural_position": "14.62413, 1.37554, 18.67057"},
        {"rank": 3, "id": "Surabi", "name": "Surabi", "cultural_position": "-1.34956, 1.52654, 23.7432"}
    ],
    "nav_target": "Kujang",
})

MOCK_DIALOGUE_RESPONSE = json.dumps({
    "spoken_output": (
        "Kita punya beberapa tujuan budaya menarik di sekitar ini. "
        "Mari mulai dari yang paling siap dikunjungi, lalu kita lihat pilihan lainnya."
    ),
    "subtitle_output": "Mulai dari tujuan teratas dulu.",
    "recommendation_dialogue": "Ada beberapa opsi menarik, jadi kita bisa pilih yang paling pas dulu.",
    "recommendation_options": ["Opsi 1", "Opsi 2", "Opsi 3"],
})

_MOCK_OPENERS_SELECTION = (
    "Baik, pilihan itu sudah saya terima.",
    "Siap, rute itu sudah kita tetapkan.",
    "Oke, keputusan Anda sudah saya catat.",
)

_MOCK_OPENERS_MULTI = (
    "Kita punya beberapa tujuan menarik di sekitar ini.",
    "Ada beberapa opsi yang bisa kita urutkan lebih dulu.",
    "Saat ini ada beberapa tujuan yang sama-sama layak dicoba.",
)

_MOCK_OPENERS_SINGLE = (
    "Saat ini ada satu tujuan yang paling relevan untuk kita datangi.",
    "Untuk langkah berikutnya, ada satu tujuan yang paling siap.",
    "Kalau kita cari rute paling efisien, ada satu tujuan yang paling pas.",
)

_MOCK_OPENERS_EMPTY = (
    "Untuk saat ini belum ada tujuan baru.",
    "Belum ada target baru, jadi kita bisa santai dulu.",
    "Saat ini tidak ada rekomendasi baru untuk dilanjutkan.",
)


def _stable_index(seed_text: str, size: int) -> int:
    if size <= 0:
        return 0
    digest = hashlib.sha1(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % size


def _join_names(names: list[str]) -> str:
    cleaned = [name.strip() for name in names if name and name.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} dan {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, dan {cleaned[-1]}"


def _build_dialogue_response(
    *,
    selected_option: str | None = None,
    scene: str = "",
    recommendation_reason: str = "",
    recommendations: list[dict[str, Any]] | list[Any] | None = None,
) -> str:
    options = [
        item.get("name", "")
        for item in (recommendations or [])
        if isinstance(item, dict) and item.get("name")
    ][:3]

    if selected_option:
        opener = _MOCK_OPENERS_SELECTION[_stable_index(f"selection:{selected_option}:{scene}", len(_MOCK_OPENERS_SELECTION))]
        return json.dumps({
            "spoken_output": (
                f"{opener} Saya akan memandu Anda menuju {selected_option} "
                f"{'di ' + scene if scene else ''}. "
                f"{recommendation_reason.strip().rstrip('.') or 'Kita lanjut dari sini.'}"
            ).strip(),
            "subtitle_output": (
                f"Baik, kita ke {selected_option}."
                if _stable_index(f"subtitle:{selected_option}", 2) == 0
                else f"Siap, menuju {selected_option}."
            ),
            "recommendation_dialogue": (
                "Pilihan Anda sudah saya catat. Kita lanjut dengan santai, saya pandu dari sini."
                if _stable_index(f"dialogue:{selected_option}", 2) == 0
                else "Keputusan itu sudah saya catat. Mari kita lanjut dengan nyaman."
            ),
            "recommendation_options": options,
        }, ensure_ascii=False)

    if not options:
        opener = _MOCK_OPENERS_EMPTY[_stable_index(f"empty:{scene}", len(_MOCK_OPENERS_EMPTY))]
        return json.dumps({
            "spoken_output": f"{opener} Kita bisa menikmati area sekitar dulu.",
            "subtitle_output": "Belum ada tujuan baru.",
            "recommendation_dialogue": "Belum ada tujuan baru; nikmati dulu suasana area ini dengan tenang.",
            "recommendation_options": [],
        }, ensure_ascii=False)

    primary_name = options[0]
    alternatives = _join_names(options[1:])
    opener = (
        _MOCK_OPENERS_SINGLE[_stable_index(f"single:{primary_name}:{scene}", len(_MOCK_OPENERS_SINGLE))]
        if len(options) == 1
        else _MOCK_OPENERS_MULTI[_stable_index(f"multi:{primary_name}:{scene}", len(_MOCK_OPENERS_MULTI))]
    )

    if len(options) == 1:
        spoken_output = (
            f"{opener} {primary_name} menjadi tujuan yang paling siap kita kunjungi. "
            f"{recommendation_reason.strip().rstrip('.') or 'Mari kita lanjut ke sana.'}"
        ).strip()
        subtitle_output = f"Fokus ke {primary_name} dulu."
    else:
        spoken_output = (
            f"{opener} Mari mulai dari {primary_name} sebagai langkah pertama. "
            f"Kalau mau jalur lain, {alternatives} juga tersedia. "
            f"{recommendation_reason.strip().rstrip('.') or 'Kita lanjut dari opsi teratas.'}"
        ).strip()
        subtitle_output = f"Mulai dari {primary_name} dulu."

    return json.dumps({
        "spoken_output": spoken_output,
        "subtitle_output": subtitle_output,
        "recommendation_dialogue": (
            "Ada beberapa opsi menarik, jadi kita bisa pilih yang paling pas dulu."
            if len(options) > 1
            else "Ada satu tujuan yang paling relevan untuk langkah berikutnya."
        ),
        "recommendation_options": options,
    }, ensure_ascii=False)


def _extract_text_payload(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    if isinstance(messages, list):
        parts: list[str] = []
        for message in messages:
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            text_value = item.get("text")
                            if text_value is not None:
                                parts.append(str(text_value))
        return "\n".join(parts)
    if isinstance(messages, dict):
        return _extract_text_payload([messages])
    return str(messages)


def _build_selection_dialogue_response(payload_text: str) -> str | None:
    try:
        parsed = json.loads(payload_text)
    except Exception:
        return None

    if not isinstance(parsed, dict) or parsed.get("mode") != "selection_confirmation":
        return None

    selected_option = str(parsed.get("selected_option", "")).strip() or "tujuan berikutnya"
    context = parsed.get("context", {})
    recommendations = context.get("recommendations", []) if isinstance(context, dict) else []
    scene = str(context.get("scene", "")).strip()
    recommendation_reason = str(context.get("recommendation_reason", "")).strip()
    return _build_dialogue_response(
        selected_option=selected_option,
        scene=scene,
        recommendation_reason=recommendation_reason,
        recommendations=recommendations,
    )


def _build_context_dialogue_response(payload_text: str) -> str | None:
    try:
        parsed = json.loads(payload_text)
    except Exception:
        return None

    if not isinstance(parsed, dict) or "recommendations" not in parsed:
        return None

    recommendations = parsed.get("recommendations", [])
    if not isinstance(recommendations, list) or not recommendations:
        return _build_dialogue_response(scene=str(parsed.get("scene", "")).strip(), recommendations=[])

    return _build_dialogue_response(
        scene=str(parsed.get("scene", "")).strip(),
        recommendation_reason=str(parsed.get("recommendation_reason", "")).strip(),
        recommendations=recommendations,
    )


class MockModel(Model):
    """
    Mock model provider for local testing without real LLM API calls.
    Returns strict JSON strings matching ContextOutput / DialogueOutput schemas.

    model_id routing:
      "mock-context"  → ContextOutput JSON
      "mock-dialogue" → DialogueOutput JSON
    """

    def __init__(self, model_id: str = "mock-model"):
        self.model_id = model_id

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {"model_id": self.model_id}

    async def structured_output(
        self, output_model: type[T], prompt: Any,
        system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        yield {"output": output_model()}

    async def stream(
        self,
        messages: Any,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        """Yields Strands StreamEvent sequence with a valid JSON response body."""

        payload_text = _extract_text_payload(messages)

        if "context" in self.model_id:
            response_text = MOCK_CONTEXT_RESPONSE
        elif "dialogue" in self.model_id:
            response_text = (
                _build_selection_dialogue_response(payload_text)
                or _build_context_dialogue_response(payload_text)
                or MOCK_DIALOGUE_RESPONSE
            )
        else:
            response_text = json.dumps({"status": "mock_response"})

        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}}
        yield {
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {"text": response_text},
            }
        }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {
                    "inputTokens": 10,
                    "outputTokens": len(response_text.split()),
                    "totalTokens": 10 + len(response_text.split()),
                },
                "metrics": {"latencyMs": 0},
            }
        }
