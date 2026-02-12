from flask import Flask, request, jsonify
from get_recommendations import get_recommendations, prepare_output
from calculate_diff import calculate_diff
from cors_handling import _build_cors_preflight_response, _corsify_actual_response
app = Flask(__name__)

@app.route('/recommendations', methods=['POST', 'OPTIONS'])
def recommendations():
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    try:
        data = request.get_json() or {}
        
        unavailable_clients = data.get("unavailable_clients", None)
        unavailable_mas = data.get("unavailable_mas", None)
        
        print(jsonify(unavailable_clients))
        print(jsonify(unavailable_mas))
        
        result = get_recommendations(unavailable_clients, unavailable_mas)
        prepared_result = prepare_output(result)
        
        return _corsify_actual_response(jsonify(prepared_result))
            
    except Exception as e:
        return _corsify_actual_response(jsonify({"error": str(e)}))

@app.route('/retrieve_diff', methods=['POST', 'OPTIONS'])
def calculate_diff_endpoint():
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    try:
        data = request.get_json() or {}
        
        add_client = data.get('add_client', None)
        add_ma = data.get('add_ma', None)
        if add_client is None or add_ma is None:
            return _corsify_actual_response(jsonify({"error": "add_client and add_ma are required"}))
        unavailable_clients = data.get('unavailable_clients', None)
        unavailable_mas = data.get('unavailable_mas', None)
        
        result = calculate_diff(add_client=add_client, add_ma=add_ma, unavailable_clients=unavailable_clients, unavailable_mas=unavailable_mas)
        
        return _corsify_actual_response(jsonify(result))
            
    except Exception as e:
        return _corsify_actual_response(jsonify({"error": str(e)}))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
