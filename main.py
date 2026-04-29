import sys
import os
from pathlib import Path

# Add src to python path
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.append(src_path)

from orchestration.coordinator import orchestrator

def run_simulation():
    """
    Main entry point to run the Hierarchical Multi-Agent system.
    Simulates a continuous VR environment monitoring loop.
    """
    print("====================================================")
    print("   VR MULTI-AGENT NPC SYSTEM INITIALIZING...       ")
    print("====================================================")
    
    try:
        # Run a single cycle as a demonstration
        # In a real VR app, this would be inside a while True loop
        # triggered by Unity events or a timer.
        orchestrator.run_cycle()
        
    except Exception as e:
        print(f"\n[!] ERROR in MAS execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_simulation()