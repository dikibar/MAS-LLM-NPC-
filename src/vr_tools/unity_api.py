import logging
from typing import Any, Dict
import json


class UnityAPIClient:
    """
    HTTP bridge to the Unity VR runtime.
    Currently uses mock data structured to match the expected real API contract.
    Replace mock responses with real `requests` calls when connecting to Unity.
    """
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.logger = logging.getLogger("UnityAPIClient")

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
                "proximity": "Near exhibit panel",
                "looking_at": "Artifact_ID_7",
                "is_interacting": False,
            }

        elif endpoint == "world/cultural_sites":
            # Full site registry with distance (metres) and visit status
            return {
                "sites": [
                    {
                        "id": "Cultural_Site_Altar",
                        "name": "Sacred Altar of Prambanan",
                        "distance_m": 18.5,
                        "visited": False,
                    },
                    {
                        "id": "Cultural_Site_Library",
                        "name": "Ancient Manuscript Library",
                        "distance_m": 34.0,
                        "visited": False,
                    },
                    {
                        "id": "Cultural_Site_Pavilion",
                        "name": "Royal Ceremonial Pavilion",
                        "distance_m": 52.0,
                        "visited": False,
                    },
                    {
                        "id": "Cultural_Site_Fountain",
                        "name": "Heritage Fountain Court",
                        "distance_m": 61.0,
                        "visited": True,   # already visited — should be filtered out
                    },
                ]
            }

        return {}

    def post(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """Simulates a POST request to Unity."""
        self.logger.info(f"POST {self.base_url}/{endpoint} | Data: {json.dumps(data)}")
        # Real implementation: requests.post(f"{self.base_url}/{endpoint}", json=data)
        return True


# Singleton client instance
unity_client = UnityAPIClient()
