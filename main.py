import sys
from pathlib import Path
from flask import Flask, jsonify, request
from pydantic import ValidationError

# Add src to python path
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.append(src_path)

from orchestration.coordinator import orchestrator
from schema.models import RecommendationSelectionRequest, SimulationRequest
from vr_tools.unity_api import unity_client

app = Flask(__name__)


@app.route('/user/status', methods=['GET'])
def get_user_status():
    return jsonify(unity_client.get("user/status")), 200


@app.route('/world/cultural_sites', methods=['GET'])
def get_cultural_sites():
    return jsonify(unity_client.get("world/cultural_sites")), 200


@app.route('/world/cultural_sites', methods=['PUT'])
def update_cultural_sites():
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({
            "status": "error",
            "message": "Request body must be valid JSON with Content-Type: application/json"
        }), 400

    sites = body.get("sites")
    if not isinstance(sites, list):
        return jsonify({
            "status": "error",
            "message": "Payload must contain a 'sites' array"
        }), 422

    for index, site in enumerate(sites):
        if not isinstance(site, dict):
            return jsonify({
                "status": "error",
                "message": f"Item at sites[{index}] must be an object"
            }), 422

    updated = unity_client.update_cultural_sites({"sites": sites})
    return jsonify({
        "status": "success",
        "message": "Cultural sites updated successfully",
        "data": updated
    }), 200


@app.route('/run-simulation', methods=['POST'])
def trigger_simulation():
    """
    POST /run-simulation

    Request body (JSON):
    {
        "playerPosition": "12.0, 0.0, 35.0"
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


@app.route('/recommendation/select', methods=['POST'])
def select_recommendation():
    """
    POST /recommendation/select

    Request body (JSON):
    {
        "selectedOption": "Kujang"
    }
    """
    try:
        body = request.get_json(force=True, silent=True)
        if body is None:
            return jsonify({
                "status": "error",
                "message": "Request body must be valid JSON with Content-Type: application/json"
            }), 400

        selection_request = RecommendationSelectionRequest.model_validate(body)
        result = orchestrator.handle_recommendation_selection(selection_request.selectedOption)

        return jsonify({
            "status": "success",
            "message": "Recommendation option selected successfully",
            "data": result.model_dump(),
        }), 200

    except ValidationError as e:
        return jsonify({
            "status": "error",
            "message": "Invalid request body",
            "details": e.errors()
        }), 422

    except ValueError as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
