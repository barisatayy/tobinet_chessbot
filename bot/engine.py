"""
bot/engine.py
-------------
Satranç Hamle Motoru Yöneticisi:
- 🟢 Tobi Light (400-600 Elo): Kullanıcının kişisel Chess.com klonu.
- 🟡 Tobi Mid (~1500-1800 Elo): Derin Alpha-Beta arama motoru.
"""

import random
import chess
from typing import Optional
from bot.custom_engine import custom_ai_instance, custom_engine_move


class Engine:
    """
    TobiNet Motor Yöneticisi (Tobi Light & Tobi Mid).
    """

    def __init__(self):
        # Varsayılan motor: Tobi Light
        self.use_tobi_light()

    def use_tobi_light(self):
        """Tobi Light aktif eder."""
        custom_ai_instance.set_mode("tobi_light")
        self.name = custom_ai_instance.active_engine_name
        self.engine_type = "tobi_light"

    def use_tobi_mid(self):
        """Tobi Mid aktif eder."""
        custom_ai_instance.set_mode("tobi_mid")
        self.name = custom_ai_instance.active_engine_name
        self.engine_type = "tobi_mid"

    def set_engine_mode(self, mode: str):
        if mode in ("tobi_light", "light"):
            self.use_tobi_light()
        elif mode in ("tobi_mid", "mid", "custom"):
            self.use_tobi_mid()

    def get_move(self, board: chess.Board) -> Optional[str]:
        """Tahta için en iyi hamleyi döner."""
        if board.is_game_over():
            return None

        legal = list(board.legal_moves)
        if not legal:
            return None

        try:
            move = custom_ai_instance.get_move(board)
            if move:
                return move
        except Exception as e:
            print(f"⚠️ [Engine Hata] Hamle üretilemedi: {e}")

        # Acil durum fallback: Yasal rastgele hamle
        return random.choice(legal).uci()

    @property
    def last_search_info(self):
        return custom_ai_instance.last_search_info

    @property
    def info(self) -> dict:
        return {
            "name": custom_ai_instance.active_engine_name,
            "engine_type": custom_ai_instance.mode,
            "has_stockfish": False,
            "has_custom": True,
            "is_light": custom_ai_instance.mode == "tobi_light",
            "is_mid": custom_ai_instance.mode == "tobi_mid",
        }
