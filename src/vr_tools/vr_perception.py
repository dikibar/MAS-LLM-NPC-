from .unity_api import unity_client

def get_environment_data():
    """
    Perception Module: Distills raw Unity environment messages.
    Returns structured data for the Context Agent.
    """
    return unity_client.get("environment/delta")

def get_user_status():
    """
    Perception Module: Extracts user proximity and action messages.
    """
    return unity_client.get("user/status")
