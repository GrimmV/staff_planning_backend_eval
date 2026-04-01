from flask import Flask, request, jsonify, make_response, url_for
from get_recommendations import get_recommendations, prepare_output
from calculate_diff import calculate_diff
from cors_handling import _build_cors_preflight_response, _corsify_actual_response
from evaluate_diff import evaluate_diff
from chat import chat
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
    
    data = request.get_json() or {}
    
    add_client = data.get('add_client', None)
    add_ma = data.get('add_ma', None)
    if add_client is None or add_ma is None:
        return _corsify_actual_response(jsonify({"error": "add_client and add_ma are required"}))
    unavailable_clients = data.get('unavailable_clients', None)
    unavailable_mas = data.get('unavailable_mas', None)
    
    result, new_mas = calculate_diff(add_client=add_client, add_ma=add_ma, unavailable_clients=unavailable_clients, unavailable_mas=unavailable_mas)
    assessment = evaluate_diff(result, new_mas)
    
    result["assessment"] = assessment
    
    return _corsify_actual_response(jsonify(result))

@app.route("/api/v1/chat", methods=["POST", "OPTIONS"])
def chat_completion():
    if request.method == "OPTIONS":
        return _build_cors_preflight_response()
    elif request.method == "POST":
        # try:
        body = request.get_json() or {}
        prompt = body.get("prompt")

        if not prompt:
            return _corsify_actual_response(
                make_response(
                    jsonify({"error": "Missing 'prompt' in request body"}), 400
                )
            )

        response = chat(prompt)

        response = make_response(
            jsonify(
                {
                    "response": response,
                }
            )
        )
        return _corsify_actual_response(response)

        # except Exception as e:
        #     error_response = make_response(
        #         jsonify({"error": f"Internal server error: {str(e)}"}), 500
        #     )
        #     return _corsify_actual_response(error_response)

def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)


@app.route("/site-map")
def site_map():
    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        # and rules that require parameters
        links.append((rule.endpoint))
    return links

@app.route("/")
def health():
    return {"status": "ok"}

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
