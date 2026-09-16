"""
controller.py
-------------
TobiNet Satranç AI kontrolcüsü ve log yöneticisi.
"""

from datetime import datetime
from bot.engine import Engine


class BotController:
    """Yapay zeka motoru ve durum yöneticisi."""

    def __init__(self, socketio=None):
        self.socketio = socketio
        self.engine = Engine()

    def log(self, message: str):
        """Konsola ve bağlı arayüze log iletir."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        if self.socketio:
            try:
                self.socketio.emit("log", {"message": message})
            except Exception:
                pass

    @property
    def status(self) -> dict:
        """Sunucu ve motor durumunu döner."""
        return {
            "state": "ready",
            "engine": self.engine.info,
        }
