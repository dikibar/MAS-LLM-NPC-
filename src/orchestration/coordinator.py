import json
import logging
import concurrent.futures
from core.config import settings
from schema.models import (
    MessagePoolState, AgentMessage,
    ContextOutput, DialogueOutput,
    RecommendationSelectionResponse,
    SimulationRequest,
)
from agents import get_context_agent, get_dialogue_agent
from vr_tools import get_cultural_sites, set_nav_target

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
    2-Agent Parallel Workflow:

    Tick Cycle:
      1. Receive SimulationRequest (playerPosition) from API.
      2. Backend reads cultural site data from the JSON-backed API.
      3. Context Agent — analyses incoming data, ranks unvisited sites,
                         outputs ContextOutput JSON → Message Pool.
      4. Fan-out in parallel from ContextOutput:
           A. Unity NavMesh receives NAV_TARGET (NPC begins moving).
           B. Dialogue Agent reads ContextOutput JSON → produces DialogueOutput JSON.
      5. Dialogue Agent sends subtitle to Unity HUD via tool_show_subtitle and
         returns a short recommendation description plus 2–3 button options for Unity UI.
    """

    def __init__(self):
        self.pool = InMemoryMessagePool()
        self.context_agent = get_context_agent()
        self.dialogue_agent = get_dialogue_agent()

        use_mock = settings.USE_MOCK_MODEL or not settings.has_openrouter_credentials
        if use_mock:
            from core.mock_model import MockModel

            self.context_agent.model = MockModel("mock-context")
            self.dialogue_agent.model = MockModel("mock-dialogue")

            if settings.USE_MOCK_MODEL:
                logging.getLogger("Coordinator").info("Using MockModel because USE_MOCK_MODEL=true.")
            else:
                logging.getLogger("Coordinator").warning(
                    "OPENROUTER_API_KEY is missing or still set to the placeholder value; falling back to MockModel."
                )
        else:
            logging.getLogger("Coordinator").info(
                "Using OpenRouter model '%s' via %s.",
                settings.OPENROUTER_MODEL,
                settings.OPENROUTER_BASE_URL,
            )

    def _run_dialogue_agent(self, context_json: str) -> DialogueOutput:
        print("[Dialogue Agent] Synthesising NPC speech in parallel...")
        raw = str(self.dialogue_agent(context_json)).strip()
        return _parse_dialogue(raw)

    def _dispatch_nav_target(self, nav_target: str) -> bool:
        print(f"[NavMesh] Dispatching target '{nav_target}' in parallel...")
        return set_nav_target(nav_target)

    def handle_recommendation_selection(self, selected_option: str) -> RecommendationSelectionResponse:
        latest_context = self.pool.state.latest_context

        if latest_context is None:
            raise ValueError("Belum ada hasil simulasi. Jalankan /run-simulation terlebih dahulu.")

        selected_site = next(
            (site for site in latest_context.recommendations if site.name == selected_option),
            None,
        )
        if selected_site is None:
            raise ValueError("Opsi yang dipilih tidak ada dalam rekomendasi aktif.")

        from vr_tools.unity_api import unity_client

        updated_sites = unity_client.mark_site_visited(selected_site.name)
        if updated_sites is None:
            raise ValueError("Objek budaya yang dipilih tidak ditemukan pada data cultural sites.")

        nav_ack = self._dispatch_nav_target(selected_site.id)
        spoken_output = (
            f"Baik, saya akan memandu Anda menuju {selected_site.name}. "
            f"Objek budaya ini telah Anda pilih sebagai tujuan berikutnya, "
            f"dan saya akan menemani navigasinya sampai kita tiba."
        )
        subtitle_output = f"Mari menuju {selected_site.name}."

        return RecommendationSelectionResponse(
            selected_option=selected_site.name,
            selected_site_id=selected_site.id,
            navmesh_ack=nav_ack,
            spoken_output=spoken_output,
            subtitle_output=subtitle_output,
        )

    def run_cycle(self, sim_request: SimulationRequest) -> dict:
        print("\n" + "=" * 54)
        print("  NEW VR TICK — PARALLEL WORKFLOW ORCHESTRATION")
        print("=" * 54)

        # ------------------------------------------------------------------
        # Build perception input from the incoming API request body
        # ------------------------------------------------------------------
        cultural_sites = get_cultural_sites()
        cultural_sites_str = json.dumps(cultural_sites, indent=2)

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
        # Phase 2: Parallel fan-out from ContextOutput
        # NavMesh moves the NPC while Dialogue Agent synthesises speech.
        # ------------------------------------------------------------------
        print("\n[Phase 2] Parallel fan-out: NavMesh moving NPC + Dialogue Agent synthesising...")
        context_json = self.pool.get_context_json_for_dialogue()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            nav_future = executor.submit(self._dispatch_nav_target, context_output.nav_target)
            dialogue_future = executor.submit(self._run_dialogue_agent, context_json)
            nav_ack = nav_future.result()
            dialogue_output = dialogue_future.result()

        self.pool.publish_dialogue(dialogue_output)

        print("\n[Dialogue Output — Validated JSON]")
        print(dialogue_output.model_dump_json(indent=2))

        print("\n" + "-" * 54)
        print(f"NAV_ACK   : {nav_ack}")
        print(f"NPC SAYS  : {dialogue_output.spoken_output}")
        print(f"SUBTITLE  : {dialogue_output.subtitle_output}")
        print(f"UI TEXT   : {dialogue_output.recommendation_dialogue}")
        print(f"UI OPTIONS: {dialogue_output.recommendation_options}")
        print("-" * 54)

        return {
            "context": context_output.model_dump(),
            "navmesh_ack": nav_ack,
            "dialogue": dialogue_output.model_dump(),
        }


# Singleton orchestrator instance
orchestrator = HierarchicalOrchestrator()
