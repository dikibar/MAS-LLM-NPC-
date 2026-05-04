from .unity_api import unity_client


def get_environment_data() -> dict:
    """
    Perception Module: Fetches raw Unity environment state.
    Returns structured data describing the current scene, event deltas,
    and a map of nearby cultural sites with their visit status.
    """
    return unity_client.get("environment/delta")


def get_user_status() -> dict:
    """
    Perception Module: Fetches the player's current position only.
    Returns the player position in world-space coordinates.
    """
    return unity_client.get("user/status")


def get_cultural_sites() -> dict:
    """
    Perception Module: Fetches the full registry of cultural sites in the current scene.
    Returns each site's ID, name, world-space cultural_position, and whether it has been visited.
    The Context Agent uses this to recommend 2-3 nearby unvisited destinations.
    """
    return unity_client.get("world/cultural_sites")
