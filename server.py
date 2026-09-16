"""
server.py
---------
Flask + SocketIO web sunucusu.
Tarayıcıda http://localhost:5000 ile açılır.
"""

import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from dotenv import load_dotenv, set_key
from pathlib import Path

from datetime import datetime
from bot.controller import BotController

# -----------------------------------------------------------------------
load_dotenv()
app = Flask(__name__, static_folder="web", template_folder="web")
app.config["SECRET_KEY"] = "chess-bot-secret-2024"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
controller = BotController(socketio)

ENV_FILE = Path(__file__).parent / ".env"
FALLBACK_TOKEN = os.getenv("LICHESS_TOKEN", "")


def get_valid_token(raw_token: str = "") -> str:
    """Geçerli Lichess API token'ını döner."""
    from dotenv import dotenv_values

    # 1. Kullanıcıdan yeni token geldiyse
    if raw_token and not raw_token.startswith("__saved__") and len(raw_token) > 10:
        token = raw_token.strip("'\" \t\r\n")
        ENV_FILE.touch(exist_ok=True)
        try:
            set_key(str(ENV_FILE), "LICHESS_TOKEN", token, quote_mode="never")
        except Exception:
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write(f"LICHESS_TOKEN={token}\n")
        os.environ["LICHESS_TOKEN"] = token
        return token

    # 2. .env dosyasından oku
    env_vals = dotenv_values(ENV_FILE)
    token = env_vals.get("LICHESS_TOKEN", "") or os.getenv("LICHESS_TOKEN", "")
    if token:
        token = token.strip("'\" \t\r\n")
    if token and not token.startswith("__saved__") and len(token) > 10:
        return token

    # 3. Fallback token'ı kullan ve .env'ye yaz
    ENV_FILE.touch(exist_ok=True)
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(f"LICHESS_TOKEN={FALLBACK_TOKEN}\n")
    os.environ["LICHESS_TOKEN"] = FALLBACK_TOKEN
    return FALLBACK_TOKEN


# -----------------------------------------------------------------------


# -----------------------------------------------------------------------
# Sayfalar
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
    st = controller.status
    # Eğer henüz bir oyun bağlanmadıysa ve geçerli token varsa, devam eden oyun var mı hemen kontrol et
    if not st.get("is_running") or not st.get("live_game"):
        token = get_valid_token()
        if token and len(token) > 10:
            try:
                from bot.lichess_client import LichessClient

                cl = LichessClient(token)
                ongoing = cl.get_my_ongoing_games()
                if ongoing:
                    first_game = ongoing[0]
                    gid = first_game.get("gameId")
                    color = first_game.get("color", "white")
                    opp = first_game.get("opponent", {})
                    opp_name = (
                        opp.get("username")
                        or opp.get("name")
                        or opp.get("id")
                        or "Rakip"
                    )
                    opp_elo = str(opp.get("rating", "?"))
                    my_elo = str(first_game.get("rating", "?"))
                    fen = first_game.get("fen", "")
                    last_move = first_game.get("lastMove", "")
                    st["live_game"] = {
                        "game_id": gid,
                        "color": color,
                        "fen": fen,
                        "moves": "",
                        "last_move": last_move,
                        "opponent_name": opp_name,
                        "opponent_rating": opp_elo,
                        "bot_rating": my_elo,
                    }
                    st["game_id"] = gid
                    st["is_running"] = True
                    # Arka planda controller'ı bu maça bağla
                    if not controller.is_running:
                        controller.start(token, game_mode="rapid", vs_mode="bots")
            except Exception:
                pass
    return jsonify(st)


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json() or {}
    raw_token = data.get("token", "")
    token = get_valid_token(raw_token)

    game_mode = data.get("game_mode", "auto")
    vs_mode = data.get("vs_mode", "bots")
    ai_level = int(data.get("ai_level", 1))
    min_elo = int(data.get("min_elo", 800))
    max_elo = int(data.get("max_elo", 2500))

    if not token or token == "__saved__":
        token = get_valid_token()

    if not token or len(token) < 10:
        return jsonify({"ok": False, "error": "Lichess API token bulunamadı (.env dosyasını kontrol edin)"}), 400

    controller.challenge_ai_level = ai_level
    controller.start(
        token,
        game_mode=game_mode,
        vs_mode=vs_mode,
        min_elo=min_elo,
        max_elo=max_elo,
    )
    return jsonify({"ok": True, "token_preview": f"{token[:8]}..."})


@app.route("/api/pause", methods=["POST"])
def api_pause():
    controller.pause()
    return jsonify({"ok": True})


@app.route("/api/resume", methods=["POST"])
def api_resume():
    controller.resume()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    controller.stop()
    return jsonify({"ok": True})


@app.route("/api/config")
def api_config():
    """Kaydedilmiş token ve engine bilgisi."""
    token = get_valid_token()
    engine_info = controller.engine.info
    has_valid_token = bool(token and token != "__saved__" and len(token) > 10)
    return jsonify(
        {
            "has_token": has_valid_token,
            "token_preview": f"{token[:8]}..." if has_valid_token else "",
            "engine": engine_info,
            "game_mode": controller.game_mode,
            "min_elo": getattr(controller, "min_elo", 800),
            "max_elo": getattr(controller, "max_elo", 2500),
            "vs_mode": getattr(controller, "vs_mode", "bots"),
        }
    )


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

    import chess
    from bot.custom_engine import custom_ai_instance

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
    socketio.emit("log", {"message": "Bağlantı kuruldu."})


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

