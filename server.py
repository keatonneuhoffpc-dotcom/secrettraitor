import json
import os
import random
import secrets
import string
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
ROOMS = {}
LOCK = threading.RLock()

def code4():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(5))

def clean_name(value):
    value = " ".join(str(value or "").split()).strip()
    return value[:18] or "Player"

def public_state(room, player_id):
    player = room["players"].get(player_id)
    if not player:
        return {"error": "Player not found"}
    players = []
    for pid, p in room["players"].items():
        item = {
            "id": pid, "name": p["name"], "alive": p["alive"],
            "is_host": pid == room["host_id"],
            "ready": p["ready"],
        }
        if room["phase"] == "ended" or (room["phase"] == "playing" and pid == player_id):
            item["role"] = p.get("role")
        players.append(item)
    return {
        "code": room["code"], "phase": room["phase"],
        "host_id": room["host_id"], "you": player_id,
        "your_role": player.get("role") if room["phase"] in ("playing", "ended") else None,
        "your_alive": player["alive"],
        "players": players,
        "traitor_count": room["traitor_count"],
        "missions_done": room["missions_done"],
        "missions_total": room["missions_total"],
        "messages": room["messages"][-60:],
        "notice": room.get("notice", ""),
        "winner": room.get("winner"),
        "last_attack": room.get("last_attack", 0),
        "attack_cooldown": 12,
        "mission_cooldown": 0,
    }

def end_check(room):
    if room["phase"] != "playing":
        return
    alive_agents = [p for p in room["players"].values() if p["alive"] and p.get("role") == "Agent"]
    alive_traitors = [p for p in room["players"].values() if p["alive"] and p.get("role") == "Traitor"]
    if room["missions_done"] >= room["missions_total"]:
        room["phase"] = "ended"
        room["winner"] = "Agents"
        room["notice"] = "All missions completed. The Agents win!"
    elif not alive_traitors:
        room["phase"] = "ended"
        room["winner"] = "Agents"
        room["notice"] = "Every Traitor has been eliminated. The Agents win!"
    elif len(alive_traitors) >= len(alive_agents):
        room["phase"] = "ended"
        room["winner"] = "Traitors"
        room["notice"] = "The Traitors have taken control. The Traitors win!"

def respond(handler, data, status=200):
    raw = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(raw)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            q = parse_qs(parsed.query)
            code = (q.get("code") or [""])[0].upper()
            pid = (q.get("pid") or [""])[0]
            with LOCK:
                room = ROOMS.get(code)
                if not room:
                    return respond(self, {"error": "Room not found. Check the code."}, 404)
                return respond(self, public_state(room, pid))
        if parsed.path == "/api/health":
            return respond(self, {"ok": True})
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return respond(self, {"error": "Invalid request."}, 400)

        with LOCK:
            if parsed.path == "/api/create":
                name = clean_name(body.get("name"))
                code = code4()
                while code in ROOMS:
                    code = code4()
                pid = secrets.token_urlsafe(12)
                room = {
                    "code": code, "host_id": pid, "phase": "lobby",
                    "players": {pid: {"name": name, "alive": True, "ready": True, "role": None}},
                    "traitor_count": 1, "missions_done": 0, "missions_total": 8,
                    "messages": [{"name": "SYSTEM", "text": f"{name} created the room.", "time": time.time()}],
                    "notice": "Waiting for friends to join.", "winner": None, "last_attack": 0,
                }
                ROOMS[code] = room
                return respond(self, {"code": code, "pid": pid})

            if parsed.path == "/api/join":
                code = str(body.get("code", "")).strip().upper()
                name = clean_name(body.get("name"))
                room = ROOMS.get(code)
                if not room:
                    return respond(self, {"error": "That room code does not exist."}, 404)
                if room["phase"] != "lobby":
                    return respond(self, {"error": "That game has already started."}, 409)
                if len(room["players"]) >= 8:
                    return respond(self, {"error": "This room is full (8 players max)."}, 409)
                pid = secrets.token_urlsafe(12)
                room["players"][pid] = {"name": name, "alive": True, "ready": True, "role": None}
                room["messages"].append({"name": "SYSTEM", "text": f"{name} joined the room.", "time": time.time()})
                room["notice"] = f"{name} joined. Share code {code} with your friends."
                return respond(self, {"code": code, "pid": pid})

            code = str(body.get("code", "")).strip().upper()
            pid = str(body.get("pid", ""))
            room = ROOMS.get(code)
            if not room or pid not in room["players"]:
                return respond(self, {"error": "Room/player not found. Rejoin the room."}, 404)
            player = room["players"][pid]

            if parsed.path == "/api/start":
                if pid != room["host_id"]:
                    return respond(self, {"error": "Only the host can start the game."}, 403)
                if room["phase"] != "lobby":
                    return respond(self, {"error": "The game has already started."}, 409)
                if len(room["players"]) < 2:
                    return respond(self, {"error": "At least 2 players are needed."}, 400)
                try:
                    n = int(body.get("traitors", 1))
                except Exception:
                    n = 1
                n = max(1, min(n, len(room["players"]) - 1))
                room["traitor_count"] = n
                ids = list(room["players"].keys())
                random.shuffle(ids)
                traitor_ids = set(ids[:n])
                for player_id, p in room["players"].items():
                    p["role"] = "Traitor" if player_id in traitor_ids else "Agent"
                    p["alive"] = True
                room["phase"] = "playing"
                room["missions_done"] = 0
                room["last_attack"] = 0
                room["notice"] = "Game started! Complete missions and watch your back."
                room["messages"].append({"name": "SYSTEM", "text": "The game has started. Roles are secret!", "time": time.time()})
                return respond(self, {"ok": True})

            if parsed.path == "/api/chat":
                if room["phase"] == "ended":
                    return respond(self, {"error": "The game has ended."}, 409)
                msg = " ".join(str(body.get("text", "")).split()).strip()[:240]
                if not msg:
                    return respond(self, {"error": "Type a message first."}, 400)
                room["messages"].append({"name": player["name"], "text": msg, "time": time.time()})
                room["messages"] = room["messages"][-100:]
                return respond(self, {"ok": True})

            if parsed.path == "/api/action":
                action = body.get("action")
                if room["phase"] != "playing":
                    return respond(self, {"error": "The game is not in progress."}, 409)
                if not player["alive"]:
                    return respond(self, {"error": "Eliminated players cannot act."}, 403)
                if action == "mission":
                    if player.get("role") != "Agent":
                        return respond(self, {"error": "Only Agents can complete missions."}, 403)
                    if room["missions_done"] >= room["missions_total"]:
                        return respond(self, {"error": "All missions are already complete."}, 409)
                    room["missions_done"] += 1
                    room["notice"] = f"{player['name']} completed a mission ({room['missions_done']}/{room['missions_total']})."
                    room["messages"].append({"name": "SYSTEM", "text": room["notice"], "time": time.time()})
                    end_check(room)
                    return respond(self, {"ok": True})
                if action == "attack":
                    if player.get("role") != "Traitor":
                        return respond(self, {"error": "Only Traitors can attack."}, 403)
                    now = time.time()
                    if now - room["last_attack"] < 12:
                        left = int(12 - (now - room["last_attack"]))
                        return respond(self, {"error": f"Attack cooldown: wait {left}s."}, 429)
                    target_id = str(body.get("target", ""))
                    target = room["players"].get(target_id)
                    if not target or not target["alive"] or target.get("role") != "Agent":
                        return respond(self, {"error": "Choose a living Agent."}, 400)
                    target["alive"] = False
                    room["last_attack"] = now
                    room["notice"] = f"{target['name']} was eliminated!"
                    room["messages"].append({"name": "SYSTEM", "text": f"A player was eliminated: {target['name']}.", "time": now})
                    end_check(room)
                    return respond(self, {"ok": True})
                return respond(self, {"error": "Unknown action."}, 400)

        return respond(self, {"error": "Unknown endpoint."}, 404)

def main():
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print("=" * 54)
    print(" SECRET TRAITOR - local multiplayer server")
    print(f" Server listening on port {port}")
    print(" For local testing: http://127.0.0.1:8000")
    print(" Press Ctrl+C to stop the server.")
    print("=" * 54)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
