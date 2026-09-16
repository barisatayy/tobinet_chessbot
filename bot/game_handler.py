"""
game_handler.py
---------------
Tek bir Lichess oyununun döngüsünü yönetir.
stream_game() → olayları işler → hamleleri gönderir → DB'ye kaydeder.
"""

import chess
import time
import random
from bot.lichess_client import LichessClient
from bot.engine import Engine
from bot.game_storage import GameStorage


class GameHandler:
    """Bir oyunun tüm döngüsünü yönetir."""

    def __init__(
        self,
        client: LichessClient,
        engine: Engine,
        game_id: str,
        bot_color: str,
        emit_fn,
        log_fn,
        should_stop_fn,
        game_mode: str = "rapid",
        storage: GameStorage = None,
        initial_opp_name: str = "Rakip",
        initial_opp_elo: str = "?",
        initial_my_elo: str = "?",
        initial_fen: str = "",
        initial_last_move: str = "",
    ):
        self.client = client
        self.engine = engine
        self.game_id = game_id
        self.bot_color = bot_color
        self.emit = emit_fn
        self.log = log_fn
        self.should_stop = should_stop_fn
        self.game_mode = game_mode
        self.storage = storage or GameStorage()
        self.board = chess.Board()
        if initial_fen:
            try:
                self.board.set_fen(initial_fen)
            except Exception:
                pass
        self._last_moves_str = ""
        self._last_move = initial_last_move
        self.opponent_name = initial_opp_name
        self.opponent_rating = initial_opp_elo
        self.bot_rating = initial_my_elo
        self._final_result = "unknown"

    @property
    def live_state(self) -> dict:
        moves_list = self._last_moves_str.strip().split() if self._last_moves_str.strip() else []
        return {
            "game_id": self.game_id,
            "color": self.bot_color,
            "fen": self.board.fen(),
            "moves": self._last_moves_str,
            "last_move": moves_list[-1] if moves_list else "",
            "opponent_name": self.opponent_name,
            "opponent_rating": self.opponent_rating,
            "bot_rating": self.bot_rating,
        }

    def run(self):
        """Oyun akışını dinler ve hamleleri yapar."""
        self.log(f"♟️  Oyun başladı: {self.game_id} ({self.bot_color})")

        # DB'ye kayıt oluştur
        self.storage.create_game(
            self.game_id, self.bot_color, self.game_mode, self.opponent_name
        )

        self.emit("game_start", {
            "game_id": self.game_id,
            "color": self.bot_color,
            "fen": self.board.fen(),
        })

        self.emit("players_info", {
            "opponent_name": self.opponent_name,
            "opponent_rating": self.opponent_rating,
            "bot_rating": self.bot_rating,
        })
        self.emit("sync_live_game", self.live_state)

        try:
            for event in self.client.stream_game(self.game_id):
                if self.should_stop():
                    self.log("⏸  Oyun duraklatıldı.")
                    break
                    
                if not event:
                    continue

                etype = event.get("type")

                if etype == "gameFull":
                    # Rakip adını ve elosunu white / black objelerinden al
                    white_info = event.get("white", {})
                    black_info = event.get("black", {})
                    if self.bot_color == "white":
                        opp_info = black_info
                        my_info = white_info
                    else:
                        opp_info = white_info
                        my_info = black_info

                    opponent = opp_info.get("name") or opp_info.get("id") or self.opponent_name or "Lichess AI"
                    opponent_rating = str(opp_info.get("rating", self.opponent_rating))
                    bot_rating = str(my_info.get("rating", self.bot_rating))

                    self.opponent_name = opponent
                    self.opponent_rating = opponent_rating
                    self.bot_rating = bot_rating

                    self.emit("players_info", {
                        "opponent_name": opponent,
                        "opponent_rating": opponent_rating,
                        "bot_rating": bot_rating
                    })

                    state = event.get("state", {})
                    self._process_state(state, initial=True)

                elif etype == "gameState":
                    self._process_state(event)

                elif etype == "chatLine":
                    room = event.get("room", "")
                    username = event.get("username", "")
                    text = event.get("text", "")
                    self.log(f"💬 [{room}] {username}: {text}")

                elif etype == "opponentGone":
                    self.log("🚶 Rakip oyunu terk etti.")
                    break

        except Exception as e:
            self.log(f"⚠️  Oyun akışı hatası: {e}")
        finally:
            # Oyunu DB'ye kaydet
            self.storage.finish_game(
                self.game_id,
                self._final_result,
                self._last_moves_str,
            )
            self.log(f"💾 Oyun kaydedildi: {self.game_id} ({self._final_result})")
            self.log(f"🏁 Oyun bitti: {self.game_id}")
            self.emit("game_over", {"game_id": self.game_id, "result": self._final_result})

    def _process_state(self, state: dict, initial: bool = False):
        """Oyun durumunu işler, gerekirse hamle yapar."""
        moves_str = state.get("moves", "")
        status = state.get("status", "started")

        # Oyun bitti mi?
        if status not in ("started", "created"):
            winner = state.get("winner", "")
            # Sonucu belirle
            if winner == self.bot_color:
                self._final_result = "win"
            elif winner and winner != self.bot_color:
                self._final_result = "loss"
            elif status == "draw":
                self._final_result = "draw"
            else:
                self._final_result = status  # resign, stalemate vs.

            self.log(f"🏁 Oyun sona erdi: {status} {'(' + winner + ' kazandı)' if winner else ''}")
            # Son hamle dizisini DB'ye kaydet
            self._last_moves_str = moves_str
            self.storage.finish_game(self.game_id, self._final_result, moves_str)
            self.emit("game_over", {
                "game_id": self.game_id,
                "status": status,
                "winner": winner,
                "result": self._final_result,
            })
            return

        # Hamle dizisi değiştiyse kaydet
        if moves_str != self._last_moves_str:
            self._last_moves_str = moves_str
            self.storage.update_moves(self.game_id, moves_str)

        # Tahtayı yeniden kur
        self.board = chess.Board()
        if moves_str:
            for move_uci in moves_str.strip().split():
                try:
                    self.board.push_uci(move_uci)
                except Exception:
                    pass

        # Tahta durumunu UI'ya gönder
        moves_list = moves_str.strip().split() if moves_str.strip() else []
        self.emit("board_update", {
            "game_id": self.game_id,
            "fen": self.board.fen(),
            "moves": moves_str,
            "moves_count": len(moves_list),
            "last_move": moves_list[-1] if moves_list else "",
            "wtime": state.get("wtime"),
            "btime": state.get("btime"),
        })

        # Sıra bizde mi?
        our_turn = (
            (self.bot_color == "white" and self.board.turn == chess.WHITE) or
            (self.bot_color == "black" and self.board.turn == chess.BLACK)
        )

        if not our_turn:
            return

        # Hamle hesapla
        time.sleep(random.uniform(0.5, 1.5))

        move = self.engine.get_move(self.board)
        if not move:
            self.log("⚠️  Motor hamle üretemedi.")
            return

        self.log(f"♟️  Hamle: {move}")

        ok = self.client.make_move(self.game_id, move)
        if ok:
            self.log(f"✅ Hamle kabul edildi: {move}")
        else:
            self.log(f"❌ Hamle reddedildi: {move}")
