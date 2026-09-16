"""
lichess_client.py
-----------------
Lichess Bot API ile iletişim kurar.
Resmi API: https://lichess.org/api
"""

import httpx
import json
from typing import Generator, Optional


LICHESS_BASE = "https://lichess.org"


class LichessClient:
    """Lichess REST + Streaming API istemcisi."""

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Hesap
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Bot hesap bilgilerini döner."""
        r = httpx.get(f"{LICHESS_BASE}/api/account", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def check_token(self) -> dict:
        """Token yetkilerini (scopes) ve hesap ID'sini sorgular."""
        try:
            r = httpx.post(
                f"{LICHESS_BASE}/api/token/test",
                headers={"Content-Type": "text/plain"},
                content=self.token,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get(self.token) or {}
        except Exception:
            pass
        return {}

    def upgrade_to_bot(self) -> bool:
        """Hesabı bot hesabına yükseltir (tek seferlik, geri alınamaz!)."""
        r = httpx.post(
            f"{LICHESS_BASE}/api/bot/account/upgrade",
            headers=self.headers,
            timeout=10,
        )
        return r.status_code == 200

    # ------------------------------------------------------------------
    # Oyun yönetimi
    # ------------------------------------------------------------------

    def accept_challenge(self, challenge_id: str) -> bool:
        r = httpx.post(
            f"{LICHESS_BASE}/api/challenge/{challenge_id}/accept",
            headers=self.headers,
            timeout=10,
        )
        return r.status_code == 200

    def decline_challenge(self, challenge_id: str) -> bool:
        r = httpx.post(
            f"{LICHESS_BASE}/api/challenge/{challenge_id}/decline",
            headers=self.headers,
            timeout=10,
        )
        return r.status_code == 200

    def cancel_challenge(self, challenge_id: str) -> bool:
        """Gönderilen bir meydan okumayı iptal eder."""
        r = httpx.post(
            f"{LICHESS_BASE}/api/challenge/{challenge_id}/cancel",
            headers=self.headers,
            timeout=10,
        )
        return r.status_code == 200

    def get_online_bots(self, count: int = 50) -> list:
        """Online botlardan belirli sayıda çeker."""
        bots = []
        try:
            with httpx.stream("GET", f"{LICHESS_BASE}/api/bot/online", headers={"Accept": "application/x-ndjson"}, timeout=10) as r:
                for line in r.iter_lines():
                    line = line.strip()
                    if line:
                        try:
                            bots.append(json.loads(line))
                            if len(bots) >= count:
                                break
                        except:
                            pass
        except Exception:
            pass
        return bots

    def get_my_ongoing_games(self) -> list:
        """Devam eden oyunlarımızın listesini döner."""
        try:
            r = httpx.get(f"{LICHESS_BASE}/api/account/playing", headers=self.headers, timeout=10)
            if r.status_code == 200:
                return r.json().get("nowPlaying", [])
        except Exception:
            pass
        return []

    def get_users_status(self, user_ids: list[str]) -> list[dict]:
        """Kullanıcıların online ve playing durumunu sorgular."""
        if not user_ids:
            return []
        try:
            ids_str = ",".join(user_ids[:50])
            r = httpx.get(f"{LICHESS_BASE}/api/users/status?ids={ids_str}", timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def create_challenge(
        self,
        username: str = "",
        clock_limit: int = 600,
        clock_increment: int = 0,
        color: str = "random",
        rated: bool = False,
    ) -> Optional[dict]:
        """
        Rastgele rakibe meydan okur (username boşsa AI'ya).
        clock_limit: saniye cinsinden (600 = 10 dakika)
        """
        if username:
            url = f"{LICHESS_BASE}/api/challenge/{username}"
        else:
            url = f"{LICHESS_BASE}/api/challenge/open"

        data = {
            "clock.limit": clock_limit,
            "clock.increment": clock_increment,
            "color": color,
            "rated": str(rated).lower(),
        }
        self.last_challenge_error = ""
        try:
            r = httpx.post(url, headers=self.headers, data=data, timeout=10)
            if r.status_code in (200, 201):
                return r.json()
            err_msg = r.text
            try:
                err_json = r.json()
                if "error" in err_json:
                    err_msg = err_json["error"]
            except Exception:
                pass
            self.last_challenge_error = f"{r.status_code} - {err_msg}"
            print(f"⚠️ [Lichess API {r.status_code}]: {err_msg}")
        except Exception as e:
            self.last_challenge_error = str(e)
            print(f"⚠️ [Lichess API Bağlantı Hatası]: {e}")
        return None

    def challenge_ai(
        self,
        level: int = 1,
        clock_limit: int = 600,
        clock_increment: int = 0,
        color: str = "random",
    ) -> Optional[dict]:
        """Lichess Stockfish AI'sına meydan okur (level 1-8)."""
        data = {
            "level": level,
            "clock.limit": clock_limit,
            "clock.increment": clock_increment,
            "color": color,
        }
        r = httpx.post(
            f"{LICHESS_BASE}/api/challenge/ai",
            headers=self.headers,
            data=data,
            timeout=10,
        )
        if r.status_code in (200, 201):
            return r.json()
        return None

    def make_move(self, game_id: str, uci_move: str) -> bool:
        """Hamle gönderir. uci_move örn: 'e2e4'"""
        r = httpx.post(
            f"{LICHESS_BASE}/api/bot/game/{game_id}/move/{uci_move}",
            headers=self.headers,
            timeout=10,
        )
        return r.status_code == 200

    def resign(self, game_id: str) -> bool:
        r = httpx.post(
            f"{LICHESS_BASE}/api/bot/game/{game_id}/resign",
            headers=self.headers,
            timeout=10,
        )
        return r.status_code == 200

    def send_chat(self, game_id: str, text: str, room: str = "player") -> bool:
        r = httpx.post(
            f"{LICHESS_BASE}/api/bot/game/{game_id}/chat",
            headers=self.headers,
            data={"room": room, "text": text},
            timeout=10,
        )
        return r.status_code == 200

    # ------------------------------------------------------------------
    # Event stream (SSE)
    # ------------------------------------------------------------------

    def stream_events(self) -> Generator[dict, None, None]:
        """
        Hesap event akışını dinler (challenge, gameStart vs.)
        Server-Sent Events (SSE) — sürekli açık bağlantı.
        """
        with httpx.stream(
            "GET",
            f"{LICHESS_BASE}/api/stream/event",
            headers=self.headers,
            timeout=None,
        ) as r:
            for line in r.iter_lines():
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
                else:
                    yield None

    def stream_game(self, game_id: str) -> Generator[dict, None, None]:
        """
        Oyun event akışını dinler (gameFull, gameState, chatLine vs.)
        """
        with httpx.stream(
            "GET",
            f"{LICHESS_BASE}/api/bot/game/stream/{game_id}",
            headers=self.headers,
            timeout=None,
        ) as r:
            for line in r.iter_lines():
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
                else:
                    yield None
