import json
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
    "user_action": "Pemain berada di area dengan beberapa tujuan budaya yang belum dikunjungi.",
    "context_summary": (
        "Pemain berada di Heritage_Museum_Wing_A dengan tiga objek budaya belum dikunjungi "
        "yang dapat direkomendasikan."
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
        "Saya sudah menyiapkan beberapa rekomendasi objek budaya di sekitar Anda. "
        "Silakan pilih tujuan yang paling ingin Anda kunjungi, dan saya akan membantu memandu perjalanannya."
    ),
    "subtitle_output": "Silakan pilih tujuan budaya berikutnya.",
    "recommendation_dialogue": (
        "Di sekitar posisi Anda ada beberapa objek budaya menarik. "
        "Pilih salah satu, dan saya akan memandu navigasinya."
    ),
    "recommendation_options": ["Opsi 1", "Opsi 2", "Opsi 3"],
})


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
    options = [item.get("name", "") for item in recommendations if isinstance(item, dict)][:3]

    return json.dumps({
        "spoken_output": (
            f"Baik, saya akan memandu Anda menuju {selected_option}. "
            f"Objek budaya ini menjadi tujuan berikutnya, dan saya akan menemani perjalanan Anda sampai tiba."
        ),
        "subtitle_output": f"Mari menuju {selected_option}.",
        "recommendation_dialogue": "Pilihan Anda sudah saya catat. Saya akan memandu perjalanan ke tujuan berikutnya.",
        "recommendation_options": options,
    }, ensure_ascii=False)


def _build_context_dialogue_response(payload_text: str) -> str | None:
    try:
        parsed = json.loads(payload_text)
    except Exception:
        return None

    if not isinstance(parsed, dict) or "recommendations" not in parsed:
        return None

    recommendations = parsed.get("recommendations", [])
    if not isinstance(recommendations, list) or not recommendations:
        return json.dumps({
            "spoken_output": (
                "Saat ini belum ada tujuan budaya baru yang perlu dipilih. "
                "Anda bisa menikmati area di sekitar Anda terlebih dahulu, lalu lanjut saat siap."
            ),
            "subtitle_output": "Belum ada tujuan baru saat ini.",
            "recommendation_dialogue": "Saat ini belum ada rekomendasi baru di sekitar Anda.",
            "recommendation_options": [],
        }, ensure_ascii=False)

    options = [
        item.get("name", "")
        for item in recommendations
        if isinstance(item, dict) and item.get("name")
    ][:3]
    if not options:
        return None

    primary_name = options[0]
    alternatives = options[1:]
    recommendation_reason = str(parsed.get("recommendation_reason", "")).strip()
    context_summary = str(parsed.get("context_summary", "")).strip()
    situation_type = str(parsed.get("situation_type", "")).strip()

    if situation_type == "single_recommendation" or not alternatives:
        spoken_output = (
            f"Saat ini tujuan budaya yang paling siap kita kunjungi adalah {primary_name}. "
            f"{recommendation_reason or 'Tujuan ini menjadi prioritas pada kondisi saat ini.'} "
            "Mari saya pandu ke sana."
        )
        recommendation_dialogue = (
            "Ada satu tujuan budaya yang belum dikunjungi dan siap dipilih."
        )
    elif alternatives:
        alternatives_text = ", ".join(alternatives)
        spoken_output = (
            f"Ada beberapa tujuan budaya yang masih bisa kita jelajahi. "
            f"Mari mulai dari {primary_name} sebagai tujuan utama berikutnya. "
            f"Jika ingin memilih jalur lain, Anda juga dapat memilih {alternatives_text}."
        )
        recommendation_dialogue = (
            context_summary
            or "Ada beberapa tujuan budaya yang belum dikunjungi. Pilih salah satu, dan saya akan memandu Anda."
        )

    return json.dumps({
        "spoken_output": spoken_output,
        "subtitle_output": f"Mari menuju {primary_name}.",
        "recommendation_dialogue": recommendation_dialogue,
        "recommendation_options": options,
    }, ensure_ascii=False)


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
