"""Multi-Agent Chat Room — Flask backend."""

from __future__ import annotations

import json
import queue
import threading
import uuid

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

from agents import AGENTS, Agent, generate_summary, get_agent, reset_agents

load_dotenv()

app = Flask(__name__, static_folder="static")

# ── Global state ──────────────────────────────────────────────
chat_history: list[dict] = []
subscribers: dict[str, queue.Queue] = {}
room_lock = threading.Lock()
room_active = False
room_paused = False
pause_event = threading.Event()
current_topic: str | None = None


def broadcast(event: str, data: dict):
    """Push an event to all SSE subscribers."""
    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    dead = []
    for sid, q in subscribers.items():
        try:
            q.put_nowait(payload)
        except Exception:
            dead.append(sid)
    for sid in dead:
        subscribers.pop(sid, None)


def add_message(agent_name: str, text: str, msg_type: str = "chat"):
    user_meta = {"avatar": "👤", "color": "#f472b6"}
    agent = AGENTS.get(agent_name)
    msg = {
        "id": uuid.uuid4().hex[:8],
        "type": msg_type,
        "agent": agent_name,
        "text": text,
        "avatar": agent.avatar if agent else user_meta["avatar"],
        "color": agent.color if agent else user_meta["color"],
    }
    chat_history.append(msg)
    broadcast("message", msg)
    return msg


# ── SSE ───────────────────────────────────────────────────────
def sse_stream(sid: str):
    q = subscribers[sid]
    try:
        while True:
            try:
                yield q.get(timeout=30)
            except queue.Empty:
                yield ": keepalive\n\n"
    except GeneratorExit:
        subscribers.pop(sid, None)


# ── Chat loop ─────────────────────────────────────────────────
def chat_loop(agent_names: list[str], topic: str | None, rounds: int):
    global room_active, room_paused, current_topic
    current_topic = topic
    room_active = True
    room_paused = False
    pause_event.set()

    add_message("系统", f"聊天开始！话题：{topic}" if topic else "聊天开始！大家畅所欲言~", "system")

    for round_num in range(rounds):
        if not room_active:
            break

        # Remind topic at the start of each round
        if topic and round_num > 0:
            add_message("系统", f"📌 讨论话题提醒：{topic}", "system")

        round_had_message = False
        for name in agent_names:
            # Wait here while paused
            while room_paused and room_active:
                pause_event.clear()
                pause_event.wait(timeout=1)
            if not room_active:
                break

            agent = get_agent(name)

            history = []
            for m in chat_history[-20:]:
                if m["type"] not in ("chat", "user"):
                    continue
                if m["agent"] == name:
                    role = "assistant"
                    prefix = ""
                elif m["type"] == "user":
                    role = "user"
                    prefix = "用户说："
                else:
                    role = "user"
                    prefix = f"{m['agent']}说："
                history.append({"role": role, "content": f"{prefix}{m['text']}"})

            if not history:
                history = [{"role": "user", "content": topic or "大家好，来聊聊天吧！"}]

            try:
                response = agent.generate_response(history, topic)
            except Exception as e:
                response = f"（出错了：{e}）"

            with room_lock:
                if room_active:
                    add_message(name, response)
                    round_had_message = True

        # Update diagram after each round
        if round_had_message and room_active:
            pass

    # Generate summary after discussion ends
    if room_active:
        add_message("系统", "讨论结束，正在生成总结…", "system")
        try:
            summary_text = generate_summary(chat_history, current_topic)
            add_message("总结", summary_text, "summary")
        except Exception as e:
            add_message("系统", f"总结生成失败：{e}", "system")

    room_active = False
    broadcast("status", {"active": False, "paused": False})


# ── Routes ────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/agents", methods=["GET"])
def list_agents():
    return jsonify([a.to_dict() for a in AGENTS.values()])


@app.route("/api/agents", methods=["POST"])
def add_agent():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    personality = (data.get("personality") or "").strip()
    color = data.get("color", "#6366f1")
    avatar = data.get("avatar", "🤖")

    if not name or not personality:
        return jsonify({"error": "名字和人设不能为空"}), 400
    if name in AGENTS:
        return jsonify({"error": f"Agent「{name}」已存在"}), 400

    AGENTS[name] = Agent(name=name, personality=personality, color=color, avatar=avatar)
    broadcast("agents_changed", {})
    return jsonify({"status": "created", "agent": AGENTS[name].to_dict()}), 201


@app.route("/api/agents/<name>", methods=["PUT"])
def update_agent(name):
    if name not in AGENTS:
        return jsonify({"error": f"Agent「{name}」不存在"}), 404

    data = request.json or {}
    agent = AGENTS[name]
    new_name = (data.get("name") or name).strip()

    if new_name != name:
        if new_name in AGENTS:
            return jsonify({"error": f"Agent「{new_name}」已存在"}), 400
        AGENTS.pop(name)

    agent.name = new_name
    agent.personality = data.get("personality", agent.personality)
    agent.color = data.get("color", agent.color)
    agent.avatar = data.get("avatar", agent.avatar)
    AGENTS[new_name] = agent

    broadcast("agents_changed", {})
    return jsonify({"status": "updated", "agent": agent.to_dict()})


@app.route("/api/agents/<name>", methods=["DELETE"])
def delete_agent(name):
    if name not in AGENTS:
        return jsonify({"error": f"Agent「{name}」不存在"}), 404
    del AGENTS[name]
    broadcast("agents_changed", {})
    return jsonify({"status": "deleted"})


@app.route("/api/agents/reset", methods=["POST"])
def reset_agents_api():
    reset_agents()
    broadcast("agents_changed", {})
    return jsonify({"status": "reset"})


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify(chat_history)


@app.route("/api/start", methods=["POST"])
def start_chat():
    global room_active
    if room_active:
        return jsonify({"error": "聊天正在进行中"}), 400

    data = request.json or {}
    agent_names = data.get("agents", list(AGENTS.keys()))
    topic = data.get("topic")
    rounds = min(data.get("rounds", 5), 20)

    for n in agent_names:
        if n not in AGENTS:
            return jsonify({"error": f"未知 agent: {n}"}), 400

    threading.Thread(
        target=chat_loop, args=(agent_names, topic, rounds), daemon=True
    ).start()
    return jsonify({"status": "started"})


@app.route("/api/user-message", methods=["POST"])
def user_message():
    if not room_active:
        return jsonify({"error": "聊天未在进行中"}), 400
    data = request.json or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "消息不能为空"}), 400
    msg = add_message("You", text, "user")
    return jsonify({"status": "sent", "message": msg})


@app.route("/api/pause", methods=["POST"])
def pause_chat():
    global room_paused
    if not room_active or room_paused:
        return jsonify({"error": "无法暂停"}), 400
    room_paused = True
    add_message("系统", "讨论已暂停，你可以输入你的观点。", "system")
    broadcast("status", {"active": True, "paused": True})
    return jsonify({"status": "paused"})


@app.route("/api/resume", methods=["POST"])
def resume_chat():
    global room_paused
    if not room_active or not room_paused:
        return jsonify({"error": "无法继续"}), 400
    room_paused = False
    pause_event.set()
    add_message("系统", "讨论继续！", "system")
    broadcast("status", {"active": True, "paused": False})
    return jsonify({"status": "resumed"})


@app.route("/api/stop", methods=["POST"])
def stop_chat():
    global room_active, room_paused
    room_active = False
    room_paused = False
    pause_event.set()
    add_message("系统", "聊天已被手动停止。", "system")
    broadcast("status", {"active": False, "paused": False})
    return jsonify({"status": "stopped"})


@app.route("/api/clear", methods=["POST"])
def clear_history():
    global room_active, room_paused
    room_active = False
    room_paused = False
    pause_event.set()
    chat_history.clear()
    return jsonify({"status": "cleared"})


@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({"active": room_active, "paused": room_paused})


@app.route("/api/events")
def sse():
    sid = uuid.uuid4().hex
    q = queue.Queue(maxsize=100)
    subscribers[sid] = q
    return Response(sse_stream(sid), mimetype="text/event-stream")


if __name__ == "__main__":
    print("🤖 Multi-Agent Chat Room starting...")
    print("   Open http://127.0.0.1:5000 in your browser")
    app.run(debug=True, port=5000)
