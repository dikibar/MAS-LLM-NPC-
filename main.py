import sys
from pathlib import Path
from flask import Flask, jsonify, request
from pydantic import ValidationError

# Add src to python path
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from orchestration.coordinator import orchestrator
from schema.models import DialogueCycleRequest, RecommendationSelectionRequest, SimulationRequest
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


def _parse_json_body():
    body = request.get_json(force=True, silent=True)
    if body is None:
        return None, jsonify({
            "status": "error",
            "message": "Request body must be valid JSON with Content-Type: application/json"
        }), 400
    return body, None, None


@app.route('/context/run', methods=['POST'])
def run_context():
    """
    POST /context/run

    Request body (JSON, preferred canonical shape):
    {
        "playerPosition": "12.0, 0.0, 35.0",
        "culturalSites": [
            {
                "id": "Surabi",
                "name": "Surabi",
                "cultural_position": "-1.34956, 1.52654, 23.7432",
                "visited": false
            }
        ]
    }

    Compatibility aliases accepted:
    - culturalObject / culturalObjects / cultural_sites
    - coordinate -> cultural_position
    - isObjectVisited -> visited
    """
    try:
        body, error_response, status_code = _parse_json_body()
        if error_response is not None:
            return error_response, status_code

        sim_request = SimulationRequest.model_validate(body)
        result = orchestrator.run_context_cycle(sim_request)

        return jsonify({
            "status": "success",
            "message": "Context agent executed successfully",
            "data": result.model_dump()
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


@app.route('/dialogue/run', methods=['POST'])
def run_dialogue():
    """
    POST /dialogue/run

    Request body (JSON):
    {
        "simulationId": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e"
    }
    """
    try:
        body, error_response, status_code = _parse_json_body()
        if error_response is not None:
            return error_response, status_code

        dialogue_request = DialogueCycleRequest.model_validate(body)
        result = orchestrator.run_dialogue_cycle(dialogue_request.simulationId)

        return jsonify({
            "status": "success",
            "message": "Dialogue agent executed successfully",
            "data": result.model_dump()
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


@app.route('/run-simulation', methods=['POST'])
def trigger_simulation():
    """
    POST /run-simulation

    Endpoint kompatibilitas yang masih menjalankan context + dialogue sekaligus.
    Untuk integrasi baru, gunakan /context/run lalu /dialogue/run secara terpisah.
    """
    try:
        body, error_response, status_code = _parse_json_body()
        if error_response is not None:
            return error_response, status_code

        sim_request = SimulationRequest.model_validate(body)
        result = orchestrator.run_cycle(sim_request)

        return jsonify({
            "status": "success",
            "message": "Simulation executed successfully",
            "data": result.model_dump()
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
        "simulationId": "41ca34e4-0a1d-4a73-8a97-2e0fd4ff1e7e",
        "selectedOption": "Julang Ngapak"
    }

    selectedOption harus sama persis dengan salah satu nilai pada
    dialogue.recommendation_options dari flow aktif.
    Backend tidak mengubah field visited. Unity tetap menjadi source of truth
    dan harus mengirim status visited terbaru pada request /context/run berikutnya.
    """
    try:
        body, error_response, status_code = _parse_json_body()
        if error_response is not None:
            return error_response, status_code

        selection_request = RecommendationSelectionRequest.model_validate(body)
        result = orchestrator.handle_recommendation_selection(
            selection_request.simulationId,
            selection_request.selectedOption,
        )

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
