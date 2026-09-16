"""
controller.py
-------------
Bot'un yaşam döngüsünü yönetir.
- Başlat / Durdur / Devam Et
- Lichess event stream'ini dinler
- Gelen oyunları GameHandler'a devreder
- SocketIO üzerinden UI'ya mesaj gönderir
"""

import threading
from bot.lichess_client import LichessClient
from bot.engine import Engine
from bot.game_handler import GameHandler


class BotController:
    """Thread-safe bot yöneticisi."""

    def __init__(self, socketio):
        self.socketio = socketio
        self.engine = Engine()

        self._client: LichessClient | None = None
        self._token: str = ""
        self._bot_username: str = ""

        self._thread: threading.Thread | None = None
        self._game_thread: threading.Thread | None = None
        self._seek_thread: threading.Thread | None = None
        self._current_handler = None

        self._kill_event = threading.Event()   # set → tamamen dur

        self.is_running = False
        self.is_paused = False
        self.current_game_id: str = ""

        # Oyun modu ayarları
        self.game_mode = "auto"           # auto / blitz / bullet / rapid
        self.challenge_ai_level = 1       # 1-8 (Lichess AI)
        self.vs_mode = "bots"             # 'bots' / 'ai' / 'seek'
        self.min_elo = 800
        self.max_elo = 2500

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        token: str,
        game_mode: str = "auto",
        vs_mode: str = "bots",
        min_elo: int = 800,
        max_elo: int = 2500,
    ):
        if self.is_running:
            if self._current_handler and self.current_game_id:
                self.emit("sync_live_game", self._current_handler.live_state)
            return
        self._token = token
        self.game_mode = game_mode
        self.vs_mode = vs_mode
        self.min_elo = min_elo
        self.max_elo = max_elo
        self._client = LichessClient(token)
        self._kill_event.clear()
        self.is_running = True
        self.is_paused = False

        self._thread = threading.Thread(
            target=self._main_loop, daemon=True, name="BotMainLoop"
        )
        self._thread.start()
        self.log("🚀 Bot başlatıldı.")
        self.emit("status", {
            "state": "running",
            "game_mode": self.game_mode,
            "min_elo": self.min_elo,
            "max_elo": self.max_elo,
            "engine": self.engine.info,
        })

    def pause(self):
        if not self.is_running or self.is_paused:
            return
        self.is_paused = True
        self.log("⏸  Bot duraklatıldı.")
        self.emit("status", {"state": "paused"})

    def resume(self):
        if not self.is_running or not self.is_paused:
            return
        self.is_paused = False
        self.log("▶  Bot devam ediyor.")
        self.emit("status", {"state": "running"})

    def stop(self):
        self._kill_event.set()
        self.is_running = False
        self.is_paused = False
        self.current_game_id = ""
        self._current_handler = None
        self.log("■  Bot durduruldu.")
        self.emit("status", {"state": "stopped"})

    # ------------------------------------------------------------------
    # Ana döngü
    # ------------------------------------------------------------------

    def _main_loop(self):
        try:
            # Hesabı doğrula
            account = self._client.get_account()
            self._bot_username = account.get("username", "?")
            title = account.get("title", "")

            if title != "BOT":
                self.log("⚠️  Bu hesap henüz Bot hesabı değil!")
                self.log("💡 Lichess'te hesabı bot'a yükseltmek için:")
                self.log("   lichess.org/api → 'Upgrade to Bot account'")
                self.emit("status", {"state": "error", "msg": "Bot hesabı değil"})
                self.is_running = False
                return

            self.log(f"✅ Giriş başarılı: {self._bot_username}")
            self.emit("status", {"state": "running", "username": self._bot_username})

            token_info = self._client.check_token()
            scopes = token_info.get("scopes", "")
            if scopes:
                self.log(f"🔑 API Yetkileri: {scopes}")
                if "challenge:write" not in scopes:
                    self.log("⚠️ UYARI: Token'da 'challenge:write' yetkisi eksik! Bot diğer botlara meydan okuyamaz.")
                    self.log("👉 Lichess'ten 'Create, accept, decline challenges' yetkisiyle yeni token alabilirsiniz.")

            # 1. Devam eden aktif bir maç var mı hemen kontrol et
            ongoing = self._client.get_my_ongoing_games()
            if ongoing:
                first_game = ongoing[0]
                gid = first_game.get("gameId")
                color = first_game.get("color", "white")
                opp = first_game.get("opponent", {})
                opp_name = opp.get("username") or opp.get("name") or opp.get("id") or "Rakip"
                opp_elo = str(opp.get("rating", "?"))
                my_elo = str(first_game.get("rating", "?"))
                fen = first_game.get("fen", "")
                last_move = first_game.get("lastMove", "")
                self.current_game_id = gid
                self.log(f"🎮 Devam eden aktif maça hemen bağlanılıyor: {gid} ({color} vs {opp_name})")
                self._start_game_thread(
                    gid,
                    color,
                    initial_opp_name=opp_name,
                    initial_opp_elo=opp_elo,
                    initial_my_elo=my_elo,
                    initial_fen=fen,
                    initial_last_move=last_move,
                )
            else:
                def delayed_start():
                    import time
                    time.sleep(1.5)
                    if not self._kill_event.is_set() and not self.current_game_id:
                        self._start_new_game()
                threading.Thread(target=delayed_start, daemon=True).start()

            for event in self._client.stream_events():
                if self._kill_event.is_set():
                    break

                while self.is_paused and not self._kill_event.is_set():
                    import time
                    time.sleep(0.5)

                if self._kill_event.is_set():
                    break

                if not event:
                    continue

                etype = event.get("type")

                if etype == "challenge":
                    challenge = event.get("challenge", {})
                    cid = challenge.get("id", "")
                    challenger = challenge.get("challenger", {}).get("name", "?")
                    self.log(f"🎯 Meydan okuma: {challenger} → kabul ediliyor")
                    self._client.accept_challenge(cid)

                elif etype == "gameStart":
                    game = event.get("game", {})
                    game_id = game.get("gameId", "")
                    color = game.get("color", "white")
                    # Zaten bu oyun için thread açıldıysa atla
                    if self._game_thread and self._game_thread.is_alive():
                        self.log(f"📡 gameStart alındı: {game_id} (thread zaten çalışıyor)")
                    else:
                        self.current_game_id = game_id
                        self.log(f"🎮 Oyun başladı (SSE): {game_id} ({color})")
                        self._start_game_thread(game_id, color)

                elif etype == "gameFinish":
                    game = event.get("game", {})
                    game_id = game.get("gameId", "")
                    self.log(f"🏁 Oyun bitti: {game_id}")
                    self.current_game_id = ""
                    self._current_handler = None
                    if self._game_thread and self._game_thread.is_alive():
                        self._game_thread.join(timeout=2.0)
                    import time
                    time.sleep(2)
                    if not self._kill_event.is_set():
                        self._start_new_game()

        except Exception as e:
            self.log(f"❌ Ana döngü hatası: {e}")
            self.emit("status", {"state": "error", "msg": str(e)})
        finally:
            self.is_running = False
            self.log("🔚 Bot thread sona erdi.")

    def _start_new_game(self):
        """Yeni oyun başlatır ve game thread'ini direkt açar."""
        clock_map = {
            "bullet": (60, 0),
            "blitz": (180, 0),
            "rapid": (600, 0),
            "auto": (180, 0),
        }
        limit, inc = clock_map.get(self.game_mode, (180, 0))

        if self.vs_mode == "ai":
            self.log(f"🤖 Lichess AI'ya (level {self.challenge_ai_level}) meydan okunuyor...")
            result = self._client.challenge_ai(
                level=self.challenge_ai_level,
                clock_limit=limit,
                clock_increment=inc,
            )
            if result:
                game_id = result.get("id", "")
                color = result.get("color", "white")
                self.current_game_id = game_id
                self.log(f"🎮 AI oyunu başladı: {game_id} ({color})")
                self.emit("status", {
                    "state": "running",
                    "game_id": game_id,
                    "game_mode": self.game_mode,
                    "engine": self.engine.info,
                })
                self._start_game_thread(game_id, color)
            else:
                self.log("⚠️  AI meydan okuma başarısız.")
        elif self.vs_mode == "bots":
            mode_desc = f"{self.game_mode}" if self.game_mode != "auto" else "tüm tempolar (Blitz/Bullet/Rapid)"
            self.log(f"🤖 Bot havuzundan uygun bot aranıyor (Elo: {self.min_elo}-{self.max_elo}, Tempo: {mode_desc})...")
            if self._seek_thread and self._seek_thread.is_alive():
                return
            self._seek_thread = threading.Thread(target=self._seek_bots_loop, daemon=True, name="SeekBots")
            self._seek_thread.start()
        else:
            self.log(f"🔍 İnsan rakip aranıyor ({self.game_mode})...")
            # Bot hesapları normal eşleştirmeye giremez, "Açık Meydan Okuma" (Open Challenge) oluşturulur
            result = self._client.create_challenge(
                clock_limit=limit,
                clock_increment=inc,
                rated=False,
            )
            if result:
                url = result.get("challenge", {}).get("url", "")
                self.log(f"🔗 İnsanlar için maç davet linki oluşturuldu:")
                self.log(f"🔗 {url}")
                self.log("⏳ Rakibin maça katılması bekleniyor...")
                self.emit("status", {
                    "state": "running",
                    "game_id": "bekleniyor...",
                    "game_mode": self.game_mode,
                    "engine": self.engine.info,
                })
            else:
                err_detail = getattr(self._client, "last_challenge_error", "")
                detail_str = f" ({err_detail})" if err_detail else ""
                self.log(f"⚠️ Açık meydan okuma oluşturulamadı{detail_str}.")

    def _seek_bots_loop(self):
        """Kullanıcının belirlediği Elo aralığındaki botları bulup rated meydan okuyan arka plan döngüsü."""
        import random
        import time

        try:
            my_account = self._client.get_account()
            my_username = my_account.get("username", "")
        except Exception:
            my_username = ""

        FAST_PRIORITY_BOTS = [
            "maia1", "maia5", "maia9",
            "sargon-1ply", "sargon-2ply", "sargon-3ply",
            "Boris-Trapsky", "simpleEval", "turkjs",
            "bernstein-2ply", "bernstein-4ply",
            "turochamp-1ply", "turochamp-2ply",
            "uSunfish-l0", "uSunfish-l1",
            "dala-700", "dala-900", "dala-1100", "dala-1300",
            "Demolito_L1", "Demolito_L2", "Demolito_L3",
            "GarboBot", "pawnrobot", "Elmichess",
            "Lynx_BOT", "CosetteBot", "Jibbby", "uSunfish"
        ]

        attempt_count = 0

        while self.is_running and self.vs_mode == "bots" and not self.current_game_id:
            while self.is_paused and not self._kill_event.is_set():
                time.sleep(0.5)
            if self._kill_event.is_set():
                break
            try:
                # 1. Devam eden mevcut bir maçımız var mı kontrol et
                ongoing = self._client.get_my_ongoing_games()
                if ongoing:
                    first_game = ongoing[0]
                    gid = first_game.get("gameId")
                    color = first_game.get("color", "white")
                    opp = first_game.get("opponent", {})
                    opp_name = opp.get("username") or opp.get("name") or opp.get("id") or "Rakip"
                    opp_elo = str(opp.get("rating", "?"))
                    my_elo = str(first_game.get("rating", "?"))
                    fen = first_game.get("fen", "")
                    last_move = first_game.get("lastMove", "")
                    self.current_game_id = gid
                    self.log(f"🎮 Mevcut oyuna bağlanılıyor: {gid} ({color} vs {opp_name})")
                    self._start_game_thread(
                        gid,
                        color,
                        initial_opp_name=opp_name,
                        initial_opp_elo=opp_elo,
                        initial_my_elo=my_elo,
                        initial_fen=fen,
                        initial_last_move=last_move,
                    )
                    break

                # 2. Online botları çek
                bots = self._client.get_online_bots(count=200)
                if not bots:
                    self.log("⚠️ Online bot bulunamadı, 3 sn sonra tekrar deneniyor...")
                    time.sleep(3)
                    continue

                # 3. Elo aralığına ve tempo formatına göre bot adaylarını çıkar
                valid_candidates = []
                modes_to_test = ["blitz", "bullet", "rapid"] if self.game_mode == "auto" else [self.game_mode]

                for b in bots:
                    uname = b.get("username", "")
                    if not uname or uname.lower() == my_username.lower():
                        continue

                    perfs = b.get("perfs", {})
                    for fmt in modes_to_test:
                        perf = perfs.get(fmt, {})
                        games_count = perf.get("games", 0)
                        if games_count < 3:
                            continue

                        bot_rating = perf.get("rating", 1500)
                        if not (self.min_elo <= bot_rating <= self.max_elo):
                            continue

                        # Zaman kontrolleri (Botların en çok kabul ettiği standartlar)
                        if fmt == "blitz":
                            limit, inc = 180, 0
                        elif fmt == "bullet":
                            limit, inc = 60, 0
                        else:  # rapid
                            limit, inc = 600, 0

                        is_priority = uname.lower() in [p.lower() for p in FAST_PRIORITY_BOTS]
                        is_blitz = (fmt == "blitz")

                        score = 0
                        if is_priority:
                            score += 150
                        if is_blitz:
                            score += 60  # Blitz botlar tarafından çok daha hızlı kabul edilir
                        if bot_rating < 2700:
                            score += 40
                        score += min(50, games_count // 50)

                        valid_candidates.append({
                            "username": uname,
                            "rating": bot_rating,
                            "format": fmt,
                            "clock_limit": limit,
                            "clock_increment": inc,
                            "games": games_count,
                            "score": score,
                        })

                if not valid_candidates:
                    self.log(f"⚠️ {self.min_elo}-{self.max_elo} Elo aralığında bot bulunamadı, 4 sn sonra taranacak...")
                    time.sleep(4)
                    continue

                # Puana göre sırala (yüksek öncelikli botlar ve popüler tempolar başa)
                random.shuffle(valid_candidates)
                valid_candidates.sort(key=lambda x: x["score"], reverse=True)

                # İlk 25 adayın canlı durumunu (meşgul mü) sorgula
                top_pool = valid_candidates[:25]
                unames = [c["username"] for c in top_pool]
                statuses = self._client.get_users_status(unames)
                status_map = {s.get("id", "").lower(): s for s in statuses}

                idle_candidates = []
                for c in top_pool:
                    s = status_map.get(c["username"].lower(), {})
                    if not s.get("playing", False):
                        idle_candidates.append(c)

                if not idle_candidates:
                    self.log("⏳ Aday botlar şu anda başka maçta, 3 sn bekleniyor...")
                    time.sleep(3)
                    continue

                high_prio = [c for c in idle_candidates if c["score"] >= 150]
                if high_prio:
                    chosen = random.choice(high_prio[:3])
                else:
                    chosen = random.choice(idle_candidates[:5])

                target_username = chosen["username"]
                bot_elo = chosen["rating"]
                target_fmt = chosen["format"]
                target_limit = chosen["clock_limit"]
                target_inc = chosen["clock_increment"]

                attempt_count += 1
                fmt_display = f"{target_fmt.upper()} ({target_limit // 60}+{target_inc})"
                self.log(f"⚔️ #{attempt_count}: {target_username} (Elo: {bot_elo} - {fmt_display}) botuna puanlı maç teklif ediliyor...")

                result = self._client.create_challenge(
                    username=target_username,
                    clock_limit=target_limit,
                    clock_increment=target_inc,
                    rated=True,
                )

                if result:
                    cid = result.get("challenge", {}).get("id")
                    self.log(f"⏳ {target_username} cevabı bekleniyor (8 sn)...")

                    for _ in range(8):
                        if self.current_game_id or not self.is_running:
                            break
                        time.sleep(1)

                    if self.current_game_id:
                        self.log(f"✅ {target_username} ile maç başladı!")
                        break

                    # Yanıt verilmediyse meydan okumayı iptal et ve sıradakine geç
                    if cid and self.is_running and not self.current_game_id:
                        self._client.cancel_challenge(cid)
                        self.log(f"⚠️ {target_username} yanıt vermedi, hemen sıradaki deneniyor...")
                        time.sleep(1)
                else:
                    err_detail = getattr(self._client, "last_challenge_error", "")
                    detail_str = f" ({err_detail})" if err_detail else ""
                    self.log(f"⚠️ {target_username} meydan okuması oluşturulamadı{detail_str}, sıradakine geçiliyor...")
                    time.sleep(1)

            except Exception as e:
                self.log(f"❌ Bot arama hatası: {e}")
                time.sleep(3)

    def _start_game_thread(self, game_id: str, color: str, **kwargs):
        """Oyun işleyicisini ayrı thread'de başlatır."""
        if self._game_thread and self._game_thread.is_alive():
            self._game_thread.join(timeout=2.0)
            if self._game_thread.is_alive():
                return

        self.current_game_id = game_id

        handler = GameHandler(
            client=self._client,
            engine=self.engine,
            game_id=game_id,
            bot_color=color,
            emit_fn=self.emit,
            log_fn=self.log,
            should_stop_fn=self._kill_event.is_set,
            game_mode=self.game_mode,
            **kwargs,
        )
        self._current_handler = handler

        self.emit("status", {
            "state": "running",
            "game_id": game_id,
            "game_mode": self.game_mode,
            "engine": self.engine.info,
            "live_game": handler.live_state,
        })
        self.emit("sync_live_game", handler.live_state)

        self._game_thread = threading.Thread(
            target=handler.run, daemon=True, name=f"Game-{game_id}"
        )
        self._game_thread.start()

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def log(self, msg: str):
        self.emit("log", {"message": msg})

    def emit(self, event: str, data: dict = None):
        self.socketio.emit(event, data or {})

    @property
    def status(self) -> dict:
        data = {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "game_id": self.current_game_id,
            "engine": self.engine.info,
            "game_mode": self.game_mode,
            "username": getattr(self, "_bot_username", ""),
        }
        if self._current_handler and self.current_game_id and self.is_running:
            try:
                data["live_game"] = self._current_handler.live_state
            except Exception:
                pass
        return data
