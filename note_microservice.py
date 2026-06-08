import json
import os
import zmq

NOTES_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.json")
MAX_NOTE_LEN = 10_000

# persistence/saved notes

def load_store() -> dict:
    if not os.path.exists(NOTES_FILE):
        return {}
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_store(store: dict):
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

# action handlers
def handle_save(request: dict, store: dict) -> dict:
    user_id   = request.get("user_id", "")
    entity_id = request.get("entity_id", "")
    note      = request.get("note", "")

    if not user_id:
        return {"status": "error", "message": "'user_id' is required."}
    if not entity_id:
        return {"status": "error", "message": "'entity_id' is required."}
    if not isinstance(note, str):
        return {"status": "error", "message": "'note' must be a string."}
    if len(note) > MAX_NOTE_LEN:
        return {"status": "error", "message": f"Note exceeds {MAX_NOTE_LEN:,} character limit ({len(note):,} chars)."}

    if user_id not in store:
        store[user_id] = {}

    store[user_id][entity_id] = note
    save_store(store)

    return {"status": "success", "message": f"Note saved for entity '{entity_id}'."}

def handle_load(request: dict, store: dict) -> dict:
    user_id   = request.get("user_id", "")
    entity_id = request.get("entity_id", "")

    if not user_id:
        return {"status": "error", "message": "'user_id' is required."}
    if not entity_id:
        return {"status": "error", "message": "'entity_id' is required."}

    note = store.get(user_id, {}).get(entity_id, "")
    return {"status": "success", "note": note}

def handle_delete(request: dict, store: dict) -> dict:
    user_id   = request.get("user_id", "")
    entity_id = request.get("entity_id", "")

    if not user_id:
        return {"status": "error", "message": "'user_id' is required."}
    if not entity_id:
        return {"status": "error", "message": "'entity_id' is required."}

    deleted = False
    if user_id in store and entity_id in store[user_id]:
        del store[user_id][entity_id]
        if not store[user_id]:
            del store[user_id]
        save_store(store)
        deleted = True

    if deleted:
        return {"status": "success", "message": f"Note for entity '{entity_id}' deleted."}
    return {"status": "success", "message": f"No note found for entity '{entity_id}' — nothing to delete."}

def handle_list(request: dict, store: dict) -> dict:
    user_id = request.get("user_id", "")

    if not user_id:
        return {"status": "error", "message": "'user_id' is required."}

    notes = store.get(user_id, {})
    return {"status": "success", "notes": notes}

# request routing

HANDLERS = {
    "save":   handle_save,
    "load":   handle_load,
    "delete": handle_delete,
    "list":   handle_list,
}

def handle_request(raw: bytes, store: dict) -> dict:
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    if not isinstance(request, dict):
        return {"status": "error", "message": "Request must be a JSON object."}

    action = str(request.get("action", "")).lower()
    if action not in HANDLERS:
        supported = ", ".join(f'"{k}"' for k in HANDLERS)
        return {"status": "error", "message": f"Unknown action '{action}'. Use one of: {supported}."}

    return HANDLERS[action](request, store)

def main():
    store = load_store()
    print(f"Loaded notes.json — {sum(len(v) for v in store.values())} notes across {len(store)} users.")

    context = zmq.Context()
    socket  = context.socket(zmq.REP) # Image: 5555 | Sorting: 5556 | Text Export: 5557 | Save/Load: 5554 | Conversion: 5558
    socket.bind("tcp://*:5559")

    print("Note Taking Microservice is running on tcp://*:5559 ...")
    print("Waiting for requests. Press Ctrl+C to stop.\n")

    try:
        while True:
            raw      = socket.recv()
            print(f"[REQUEST]  {raw.decode()}")
            response = handle_request(raw, store)
            payload  = json.dumps(response, ensure_ascii=False)
            socket.send_string(payload)
            print(f"[RESPONSE] {payload}\n")

    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        socket.close()
        context.destroy()

if __name__ == "__main__":
    main()