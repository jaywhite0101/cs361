import json
import os
import zmq

UNITS_FILE = os.path.join(os.path.dirname(__file__), "units.json")


# loads units from the units.json file

def load_units(path: str) -> dict:
    with open(path, "r") as f:
        data = json.load(f)
    # strip the readme key so only real categories remain
    return {k: v for k, v in data.items() if not k.startswith("_")}


def find_category(unit: str, unit_data: dict):
    """Return (category_name, category_dict) for a unit, or None if not found."""
    unit = unit.lower()
    for category, info in unit_data.items():
        if unit in info["units"]:
            return category, info
    return None

def convert_standard(value: float, from_unit: str, to_unit: str, category: dict) -> float:
    """Convert using ratio-to-base for all non-temperature categories."""
    units      = category["units"]
    in_base    = value * units[from_unit]
    return in_base / units[to_unit]

def convert_temperature(value: float, from_unit: str, to_unit: str, category: dict) -> float:
    """Convert temperature using per-unit offset/scale formulas."""
    units    = category["units"]
    src      = units[from_unit]
    dst      = units[to_unit]

    in_base  = (value + src["to_base_offset"]) * src["to_base_scale"]
    result   = in_base * dst["from_base_scale"] + dst.get("from_base_add", 0)
    return result

# request handler

def handle_request(raw: bytes, unit_data: dict) -> dict:
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    if not isinstance(request, dict):
        return {"status": "error", "message": "Request must be a JSON object."}

    action = str(request.get("action", "")).lower()

    if action == "scale":
        return handle_scale(request)

    if action == "convert":
        return handle_convert(request, unit_data)

    return {"status": "error", "message": f"Unknown action '{action}'. Use 'scale' or 'convert'."}


def handle_scale(request: dict) -> dict:
    value        = request.get("value")
    unit         = request.get("unit", "")
    scale_factor = request.get("scale_factor")

    if not isinstance(value, (int, float)):
        return {"status": "error", "message": "'value' must be a number."}
    if not isinstance(scale_factor, (int, float)):
        return {"status": "error", "message": "'scale_factor' must be a number."}

    result = round(value * scale_factor, 6)
    return {"status": "success", "result": result, "unit": unit}


def handle_convert(request: dict, unit_data: dict) -> dict:
    value     = request.get("value")
    from_unit = str(request.get("from_unit", "")).lower()
    to_unit   = str(request.get("to_unit", "")).lower()

    if not isinstance(value, (int, float)):
        return {"status": "error", "message": "'value' must be a number."}
    if not from_unit:
        return {"status": "error", "message": "'from_unit' is required."}
    if not to_unit:
        return {"status": "error", "message": "'to_unit' is required."}

    from_lookup = find_category(from_unit, unit_data)
    to_lookup   = find_category(to_unit, unit_data)

    if from_lookup is None:
        return {"status": "error", "message": f"Unknown unit '{from_unit}'. Check units.json to add it."}
    if to_lookup is None:
        return {"status": "error", "message": f"Unknown unit '{to_unit}'. Check units.json to add it."}

    from_category, from_info = from_lookup
    to_category,   _         = to_lookup

    if from_category != to_category:
        return {
            "status":  "error",
            "message": f"Cannot convert '{from_unit}' ({from_category}) to '{to_unit}' ({to_category}): incompatible unit types."
        }

    if from_unit == to_unit:
        return {"status": "success", "result": value, "unit": to_unit}

    if from_category == "temperature":
        result = convert_temperature(value, from_unit, to_unit, from_info)
    else:
        result = convert_standard(value, from_unit, to_unit, from_info)

    return {"status": "success", "result": round(result, 6), "unit": to_unit}

def main():
    unit_data = load_units(UNITS_FILE)
    print(f"Loaded {sum(len(c['units']) for c in unit_data.values())} units across {len(unit_data)} categories from {UNITS_FILE}")

    context = zmq.Context()
    socket  = context.socket(zmq.REP) # Image: 5555 | Sorting: 5556 | Text Export: 5557 | Save/Load: 5554
    socket.bind("tcp://*:5558")

    print("Unit Conversion Microservice is running on tcp://*:5558 ...")
    print("Waiting for requests. Press Ctrl+C to stop.\n")

    try:
        while True:
            raw      = socket.recv()
            print(f"[REQUEST]  {raw.decode()}")
            response = handle_request(raw, unit_data)
            payload  = json.dumps(response)
            socket.send_string(payload)
            print(f"[RESPONSE] {payload}\n")

    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        socket.close()
        context.destroy()


if __name__ == "__main__":
    main()