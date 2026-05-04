import sys
from pathlib import Path
from flask import Flask, jsonify, request
from pydantic import ValidationError

# Add src to python path
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.append(src_path)

from orchestration.coordinator import orchestrator
from schema.models import SimulationRequest

app = Flask(__name__)


@app.route('/run-simulation', methods=['POST'])
def trigger_simulation():
    """
    POST /run-simulation

    Request body (JSON):
    {
        "playerPosition": "12.0, 0.0, 35.0",
        "culturalObject": [
            {
                "name": "Sacred Altar of Prambanan",
                "coordinate": "18.5, 0.0, 30.0",
                "isObjectVisited": false
            },
            ...
        ]
    }
    """
    try:
        # Parse and validate request body
        body = request.get_json(force=True, silent=True)
        if body is None:
            return jsonify({
                "status": "error",
                "message": "Request body must be valid JSON with Content-Type: application/json"
            }), 400

        sim_request = SimulationRequest.model_validate(body)

        # Run the multi-agent cycle with the incoming data
        result = orchestrator.run_cycle(sim_request)

        return jsonify({
            "status": "success",
            "message": "Simulation executed successfully",
            "data": result
        }), 200

    except ValidationError as e:
        return jsonify({
            "status": "error",
            "message": "Invalid request body",
            "details": e.errors()
        }), 422

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)