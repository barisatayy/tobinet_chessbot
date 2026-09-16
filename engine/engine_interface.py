"""
engine_interface.py
-------------------
Satranç engine bağlantısı.
Şu an için: rastgele legal hamle üretir (placeholder).
İleride: Stockfish veya custom AI buraya bağlanacak.
"""

import random
import chess
from typing import Optional


class EngineInterface:
    """
    Satranç motoru arayüzü.
    get_best_move(fen) → UCI hamle string döner.
    
    Şu anki implementasyon: rastgele legal hamle.
    İleride değiştirilecek: Stockfish / custom neural net.
    """

    def __init__(self):
        self.engine_name = "Random (Placeholder)"
        self._stockfish = None
        # İleride: self._stockfish = Stockfish(path="stockfish.exe")

    def get_best_move(self, fen: str) -> Optional[str]:
        """
        Verilen FEN pozisyonu için en iyi hamleyi döner.
        Returns: UCI format string (örn: "e2e4") veya None
        """
        try:
            board = chess.Board(fen)
            
            if board.is_game_over():
                return None
            
            legal_moves = list(board.legal_moves)
            if not legal_moves:
                return None
            
            # TODO: Burası Stockfish veya AI ile değiştirilecek
            move = self._random_move(board, legal_moves)
            return move.uci()
            
        except Exception as e:
            return None

    def _random_move(self, board: chess.Board, legal_moves: list) -> chess.Move:
        """
        Biraz daha akıllı rastgele: mat/şah pozisyonlarını tercih eder.
        """
        # Mat yapabiliyorsa yap
        for move in legal_moves:
            board.push(move)
            if board.is_checkmate():
                board.pop()
                return move
            board.pop()
        
        # Şah verebiliyorsa ver
        check_moves = [m for m in legal_moves if board.gives_check(m)]
        if check_moves and random.random() < 0.4:
            return random.choice(check_moves)
        
        # Capture move tercih et (biraz agresif oyna)
        captures = [m for m in legal_moves if board.is_capture(m)]
        if captures and random.random() < 0.6:
            return random.choice(captures)
        
        # Tamamen rastgele
        return random.choice(legal_moves)

    def set_stockfish(self, path: str, depth: int = 15):
        """
        Stockfish engine'i ayarla.
        pip install stockfish gerektirir.
        """
        try:
            from stockfish import Stockfish
            self._stockfish = Stockfish(path=path, depth=depth)
            self.engine_name = f"Stockfish (depth={depth})"
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def set_custom_ai(self, ai_callable):
        """
        Eğitilmiş AI modelini bağlar.
        ai_callable: (fen: str) -> uci_move: str fonksiyonu
        """
        self._custom_ai = ai_callable
        self.engine_name = "Custom AI"

    @property
    def name(self) -> str:
        return self.engine_name
