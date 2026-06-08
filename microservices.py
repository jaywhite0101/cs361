import json
import zmq

PORTS = {
    "sorting":    5556,
    "export":     5557,
    "conversion": 5558,
    "notes":      5559,
}

TIMEOUT_MS = 3000

def _call(port: int, request: dict) -> dict:
    context = zmq.Context()
    socket  = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, TIMEOUT_MS)
    socket.setsockopt(zmq.LINGER, 0)
    try:
        socket.connect(f"tcp://localhost:{port}")
        socket.send_json(request)
        return json.loads(socket.recv_string())
    except zmq.error.Again:
        return {"status": "error", "message": "Microservice timed out — make sure it is running."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        socket.close()
        context.term()


# Sorting

def sort_recipes(recipe_dicts: list, sort_key: str, order: str = "ASC") -> dict:
    return _call(PORTS["sorting"], {
        "action":    "sort",
        "data":      recipe_dicts,
        "sort_keys": [sort_key],
        "orders":    [order],
    })


# Text Export

def export_recipe(title: str, ingredients: list, instructions: list, fmt: str) -> dict:
    return _call(PORTS["export"], {
        "format": fmt,
        "data": {
            "title":    title,
            "sections": [
                {"heading": "Ingredients",  "items": ingredients},
                {"heading": "Instructions", "items": instructions},
            ],
        },
    })


# Unit Conversion

def scale_value(value: float, scale_factor: float) -> dict:
    return _call(PORTS["conversion"], {
        "action":       "scale",
        "value":        value,
        "unit":         "",
        "scale_factor": scale_factor,
    })


# Note Taking

def save_note(user_id: str, entity_id: str, note: str) -> dict:
    return _call(PORTS["notes"], {
        "action":    "save",
        "user_id":   user_id,
        "entity_id": entity_id,
        "note":      note,
    })


def load_note(user_id: str, entity_id: str) -> dict:
    return _call(PORTS["notes"], {
        "action":    "load",
        "user_id":   user_id,
        "entity_id": entity_id,
    })


def delete_note(user_id: str, entity_id: str) -> dict:
    return _call(PORTS["notes"], {
        "action":    "delete",
        "user_id":   user_id,
        "entity_id": entity_id,
    })