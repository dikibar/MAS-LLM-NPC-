import json
import logging
import concurrent.futures
from schema.models import (
    MessagePoolState, AgentMessage,
    ContextOutput, DialogueOutput,
    SimulationRequest,
)
from agents import get_context_agent, get_dialogue_agent
from vr_tools import show_subtitle

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


# ---------------------------------------------------------------------------
# In-Memory Message Pool
# ---------------------------------------------------------------------------
class InMemoryMessagePool:
    """
    Shared blackboard for agent communication.
    Stores validated Pydantic objects (not raw strings) for type-safe access.
    """

    def __init__(self):
        self.state = MessagePoolState()
        self.logger = logging.getLogger("MessagePool")

    def publish_context(self, output: ContextOutput):
        self.state.latest_context = output
        self.state.history.append(
            AgentMessage(role="context", content=output.model_dump_json())
        )
        self.logger.info(f"Context Published: scene={output.scene} | nav_target={output.nav_target}")

    def publish_dialogue(self, output: DialogueOutput):
        self.state.latest_dialogue = output
        self.state.history.append(
            AgentMessage(role="dialogue", content=output.spoken_output)
        )
        self.logger.info(f"Dialogue Published: {output.subtitle_output}")

    def get_context_json_for_dialogue(self) -> str:
        """Returns the Context Agent's validated output as a JSON string for the Dialogue Agent."""
        if self.state.latest_context:
            return self.state.latest_context.model_dump_json(indent=2)
        return "{}"


# ---------------------------------------------------------------------------
# JSON parsing helpers with fallback
# ---------------------------------------------------------------------------
def _parse_context(raw: str) -> ContextOutput:
    """Parse and validate the Context Agent's JSON output."""
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return ContextOutput.model_validate_json(clean)
    except Exception as e:
        logging.getLogger("Coordinator").warning(f"Context JSON parse failed: {e}\nRaw: {raw[:200]}")
        raise


def _parse_dialogue(raw: str) -> DialogueOutput:
    """Parse and validate the Dialogue Agent's JSON output."""
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return DialogueOutput.model_validate_json(clean)
    except Exception as e:
        logging.getLogger("Coordinator").warning(f"Dialogue JSON parse failed: {e}\nRaw: {raw[:200]}")
        raise


# ---------------------------------------------------------------------------
# Hierarchical Orchestrator
# ---------------------------------------------------------------------------
class HierarchicalOrchestrator:
    """
    2-Agent Parallel Architecture:

    Tick Cycle:
      1. Receive SimulationRequest (playerPosition + culturalObject[]) from API.
      2. Context Agent — analyses incoming data, ranks unvisited sites,
                         outputs ContextOutput JSON → Message Pool.
      3. Parallel:
           A. Unity NavMesh receives NAV_TARGET (NPC begins moving).
           B. Dialogue Agent reads ContextOutput JSON → produces DialogueOutput JSON.
      4. show_subtitle sends subtitle to Unity HUD.
    """

    def __init__(self):
        self.pool = InMemoryMessagePool()
        self.context_agent = get_context_agent()
        self.dialogue_agent = get_dialogue_agent()

        # Inject MockModel for local simulation (replace with real model keys when ready)
        from core.mock_model import MockModel
        self.context_agent.model = MockModel("mock-context")
        self.dialogue_agent.model = MockModel("mock-dialogue")

    def _run_dialogue_agent(self, context_json: str) -> DialogueOutput:
        print("[Dialogue Agent] Synthesising NPC speech in parallel...")
        raw = str(self.dialogue_agent(context_json)).strip()
        return _parse_dialogue(raw)

    def run_cycle(self, sim_request: SimulationRequest) -> dict:
        print("\n" + "=" * 54)
        print("  NEW VR TICK — 2-AGENT PARALLEL ARCHITECTURE")
        print("=" * 54)

        # ------------------------------------------------------------------
        # Build perception input from the incoming API request body
        # ------------------------------------------------------------------
        cultural_sites_str = json.dumps([
            {
                "name": obj.name,
                "coordinate": obj.coordinate,
                "isObjectVisited": obj.isObjectVisited,
            }
            for obj in sim_request.culturalObject
        ], indent=2)

        perception_input = (
            f"PLAYER_POSITION: {sim_request.playerPosition}\n"
            f"CULTURAL_OBJECTS:\n{cultural_sites_str}"
        )

        # ------------------------------------------------------------------
        # Phase 1: Context Agent
        # ------------------------------------------------------------------
        print("\n[Phase 1] Context Agent — perceiving world & selecting sites...")
        context_raw = str(self.context_agent(perception_input)).strip()
        context_output = _parse_context(context_raw)
        self.pool.publish_context(context_output)

        print("\n[Context Output — Validated JSON]")
        print(context_output.model_dump_json(indent=2))

        # ------------------------------------------------------------------
        # Phase 2: Parallel Handover
        # Unity NavMesh moves the NPC; Dialogue Agent synthesises speech.
        # ------------------------------------------------------------------
        print("\n[Phase 2] Parallel: NavMesh moving NPC + Dialogue Agent synthesising...")
        context_json = self.pool.get_context_json_for_dialogue()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._run_dialogue_agent, context_json)
            dialogue_output = future.result()

        self.pool.publish_dialogue(dialogue_output)

        # ------------------------------------------------------------------
        # Phase 3: Output to Unity HUD
        # ------------------------------------------------------------------
        show_subtitle(dialogue_output.subtitle_output)

        print("\n[Dialogue Output — Validated JSON]")
        print(dialogue_output.model_dump_json(indent=2))

        print("\n" + "-" * 54)
        print(f"NPC SAYS  : {dialogue_output.spoken_output}")
        print(f"SUBTITLE  : {dialogue_output.subtitle_output}")
        print("-" * 54)

        return {
            "context": context_output.model_dump(),
            "dialogue": dialogue_output.model_dump(),
        }


# Singleton orchestrator instance
orchestrator = HierarchicalOrchestrator()
