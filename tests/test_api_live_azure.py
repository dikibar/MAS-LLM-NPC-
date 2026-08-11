import io
import os
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

from core.config import settings
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


def live_context_payload() -> dict:
    return {
        "timestamp": "2026-06-13T12:00:00Z",
        "scene": "Sunda",
        "playerPosition": "0, 0, 0",
        "culturalSites": [
            {
                "id": name,
                "name": name,
                "cultural_position": position,
                "visited": name == "Surabi",
            }
            for name, position in SITE_POSITIONS.items()
        ],
    }


@unittest.skipUnless(
    os.getenv("RUN_AZURE_INTEGRATION", "").lower() == "true",
    "Set RUN_AZURE_INTEGRATION=true to call the live Azure model.",
)
class AzureLiveAPIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if settings.USE_MOCK_MODEL:
            raise unittest.SkipTest("USE_MOCK_MODEL must be false for the live Azure test.")
        if not settings.has_openrouter_credentials:
            raise unittest.SkipTest("Azure/OpenAI-compatible credentials are not configured.")
        if ".azure.com" not in settings.llm_base_url:
            raise unittest.SkipTest("OPENROUTER_BASE_URL is not an Azure endpoint.")

        cls.original_pool = orchestrator.pool
        app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        orchestrator.pool = cls.original_pool

    def setUp(self):
        orchestrator.pool = InMemoryMessagePool()
        self.client = app.test_client()

    def post(self, path: str, payload: dict):
        with redirect_stdout(io.StringIO()):
            return self.client.post(path, json=payload)

    def assert_success(self, response):
        body = response.get_json()
        self.assertEqual(response.status_code, 200, body)
        self.assertEqual(body["status"], "success", body)
        return body["data"]

    def test_live_context_dialogue_selection_flow_with_uq(self):
        context_data = self.assert_success(
            self.post("/context/run", live_context_payload())
        )
        simulation_id = context_data["simulation_id"]
        context = context_data["context"]
        expected_options = ["Angklung", "Julang Ngapak", "Kujang"]

        self.assertEqual(context["nav_target"], "Angklung")
        self.assertEqual(
            [item["name"] for item in context["recommendations"]],
            expected_options,
        )

        context_uq = orchestrator.context_agent.last_uq_report
        self.assertEqual(context_uq["sample_count"], 3)
        self.assertGreaterEqual(context_uq["selected_cdeg"], 0.0)
        self.assertLessEqual(context_uq["selected_cdeg"], 1.0)
        self.assertGreaterEqual(context_uq["udeg"], 0.0)
        self.assertLessEqual(context_uq["udeg"], 1.0)

        dialogue_data = self.assert_success(
            self.post("/dialogue/run", {"simulationId": simulation_id})
        )
        dialogue = dialogue_data["dialogue"]
        self.assertEqual(dialogue["recommendation_options"], expected_options)
        self.assertIn("Angklung", dialogue["subtitle_output"])
        self.assertLessEqual(len(dialogue["subtitle_output"].split()), 15)

        dialogue_uq = orchestrator.dialogue_agent.last_uq_report
        self.assertEqual(dialogue_uq["sample_count"], 3)
        self.assertGreaterEqual(dialogue_uq["selected_cdeg"], 0.0)
        self.assertLessEqual(dialogue_uq["selected_cdeg"], 1.0)
        self.assertGreaterEqual(dialogue_uq["selected_grounding"], 0.0)
        self.assertLessEqual(dialogue_uq["selected_grounding"], 1.0)

        selection_data = self.assert_success(
            self.post(
                "/recommendation/select",
                {
                    "simulationId": simulation_id,
                    "selectedOption": "Julang Ngapak",
                },
            )
        )
        self.assertEqual(selection_data["selected_option"], "Julang Ngapak")
        self.assertEqual(selection_data["selected_site_id"], "Julang Ngapak")
        self.assertIn("Julang Ngapak", selection_data["subtitle_output"])

        saved_session = orchestrator.pool.get_session(simulation_id)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.context.nav_target, "Julang Ngapak")


if __name__ == "__main__":
    unittest.main()
