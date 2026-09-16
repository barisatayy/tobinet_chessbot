"""
game_storage.py
---------------
Oyun kayıt katmanı (No-op).
Kalıcı veritabanı tutulmaz.
"""


class GameStorage:
    def __init__(self, *args, **kwargs):
        pass

    def create_game(self, *args, **kwargs):
        pass

    def finish_game(self, *args, **kwargs):
        pass

    def update_moves(self, *args, **kwargs):
        pass

    def get_all_games(self, limit=50):
        return []

    def get_game(self, game_id):
        return None
