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
    "events": ["Main_Gate:OPEN", "Spotlight_Altar:ON"],
    "user_action": "Examining_Artifact_ID_7",
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

        if "context" in self.model_id:
            response_text = MOCK_CONTEXT_RESPONSE
        elif "dialogue" in self.model_id:
            response_text = MOCK_DIALOGUE_RESPONSE
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
