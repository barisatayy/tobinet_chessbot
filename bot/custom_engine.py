"""
bot/custom_engine.py
--------------------
Özel Satranç Motorlarımız:
1. 🟢 Tobi Light (400-600 Elo):
   - Kullanıcının ('tobildak') Chess.com'daki 1.483 maçından eğitilen kişisel klon modeli.
   - 5.199 pozisyonluk kişisel açılış hafızası (Opening Repertoire) ve insansı olasılık örneklemesi.
2. 🟡 Tobi Mid (~1500-1800 Elo):
   - Büyük Usta oyunlarıyla eğitilmiş derin ResNet omurgası.
   - 4-6 derinlikli İteratif Alpha-Beta budaması, Sükunet araması (Quiescence) ve Zobrist Önbelleği (TT).
"""

import os
import sys
import time
import json
import random
import numpy as np
import chess
from pathlib import Path
from ai.encoder import board_to_tensor, get_legal_move_mask, move_to_index

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import torch
    from ai.model import ChessResNet
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

CHECKPOINTS_DIR = Path(__file__).parent.parent / "ai" / "checkpoints"
TOBI_LIGHT_MODEL_PATH = CHECKPOINTS_DIR / "tobi_light.pt"
TOBI_LIGHT_OPENINGS_PATH = CHECKPOINTS_DIR / "tobi_light_openings.json"
TOBI_MID_MODEL_PATH = CHECKPOINTS_DIR / "best_model.pt"

# TT Bayrakları
EXACT = 0
LOWERBOUND = 1
UPPERBOUND = 2


# ==============================================================================
# 1. POZİSYON DEĞERLENDİRME (PeSTO Piece-Square Tables)
# ==============================================================================

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

PST_PAWN = [
      0,   0,   0,   0,   0,   0,   0,   0,
     50,  50,  50,  50,  50,  50,  50,  50,
     10,  10,  20,  30,  30,  20,  10,  10,
      5,   5,  10,  25,  25,  10,   5,   5,
      0,   0,   0,  20,  20,   0,   0,   0,
      5,  -5, -10,   0,   0, -10,  -5,   5,
      5,  10,  10, -20, -20,  10,  10,   5,
      0,   0,   0,   0,   0,   0,   0,   0
]

PST_KNIGHT = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]

PST_BISHOP = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]

PST_ROOK = [
      0,   0,   0,   0,   0,   0,   0,   0,
      5,  10,  10,  10,  10,  10,  10,   5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
      0,   0,   0,   5,   5,   0,   0,   0
]

PST_QUEEN = [
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,  -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20
]

PST_KING = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,   0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20
]

PST_MAP = {
    chess.PAWN: PST_PAWN,
    chess.KNIGHT: PST_KNIGHT,
    chess.BISHOP: PST_BISHOP,
    chess.ROOK: PST_ROOK,
    chess.QUEEN: PST_QUEEN,
    chess.KING: PST_KING,
}


def evaluate_board(board: chess.Board) -> int:
    """Tahtayı centipawn cinsinden değerlendirir (Beyaz için pozitif, Siyah için negatif)."""
    if board.is_checkmate():
        return -99999 if board.turn == chess.WHITE else 99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    piece_map = board.piece_map()
    for sq, piece in piece_map.items():
        val = PIECE_VALUES[piece.piece_type]
        pst = PST_MAP[piece.piece_type]

        if piece.color == chess.WHITE:
            pst_val = pst[chess.square_mirror(sq)]
            score += val + pst_val
        else:
            pst_val = pst[sq]
            score -= (val + pst_val)

    # Fil Çifti Bonusu (+30 cp)
    white_bishops = len(board.pieces(chess.BISHOP, chess.WHITE))
    black_bishops = len(board.pieces(chess.BISHOP, chess.BLACK))
    if white_bishops >= 2: score += 30
    if black_bishops >= 2: score -= 30

    # Rok Hakkı Bonusu (+15 cp)
    if board.has_castling_rights(chess.WHITE): score += 15
    if board.has_castling_rights(chess.BLACK): score -= 15

    return score


# ==============================================================================
# 2. TOBI LIGHT ENGINE (~400-600 Elo Kişisel Klon)
# ==============================================================================

def is_hanging_blunder(board: chess.Board, move: chess.Move) -> bool:
    """
    1-ply Güvenlik Kontrolü (Blunder Kalkanı):
    Hamle yapıldığında ağır taşın (Vezir, Kale, Hafif Taş) intihar şeklinde
    rakibe bedavaya verilip verilmediğini tespit eder.
    """
    mover_piece = board.piece_at(move.from_square)
    if not mover_piece:
        return False

    pt = mover_piece.piece_type
    if pt not in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
        return False

    us = board.turn
    them = not us
    to_sq = move.to_square

    # 1. Rakip piyon tarafından vuruluyor mu?
    pawn_attacks = board.attackers(them, to_sq)
    enemy_pawns = [sq for sq in pawn_attacks if board.piece_at(sq).piece_type == chess.PAWN]
    if enemy_pawns:
        captured = board.piece_at(to_sq)
        cap_val = PIECE_VALUES.get(captured.piece_type, 0) if captured else 0
        if cap_val < PIECE_VALUES[pt]:
            return True

    # 2. Taş korumasız mı ve rakip tarafından ilk hamlede alınabiliyor mu?
    board.push(move)
    is_under_attack = board.is_attacked_by(them, to_sq)
    is_defended = board.is_attacked_by(us, to_sq)

    blunder = False
    if is_under_attack:
        if not is_defended:
            blunder = True
        elif pt == chess.QUEEN:
            attackers = board.attackers(them, to_sq)
            for a_sq in attackers:
                a_piece = board.piece_at(a_sq)
                if a_piece and a_piece.piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK):
                    blunder = True
                    break
        elif pt == chess.ROOK:
            attackers = board.attackers(them, to_sq)
            for a_sq in attackers:
                a_piece = board.piece_at(a_sq)
                if a_piece and a_piece.piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP):
                    blunder = True
                    break

    board.pop()
    return blunder


# ==============================================================================
# 2. ORTAK DERİN ARAMA MOTORU (DeepSearchEngine)
# ==============================================================================

class DeepSearchEngine:
    def __init__(self, model=None, device="cpu"):
        self.model = model
        self.device = device
        self.tt = {}
        self.killers = {}
        self.history = {}
        self.nodes = 0
        self.time_abort = False

    def order_moves(self, board: chess.Board, moves, pv_move=None, ply=0):
        k1, k2 = self.killers.get(ply, (None, None))

        def move_score(move: chess.Move):
            if pv_move and move == pv_move:
                return 2000000
            if board.is_capture(move):
                victim = board.piece_at(move.to_square)
                attacker = board.piece_at(move.from_square)
                v_val = PIECE_VALUES.get(victim.piece_type, 100) if victim else 100
                a_val = PIECE_VALUES.get(attacker.piece_type, 100) if attacker else 100
                return 1000000 + (v_val * 10 - a_val)
            if move.promotion:
                return 950000
            if move == k1:
                return 900000
            if move == k2:
                return 800000
            return self.history.get((move.from_square, move.to_square), 0)

        return sorted(moves, key=move_score, reverse=True)

    def quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int, deadline: float, qdepth: int = 0) -> int:
        self.nodes += 1
        if (self.nodes & 1023) == 0 and time.time() > deadline:
            self.time_abort = True
            return alpha

        if board.is_checkmate():
            return -99999 + ply
        if board.is_stalemate() or board.can_claim_threefold_repetition() or board.is_repetition(3) or board.is_insufficient_material():
            eval_score = evaluate_board(board)
            my_eval = eval_score if board.turn == chess.WHITE else -eval_score
            if my_eval > 80:
                return -80000 + ply  # Kazançlıyken beraberlik/pat felakettir
            elif my_eval < -80:
                return 80000 - ply   # Kaybederken beraberlik büyük bir kurtuluştur
            return 0

        stand_pat = evaluate_board(board)
        if board.turn == chess.BLACK:
            stand_pat = -stand_pat

        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        if qdepth >= 8:
            return alpha

        if stand_pat + 950 < alpha:
            return alpha

        captures = [m for m in board.legal_moves if board.is_capture(m)]
        ordered_captures = self.order_moves(board, captures, None, ply)

        for move in ordered_captures:
            board.push(move)
            score = -self.quiescence(board, -beta, -alpha, ply + 1, deadline, qdepth + 1)
            board.pop()

            if self.time_abort:
                return alpha

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

        return alpha

    def alpha_beta(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int, deadline: float) -> int:
        self.nodes += 1
        if (self.nodes & 1023) == 0 and time.time() > deadline:
            self.time_abort = True
            return alpha

        if board.is_checkmate():
            return -99999 + ply

        # 3 hamle tekrarı / Pat / Yetersiz materyal kontrolü
        is_draw = (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_threefold_repetition()
            or board.is_repetition(3)
        )
        if is_draw:
            eval_score = evaluate_board(board)
            my_eval = eval_score if board.turn == chess.WHITE else -eval_score
            if my_eval > 80:
                return -80000 + ply  # Kazançlıyken beraberlik/pat yapmak maçı kaybetmekle eşdeğerdir!
            elif my_eval < -80:
                return 80000 - ply   # Kaybederken beraberlik kurtuluştur!
            return 0

        # 2 hamle tekrarı: Üstün tarafın aynı pozisyona 2. kez girmesini cezalandır (Tekrar tuzağı kalkanı)
        if board.is_repetition(2):
            eval_score = evaluate_board(board)
            my_eval = eval_score if board.turn == chess.WHITE else -eval_score
            if my_eval < -50:
                # Rakip (az önce hamle yapan üstün taraf) 2. tekrara girdi; onun için -400 ceza!
                return 400
            elif my_eval > 50:
                return -400  # Kazançlıyken tekrara girme

        in_check = board.is_check()
        if in_check:
            depth += 1

        tt_key = board._transposition_key()
        tt_entry = self.tt.get(tt_key)
        pv_move = None
        if tt_entry is not None:
            tt_depth, tt_score, tt_flag, tt_best = tt_entry
            pv_move = tt_best
            if tt_depth >= depth:
                if tt_flag == EXACT:
                    return tt_score
                elif tt_flag == LOWERBOUND and tt_score >= beta:
                    return tt_score
                elif tt_flag == UPPERBOUND and tt_score <= alpha:
                    return tt_score

        if depth <= 0:
            return self.quiescence(board, alpha, beta, ply, deadline)

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return -99999 + ply if in_check else 0

        ordered_moves = self.order_moves(board, legal_moves, pv_move, ply)

        best_score = -999999
        best_move = None
        orig_alpha = alpha

        for move in ordered_moves:
            board.push(move)
            score = -self.alpha_beta(board, depth - 1, -beta, -alpha, ply + 1, deadline)
            board.pop()

            if self.time_abort:
                return alpha

            if score > best_score:
                best_score = score
                best_move = move

            if score > alpha:
                alpha = score

            if alpha >= beta:
                if not board.is_capture(move):
                    k1, _ = self.killers.get(ply, (None, None))
                    self.killers[ply] = (move, k1)
                    key = (move.from_square, move.to_square)
                    self.history[key] = self.history.get(key, 0) + depth * depth
                break

        if not self.time_abort:
            if best_score <= orig_alpha:
                flag = UPPERBOUND
            elif best_score >= beta:
                flag = LOWERBOUND
            else:
                flag = EXACT
            self.tt[tt_key] = (depth, best_score, flag, best_move)

        return best_score

    def search(self, board: chess.Board, max_depth: int = 5, time_limit: float = 10.0):
        start_time = time.time()
        deadline = start_time + time_limit
        self.nodes = 0
        self.time_abort = False
        self.killers.clear()

        if len(self.tt) > 400000:
            self.tt.clear()

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None, 0, 0, 0.0, 0

        if len(legal_moves) == 1:
            return legal_moves[0], 0, 1, 0.0, 1

        root_scores = {m: 0.0 for m in legal_moves}
        if self.model is not None:
            try:
                t = board_to_tensor(board)
                mask = get_legal_move_mask(board)
                probs, val = self.model.predict(t, legal_mask=mask, device=self.device)
                for m in legal_moves:
                    idx = move_to_index(m, board.turn)
                    root_scores[m] = float(probs[idx])
            except Exception as e:
                pass

        sorted_root_moves = sorted(legal_moves, key=lambda m: root_scores[m], reverse=True)

        # Kök değerlendirmesi (Botumuzun mevcut durumu)
        root_eval = evaluate_board(board)
        we_are_ahead = (root_eval > 50) if board.turn == chess.WHITE else (root_eval < -50)
        we_are_behind = (root_eval < -50) if board.turn == chess.WHITE else (root_eval > 50)

        # Başlangıç hamlesi: Kazançlıysak doğrudan beraberlik veya pat getirmeyen ilk hamle olsun
        best_move_overall = sorted_root_moves[0]
        if we_are_ahead and len(sorted_root_moves) > 1:
            for m in sorted_root_moves:
                board.push(m)
                m_draw = (
                    board.is_stalemate()
                    or board.can_claim_threefold_repetition()
                    or board.is_repetition(3)
                    or board.is_insufficient_material()
                )
                board.pop()
                if not m_draw:
                    best_move_overall = m
                    break

        best_score_overall = 0
        completed_depth = 0

        for current_depth in range(1, max_depth + 1):
            if time.time() >= deadline:
                break

            depth_best_move = None
            depth_best_score = -999999
            alpha = -999999
            beta = 999999

            if best_move_overall:
                sorted_root_moves = [best_move_overall] + [m for m in sorted_root_moves if m != best_move_overall]

            for move in sorted_root_moves:
                board.push(move)
                
                # Kök hamle anında beraberlik yaratıyor mu?
                root_draw = (
                    board.is_stalemate()
                    or board.can_claim_threefold_repetition()
                    or board.is_repetition(3)
                    or board.is_insufficient_material()
                )
                if root_draw:
                    if we_are_ahead:
                        # Kazançlıyken beraberlik yapmak ŞAH MAT OLMAKLA EŞDEĞERDİR!
                        score = -95000
                    elif we_are_behind:
                        # Kaybederken beraberlik kurtuluştur!
                        score = 95000
                    else:
                        score = 0
                else:
                    score = -self.alpha_beta(board, current_depth - 1, -beta, -alpha, 1, deadline)
                    # Kazançlıyken kök hamlenin 2. tekrara girmesine -500 cp ceza (taş sallama engeli)
                    if we_are_ahead and board.is_repetition(2):
                        score -= 500
                board.pop()

                if self.time_abort:
                    break

                if score > depth_best_score:
                    depth_best_score = score
                    depth_best_move = move

                if score > alpha:
                    alpha = score

            if not self.time_abort and depth_best_move:
                best_move_overall = depth_best_move
                best_score_overall = depth_best_score
                completed_depth = current_depth

                if abs(best_score_overall) >= 90000:
                    break
            else:
                break

        total_time = time.time() - start_time
        return best_move_overall, best_score_overall, completed_depth, total_time, self.nodes


# ==============================================================================
# 2.5. GÜVENLİK KALKANI (Anti-Pat & Anti-3 Hamle Tekrarı Güvencesi)
# ==============================================================================

def filter_safe_winning_move(board: chess.Board, chosen_move: chess.Move) -> chess.Move:
    """
    3. Katman Güvenlik Kalkanı:
    Bot kazançlı durumdayken pat veya 3-hamle tekrarı yapmasını %100 kesinlikle engeller.
    Eğer seçilen hamle beraberliğe (pat / 3-tekrar) yol açıyorsa ve başka yasal hamle varsa,
    kazancı koruyan güvenli bir alternatif hamleye yönlendirir.
    """
    legal_moves = list(board.legal_moves)
    if len(legal_moves) <= 1:
        return chosen_move

    board.push(chosen_move)
    is_draw = (
        board.is_stalemate()
        or board.can_claim_threefold_repetition()
        or board.is_repetition(3)
        or board.is_insufficient_material()
    )
    is_rep2 = board.is_repetition(2)
    board.pop()

    bot_color = board.turn
    root_eval = evaluate_board(board)
    our_eval = root_eval if bot_color == chess.WHITE else -root_eval

    # 1. Öncelik: Kazançlıyken (our_eval > 40 cp) Pat veya 3. Tekrar KESİNLİKLE YASAKTIR!
    if our_eval > 40 and is_draw:
        print(f"🚨 [Anti-Pat & Anti-Tekrar Kalkanı] {chosen_move.uci()} hamlesi maçı beraberlik/pat yapıyordu! İptal ediliyor...")
        candidates = []
        for m in legal_moves:
            if m == chosen_move:
                continue
            board.push(m)
            m_draw = (
                board.is_stalemate()
                or board.can_claim_threefold_repetition()
                or board.is_repetition(3)
                or board.is_insufficient_material()
            )
            m_rep2 = board.is_repetition(2)
            eval_after = evaluate_board(board)
            my_score = eval_after if bot_color == chess.WHITE else -eval_after
            board.pop()

            if not m_draw:
                penalty = 300 if m_rep2 else 0
                candidates.append((m, my_score - penalty))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            safe_move = candidates[0][0]
            print(f"🛡️ [Kalkan Devrede] Güvenli hamle seçildi: {safe_move.uci()} (Alternatif sayısı: {len(candidates)})")
            return safe_move

    # 2. Öncelik: Kazançlıyken 2. tekrar ile taş sallamayı önle (alternatif varsa)
    if our_eval > 60 and is_rep2 and len(legal_moves) > 1:
        candidates = []
        for m in legal_moves:
            if m == chosen_move:
                continue
            board.push(m)
            m_draw = (
                board.is_stalemate()
                or board.can_claim_threefold_repetition()
                or board.is_repetition(3)
                or board.is_insufficient_material()
            )
            m_rep2 = board.is_repetition(2)
            eval_after = evaluate_board(board)
            my_score = eval_after if bot_color == chess.WHITE else -eval_after
            board.pop()

            if not m_draw and not m_rep2:
                candidates.append((m, my_score))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            safe_move = candidates[0][0]
            print(f"🛡️ [Tekrar Önleme] 2. tekrara giren {chosen_move.uci()} yerine {safe_move.uci()} oynanıyor.")
            return safe_move

    return chosen_move


# ==============================================================================
# 3. TOBI LIGHT ENGINE (tobildak Klon Modeli - Aynı Derin Arama Mimarisi)
# ==============================================================================

class TobiLightEngine:
    """
    🟢 Tobi Light:
    - tobildak'ın kendi Chess.com maçlarıyla eğitilmiş ResNet modeli (tobi_light.pt).
    - Kişisel açılış repertuarı hafızası (tobi_light_openings.json).
    - Tobi Mid ile BİREBİR AYNI DeepSearchEngine mimarisi (Alpha-Beta Minimax, Quiescence, TT).
    - Hamle öncelikleri tobildak'ın tarzına göredir; derin arama ile intihar hamleleri ve taktik tuzaklar önlenir.
    """
    def __init__(self, device="cuda" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"):
        self.device = device
        self.model = None
        self.openings = {}
        self.search_engine = DeepSearchEngine(model=None, device=self.device)
        self.last_search_info = None
        self._load()

    def _load(self):
        # 1. Açılış Hafızasını Yükle
        if TOBI_LIGHT_OPENINGS_PATH.exists():
            try:
                with open(TOBI_LIGHT_OPENINGS_PATH, "r", encoding="utf-8") as f:
                    self.openings = json.load(f)
                print(f"📖 [Tobi Light] {len(self.openings):,} açılış pozisyonu hafızaya alındı.")
            except Exception as e:
                print(f"⚠️ [Tobi Light] Açılış hafızası okunamadı: {e}")

        # 2. tobildak Verileriyle Eğitilmiş ResNet Modelini Yükle
        best_path = CHECKPOINTS_DIR / "tobi_light_best.pt"
        target_path = best_path if best_path.exists() else TOBI_LIGHT_MODEL_PATH
        if HAS_TORCH and target_path.exists():
            try:
                ckpt = torch.load(target_path, map_location=self.device, weights_only=False)
                blocks = ckpt.get("num_blocks", 8)
                filters = ckpt.get("num_filters", 192)
                model = ChessResNet(num_blocks=blocks, num_filters=filters)
                model.load_state_dict(ckpt["model_state_dict"])
                model.to(self.device)
                model.eval()
                self.model = model
                self.search_engine.model = self.model
                self.search_engine.device = self.device
                val_acc = ckpt.get("val_acc", 0.0)
                print(f"🟢 [Tobi Light] Klon modeli yüklendi! (Doğruluk: %{val_acc:.1f}, {self.device.upper()})")
            except Exception as e:
                print(f"❌ [Tobi Light] Model yüklenirken hata: {e}")

    def get_move(self, board: chess.Board, max_depth: int = 3, time_limit: float = 3.0) -> str:
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return ""

        if len(legal_moves) == 1:
            return legal_moves[0].uci()

        # 1. Aşama: Kişisel Açılış Hafızası (tobildak'ın gerçek repertuarı)
        fen_key = board.board_fen()
        if fen_key in self.openings:
            hist_moves = self.openings[fen_key]
            valid_cands = []
            weights = []
            for m_uci, count in hist_moves.items():
                m_obj = chess.Move.from_uci(m_uci)
                if m_obj in legal_moves:
                    valid_cands.append(m_obj)
                    weights.append(count)

            if valid_cands:
                chosen = random.choices(valid_cands, weights=weights, k=1)[0]
                # Güvenlik Kalkanı: Açılış havuzundan gelse dahi kazancı pat/3-tekrar yapamaz
                chosen = filter_safe_winning_move(board, chosen)
                print(f"🟢 [Tobi Light] Hamle: {chosen.uci()} (Kişisel Açılış Hafızası)")
                self.last_search_info = {
                    "engine": "Tobi Light",
                    "move": chosen.uci(),
                    "eval_str": "Açılış Hafızası",
                    "depth": 1,
                    "nodes": 1,
                    "elapsed": 0.01,
                }
                return chosen.uci()

        # 2. Aşama: Tobi Mid ile BİREBİR AYNI ARAMA MİMARİSİ (DeepSearchEngine)
        best_move, score, depth, elapsed, nodes = self.search_engine.search(
            board, max_depth=max_depth, time_limit=time_limit
        )

        if not best_move:
            best_move = legal_moves[0]

        # 3. Katman Güvenlik Kalkanı: Pat ve 3-Tekrar Güvencesi
        best_move = filter_safe_winning_move(board, best_move)

        eval_str = f"{score/100:+.2f}" if abs(score) < 90000 else f"M{abs(99999 - abs(score))}"
        print(f"🟢 [Tobi Light] Derinlik {depth} | Hamle: {best_move.uci()} | Skor: {eval_str} | {nodes:,} pozisyon ({elapsed:.2f}s)")

        self.last_search_info = {
            "engine": "Tobi Light",
            "move": best_move.uci(),
            "score": score,
            "eval_str": eval_str,
            "depth": depth,
            "elapsed": round(elapsed, 2),
            "nodes": nodes,
        }
        return best_move.uci()


# ==============================================================================
# 4. TOBI MID ENGINE (1800-2200 Elo Verisi - Aynı Derin Arama Mimarisi)
# ==============================================================================

class TobiMidEngine:
    def __init__(self, device="cuda" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"):
        self.device = device
        self.model = None
        self.search_engine = DeepSearchEngine(model=None, device=self.device)
        self.last_search_info = None
        self._load()

    def _load(self):
        if not TOBI_MID_MODEL_PATH.exists():
            parts = sorted(CHECKPOINTS_DIR.glob("best_model.pt.part*"))
            if parts:
                try:
                    with open(TOBI_MID_MODEL_PATH, "wb") as outfile:
                        for p in parts:
                            with open(p, "rb") as infile:
                                outfile.write(infile.read())
                    print("🟡 [Tobi Mid] Model parçaları birleştirildi.")
                except Exception as e:
                    print(f"❌ [Tobi Mid] Parçalar birleştirilirken hata: {e}")

        if HAS_TORCH and TOBI_MID_MODEL_PATH.exists():
            try:
                ckpt = torch.load(TOBI_MID_MODEL_PATH, map_location=self.device, weights_only=False)
                blocks = ckpt.get("num_blocks", 8)
                filters = ckpt.get("num_filters", 192)
                model = ChessResNet(num_blocks=blocks, num_filters=filters)
                model.load_state_dict(ckpt["model_state_dict"])
                model.to(self.device)
                model.eval()
                self.model = model
                self.search_engine.model = self.model
                self.search_engine.device = self.device
                epoch = ckpt.get("epoch", 1)
                print(f"🟡 [Tobi Mid] Derin Model yüklendi! (Epoch {epoch}, {self.device.upper()})")
            except Exception as e:
                print(f"❌ [Tobi Mid] Model yüklenirken hata: {e}")

    def get_move(self, board: chess.Board, max_depth: int = 5, time_limit: float = 8.0) -> str:
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return ""

        if len(legal_moves) == 1:
            return legal_moves[0].uci()

        best_move, score, depth, elapsed, nodes = self.search_engine.search(
            board, max_depth=max_depth, time_limit=time_limit
        )

        if not best_move:
            best_move = legal_moves[0]

        # 3. Katman Güvenlik Kalkanı: Pat ve 3-Tekrar Güvencesi
        best_move = filter_safe_winning_move(board, best_move)

        eval_str = f"{score/100:+.2f}" if abs(score) < 90000 else f"M{abs(99999 - abs(score))}"
        print(f"🟡 [Tobi Mid] Derinlik {depth} | Hamle: {best_move.uci()} | Skor: {eval_str} | {nodes:,} pozisyon ({elapsed:.2f}s)")

        self.last_search_info = {
            "engine": "Tobi Mid",
            "move": best_move.uci(),
            "score": score,
            "eval_str": eval_str,
            "depth": depth,
            "elapsed": round(elapsed, 2),
            "nodes": nodes,
        }
        return best_move.uci()


# ==============================================================================
# 4. MERKEZİ MOTOR YÖNETİCİSİ (TobiManager)
# ==============================================================================

class CustomChessAI:
    def __init__(self):
        self.device = "cuda" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"
        self.light_engine = TobiLightEngine(device=self.device)
        self.mid_engine = TobiMidEngine(device=self.device)
        # Varsayılan mod: Tobi Light
        self.mode = "tobi_light"

    def set_mode(self, mode: str):
        if mode in ("tobi_light", "light"):
            self.mode = "tobi_light"
            print("Aktif Motor: Tobi Light")
        elif mode in ("tobi_mid", "mid", "custom"):
            self.mode = "tobi_mid"
            print("Aktif Motor: Tobi Mid")
        return self.active_engine_name

    @property
    def active_engine_name(self) -> str:
        if self.mode == "tobi_light":
            return "Tobi Light"
        return "Tobi Mid"

    @property
    def last_search_info(self):
        if self.mode == "tobi_light":
            return self.light_engine.last_search_info
        return self.mid_engine.last_search_info

    def get_move(self, board: chess.Board) -> str:
        if board.is_game_over():
            return ""

        if self.mode == "tobi_light":
            return self.light_engine.get_move(board, max_depth=3, time_limit=3.0)
        else:
            return self.mid_engine.get_move(board, max_depth=5, time_limit=8.0)


# Singleton
custom_ai_instance = CustomChessAI()


def custom_engine_move(board: chess.Board) -> str:
    return custom_ai_instance.get_move(board)
