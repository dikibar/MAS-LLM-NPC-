import logging
from typing import Any, Dict, Optional
import json

# Placeholder for real requests library if needed later
# import requests

class UnityAPIClient:
    """
    Base client for communicating with Unity's API.
    In this initial version, it uses mock data but is structured for HTTP calls.
    """
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.logger = logging.getLogger("UnityAPIClient")

    def get(self, endpoint: str) -> Dict[str, Any]:
        """Simulates a GET request to Unity."""
        self.logger.info(f"GET {self.base_url}/{endpoint}")
        
        # Mock logic based on endpoints
        if endpoint == "environment/delta":
            return {
                "timestamp": "2026-04-29T11:25:00Z",
                "scene": "Great_Hall",
                "events": ["North_Gate:LOCKED", "Chandelier:ON"],
                "user_position": {"x": 10.5, "y": 0.0, "z": 40.0}
            }
        elif endpoint == "user/status":
            return {
                "proximity": "Far from North_Gate",
                "target": "North_Gate",
                "is_stuck": True
            }
        return {}

    def post(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """Simulates a POST request to Unity."""
        self.logger.info(f"POST {self.base_url}/{endpoint} Data: {json.dumps(data)}")
        # In a real scenario: requests.post(f"{self.base_url}/{endpoint}", json=data)
        return True

# Singleton client instance
unity_client = UnityAPIClient()
