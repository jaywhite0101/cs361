import zmq
import json

def format_markdown(data: dict) -> str:
    lines = []

    title = data.get("title", "").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")

    for section in data.get("sections", []):
        heading = section.get("heading", "").strip()
        items   = section.get("items", [])

        if heading:
            lines.append(f"## {heading}")
            lines.append("")

        for item in items:
            lines.append(f"- {str(item).strip()}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

def format_plain(data: dict) -> str:
    lines = []

    title = data.get("title", "").strip()
    if title:
        lines.append(title.upper())
        lines.append("=" * len(title))
        lines.append("")

    for section in data.get("sections", []):
        heading = section.get("heading", "").strip()
        items   = section.get("items", [])

        if heading:
            lines.append(heading)
            lines.append("-" * len(heading))

        for i, item in enumerate(items, 1):
            lines.append(f"  {i}. {str(item).strip()}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


FORMATTERS = {
    "markdown": format_markdown,
    "plain":    format_plain,
}

def handle_request(raw: bytes) -> dict:
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    if not isinstance(request, dict):
        return {"status": "error", "message": "Request must be a JSON object."}

    fmt = str(request.get("format", "markdown")).lower()
    if fmt not in FORMATTERS:
        supported = ", ".join(f'"{k}"' for k in FORMATTERS)
        return {"status": "error", "message": f"Unknown format '{fmt}'. Supported: {supported}."}

    data = request.get("data")
    if not isinstance(data, dict):
        return {"status": "error", "message": "'data' must be a JSON object with optional 'title' and 'sections'."}

    sections = data.get("sections", [])
    if not isinstance(sections, list):
        return {"status": "error", "message": "'data.sections' must be a list."}

    try:
        formatted = FORMATTERS[fmt](data)
    except Exception as e:
        return {"status": "error", "message": f"Formatting failed: {e}"}

    return {"status": "success", "formatted_text": formatted}

def main():
    context = zmq.Context()
    socket  = context.socket(zmq.REP)
    socket.bind("tcp://*:5557")

    print("Text Export Microservice is running on tcp://*:5557 ...")
    print("Waiting for requests. Press Ctrl+C to stop.\n")

    try:
        while True:
            raw      = socket.recv()
            print(f"[REQUEST]  {raw.decode()}")
            response = handle_request(raw)
            payload  = json.dumps(response)
            socket.send_string(payload)
            print(f"[RESPONSE] status={response['status']}\n")

    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        socket.close()
        context.destroy()


if __name__ == "__main__":
    main()