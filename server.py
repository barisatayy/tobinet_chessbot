"""
server.py
---------
TobiNet Satranç AI — Flask + SocketIO Web Sunucusu.
Tarayıcıda http://localhost:5000 ile açılır.
"""

import os
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
import chess
from bot.controller import BotController
from bot.custom_engine import custom_ai_instance

app = Flask(__name__, static_folder="web", template_folder="web")
app.config["SECRET_KEY"] = "tobinet-secret-key-2024"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
controller = BotController(socketio)


# -----------------------------------------------------------------------
# Sayfalar ve Statik Dosyalar
# -----------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("web", filename)


# -----------------------------------------------------------------------
# REST API
# -----------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    return jsonify(controller.status)


@app.route("/api/engine/config", methods=["POST"])
def api_engine_config():
    """Motor ayarlarını güncelle (Tobi Light veya Tobi Mid)."""
    data = request.get_json() or {}
    engine_type = data.get("engine_type", "tobi_light")

    if engine_type in ("tobi_light", "light"):
        controller.engine.use_tobi_light()
        controller.log("Motor seçildi: Tobi Light")
    elif engine_type in ("tobi_mid", "mid", "custom"):
        controller.engine.use_tobi_mid()
        controller.log("Motor seçildi: Tobi Mid")

    return jsonify({"ok": True, "engine": controller.engine.info})


@app.route("/api/play/move", methods=["POST"])
def api_play_move():
    """Kullanıcının lokalde bota karşı veya bot vs bot modunda hamle üretmesi."""
    data = request.get_json() or {}
    fen = data.get("fen", "")
    if not fen:
        return jsonify({"ok": False, "error": "FEN pozisyonu gerekli"}), 400

    try:
        board = chess.Board(fen)
        if board.is_game_over():
            return jsonify({"ok": False, "error": "Oyun zaten bitmiş"})

        engine_choice = data.get("engine", "")
        if engine_choice in ("tobi_light", "light"):
            move_uci = custom_ai_instance.light_engine.get_move(board, max_depth=3, time_limit=3.0)
            search_info = custom_ai_instance.light_engine.last_search_info
            engine_name = "Tobi Light"
        elif engine_choice in ("tobi_mid", "mid"):
            move_uci = custom_ai_instance.mid_engine.get_move(board, max_depth=5, time_limit=6.0)
            search_info = custom_ai_instance.mid_engine.last_search_info
            engine_name = "Tobi Mid"
        else:
            move_uci = controller.engine.get_move(board)
            search_info = getattr(controller.engine, "last_search_info", None)
            engine_name = controller.engine.name

        if not move_uci:
            return jsonify({"ok": False, "error": "Motor hamle üretemedi"}), 500

        if search_info:
            engine_title = search_info.get("engine", engine_name)
            sc = search_info.get("eval_str", "")
            el = search_info.get("elapsed", 0.0)
            nodes = search_info.get("nodes", 0)
            controller.log(f"[{engine_title}] Hamle: {move_uci} | {sc} ({nodes:,} poz, {el}s)")

        move = chess.Move.from_uci(move_uci)
        board.push(move)

        return jsonify(
            {
                "ok": True,
                "move": move_uci,
                "new_fen": board.fen(),
                "engine": engine_name,
                "search_info": search_info,
                "is_game_over": board.is_game_over(),
                "is_check": board.is_check(),
                "result": board.result() if board.is_game_over() else None,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -----------------------------------------------------------------------
# SocketIO olayları
# -----------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    st = controller.status
    socketio.emit("status", st)


@socketio.on("disconnect")
def on_disconnect():
    pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 50)
    print("  TobiNet Chess AI")
    print(f"  http://localhost:{port}")
    print("=" * 50 + "\n")
    socketio.run(
        app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True
    )
