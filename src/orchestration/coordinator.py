import logging
from typing import Dict, Any, Optional
from datetime import datetime
from schema.models import MessagePoolState, AgentMessage
from agents import get_context_agent, get_guidance_agent, get_dialogue_agent
from vr_tools import get_environment_data, get_user_status, show_subtitle

class InMemoryMessagePool:
    """
    A unified data structure to store agent communications.
    Implementation of the 'Mutual Interaction' module.
    """
    def __init__(self):
        self.state = MessagePoolState()
        self.logger = logging.getLogger("MessagePool")

    def publish_context(self, summary: str):
        self.state.latest_context = summary
        self.state.history.append(AgentMessage(role="context", content=summary))
        self.logger.info(f"Context Published: {summary}")

    def publish_plan(self, plan: str):
        self.state.latest_plan = plan
        self.state.history.append(AgentMessage(role="guidance", content=plan))
        self.logger.info(f"Plan Published: {plan}")

    def publish_dialogue(self, spoken: str, subtitle: str):
        self.state.latest_dialogue = {"spoken": spoken, "subtitle": subtitle}
        self.state.history.append(AgentMessage(role="dialogue", content=spoken))
        self.logger.info(f"Dialogue Published: {subtitle}")

    def get_full_state_for_synthesis(self) -> str:
        """Returns a combined string for the Dialogue Agent (Parent Node)."""
        return (
            f"LATEST_CONTEXT: {self.state.latest_context}\n"
            f"LATEST_GUIDANCE_PLAN: {self.state.latest_plan}"
        )

class HierarchicalOrchestrator:
    """
    Parent Node Logic: Orchestrates the sequential flow of child agents.
    1. Fetch Perception
    2. Run Context Agent
    3. Run Guidance Agent
    4. Run Dialogue Agent (Subscriber)
    """
    def __init__(self):
        self.pool = InMemoryMessagePool()
        self.context_agent = get_context_agent()
        self.guidance_agent = get_guidance_agent()
        self.dialogue_agent = get_dialogue_agent()
        
        # Inject MockModel for local simulation if real keys are missing
        from core.mock_model import MockModel
        self.context_agent.model = MockModel("mock-context")
        self.guidance_agent.model = MockModel("mock-guidance")
        self.dialogue_agent.model = MockModel("mock-dialogue")

    def run_cycle(self):
        print("\n--- NEW VR TICK ---")
        
        # 1. Perception Logic
        env_data = get_environment_data()
        user_status = get_user_status()
        perception_input = f"ENV: {env_data} | USER: {user_status}"
        
        # 2. Context Agent (Child Node - Perception Module)
        print("Trigerring Context Agent...")
        context_output_res = self.context_agent(f"Environment data: {perception_input}")
        context_output = str(context_output_res).strip()
        self.pool.publish_context(context_output)
        
        # 3. Guidance Agent (Child Node - Self-Action Module)
        print("Trigerring Guidance Agent...")
        guidance_output_res = self.guidance_agent(f"Current State Summary: {context_output}")
        guidance_output = str(guidance_output_res).strip()
        self.pool.publish_plan(guidance_output)
        
        # 4. Dialogue Agent (Parent Node - Mutual Interaction)
        print("Trigerring Dialogue Agent (Parent Synthesis)...")
        synthesis_input = self.pool.get_full_state_for_synthesis()
        dialogue_output_res = self.dialogue_agent(synthesis_input)
        dialogue_output = str(dialogue_output_res).strip()
        
        # Parse standard output format from prompt: 
        # SPOKEN_OUTPUT: "..." SUBTITLE_OUTPUT: "..."
        spoken = "Dialog speech..."
        subtitle = "Dialog subtitle..."
        if "SPOKEN_OUTPUT:" in dialogue_output:
            parts = dialogue_output.split("SUBTITLE_OUTPUT:")
            spoken = parts[0].replace("SPOKEN_OUTPUT:", "").strip().strip('"')
            subtitle = parts[1].strip().strip('"') if len(parts) > 1 else spoken[:15]
            
        self.pool.publish_dialogue(spoken, subtitle)
        
        # 5. Output to VR
        show_subtitle(subtitle)
        print(f"\nNPC SAYS: {spoken}")
        return spoken

orchestrator = HierarchicalOrchestrator()
