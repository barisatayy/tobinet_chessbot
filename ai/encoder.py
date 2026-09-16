"""
ai/encoder.py
-------------
Satranç tahtasını derin öğrenme modeline girdi olacak Tensörlere (18x8x8)
ve legal hamleleri modelin tahmin edeceği Policy indekslerine dönüştürür.
"""

import numpy as np
import chess

# Toplam hamle uzayı: 64x64 = 4096 (kare-kare) + 72 (özel terfiler: 8 dikey x 3 yön x 3 taş) = 4168
NUM_ACTIONS = 4168

# Taş tipleri sırası
PIECE_TYPES = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]


def board_to_tensor(board: chess.Board) -> np.ndarray:
    """
    chess.Board nesnesini (18, 8, 8) boyutunda float32 numpy tensörüne dönüştürür.
    Kanallar (Oyuncu Perspektifinde - Canonical Perspective):
      0-5:   Sırası gelen oyuncunun taşları (P, N, B, R, Q, K)
      6-11:  Rakip oyuncunun taşları (P, N, B, R, Q, K)
      12:    Bizim Şah Kanadı Rok Hakkı (tüm kareler 1 veya 0)
      13:    Bizim Vezir Kanadı Rok Hakkı
      14:    Rakip Şah Kanadı Rok Hakkı
      15:    Rakip Vezir Kanadı Rok Hakkı
      16:    Geçerken alma (En Passant) karesi varsa 1
      17:    Hamle sayısı normalizasyonu (hamle_sayısı / 100.0)
    """
    tensor = np.zeros((18, 8, 8), dtype=np.float32)
    us = board.turn
    them = not us

    # Eğer sıra siyahtaysa tahtayı dikeyde ters çeviriyoruz (Canonical view)
    # Böylece sinir ağı her zaman "aşağıdan yukarıya oynayan taraf" mantığıyla öğrenir
    flip = (us == chess.BLACK)

    def sq_to_coord(sq: int):
        r = chess.square_rank(sq)
        f = chess.square_file(sq)
        if flip:
            r = 7 - r
        return r, f

    # 1. Taş kanalları
    for i, ptype in enumerate(PIECE_TYPES):
        # Bizim taşlarımız (0-5)
        for sq in board.pieces(ptype, us):
            r, f = sq_to_coord(sq)
            tensor[i, r, f] = 1.0

        # Rakip taşları (6-11)
        for sq in board.pieces(ptype, them):
            r, f = sq_to_coord(sq)
            tensor[i + 6, r, f] = 1.0

    # 2. Rok Hakları (12-15)
    if board.has_kingside_castling_rights(us):
        tensor[12, :, :] = 1.0
    if board.has_queenside_castling_rights(us):
        tensor[13, :, :] = 1.0
    if board.has_kingside_castling_rights(them):
        tensor[14, :, :] = 1.0
    if board.has_queenside_castling_rights(them):
        tensor[15, :, :] = 1.0

    # 3. Geçerken alma (En Passant) (16)
    if board.ep_square is not None:
        r, f = sq_to_coord(board.ep_square)
        tensor[16, r, f] = 1.0

    # 4. Hamle sayısı (17)
    tensor[17, :, :] = min(board.fullmove_number / 100.0, 1.0)

    return tensor


def move_to_index(move: chess.Move, turn: chess.Color) -> int:
    """
    chess.Move nesnesini [0, 4159] aralığında tek bir integer indekse çevirir.
    turn: Hamleyi yapan oyuncunun rengi (siyahsa kareler flip edilir).
    """
    from_sq = move.from_square
    to_sq = move.to_square

    if turn == chess.BLACK:
        from_sq = chess.square_mirror(from_sq)
        to_sq = chess.square_mirror(to_sq)

    # Standart hamle veya Vezir terfisi: [0, 4095]
    if move.promotion is None or move.promotion == chess.QUEEN:
        return from_sq * 64 + to_sq

    # Özel terfiler (At, Kale, Fil): [4096, 4159]
    promo_map = {chess.KNIGHT: 0, chess.BISHOP: 1, chess.ROOK: 2}
    promo_code = promo_map.get(move.promotion, 0)
    from_file = chess.square_file(from_sq)
    to_file = chess.square_file(to_sq)
    diff = to_file - from_file + 1  # 0, 1, 2
    return 4096 + (from_file * 3 + diff) * 3 + promo_code


def index_to_move(index: int, board: chess.Board) -> chess.Move | None:
    """
    Modelin ürettiği policy indeksini tahta üzerindeki legal bir chess.Move nesnesine çevirir.
    """
    turn = board.turn

    if index < 4096:
        from_sq = index // 64
        to_sq = index % 64
        if turn == chess.BLACK:
            from_sq = chess.square_mirror(from_sq)
            to_sq = chess.square_mirror(to_sq)

        piece = board.piece_at(from_sq)
        if piece and piece.piece_type == chess.PAWN:
            to_rank = chess.square_rank(to_sq)
            if (turn == chess.WHITE and to_rank == 7) or (turn == chess.BLACK and to_rank == 0):
                m = chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
                if m in board.legal_moves:
                    return m

        m = chess.Move(from_sq, to_sq)
        if m in board.legal_moves:
            return m
    else:
        sub = index - 4096
        promo_code = sub % 3
        inv_promo = [chess.KNIGHT, chess.BISHOP, chess.ROOK][promo_code]
        slot = sub // 3
        from_file = slot // 3
        diff = (slot % 3) - 1
        to_file = from_file + diff

        from_rank = 6 if turn == chess.WHITE else 1
        to_rank = 7 if turn == chess.WHITE else 0

        from_sq = chess.square(from_file, from_rank)
        to_sq = chess.square(to_file, to_rank)

        m = chess.Move(from_sq, to_sq, promotion=inv_promo)
        if m in board.legal_moves:
            return m

    return None


def get_legal_move_mask(board: chess.Board) -> np.ndarray:
    """
    Tahtadaki sadece yasal olan hamlelerin indekslerini True, diğerlerini False yapan maske.
    """
    mask = np.zeros(NUM_ACTIONS, dtype=bool)
    turn = board.turn
    for move in board.legal_moves:
        idx = move_to_index(move, turn)
        if idx < NUM_ACTIONS:
            mask[idx] = True
    return mask
