import zmq
import json
import random

def sort_data(data: list, sort_keys: list, orders: list) -> list:
    if not sort_keys:
        raise ValueError("sort_keys must contain at least one key.")
    if len(sort_keys) != len(orders):
        raise ValueError("sort_keys and orders must be the same length.")

    for o in orders:
        if o.upper() not in ("ASC", "DESC"):
            raise ValueError(f"Invalid order '{o}'. Must be 'ASC' or 'DESC'.")

    # multi-pass stable sort, rightmost key first so primary key takes priority
    result = list(data)
    for key, order in reversed(list(zip(sort_keys, orders))):
        reverse = order.upper() == "DESC"
        result = sorted(
            result,
            key=lambda item, k=key: (
                (1, "")          if item.get(k) is None else
                (0, item.get(k))
            ),
            reverse=reverse,
        )
    return result

def handle_request(raw: bytes) -> dict:
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    action = request.get("action", "sort").lower()
    data   = request.get("data", [])

    if not isinstance(data, list):
        return {"status": "error", "message": "'data' must be a list."}

    if action == "random":
        shuffled = list(data)
        random.shuffle(shuffled)
        return {"status": "success", "sorted_data": shuffled}

    if action == "sort":
        sort_keys = request.get("sort_keys", [])
        orders    = request.get("orders", [])

        if sort_keys and not orders:
            orders = ["ASC"] * len(sort_keys)

        try:
            sorted_data = sort_data(data, sort_keys, orders)
        except (ValueError, TypeError) as e:
            return {"status": "error", "message": str(e)}

        return {"status": "success", "sorted_data": sorted_data}

    return {"status": "error", "message": f"Unknown action '{action}'. Use 'sort' or 'random'."}

def main():
    context = zmq.Context()
    socket  = context.socket(zmq.REP) # image microservice uses 5555, save/load uses 5554
    socket.bind("tcp://*:5556")

    print("Sorting Microservice is running on tcp://*:5556 ...")
    print("Waiting for requests. Press Ctrl+C to stop.\n")

    try:
        while True:
            raw      = socket.recv()
            print(f"[REQUEST]  {raw.decode()}")
            response = handle_request(raw)
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

