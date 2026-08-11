import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from orchestration.coordinator import (  # noqa: E402
    _default_context_interpretation,
    _merge_context_interpretation,
)
from schema.models import EnvironmentSnapshot, SiteRecommendation  # noqa: E402


class ContextInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.environment = EnvironmentSnapshot(
            timestamp="2026-06-13T14:00:00",
            scene="Heritage_Museum_Wing_A",
            user_position={"x": 0.0, "y": 0.0, "z": 0.0},
        )
        self.recommendations = [
            SiteRecommendation(
                rank=1,
                id="Surabi",
                name="Surabi",
                cultural_position="1, 0, 0",
            ),
            SiteRecommendation(
                rank=2,
                id="Angklung",
                name="Angklung",
                cultural_position="2, 0, 0",
            ),
            SiteRecommendation(
                rank=3,
                id="Kujang",
                name="Kujang",
                cultural_position="3, 0, 0",
            ),
        ]

    def test_multiple_recommendations_do_not_claim_total_unvisited_count(self):
        result = _default_context_interpretation(
            self.environment,
            self.recommendations,
        )

        self.assertIn("3 rekomendasi teratas", result["context_summary"])
        self.assertNotIn("3 objek budaya belum dikunjungi", result["context_summary"])
        self.assertIn("terdekat", result["recommendation_reason"])

    def test_merge_rejects_speculative_action_and_tautological_reason(self):
        parsed = {
            "user_action": "Pemain sedang mengamati dan mempertimbangkan pilihannya.",
            "recommendation_reason": (
                "Surabi diprioritaskan sesuai urutan rekomendasi yang tersedia."
            ),
            "situation_type": "multiple_recommendations",
            "dialogue_intent": "guide_to_primary_with_alternatives",
            "recommendations": [
                {"rank": item.rank, "id": item.id, "name": item.name}
                for item in self.recommendations
            ],
        }

        result = _merge_context_interpretation(
            parsed,
            self.environment,
            self.recommendations,
        )

        self.assertNotIn("mengamati", result["user_action"])
        self.assertIn("Heritage_Museum_Wing_A", result["user_action"])
        self.assertIn("terdekat", result["recommendation_reason"])
        self.assertNotIn("sesuai urutan", result["recommendation_reason"])


if __name__ == "__main__":
    unittest.main()
