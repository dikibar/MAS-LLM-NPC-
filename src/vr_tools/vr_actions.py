from .unity_api import unity_client


def set_nav_target(target_id: str) -> bool:
    """
    Self-Action Module: Tells Unity NavMesh the destination identity.
    The NPC will autonomously pathfind to this target using Unity's built-in NavMesh.
    
    Args:
        target_id: The Unity GameObject name/ID of the destination
                   (e.g., "Cultural_Site_Library", "Cultural_Site_Altar").
    Returns:
        True if Unity acknowledged the command.
    """
    payload = {"command": "NAV_TO_TARGET", "target_id": target_id}
    return unity_client.post("npc/navmesh", payload)


def show_subtitle(text: str, duration: float = 5.0):
    """
    Mutual Interaction Module: Displays NPC dialogue in the VR HUD.

    Args:
        text: The condensed subtitle text (≤ 15 words).
        duration: Duration in seconds the subtitle remains on screen.
    """
    payload = {"command": "DISPLAY_SUBTITLE", "text": text, "duration": duration}
    return unity_client.post("npc/ui", payload)
