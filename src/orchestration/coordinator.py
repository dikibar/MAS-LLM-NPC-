import json
import logging
import math
import uuid
from core.config import settings
from schema.models import (
    ContextCycleResponse,
    ContextAgentInput,
    CulturalSitesPayload,
    DialogueCycleResponse,
    EnvironmentSnapshot,
    MessagePoolState, AgentMessage,
    ContextOutput, DialogueOutput,
    RecommendationSelectionResponse,
    SiteRecommendation,
    SimulationRequest,
    SimulationCycleResponse,
    SimulationSessionState,
    UserStatusSnapshot,
)
from agents import get_context_agent, get_dialogue_agent, set_context_runtime_snapshot
from vr_tools import set_nav_target, show_subtitle

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
        self.sessions: dict[str, SimulationSessionState] = {}

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

    def save_session(self, session: SimulationSessionState):
        self.sessions[session.simulation_id] = session
        self.logger.info(f"Session Saved: simulation_id={session.simulation_id}")

    def get_session(self, simulation_id: str) -> SimulationSessionState | None:
        return self.sessions.get(simulation_id)

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


def _clean_json_text(raw: str) -> str:
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def _parse_vector3(position: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in position.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Invalid coordinate format: '{position}'. Expected 'x, y, z'.")
    return tuple(float(part) for part in parts)


def _distance_between(position_a: str, position_b: str) -> float:
    ax, ay, az = _parse_vector3(position_a)
    bx, by, bz = _parse_vector3(position_b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _rank_unvisited_sites(player_position: str, payload: CulturalSitesPayload) -> list[SiteRecommendation]:
    unvisited_sites = [site for site in payload.sites if not site.visited]
    ranked_sites = sorted(
        unvisited_sites,
        key=lambda site: (_distance_between(player_position, site.cultural_position), site.name.lower()),
    )

    return [
        SiteRecommendation(
            rank=index,
            id=site.id,
            name=site.name,
            cultural_position=site.cultural_position,
        )
        for index, site in enumerate(ranked_sites[:3], start=1)
    ]


def _default_context_interpretation(
    environment_snapshot: EnvironmentSnapshot,
    ranked_recommendations: list[SiteRecommendation],
) -> dict[str, str]:
    if not ranked_recommendations:
        return {
            "user_action": "Pemain berada di area tanpa tujuan budaya baru yang belum dikunjungi.",
            "context_summary": (
                f"Pemain berada di {environment_snapshot.scene}, tetapi semua objek budaya "
                "pada snapshot saat ini sudah dikunjungi atau tidak ada kandidat baru."
            ),
            "situation_type": "all_sites_visited",
            "recommendation_reason": "Tidak ada rekomendasi baru karena tidak ditemukan objek budaya dengan status belum dikunjungi.",
            "dialogue_intent": "no_new_destination",
        }

    primary_site = ranked_recommendations[0]
    recommendation_count = len(ranked_recommendations)

    if recommendation_count == 1:
        return {
            "user_action": "Pemain berada dekat satu tujuan budaya yang belum dikunjungi.",
            "context_summary": (
                f"Pemain berada di {environment_snapshot.scene} dengan satu objek budaya "
                f"belum dikunjungi yang siap diarahkan, yaitu {primary_site.name}."
            ),
            "situation_type": "single_recommendation",
            "recommendation_reason": (
                f"{primary_site.name} diprioritaskan karena menjadi satu-satunya objek budaya "
                "yang belum dikunjungi pada snapshot saat ini."
            ),
            "dialogue_intent": "guide_to_single_primary",
        }

    alternative_names = ", ".join(site.name for site in ranked_recommendations[1:])
    return {
        "user_action": "Pemain berada di area dengan beberapa tujuan budaya yang belum dikunjungi.",
        "context_summary": (
            f"Pemain berada di {environment_snapshot.scene} dengan {recommendation_count} "
            f"objek budaya belum dikunjungi yang dapat direkomendasikan."
        ),
        "situation_type": "multiple_recommendations",
        "recommendation_reason": (
            f"{primary_site.name} diprioritaskan sebagai tujuan utama karena menjadi kandidat "
            f"terdekat yang belum dikunjungi. Alternatif yang tersedia: {alternative_names}."
        ),
        "dialogue_intent": "guide_to_primary_with_alternatives",
    }


def _context_text_value(parsed: dict, field_name: str, fallback_value: str) -> str:
    value = parsed.get(field_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback_value


def _merge_context_interpretation(
    parsed: dict,
    environment_snapshot: EnvironmentSnapshot,
    ranked_recommendations: list[SiteRecommendation],
) -> dict[str, str]:
    defaults = _default_context_interpretation(environment_snapshot, ranked_recommendations)
    recommendation_names = {site.name for site in ranked_recommendations}
    parsed_recommendation_names = {
        item.get("name")
        for item in parsed.get("recommendations", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    parsed_reason = _context_text_value(parsed, "recommendation_reason", "")
    parsed_situation_type = _context_text_value(parsed, "situation_type", "")
    parsed_dialogue_intent = _context_text_value(parsed, "dialogue_intent", "")

    if ranked_recommendations:
        primary_name = ranked_recommendations[0].name
        ungrounded_names_in_reason = [
            name
            for name in parsed_recommendation_names
            if name not in recommendation_names and name in parsed_reason
        ]
        reason_mentions_primary = primary_name in parsed_reason
        recommendation_reason = (
            parsed_reason
            if parsed_reason and reason_mentions_primary and not ungrounded_names_in_reason
            else defaults["recommendation_reason"]
        )
    else:
        recommendation_reason = (
            parsed_reason
            if parsed_reason and "tidak ada" in parsed_reason.lower()
            else defaults["recommendation_reason"]
        )

    return {
        "user_action": _context_text_value(parsed, "user_action", defaults["user_action"]),
        "context_summary": defaults["context_summary"],
        "situation_type": (
            parsed_situation_type
            if parsed_situation_type == defaults["situation_type"]
            else defaults["situation_type"]
        ),
        "recommendation_reason": recommendation_reason,
        "dialogue_intent": (
            parsed_dialogue_intent
            if parsed_dialogue_intent == defaults["dialogue_intent"]
            else defaults["dialogue_intent"]
        ),
    }


def _build_context_output(
    raw: str,
    environment_snapshot: EnvironmentSnapshot,
    ranked_recommendations: list[SiteRecommendation],
) -> ContextOutput:
    cleaned = _clean_json_text(raw)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = {}

    if isinstance(parsed, dict) and parsed.get("status") in {"NO_DELTA", "ALL_VISITED"}:
        parsed["user_action"] = parsed["status"]
    else:
        parsed = parsed if isinstance(parsed, dict) else {}

    interpretation = _merge_context_interpretation(
        parsed,
        environment_snapshot,
        ranked_recommendations,
    )

    return ContextOutput(
        timestamp=environment_snapshot.timestamp,
        scene=environment_snapshot.scene,
        user_action=interpretation["user_action"],
        context_summary=interpretation["context_summary"],
        situation_type=interpretation["situation_type"],
        recommendation_reason=interpretation["recommendation_reason"],
        dialogue_intent=interpretation["dialogue_intent"],
        recommendations=ranked_recommendations,
        nav_target=ranked_recommendations[0].id if ranked_recommendations else "",
    )


def _build_dialogue_output(recommendations: list[SiteRecommendation]) -> DialogueOutput:
    if not recommendations:
        return DialogueOutput(
            spoken_output=(
                "Saat ini belum ada tujuan budaya baru yang perlu dipilih. "
                "Anda bisa menikmati area di sekitar Anda terlebih dahulu, lalu lanjut saat siap."
            ),
            subtitle_output="Belum ada tujuan baru saat ini.",
            recommendation_dialogue="Saat ini belum ada rekomendasi baru di sekitar Anda.",
            recommendation_options=[],
        )

    primary_name = recommendations[0].name
    fallback_options = [site.name for site in recommendations[:3]]
    alternative_names = fallback_options[1:]

    if alternative_names:
        alternatives_text = ", ".join(alternative_names)
        spoken_output = (
            f"Saya sudah menyiapkan beberapa rekomendasi objek budaya di sekitar Anda. "
            f"Mari kita mulai dari {primary_name} sebagai tujuan utama, "
            f"dan Anda juga bisa memilih {alternatives_text} setelahnya."
        )
    else:
        spoken_output = (
            f"Saya sudah menyiapkan tujuan budaya berikutnya untuk Anda. "
            f"Mari kita mulai dari {primary_name}."
        )

    return DialogueOutput(
        spoken_output=spoken_output,
        subtitle_output=f"Mari menuju {primary_name}.",
        recommendation_dialogue=(
            "Di sekitar posisi Anda ada beberapa objek budaya menarik. "
            "Pilih salah satu, dan saya akan memandu navigasinya."
        ),
        recommendation_options=fallback_options,
    )


def _build_selection_dialogue_output(
    selected_site: SiteRecommendation,
    recommendations: list[SiteRecommendation],
) -> DialogueOutput:
    fallback_options = [site.name for site in recommendations[:3]]
    return DialogueOutput(
        spoken_output=(
            f"Baik, saya akan memandu Anda menuju {selected_site.name}. "
            f"Objek budaya ini menjadi tujuan berikutnya, dan saya akan menemani perjalanan Anda sampai tiba."
        ),
        subtitle_output=f"Mari menuju {selected_site.name}.",
        recommendation_dialogue=(
            "Pilihan Anda sudah saya catat. Saya akan memandu perjalanan ke tujuan berikutnya."
        ),
        recommendation_options=fallback_options,
    )


# ---------------------------------------------------------------------------
# Hierarchical Orchestrator
# ---------------------------------------------------------------------------
class HierarchicalOrchestrator:
    """
    2-Agent Parallel Workflow:

    Tick Cycle:
      1. Receive SimulationRequest (timestamp + scene + playerPosition + culturalSites) from API.
      2. Backend reads live cultural site data from the simulation request body.
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
        if not nav_target:
            print("[NavMesh] Tidak ada target navigasi aktif.")
            return False
        print(f"[NavMesh] Dispatching target '{nav_target}' in parallel...")
        return set_nav_target(nav_target)

    def _dispatch_subtitle(self, subtitle_text: str) -> bool:
        if not subtitle_text:
            return False
        print(f"[HUD] Displaying subtitle '{subtitle_text}'...")
        return bool(show_subtitle(subtitle_text))

    def _build_runtime_context(
        self,
        sim_request: SimulationRequest,
    ) -> tuple[EnvironmentSnapshot, CulturalSitesPayload, list[SiteRecommendation], dict]:
        player_x, player_y, player_z = _parse_vector3(sim_request.playerPosition)
        environment_snapshot = EnvironmentSnapshot.model_validate(
            {
                "timestamp": sim_request.timestamp,
                "scene": sim_request.scene,
                "user_position": {
                    "x": player_x,
                    "y": player_y,
                    "z": player_z,
                },
            }
        )
        user_status_snapshot = UserStatusSnapshot.model_validate(
            {"player_position": sim_request.playerPosition}
        )
        cultural_sites_payload = CulturalSitesPayload(sites=sim_request.culturalSites)
        ranked_recommendations = _rank_unvisited_sites(sim_request.playerPosition, cultural_sites_payload)
        context_agent_input = ContextAgentInput(
            player_position=sim_request.playerPosition,
            environment=environment_snapshot,
            user_status=user_status_snapshot,
            cultural_sites=cultural_sites_payload,
            precomputed_recommendations=ranked_recommendations,
        )
        return (
            environment_snapshot,
            cultural_sites_payload,
            ranked_recommendations,
            context_agent_input.model_dump(),
        )

    def _run_context_agent(
        self,
        runtime_snapshot: dict,
        environment_snapshot: EnvironmentSnapshot,
        ranked_recommendations: list[SiteRecommendation],
    ) -> ContextOutput:
        print("\n[Phase 1] Context Agent — perceiving world & selecting sites...")
        set_context_runtime_snapshot(runtime_snapshot)
        context_instruction = (
            "Gunakan bounded runtime tools untuk membaca snapshot request aktif, "
            "lalu hasilkan satu objek JSON ContextOutput yang lengkap."
        )
        context_raw = str(self.context_agent(context_instruction)).strip()
        try:
            context_output = _parse_context(context_raw)
            interpretation = _merge_context_interpretation(
                context_output.model_dump(),
                environment_snapshot,
                ranked_recommendations,
            )
            return context_output.model_copy(
                update={
                    "timestamp": environment_snapshot.timestamp,
                    "scene": environment_snapshot.scene,
                    "user_action": interpretation["user_action"],
                    "context_summary": interpretation["context_summary"],
                    "situation_type": interpretation["situation_type"],
                    "recommendation_reason": interpretation["recommendation_reason"],
                    "dialogue_intent": interpretation["dialogue_intent"],
                    "recommendations": ranked_recommendations,
                    "nav_target": ranked_recommendations[0].id if ranked_recommendations else "",
                }
            )
        except Exception:
            return _build_context_output(
                context_raw,
                environment_snapshot,
                ranked_recommendations,
            )

    def run_context_cycle(self, sim_request: SimulationRequest) -> ContextCycleResponse:
        print("\n" + "=" * 54)
        print("  NEW VR TICK — CONTEXT WORKFLOW")
        print("=" * 54)

        environment_snapshot, cultural_sites_payload, ranked_recommendations, runtime_snapshot = (
            self._build_runtime_context(sim_request)
        )
        context_output = self._run_context_agent(
            runtime_snapshot,
            environment_snapshot,
            ranked_recommendations,
        )
        self.pool.publish_context(context_output)

        print("\n[Context Output — Validated JSON]")
        print(context_output.model_dump_json(indent=2))

        nav_ack = self._dispatch_nav_target(context_output.nav_target)
        simulation_id = str(uuid.uuid4())
        self.pool.save_session(
            SimulationSessionState(
                simulation_id=simulation_id,
                player_position=sim_request.playerPosition,
                cultural_sites=cultural_sites_payload,
                context=context_output,
            )
        )

        print("\n" + "-" * 54)
        print(f"NAV_ACK   : {nav_ack}")
        print(f"NAV_TARGET: {context_output.nav_target}")
        print("-" * 54)

        return ContextCycleResponse(
            simulation_id=simulation_id,
            context=context_output,
            navmesh_ack=nav_ack,
        )

    def run_dialogue_cycle(self, simulation_id: str) -> DialogueCycleResponse:
        session = self.pool.get_session(simulation_id)
        if session is None:
            raise ValueError("simulationId tidak ditemukan. Jalankan /context/run terlebih dahulu.")

        print("\n" + "=" * 54)
        print("  DIALOGUE WORKFLOW")
        print("=" * 54)

        context_json = session.context.model_dump_json(indent=2)
        try:
            dialogue_output = self._run_dialogue_agent(context_json)
            if session.context.recommendations:
                primary_name = session.context.recommendations[0].name.lower()
                primary_mentioned = (
                    primary_name in dialogue_output.spoken_output.lower()
                    or primary_name in dialogue_output.subtitle_output.lower()
                )
                if not primary_mentioned:
                    raise ValueError("Dialogue output did not mention the primary recommendation.")
        except Exception:
            logging.getLogger("Coordinator").warning(
                "Dialogue Agent fallback activated for simulation_id=%s",
                simulation_id,
            )
            dialogue_output = _build_dialogue_output(session.context.recommendations)
        dialogue_output = dialogue_output.model_copy(
            update={
                "recommendation_options": [site.name for site in session.context.recommendations],
            }
        )
        self._dispatch_subtitle(dialogue_output.subtitle_output)
        self.pool.publish_dialogue(dialogue_output)
        self.pool.save_session(
            SimulationSessionState(
                simulation_id=session.simulation_id,
                player_position=session.player_position,
                cultural_sites=session.cultural_sites,
                context=session.context,
                dialogue=dialogue_output,
            )
        )

        print("\n[Dialogue Output — Validated JSON]")
        print(dialogue_output.model_dump_json(indent=2))

        print("\n" + "-" * 54)
        print(f"NPC SAYS  : {dialogue_output.spoken_output}")
        print(f"SUBTITLE  : {dialogue_output.subtitle_output}")
        print(f"UI TEXT   : {dialogue_output.recommendation_dialogue}")
        print(f"UI OPTIONS: {dialogue_output.recommendation_options}")
        print("-" * 54)

        return DialogueCycleResponse(
            simulation_id=simulation_id,
            dialogue=dialogue_output,
        )

    def handle_recommendation_selection(
        self,
        simulation_id: str,
        selected_option: str,
    ) -> RecommendationSelectionResponse:
        session = self.pool.get_session(simulation_id)

        if session is None:
            raise ValueError("simulationId tidak ditemukan. Jalankan /context/run terlebih dahulu.")

        latest_context = session.context

        selected_site = next(
            (site for site in latest_context.recommendations if site.name == selected_option),
            None,
        )
        if selected_site is None:
            raise ValueError("Opsi yang dipilih tidak ada dalam rekomendasi aktif.")

        updated_context = session.context.model_copy(
            update={
                "nav_target": selected_site.id,
            }
        )

        nav_ack = self._dispatch_nav_target(selected_site.id)
        selection_payload = json.dumps(
            {
                "mode": "selection_confirmation",
                "selected_option": selected_site.name,
                "selected_site_id": selected_site.id,
                "context": updated_context.model_dump(),
            },
            ensure_ascii=False,
        )
        try:
            selection_dialogue = self._run_dialogue_agent(selection_payload)
            if selected_site.name.lower() not in selection_dialogue.spoken_output.lower():
                raise ValueError("Selection dialogue did not mention the selected site.")
        except Exception:
            logging.getLogger("Coordinator").warning(
                "Dialogue Agent selection fallback activated for simulation_id=%s",
                simulation_id,
            )
            selection_dialogue = _build_selection_dialogue_output(
                selected_site,
                session.context.recommendations,
            )

        updated_dialogue = selection_dialogue.model_copy(
            update={
                "recommendation_options": [site.name for site in session.context.recommendations],
            }
        )
        spoken_output = updated_dialogue.spoken_output
        subtitle_output = updated_dialogue.subtitle_output
        self._dispatch_subtitle(subtitle_output)
        self.pool.publish_dialogue(updated_dialogue)

        self.pool.save_session(
            SimulationSessionState(
                simulation_id=session.simulation_id,
                player_position=session.player_position,
                cultural_sites=session.cultural_sites,
                context=updated_context,
                dialogue=updated_dialogue,
            )
        )

        return RecommendationSelectionResponse(
            selected_option=selected_site.name,
            selected_site_id=selected_site.id,
            navmesh_ack=nav_ack,
            spoken_output=spoken_output,
            subtitle_output=subtitle_output,
        )

    def run_cycle(self, sim_request: SimulationRequest) -> SimulationCycleResponse:
        context_result = self.run_context_cycle(sim_request)
        dialogue_result = self.run_dialogue_cycle(context_result.simulation_id)
        return SimulationCycleResponse(
            simulation_id=context_result.simulation_id,
            context=context_result.context,
            navmesh_ack=context_result.navmesh_ack,
            dialogue=dialogue_result.dialogue,
        )


# Singleton orchestrator instance
orchestrator = HierarchicalOrchestrator()
