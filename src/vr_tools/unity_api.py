import logging
from typing import Any, Dict
import json

from core.config import settings


class UnityAPIClient:
    """
    HTTP bridge to the Unity VR runtime.
    Currently uses mock data structured to match the expected real API contract.
    Replace mock responses with real `requests` calls when connecting to Unity.
    """
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.logger = logging.getLogger("UnityAPIClient")
        self.cultural_sites_path = settings.BASE_DIR / "data" / "cultural_sites.json"

    def _load_cultural_sites(self) -> Dict[str, Any]:
        with self.cultural_sites_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def update_cultural_sites(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.cultural_sites_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")
        return payload

    def get(self, endpoint: str) -> Dict[str, Any]:
        """Simulates a GET request to Unity."""
        self.logger.info(f"GET {self.base_url}/{endpoint}")

        if endpoint == "environment/delta":
            return {
                "timestamp": "2026-05-01T12:30:00Z",
                "scene": "Heritage_Museum_Wing_A",
                "events": ["Main_Gate:OPEN", "Chandelier:ON", "Spotlight_Altar:ON"],
                "user_position": {"x": 12.0, "y": 0.0, "z": 35.0},
            }

        elif endpoint == "user/status":
            return {
                "player_position": "12.0, 0.0, 35.0",
            }

        elif endpoint == "world/cultural_sites":
            return self._load_cultural_sites()

        return {}

    def post(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """Simulates a POST request to Unity."""
        self.logger.info(f"POST {self.base_url}/{endpoint} | Data: {json.dumps(data)}")
        # Real implementation: requests.post(f"{self.base_url}/{endpoint}", json=data)
        return True


# Singleton client instance
unity_client = UnityAPIClient()
