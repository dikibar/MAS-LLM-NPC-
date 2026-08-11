import json
import logging
import math
import time
import uuid
from typing import NamedTuple
from core.config import settings
from schema.models import (
    ContextCycleResponse,
    ContextAgentInput,
    CulturalSitesPayload,
    DialogueCycleResponse,
    EnvironmentSnapshot,
    MessagePoolState, AgentMessage,
    ContextOutput, DialogueOutput,
    PLAYER_POSITION_SOURCE_LAST_KNOWN,
    PLAYER_POSITION_SOURCE_LAST_KNOWN_OTHER_SCENE,
    PLAYER_POSITION_SOURCE_LIVE,
    RecommendationSelectionResponse,
    SiteRecommendation,
    SimulationRequest,
    SimulationCycleResponse,
    SimulationSessionState,
    UserStatusSnapshot,
    parse_position_string,
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


CONTEXT_AGENT_USER_PROMPT = """
Anda sedang menjalankan satu tick runtime VR museum budaya.

Gunakan hanya bounded runtime tools yang tersedia untuk membaca snapshot request aktif:
1. status pemain,
2. daftar cultural sites,
3. rekomendasi yang sudah dihitung dan diurutkan oleh sistem.

Tugas Anda:
- baca snapshot runtime aktif,
- pertahankan urutan rekomendasi persis seperti data rekomendasi yang tersedia,
- jangan membuat ranking baru,
- jangan mengambil data dari luar snapshot,
- hasilkan satu objek JSON ContextOutput lengkap sesuai schema sistem.

Fokus interpretasi:
- jelaskan keadaan pemain berdasarkan scene dan rekomendasi yang tersedia,
- tentukan situation_type,
- jelaskan alasan rekomendasi utama secara singkat dan grounded,
- tentukan dialogue_intent untuk Dialogue Agent,
- set nav_target sesuai id rekomendasi rank-1.

Jika tidak ada rekomendasi aktif, gunakan recommendations: [] dan nav_target: "".

Output hanya JSON valid tanpa markdown, tanpa penjelasan tambahan, dan tanpa istilah
internal seperti backend, tool, precomputed, atau cultural_position pada field interpretatif.
""".strip()


DIALOGUE_AGENT_RECOMMENDATION_USER_PROMPT = {
    "task": "Ubah ContextOutput tervalidasi menjadi DialogueOutput untuk NPC pemandu budaya.",
    "mode": "context_recommendation_synthesis",
    "instructions": [
        "Gunakan recommendation rank-1 sebagai tujuan utama aktif.",
        "Gunakan recommendation rank-2 dan rank-3 sebagai alternatif jika tersedia.",
        "Pertahankan urutan recommendation_options persis seperti urutan recommendations.",
        "Jangan tampilkan id, koordinat, angka jarak, istilah teknis, atau instruksi sistem.",
        "Jika recommendations kosong, jangan memaksa navigasi.",
        "Tulis semua teks dalam bahasa Indonesia yang hangat, ringkas, dan natural.",
        "Output hanya satu objek JSON DialogueOutput valid.",
    ],
}


DIALOGUE_AGENT_SELECTION_USER_PROMPT = {
    "task": "Ubah pilihan pemain menjadi DialogueOutput konfirmasi untuk NPC pemandu budaya.",
    "mode": "selection_confirmation_synthesis",
    "instructions": [
        "Konfirmasi selected_option sebagai tujuan yang dipilih pemain.",
        "Pastikan subtitle_output menyebut selected_option.",
        "Pertahankan recommendation_options dari context aktif.",
        "Jangan tampilkan koordinat, angka jarak, istilah teknis, atau instruksi sistem.",
        "Gunakan nada pemandu yang meyakinkan dan natural.",
        "Output hanya satu objek JSON DialogueOutput valid.",
    ],
}


def _build_dialogue_recommendation_user_prompt(context: ContextOutput) -> str:
    """Build the Dialogue Agent user prompt for the initial recommendation mode."""
    payload = context.model_dump()
    payload["runtime_instruction"] = DIALOGUE_AGENT_RECOMMENDATION_USER_PROMPT
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_dialogue_selection_user_prompt(
    selected_site: SiteRecommendation,
    updated_context: ContextOutput,
) -> str:
    """Build the Dialogue Agent user prompt for player selection confirmation mode."""
    return json.dumps(
        {
            "mode": "selection_confirmation",
            "runtime_instruction": DIALOGUE_AGENT_SELECTION_USER_PROMPT,
            "selected_option": selected_site.name,
            "selected_site_id": selected_site.id,
            "context": updated_context.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )


class LatencyTrace:
    """Small per-request profiler for identifying slow MAS phases."""

    def __init__(self, label: str):
        self.label = label
        self._started_at = time.perf_counter()
        self._last_mark = self._started_at
        self._phases: list[tuple[str, float]] = []

    def mark(self, phase_name: str) -> None:
        now = time.perf_counter()
        self._phases.append((phase_name, (now - self._last_mark) * 1000))
        self._last_mark = now

    def log(self, logger: logging.Logger | None = None) -> None:
        total_ms = (time.perf_counter() - self._started_at) * 1000
        phase_summary = " | ".join(
            f"{phase_name}={duration_ms:.1f}ms"
            for phase_name, duration_ms in self._phases
        )
        message = f"[Latency] {self.label} total={total_ms:.1f}ms"
        if phase_summary:
            message = f"{message} | {phase_summary}"

        if logger:
            logger.info(message)
        else:
            print(message)


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
        # Posisi pemain valid terakhir per scene, dipakai sebagai fallback saat
        # Unity tidak bisa membaca posisi pemain di luar NavMesh surface.
        self.last_known_player_positions: dict[str, str] = {}
        self.latest_player_position: str | None = None

    def publish_context(self, output: ContextOutput):
        self.state.latest_context = output
        self.state.history.append(
            AgentMessage(role="context", content=output.model_dump_json())
        )
        self.logger.info(f"Context Published: scene={output.scene} | nav_target={output.nav_target}")

    def publish_dialogue(self, output: DialogueOutput):
        self.state.latest_dialogue = output
        self.state.history.append(
            AgentMessage(role="dialogue", content=output.recommendation_dialogue)
        )
        self.logger.info(f"Dialogue Published: {output.subtitle_output}")

    def save_session(self, session: SimulationSessionState):
        self.sessions[session.simulation_id] = session
        self.logger.info(f"Session Saved: simulation_id={session.simulation_id}")

    def get_session(self, simulation_id: str) -> SimulationSessionState | None:
        return self.sessions.get(simulation_id)

    def remember_player_position(self, scene: str, player_position: str) -> None:
        """Store the last position Unity could actually sample inside a scene."""
        self.last_known_player_positions[scene] = player_position
        self.latest_player_position = player_position

    def recall_player_position(self, scene: str) -> tuple[str | None, str | None]:
        """
        Return the newest usable position for a scene and where it came from.

        Falls back to the newest position from any scene so one off-NavMesh tick
        can never stall the runtime loop.
        """
        scoped_position = self.last_known_player_positions.get(scene)
        if scoped_position:
            return scoped_position, PLAYER_POSITION_SOURCE_LAST_KNOWN
        if self.latest_player_position:
            return self.latest_player_position, PLAYER_POSITION_SOURCE_LAST_KNOWN_OTHER_SCENE
        return None, None

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


class ResolvedPlayerPosition(NamedTuple):
    """Position used for one runtime tick plus where it was taken from."""
    position: str
    source: str


def _parse_vector3(position: str) -> tuple[float, float, float]:
    coordinates = parse_position_string(position)
    if coordinates is None:
        raise ValueError(f"Invalid coordinate format: '{position}'. Expected finite 'x, y, z'.")
    return coordinates


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
            "user_action": (
                f"Pemain berada di {environment_snapshot.scene} tanpa rekomendasi tujuan baru."
            ),
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
            "user_action": (
                f"Pemain berada di {environment_snapshot.scene} dengan satu rekomendasi tujuan."
            ),
            "context_summary": (
                f"Tersedia satu rekomendasi tujuan yang belum dikunjungi di "
                f"{environment_snapshot.scene}, yaitu {primary_site.name}."
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
        "user_action": (
            f"Pemain berada di {environment_snapshot.scene} dengan beberapa rekomendasi tujuan."
        ),
        "context_summary": (
            f"Tersedia {recommendation_count} rekomendasi teratas dari objek budaya yang "
            f"belum dikunjungi di {environment_snapshot.scene}."
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
        reason_explains_ranking = (
            "terdekat" in parsed_reason.lower()
            if len(ranked_recommendations) > 1
            else "satu-satunya" in parsed_reason.lower()
        )
        recommendation_reason = (
            parsed_reason
            if (
                parsed_reason
                and reason_mentions_primary
                and reason_explains_ranking
                and not ungrounded_names_in_reason
            )
            else defaults["recommendation_reason"]
        )
    else:
        recommendation_reason = (
            parsed_reason
            if parsed_reason and "tidak ada" in parsed_reason.lower()
            else defaults["recommendation_reason"]
        )

    return {
        # Runtime input describes state and position, not an observed player action.
        "user_action": defaults["user_action"],
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
            recommendation_dialogue="Belum ada tujuan baru; nikmati dulu suasana area ini dengan tenang.",
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
        subtitle_output=f"Mulai dari {primary_name} dulu.",
        recommendation_dialogue=(
            "Ada beberapa pilihan menarik di sekitar sini. "
            "Pilih yang paling membuat Anda penasaran."
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
        subtitle_output=f"Baik, kita ke {selected_site.name}.",
        recommendation_dialogue=(
            "Pilihan Anda sudah saya catat. Kita lanjut dengan santai, saya pandu dari sini."
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
        self._default_context_sample_count = self.context_agent.sample_count
        self._default_dialogue_sample_count = self.dialogue_agent.sample_count

        if settings.is_fast_latency_mode:
            self.context_agent.sample_count = 1
            self.dialogue_agent.sample_count = 1

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
                "Using external LLM model '%s' via %s.",
                settings.llm_model,
                settings.llm_base_url,
            )

        logging.getLogger("Coordinator").info(
            "Latency mode active: %s (context_samples=%d, dialogue_samples=%d)",
            settings.runtime_latency_mode,
            self.context_agent.sample_count,
            self.dialogue_agent.sample_count,
        )

    def _run_dialogue_agent(self, context_json: str) -> DialogueOutput:
        print("[Dialogue Agent] Synthesising NPC speech in parallel...")
        # User prompt for Dialogue Agent:
        # - initial recommendation mode: ContextOutput JSON + runtime_instruction
        # - selection mode: selection_confirmation JSON + runtime_instruction
        # Keep the prompt JSON-only because the Dialogue Agent UQ and grounding
        # helpers parse the user prompt directly with json.loads.
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

    def _resolve_player_position(self, sim_request: SimulationRequest) -> ResolvedPlayerPosition:
        """
        Pick the player position for this tick.

        Unity cannot sample a position while the player stands off the NavMesh
        surface (standing on top of a door, for example) and sends an empty or
        NaN playerPosition for those ticks. Reuse the last position Unity could
        read instead of aborting, so the MAS cycle keeps running to the end of
        the session.
        """
        logger = logging.getLogger("Coordinator")

        if sim_request.playerPosition:
            self.pool.remember_player_position(sim_request.scene, sim_request.playerPosition)
            return ResolvedPlayerPosition(sim_request.playerPosition, PLAYER_POSITION_SOURCE_LIVE)

        recalled_position, recall_source = self.pool.recall_player_position(sim_request.scene)
        if recalled_position is None:
            raise ValueError(
                "playerPosition tidak terbaca dan belum ada posisi pemain terakhir yang tersimpan. "
                "Kirim minimal satu request dengan playerPosition valid sebelum pemain keluar dari NavMesh surface."
            )

        logger.warning(
            "playerPosition tidak terbaca pada scene '%s' (pemain kemungkinan di luar NavMesh surface); "
            "memakai posisi terakhir '%s' (source=%s).",
            sim_request.scene,
            recalled_position,
            recall_source,
        )
        return ResolvedPlayerPosition(recalled_position, recall_source)

    def _build_runtime_context(
        self,
        sim_request: SimulationRequest,
    ) -> tuple[
        EnvironmentSnapshot,
        CulturalSitesPayload,
        list[SiteRecommendation],
        dict,
        ResolvedPlayerPosition,
    ]:
        resolved_position = self._resolve_player_position(sim_request)
        player_x, player_y, player_z = _parse_vector3(resolved_position.position)
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
            {"player_position": resolved_position.position}
        )
        cultural_sites_payload = CulturalSitesPayload(sites=sim_request.culturalSites)
        ranked_recommendations = _rank_unvisited_sites(resolved_position.position, cultural_sites_payload)
        context_agent_input = ContextAgentInput(
            player_position=resolved_position.position,
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
            resolved_position,
        )

    def _run_context_agent(
        self,
        runtime_snapshot: dict,
        environment_snapshot: EnvironmentSnapshot,
        ranked_recommendations: list[SiteRecommendation],
    ) -> ContextOutput:
        print("\n[Phase 1] Context Agent — perceiving world & selecting sites...")
        set_context_runtime_snapshot(runtime_snapshot)
        # User prompt for Context Agent: trigger instruction; factual data is read via tools.
        context_raw = str(self.context_agent(CONTEXT_AGENT_USER_PROMPT)).strip()
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
        trace = LatencyTrace("context_cycle")
        print("\n" + "=" * 54)
        print("  NEW VR TICK — CONTEXT WORKFLOW")
        print("=" * 54)

        (
            environment_snapshot,
            cultural_sites_payload,
            ranked_recommendations,
            runtime_snapshot,
            resolved_position,
        ) = self._build_runtime_context(sim_request)
        trace.mark("build_runtime_context")
        context_output = self._run_context_agent(
            runtime_snapshot,
            environment_snapshot,
            ranked_recommendations,
        )
        trace.mark("context_agent")
        self.pool.publish_context(context_output)
        trace.mark("publish_context")

        print("\n[Context Output — Validated JSON]")
        print(context_output.model_dump_json(indent=2))

        nav_ack = self._dispatch_nav_target(context_output.nav_target)
        trace.mark("navmesh_dispatch")
        simulation_id = str(uuid.uuid4())
        self.pool.save_session(
            SimulationSessionState(
                simulation_id=simulation_id,
                player_position=resolved_position.position,
                cultural_sites=cultural_sites_payload,
                context=context_output,
            )
        )

        print("\n" + "-" * 54)
        print(f"NAV_ACK   : {nav_ack}")
        print(f"NAV_TARGET: {context_output.nav_target}")
        print(f"PLAYER_POS: {resolved_position.position} (source={resolved_position.source})")
        print("-" * 54)
        trace.mark("save_session")
        trace.log(logging.getLogger("Coordinator"))

        return ContextCycleResponse(
            simulation_id=simulation_id,
            context=context_output,
            navmesh_ack=nav_ack,
            player_position=resolved_position.position,
            player_position_source=resolved_position.source,
        )

    def run_dialogue_cycle(self, simulation_id: str) -> DialogueCycleResponse:
        trace = LatencyTrace("dialogue_cycle")
        session = self.pool.get_session(simulation_id)
        if session is None:
            raise ValueError("simulationId tidak ditemukan. Jalankan /context/run terlebih dahulu.")
        trace.mark("load_session")

        print("\n" + "=" * 54)
        print("  DIALOGUE WORKFLOW")
        print("=" * 54)

        context_json = _build_dialogue_recommendation_user_prompt(session.context)
        trace.mark("serialize_context")
        try:
            dialogue_output = self._run_dialogue_agent(context_json)
            trace.mark("dialogue_agent")
            if session.context.recommendations:
                primary_name = session.context.recommendations[0].name.lower()
                primary_mentioned = (
                    primary_name in dialogue_output.recommendation_dialogue.lower()
                    or primary_name in dialogue_output.subtitle_output.lower()
                )
                if not primary_mentioned:
                    raise ValueError("HUD output did not mention the primary recommendation.")
        except Exception:
            logging.getLogger("Coordinator").warning(
                "Dialogue Agent fallback activated for simulation_id=%s",
                simulation_id,
            )
            dialogue_output = _build_dialogue_output(session.context.recommendations)
            trace.mark("dialogue_fallback")
        dialogue_output = dialogue_output.model_copy(
            update={
                "recommendation_options": [site.name for site in session.context.recommendations],
            }
        )
        trace.mark("normalize_dialogue")
        self._dispatch_subtitle(dialogue_output.subtitle_output)
        trace.mark("subtitle_dispatch")
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
        print(f"HUD TEXT  : {dialogue_output.recommendation_dialogue}")
        print(f"SUBTITLE  : {dialogue_output.subtitle_output}")
        print(f"UI OPTIONS: {dialogue_output.recommendation_options}")
        print("-" * 54)
        trace.mark("publish_and_save")
        trace.log(logging.getLogger("Coordinator"))

        return DialogueCycleResponse(
            simulation_id=simulation_id,
            dialogue=dialogue_output,
        )

    def handle_recommendation_selection(
        self,
        simulation_id: str,
        selected_option: str,
    ) -> RecommendationSelectionResponse:
        trace = LatencyTrace("recommendation_selection")
        session = self.pool.get_session(simulation_id)

        if session is None:
            raise ValueError("simulationId tidak ditemukan. Jalankan /context/run terlebih dahulu.")
        trace.mark("load_session")

        latest_context = session.context

        selected_site = next(
            (site for site in latest_context.recommendations if site.name == selected_option),
            None,
        )
        if selected_site is None:
            raise ValueError("Opsi yang dipilih tidak ada dalam rekomendasi aktif.")
        trace.mark("validate_selection")

        updated_context = session.context.model_copy(
            update={
                "nav_target": selected_site.id,
            }
        )

        nav_ack = self._dispatch_nav_target(selected_site.id)
        trace.mark("navmesh_dispatch")
        # User prompt for Dialogue Agent: selection confirmation JSON payload.
        selection_payload = _build_dialogue_selection_user_prompt(selected_site, updated_context)
        try:
            selection_dialogue = self._run_dialogue_agent(selection_payload)
            trace.mark("dialogue_agent")
            if selected_site.name.lower() not in selection_dialogue.subtitle_output.lower():
                raise ValueError("Selection subtitle did not mention the selected site.")
        except Exception:
            logging.getLogger("Coordinator").warning(
                "Dialogue Agent selection fallback activated for simulation_id=%s",
                simulation_id,
            )
            selection_dialogue = _build_selection_dialogue_output(
                selected_site,
                session.context.recommendations,
            )
            trace.mark("dialogue_fallback")

        updated_dialogue = selection_dialogue.model_copy(
            update={
                "recommendation_options": [site.name for site in session.context.recommendations],
            }
        )
        trace.mark("normalize_dialogue")
        spoken_output = updated_dialogue.spoken_output
        subtitle_output = updated_dialogue.subtitle_output
        self._dispatch_subtitle(subtitle_output)
        trace.mark("subtitle_dispatch")
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
        trace.mark("publish_and_save")
        trace.log(logging.getLogger("Coordinator"))

        return RecommendationSelectionResponse(
            selected_option=selected_site.name,
            selected_site_id=selected_site.id,
            navmesh_ack=nav_ack,
            spoken_output=spoken_output,
            subtitle_output=subtitle_output,
        )

    def run_cycle(self, sim_request: SimulationRequest) -> SimulationCycleResponse:
        trace = LatencyTrace("simulation_cycle")
        context_result = self.run_context_cycle(sim_request)
        trace.mark("context_cycle")
        dialogue_result = self.run_dialogue_cycle(context_result.simulation_id)
        trace.mark("dialogue_cycle")
        trace.log(logging.getLogger("Coordinator"))
        return SimulationCycleResponse(
            simulation_id=context_result.simulation_id,
            context=context_result.context,
            navmesh_ack=context_result.navmesh_ack,
            player_position=context_result.player_position,
            player_position_source=context_result.player_position_source,
            dialogue=dialogue_result.dialogue,
        )


# Singleton orchestrator instance
orchestrator = HierarchicalOrchestrator()
