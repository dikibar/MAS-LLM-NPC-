from .unity_api import unity_client

def move_npc(x: float, y: float, z: float):
    """
    Self-Action Module: Sends coordinate-based movement to VR.
    """
    payload = {"command": "MOVE_TO", "coordinates": {"x": x, "y": y, "z": z}}
    return unity_client.post("npc/command", payload)

def show_subtitle(text: str, duration: float = 5.0):
    """
    Mutual Interaction Module: Displays NPC dialogue in VR.
    """
    payload = {"command": "DISPLAY_SUBTITLE", "text": text, "duration": duration}
    return unity_client.post("npc/ui", payload)

def trigger_animation(animation_id: str):
    """
    Self-Action Module: Triggers visual cues (like pointing).
    """
    payload = {"command": "PLAY_ANIMATION", "id": animation_id}
    return unity_client.post("npc/action", payload)
