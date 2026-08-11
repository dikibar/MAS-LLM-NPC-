import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.mock_model import MockModel
from main import app, orchestrator
from orchestration.coordinator import InMemoryMessagePool


SITE_POSITIONS = {
    "Surabi": "1, 0, 0",
    "Angklung": "2, 0, 0",
    "Julang Ngapak": "3, 0, 0",
    "Kujang": "4, 0, 0",
    "Badak Heuay": "5, 0, 0",
    "Tagog Anjing": "6, 0, 0",
    "Tari Jaipong": "7, 0, 0",
    "Suling Sunda": "8, 0, 0",
}


def cultural_sites(
    *,
    visited: set[str] | None = None,
    positions: dict[str, str] | None = None,
) -> list[dict]:
    visited = visited or set()
    positions = positions or SITE_POSITIONS
    return [
        {
            "id": name,
            "name": name,
            "cultural_position": positions[name],
            "visited": name in visited,
        }
        for name in SITE_POSITIONS
    ]


def context_payload(
    *,
    visited: set[str] | None = None,
    positions: dict[str, str] | None = None,
) -> dict:
    return {
        "timestamp": "2026-06-13T12:00:00Z",
        "scene": "Sunda",
        "playerPosition": "0, 0, 0",
        "culturalSites": cultural_sites(
            visited=visited,
            positions=positions,
        ),
    }


class MultiAgentAPIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_context_model = orchestrator.context_agent.model
        cls.original_dialogue_model = orchestrator.dialogue_agent.model
        cls.original_pool = orchestrator.pool

        orchestrator.context_agent.model = MockModel("mock-context")
        orchestrator.dialogue_agent.model = MockModel("mock-dialogue")
        app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        orchestrator.context_agent.model = cls.original_context_model
        orchestrator.dialogue_agent.model = cls.original_dialogue_model
        orchestrator.pool = cls.original_pool

    def setUp(self):
        orchestrator.pool = InMemoryMessagePool()
        self.client = app.test_client()

    def post(self, path: str, payload: dict):
        # Agent and orchestrator print detailed traces intended for manual runs.
        # Suppress them here so the integration-test output stays readable.
        with redirect_stdout(io.StringIO()):
            return self.client.post(path, json=payload)

    def test_context_run_ranks_nearest_unvisited_sites(self):
        response = self.post(
            "/context/run",
            context_payload(visited={"Surabi", "Julang Ngapak"}),
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        data = body["data"]
        context = data["context"]

        self.assertEqual(body["status"], "success")
        self.assertTrue(data["simulation_id"])
        self.assertEqual(context["nav_target"], "Angklung")
        self.assertEqual(
            [item["name"] for item in context["recommendations"]],
            ["Angklung", "Kujang", "Badak Heuay"],
        )
        self.assertEqual(
            [item["rank"] for item in context["recommendations"]],
            [1, 2, 3],
        )
        self.assertNotIn(
            "Surabi",
            [item["name"] for item in context["recommendations"]],
        )

    def test_context_dialogue_selection_flow_updates_session_target(self):
        context_response = self.post("/context/run", context_payload())
        context_data = context_response.get_json()["data"]
        simulation_id = context_data["simulation_id"]
        expected_options = [
            item["name"]
            for item in context_data["context"]["recommendations"]
        ]

        dialogue_response = self.post(
            "/dialogue/run",
            {"simulationId": simulation_id},
        )
        self.assertEqual(dialogue_response.status_code, 200)
        dialogue = dialogue_response.get_json()["data"]["dialogue"]
        self.assertEqual(dialogue["recommendation_options"], expected_options)
        self.assertLessEqual(len(dialogue["subtitle_output"].split()), 15)
        self.assertIn(expected_options[0], dialogue["subtitle_output"])
        for option in expected_options:
            self.assertNotIn(option, dialogue["recommendation_dialogue"])

        selected_option = expected_options[1]
        selection_response = self.post(
            "/recommendation/select",
            {
                "simulationId": simulation_id,
                "selectedOption": selected_option,
            },
        )
        self.assertEqual(selection_response.status_code, 200)
        selection = selection_response.get_json()["data"]
        self.assertEqual(selection["selected_option"], selected_option)
        self.assertEqual(selection["selected_site_id"], selected_option)
        self.assertIn(selected_option, selection["subtitle_output"])

        saved_session = orchestrator.pool.get_session(simulation_id)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.context.nav_target, selected_option)
        self.assertIsNotNone(saved_session.dialogue)
        for option in expected_options:
            self.assertNotIn(option, saved_session.dialogue.recommendation_dialogue)

    def test_dialogue_uses_requested_session_not_latest_global_context(self):
        first_positions = dict(SITE_POSITIONS)
        first_positions["Surabi"] = "0.5, 0, 0"
        first_context = self.post(
            "/context/run",
            context_payload(positions=first_positions),
        ).get_json()["data"]

        second_positions = dict(SITE_POSITIONS)
        second_positions["Angklung"] = "0.25, 0, 0"
        second_positions["Surabi"] = "10, 0, 0"
        second_context = self.post(
            "/context/run",
            context_payload(positions=second_positions),
        ).get_json()["data"]

        self.assertEqual(first_context["context"]["nav_target"], "Surabi")
        self.assertEqual(second_context["context"]["nav_target"], "Angklung")

        first_dialogue = self.post(
            "/dialogue/run",
            {"simulationId": first_context["simulation_id"]},
        ).get_json()["data"]["dialogue"]

        self.assertEqual(first_dialogue["recommendation_options"][0], "Surabi")
        self.assertIn("Surabi", first_dialogue["subtitle_output"])

    def test_all_sites_visited_returns_empty_navigation_and_options(self):
        all_visited = set(SITE_POSITIONS)
        context_response = self.post(
            "/context/run",
            context_payload(visited=all_visited),
        )

        self.assertEqual(context_response.status_code, 200)
        context_data = context_response.get_json()["data"]
        context = context_data["context"]
        self.assertEqual(context["situation_type"], "all_sites_visited")
        self.assertEqual(context["nav_target"], "")
        self.assertEqual(context["recommendations"], [])
        self.assertFalse(context_data["navmesh_ack"])

        dialogue_response = self.post(
            "/dialogue/run",
            {"simulationId": context_data["simulation_id"]},
        )
        self.assertEqual(dialogue_response.status_code, 200)
        dialogue = dialogue_response.get_json()["data"]["dialogue"]
        self.assertEqual(dialogue["recommendation_options"], [])
        self.assertTrue(dialogue["subtitle_output"])

    def test_unknown_session_is_rejected(self):
        dialogue_response = self.post(
            "/dialogue/run",
            {"simulationId": "unknown-session"},
        )
        selection_response = self.post(
            "/recommendation/select",
            {
                "simulationId": "unknown-session",
                "selectedOption": "Surabi",
            },
        )

        self.assertEqual(dialogue_response.status_code, 400)
        self.assertEqual(selection_response.status_code, 400)
        self.assertIn("tidak ditemukan", dialogue_response.get_json()["message"])
        self.assertIn("tidak ditemukan", selection_response.get_json()["message"])

    def test_option_outside_active_recommendations_is_rejected(self):
        context_response = self.post("/context/run", context_payload())
        simulation_id = context_response.get_json()["data"]["simulation_id"]

        response = self.post(
            "/recommendation/select",
            {
                "simulationId": simulation_id,
                "selectedOption": "Objek Tidak Dikenal",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("tidak ada", response.get_json()["message"])

    def test_off_navmesh_tick_reuses_last_known_player_position(self):
        # Pemain berdiri dekat Suling Sunda ("8, 0, 0") saat posisi masih terbaca.
        on_mesh_payload = context_payload()
        on_mesh_payload["playerPosition"] = "9, 0, 0"
        on_mesh_response = self.post("/context/run", on_mesh_payload)

        self.assertEqual(on_mesh_response.status_code, 200)
        on_mesh_data = on_mesh_response.get_json()["data"]
        self.assertEqual(on_mesh_data["player_position"], "9, 0, 0")
        self.assertEqual(on_mesh_data["player_position_source"], "live")
        self.assertEqual(on_mesh_data["context"]["nav_target"], "Suling Sunda")

        # Unity gagal membaca posisi saat pemain naik ke pintu (di luar NavMesh).
        off_mesh_variants = {
            "null": None,
            "empty_string": "",
            "nan_vector": "NaN, NaN, NaN",
            "missing_field": "__omit__",
        }

        for variant_name, player_position in off_mesh_variants.items():
            with self.subTest(variant=variant_name):
                off_mesh_payload = context_payload()
                if player_position == "__omit__":
                    off_mesh_payload.pop("playerPosition")
                else:
                    off_mesh_payload["playerPosition"] = player_position

                response = self.post("/context/run", off_mesh_payload)

                self.assertEqual(response.status_code, 200)
                data = response.get_json()["data"]
                self.assertEqual(data["player_position"], "9, 0, 0")
                self.assertEqual(data["player_position_source"], "last_known")
                self.assertEqual(data["context"]["nav_target"], "Suling Sunda")
                self.assertTrue(data["navmesh_ack"])

    def test_off_navmesh_tick_keeps_dialogue_and_selection_flow_running(self):
        self.post("/context/run", context_payload())

        off_mesh_payload = context_payload()
        off_mesh_payload["playerPosition"] = None
        context_data = self.post("/context/run", off_mesh_payload).get_json()["data"]
        simulation_id = context_data["simulation_id"]

        dialogue_response = self.post("/dialogue/run", {"simulationId": simulation_id})
        self.assertEqual(dialogue_response.status_code, 200)
        options = dialogue_response.get_json()["data"]["dialogue"]["recommendation_options"]
        self.assertEqual(options[0], "Surabi")

        selection_response = self.post(
            "/recommendation/select",
            {"simulationId": simulation_id, "selectedOption": options[1]},
        )
        self.assertEqual(selection_response.status_code, 200)
        self.assertTrue(selection_response.get_json()["data"]["navmesh_ack"])

    def test_off_navmesh_tick_falls_back_to_other_scene_position(self):
        self.post("/context/run", context_payload())

        other_scene_payload = context_payload()
        other_scene_payload["scene"] = "Jawa"
        other_scene_payload["playerPosition"] = ""
        response = self.post("/context/run", other_scene_payload)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["player_position"], "0, 0, 0")
        self.assertEqual(data["player_position_source"], "last_known_other_scene")

    def test_off_navmesh_tick_without_stored_position_is_rejected(self):
        payload = context_payload()
        payload["playerPosition"] = None

        response = self.post("/context/run", payload)

        self.assertEqual(response.status_code, 422)
        self.assertIn("posisi pemain terakhir", response.get_json()["message"])

    def test_invalid_context_payload_returns_validation_error(self):
        payload = context_payload()
        payload["playerPosition"] = "invalid-coordinate"

        response = self.post("/context/run", payload)

        self.assertEqual(response.status_code, 422)
        body = response.get_json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["message"], "Invalid request body")
        self.assertTrue(body["details"])


if __name__ == "__main__":
    unittest.main()
