import asyncio
from typing import Any, AsyncGenerator, AsyncIterable, Optional, TypeVar
from pydantic import BaseModel
from strands.models.model import Model
from strands.types.streaming import StreamEvent

T = TypeVar("T", bound=BaseModel)

class MockModel(Model):
    """
    A mock model provider for testing the multi-agent system without real LLM calls.
    Returns predefined responses based on the agent name.
    """
    def __init__(self, model_id: str = "mock-model"):
        self.model_id = model_id

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {"model_id": self.model_id}

    async def structured_output(
        self, output_model: type[T], prompt: Any, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        # Minimal mock implementation
        yield {"output": output_model()}

    async def stream(
        self,
        messages: Any,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        """
        Simulates a model response.
        """
        # Parse prompt text safely from the last message
        last_message = messages[-1] if messages else {}
        content_list = last_message.get("content", [])
        prompt_text = ""
        for block in content_list:
            if isinstance(block, dict) and "text" in block:
                prompt_text += block["text"]

        response_text = "Standard mock response."

        # Context Agent Mock
        if "Context Agent" in (system_prompt or ""):
            response_text = "[T=00:03:12] SCENE:Great_Hall | EVENTS:North_Gate→LOCKED,Chandelier→ON | USER:Entered_Great_Hall"
        
        # Guidance Agent Mock
        elif "Guidance Agent" in (system_prompt or ""):
            response_text = "MOVE_TO: 12.5, 0.0, 45.0 → INTERACT: OPEN_Door_ID_3"
            if "LOCKED" in prompt_text:
                response_text = "BLOCKED: North_Gate is locked at 50.0, 0.0, 50.0 — Reporting to Message Pool."

        # Dialogue Agent Mock
        elif "Dialogue Agent" in (system_prompt or ""):
            if "BLOCKED" in prompt_text:
                response_text = (
                    "SPOKEN_OUTPUT: \"It seems the North Gate is barred for now. Perhaps we should look for another way?\" "
                    "SUBTITLE_OUTPUT: \"Gate is locked. Let's find another way.\""
                )
            else:
                response_text = (
                    "SPOKEN_OUTPUT: \"Welcome to the Great Hall! Please follow me towards the North Gate.\" "
                    "SUBTITLE_OUTPUT: \"Welcome! Follow me to the gate.\""
                )

        # Yield result as expected by Strands
        from strands.agent.agent_result import AgentResult
        from strands.telemetry.metrics import EventLoopMetrics
        
        # Message is a TypedDict
        msg = {
            "role": "assistant",
            "content": [{"text": response_text}]
        }
        
        # AgentResult is a dataclass
        res = AgentResult(
            stop_reason="end_turn",
            message=msg,
            metrics=EventLoopMetrics(),
            state={}
        )
        
        yield {"result": res, "data": response_text, "complete": True}
