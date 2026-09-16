/**
 * app.js — Chess Bot Web Arayüzü
 * Socket.IO + chessboard.js + chess.js entegrasyonu
 */

// ── Socket.IO ────────────────────────────────────────────────
const socket = io();

// ── Uygulama Durumu ──────────────────────────────────────────
const State = {
  isRunning: false,
  isPaused: false,
  gameId: "",
  color: "white",
  fen: "start",
  moveCount: 0,
  settings: {
    token: "__saved__",
    game_mode: "auto",
    vs_mode: "bots",
    ai_level: 1,
  },
};

// ── Kullanıcı Modülü (Onboarding & Profil) ───────────────────
const UserModule = {
  STORAGE_KEY: "tobinet_username",

  getUsername() {
    const saved = localStorage.getItem(this.STORAGE_KEY);
    if (saved && saved.trim()) {
      return saved.trim().substring(0, 16);
    }
    return "";
  },

  init() {
    const current = this.getUsername();
    if (!current) {
      this.openOnboardingModal();
    } else {
      this.updateUI(current);
    }
  },

  openOnboardingModal() {
    const backdrop = document.getElementById("username-backdrop");
    const modal = document.getElementById("username-modal");
    const closeBtn = document.getElementById("btn-close-username-modal");
    const title = document.getElementById("username-modal-title");
    const desc = document.getElementById("username-modal-desc");
    const input = document.getElementById("input-username");
    const err = document.getElementById("username-error-msg");

    if (title) title.textContent = "TobiNet Satranç";
    if (desc) desc.textContent = "Satranç maçlarında kullanılacak kullanıcı adınızı belirleyin:";
    if (closeBtn) closeBtn.style.display = "none";
    if (err) err.style.display = "none";
    if (input) {
      input.value = "";
      setTimeout(() => input.focus(), 150);
    }

    if (backdrop) {
      backdrop.style.display = "block";
      backdrop.classList.add("open");
    }
    if (modal) {
      modal.style.display = "flex";
      modal.classList.add("open");
    }
  },

  openEditModal() {
    const backdrop = document.getElementById("username-backdrop");
    const modal = document.getElementById("username-modal");
    const closeBtn = document.getElementById("btn-close-username-modal");
    const title = document.getElementById("username-modal-title");
    const desc = document.getElementById("username-modal-desc");
    const input = document.getElementById("input-username");
    const err = document.getElementById("username-error-msg");

    if (title) title.textContent = "Kullanıcı Adı Düzenle";
    if (desc) desc.textContent = "Yeni kullanıcı adınızı yazın:";
    if (closeBtn) closeBtn.style.display = "inline-block";
    if (err) err.style.display = "none";
    if (input) {
      input.value = this.getUsername() || "Oyuncu";
      setTimeout(() => {
        input.focus();
        input.select();
      }, 150);
    }

    if (backdrop) {
      backdrop.style.display = "block";
      backdrop.classList.add("open");
    }
    if (modal) {
      modal.style.display = "flex";
      modal.classList.add("open");
    }
  },

  closeModal() {
    const current = this.getUsername();
    if (!current) return;
    const backdrop = document.getElementById("username-backdrop");
    const modal = document.getElementById("username-modal");
    if (backdrop) {
      backdrop.style.display = "none";
      backdrop.classList.remove("open");
    }
    if (modal) {
      modal.style.display = "none";
      modal.classList.remove("open");
    }
  },

  saveUsername() {
    const input = document.getElementById("input-username");
    const err = document.getElementById("username-error-msg");
    const val = (input ? input.value : "").trim();

    if (!val) {
      if (err) {
        err.textContent = "Lütfen bir kullanıcı adı girin.";
        err.style.display = "block";
      }
      return;
    }

    const sanitized = val.substring(0, 16);
    localStorage.setItem(this.STORAGE_KEY, sanitized);
    this.updateUI(sanitized);
    this.closeModal();

    if (typeof PlayApp !== "undefined" && PlayApp.updatePlayerCards) {
      PlayApp.updatePlayerCards();
    }
  },

  updateUI(username) {
    const topbarEl = document.getElementById("topbar-username");
    if (topbarEl) topbarEl.textContent = username;
    const bottomName = document.getElementById("play-bottom-name");
    if (bottomName) bottomName.textContent = username;
  }
};

// ── Satranç Tahtası ──────────────────────────────────────────
let board = null;
let game  = new Chess();

function formatClock(ms) {
  if (ms === null || ms === undefined) return "—";
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${sec < 10 ? '0' : ''}${sec}`;
}

function renderCapturedPieces(chessInstance, colorTop, colorBottom, elTopId, elBottomId) {
  const pieceValues = { 'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9 };
  const pieceNames = { 'p': 'Piyon (1)', 'n': 'At (3)', 'b': 'Fil (3)', 'r': 'Kale (5)', 'q': 'Vezir (9)' };
  let whiteCaptured = [];
  let blackCaptured = [];
  let whiteMat = 0;
  let blackMat = 0;
  
  // Hangi taşlar yendi?
  chessInstance.history({ verbose: true }).forEach(m => {
    if (m.captured) {
      if (m.color === 'w') whiteCaptured.push(m.captured);
      else blackCaptured.push(m.captured);
    }
  });
  
  // Tahtadaki materyal puanını hesapla
  const fen = chessInstance.fen().split(' ')[0];
  for (let c of fen) {
    const p = c.toLowerCase();
    if (pieceValues[p]) {
      if (c === c.toUpperCase()) whiteMat += pieceValues[p];
      else blackMat += pieceValues[p];
    }
  }
  
  const whiteAdv = Math.max(0, whiteMat - blackMat);
  const blackAdv = Math.max(0, blackMat - whiteMat);
  
  // Değere göre sırala (Piyon -> Vezir)
  const sortPieces = (a, b) => pieceValues[a] - pieceValues[b];
  whiteCaptured.sort(sortPieces); 
  blackCaptured.sort(sortPieces); 
  
  const buildHTML = (capturedArr, isWhiteCapturing, adv) => {
    if (!capturedArr || capturedArr.length === 0) return '';
    let html = '';
    const colorCode = isWhiteCapturing ? 'b' : 'w'; // Beyaz, Siyah taşları yer
    capturedArr.forEach(p => {
      html += `<div class="captured-piece" title="${pieceNames[p] || p}" style="background-image: url(/img/chesspieces/wikipedia/${colorCode}${p.toUpperCase()}.png)"></div>`;
    });
    if (adv > 0) {
      html += `<span class="score-advantage">+${adv}</span>`;
    }
    return html;
  };
  
  const topIsWhite = colorTop === 'white';
  const topHTML = buildHTML(topIsWhite ? whiteCaptured : blackCaptured, topIsWhite, topIsWhite ? whiteAdv : blackAdv);
  const botHTML = buildHTML(!topIsWhite ? whiteCaptured : blackCaptured, !topIsWhite, !topIsWhite ? whiteAdv : blackAdv);
  
  const topEl = document.getElementById(elTopId);
  const botEl = document.getElementById(elBottomId);
  if (topEl) topEl.innerHTML = topHTML;
  if (botEl) botEl.innerHTML = botHTML;
}

function highlightKingCheck(chessInstance, boardSelector) {
  $(`${boardSelector} .square-55d63`).removeClass("king-check-pulse");
  if (!chessInstance || !chessInstance.in_check()) return;

  const color = chessInstance.turn();
  const b = chessInstance.board();
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const p = b[r][c];
      if (p && p.type === 'k' && p.color === color) {
        const sq = String.fromCharCode(97 + c) + (8 - r);
        const sqEl = $(`${boardSelector} [data-square="${sq}"]`);
        if (sqEl.length) {
          sqEl.removeClass("king-check-pulse");
          if (sqEl[0]) void sqEl[0].offsetWidth; // trigger reflow
          sqEl.addClass("king-check-pulse");
        }
        return;
      }
    }
  }
}

function initBoard() {
  board = Chessboard("board", {
    position: "start",
    pieceTheme: "/img/chesspieces/wikipedia/{piece}.png",
    draggable: false,
    showNotation: true,
  });
  $(window).resize(board.resize);
}

function updateBoard(fen, lastMove) {
  if (!board) return;

  game.load(fen);
  board.position(fen, true); // true = animate

  // Son hamleyi highlight et
  $(".square-55d63").removeClass("highlight-last-move");
  if (lastMove && lastMove.length >= 4) {
    const from = lastMove.slice(0, 2);
    const to   = lastMove.slice(2, 4);
    $(`[data-square="${from}"]`).addClass("highlight-last-move");
    $(`[data-square="${to}"]`).addClass("highlight-last-move");
  }

  // Şah çekildiyse şahı parlat
  highlightKingCheck(game, "#board");

  // Son hamle barı güncelle
  const lastMoveEl = document.getElementById("last-move-val");
  if (lastMove) lastMoveEl.textContent = lastMove;
  document.getElementById("val-moves").textContent = game.history().length;

  // Yenilen taşları güncelle
  const colorTop = State.color === "white" ? "black" : "white";
  const colorBot = State.color;
  renderCapturedPieces(game, colorTop, colorBot, "opponent-captured", "bot-captured");
}

// ── Log Paneli ───────────────────────────────────────────────
const Log = (() => {
  let count = 0;
  const body  = document.getElementById("log-body");
  const countEl = document.getElementById("log-count");

  const COLOR_MAP = {
    "[+]": "green", "başladı": "green",
    "[-]": "red",   "hata": "red", "error": "red",
    "[!]": "yellow", "şah": "yellow",
    "bağlandı": "blue", "sunucu": "blue",
  };

  function getColor(msg) {
    for (const [icon, cls] of Object.entries(COLOR_MAP)) {
      if (msg.includes(icon)) return cls;
    }
    return "";
  }

  function add(msg) {
    const now = new Date();
    const ts  = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}:${String(now.getSeconds()).padStart(2,"0")}`;

    const entry = document.createElement("div");
    entry.className = `log-entry ${getColor(msg)}`;
    entry.innerHTML = `
      <span class="log-time">${ts}</span>
      <span class="log-msg">${escHtml(msg)}</span>
    `;
    body.appendChild(entry);
    body.scrollTop = body.scrollHeight;

    count++;
    countEl.textContent = `${count} kayıt`;
  }

  function clear() {
    body.innerHTML = "";
    count = 0;
    countEl.textContent = "0 kayıt";
  }

  return { add, clear };
})();

function escHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Durum Güncelleyici ───────────────────────────────────────
function setStatus(state, text) {
  const dot  = document.getElementById("status-dot");
  const label = document.getElementById("status-text");
  dot.className   = `status-dot ${state}`;
  label.textContent = text;
  label.style.color = {
    running: "#22c55e",
    paused:  "#f59e0b",
    error:   "#ef4444",
    stopped: "#94a3b8",
  }[state] || "#94a3b8";
}

function updateButtons() {
  const s = State;
  const btnStart = document.getElementById("btn-start");
  const btnPause = document.getElementById("btn-pause");
  const btnResume = document.getElementById("btn-resume");
  const btnStop = document.getElementById("btn-stop");
  if (btnStart) btnStart.disabled = s.isRunning;
  if (btnPause) btnPause.disabled = !s.isRunning || s.isPaused;
  if (btnResume) btnResume.disabled = !s.isPaused;
  if (btnStop) btnStop.disabled = !s.isRunning;

  const mmStart = document.getElementById("btn-mm-start");
  const mmStop  = document.getElementById("btn-mm-stop");
  if (mmStart && mmStop) {
    if (s.isRunning) {
      mmStart.style.display = "none";
      mmStop.style.display = "inline-flex";
    } else {
      mmStart.style.display = "inline-flex";
      mmStop.style.display = "none";
    }
  }
}

// ── Socket.IO Olayları ───────────────────────────────────────
socket.on("connect",    () => Log.add("Sunucuya bağlanıldı."));
socket.on("disconnect", () => Log.add("Sunucu bağlantısı kesildi."));

socket.on("log", (data) => {
  Log.add(data.message);
});

function syncLiveGame(lg) {
  if (!lg || !lg.game_id) return;

  State.gameId = lg.game_id;
  State.color  = lg.color || "white";
  State.isRunning = true;
  State.isPaused  = false;
  setStatus("running", "Çalışıyor");
  updateButtons();

  // Overlay'i gizle
  document.getElementById("board-overlay").classList.add("hidden");
  document.getElementById("val-game").textContent  = lg.game_id.slice(0, 8) + "...";
  document.getElementById("val-color").textContent = lg.color === "white" ? "Beyaz" : "Siyah";
  document.getElementById("bot-tag").style.order   = lg.color === "white" ? "2" : "0";

  // Oyuncu isimleri & Elo
  if (lg.opponent_name) {
    document.getElementById("opponent-name").textContent = lg.opponent_name;
  }
  if (lg.opponent_rating && lg.opponent_rating !== "?") {
    document.getElementById("opponent-elo").textContent = `(${lg.opponent_rating})`;
  } else {
    document.getElementById("opponent-elo").textContent = "";
  }
  if (lg.bot_rating && lg.bot_rating !== "?") {
    document.getElementById("bot-elo").textContent = `(${lg.bot_rating})`;
  } else {
    document.getElementById("bot-elo").textContent = "";
  }

  // Tahta pozisyonu ve hamleleri yükle
  if (board) {
    board.orientation(lg.color);
    if (lg.fen) {
      updateBoard(lg.fen, lg.last_move);
    }
  }
}

socket.on("status", (data) => {
  State.isRunning = data.is_running ?? State.isRunning;
  State.isPaused  = data.is_paused  ?? State.isPaused;
  State.gameId    = data.game_id    ?? State.gameId;

  if (data.state === "running") {
    State.isRunning = true; State.isPaused = false;
    setStatus("running", "Çalışıyor");
  } else if (data.state === "paused") {
    State.isPaused = true;
    setStatus("paused", "Duraklatıldı");
  } else if (data.state === "stopped" || data.state === "error") {
    State.isRunning = false; State.isPaused = false;
    setStatus(data.state === "error" ? "error" : "stopped",
              data.state === "error" ? `Hata: ${data.msg}` : "Durduruldu");
  }

  if (data.username) {
    document.getElementById("val-username").textContent = data.username;
    document.getElementById("bot-name").textContent = data.username;
  }
  if (data.engine)    document.getElementById("val-engine").textContent = data.engine.name;
  if (data.game_mode) document.getElementById("val-mode").textContent   = data.game_mode;
  if (data.game_id)   document.getElementById("val-game").textContent   = data.game_id.slice(0, 8) + "...";

  if (data.live_game) {
    syncLiveGame(data.live_game);
  }

  updateButtons();
});

socket.on("sync_live_game", (data) => {
  syncLiveGame(data);
});

socket.on("game_start", (data) => {
  State.gameId = data.game_id;
  State.color  = data.color;
  State.isRunning = true;
  State.isPaused = false;
  setStatus("running", "Çalışıyor");
  updateButtons();

  document.getElementById("board-overlay").classList.add("hidden");
  document.getElementById("val-game").textContent  = data.game_id.slice(0, 8) + "...";
  document.getElementById("val-color").textContent = data.color === "white" ? "⬜ Beyaz" : "⬛ Siyah";
  document.getElementById("bot-tag").style.order   = data.color === "white" ? "2" : "0";

  // Tahtayı renke göre çevir
  if (board) board.orientation(data.color);
  game = new Chess();
  board.start(false);

  Log.add(`Oyun başladı! Renk: ${data.color}`);
});

socket.on("players_info", (data) => {
  document.getElementById("opponent-name").textContent = data.opponent_name || "Rakip";
  
  if (data.opponent_rating && data.opponent_rating !== "?") {
    document.getElementById("opponent-elo").textContent = `(${data.opponent_rating})`;
  } else {
    document.getElementById("opponent-elo").textContent = "";
  }

  if (data.bot_rating && data.bot_rating !== "?") {
    document.getElementById("bot-elo").textContent = `(${data.bot_rating})`;
  } else {
    document.getElementById("bot-elo").textContent = "";
  }
});

socket.on("board_update", (data) => {
  updateBoard(data.fen, data.last_move);
  if (data.wtime !== undefined && data.btime !== undefined && data.wtime !== null && data.btime !== null) {
    const isBotWhite = State.color === "white";
    const botTime = isBotWhite ? data.wtime : data.btime;
    const oppTime = isBotWhite ? data.btime : data.wtime;

    const oppClockEl = document.getElementById("opponent-clock");
    const botClockEl = document.getElementById("bot-clock");
    if (oppClockEl) {
      oppClockEl.textContent = formatClock(oppTime);
      oppClockEl.classList.toggle("low-time", oppTime < 30000);
      const isOppTurn = (isBotWhite && game.turn() === "b") || (!isBotWhite && game.turn() === "w");
      oppClockEl.classList.toggle("active", isOppTurn);
    }
    if (botClockEl) {
      botClockEl.textContent = formatClock(botTime);
      botClockEl.classList.toggle("low-time", botTime < 30000);
      const isBotTurn = (isBotWhite && game.turn() === "w") || (!isBotWhite && game.turn() === "b");
      botClockEl.classList.toggle("active", isBotTurn);
    }
  }
});

socket.on("game_over", (data) => {
  document.getElementById("board-overlay").classList.remove("hidden");
  document.querySelector(".board-overlay-text").textContent = "Oyun Bitti";
  const status = data.status || "";
  const winner = data.winner || "";
  document.querySelector(".board-overlay-sub").textContent =
    winner ? `Kazanan: ${winner}` : status;

  Log.add(`Oyun bitti. ${winner ? "Kazanan: " + winner : status}`);

  setTimeout(() => {
    document.querySelector(".board-overlay-text").textContent = "Yeni oyun bekleniyor...";
    document.querySelector(".board-overlay-sub").textContent = "";
  }, 2000);
});

// ── Matchmaker & App Kontrolleri ─────────────────────────────
const Matchmaker = {
  setVs(mode) {
    State.settings.vs_mode = mode;
    document.getElementById("mm-opt-bot")?.classList.toggle("active", mode === "bots");
    document.getElementById("mm-opt-human")?.classList.toggle("active", mode === "seek");
    const eloField = document.getElementById("mm-elo-field");
    const noteEl = document.getElementById("mm-info-note");
    if (eloField) eloField.style.display = (mode === "bots") ? "block" : "none";
    if (noteEl) {
      noteEl.innerHTML = (mode === "bots") 
        ? "Puanlı (rated) maçlar Lichess kuralları gereği botlar arasında oynanır."
        : "Lichess kuralları gereği bot hesapları insanlarla puanlı maç yapamaz, davet linki oluşturulur.";
    }
    const btnText = document.getElementById("btn-mm-start");
    if (btnText) {
      btnText.innerHTML = (mode === "bots") 
        ? "PUAN MAÇI BAŞLAT" 
        : "DAVET LİNKİ OLUŞTUR";
    }
  },

  setRange(min, max, btn) {
    const minInput = document.getElementById("mm-min-elo");
    const maxInput = document.getElementById("mm-max-elo");
    if (minInput) minInput.value = min;
    if (maxInput) maxInput.value = max;
    document.querySelectorAll(".mm-chip").forEach(c => c.classList.remove("active"));
    if (btn) btn.classList.add("active");
    this.updateSubText(min, max);
  },

  onCustomElo() {
    document.querySelectorAll(".mm-chip").forEach(c => c.classList.remove("active"));
    const min = parseInt(document.getElementById("mm-min-elo")?.value) || 800;
    const max = parseInt(document.getElementById("mm-max-elo")?.value) || 2500;
    this.updateSubText(min, max);
  },

  updateSubText(min, max) {
    const sub = document.getElementById("mm-elo-sub");
    if (sub) sub.textContent = `${min} - ${max} Elo`;
  },

  start() {
    App.start();
  }
};

const App = {
  start() {
    const overlay = document.getElementById("board-overlay");
    if (overlay) overlay.classList.remove("hidden");
    const overlayText = document.querySelector(".board-overlay-text");
    const overlaySub = document.querySelector(".board-overlay-sub");
    if (overlayText) overlayText.textContent = "Bot rakip aranıyor...";
    if (overlaySub) overlaySub.textContent = "Lütfen bekleyin...";

    const minElo = parseInt(document.getElementById("mm-min-elo")?.value) || 800;
    const maxElo = parseInt(document.getElementById("mm-max-elo")?.value) || 2500;
    const vsMode = State.settings.vs_mode || "bots";
    const gameMode = State.settings.game_mode || "auto";

    fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: State.settings.token || "__saved__",
        game_mode: gameMode,
        vs_mode: vsMode,
        min_elo: minElo,
        max_elo: maxElo,
      }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          if (vsMode === "bots") {
            Log.add(`Puan maçı aranıyor (Tempo: ${gameMode})...`);
          } else {
            Log.add("İnsan rakip aranıyor...");
          }
        } else {
          Log.add(`Başlatma hatası: ${d.error}`);
          if (overlayText) overlayText.textContent = "Hata oluştu";
          if (overlaySub) overlaySub.textContent = d.error || "Tekrar deneyin";
        }
      })
      .catch(err => {
        Log.add(`Bağlantı hatası: ${err.message}`);
      });
  },

  pause()  { fetch("/api/pause",  { method: "POST" }); },
  resume() { fetch("/api/resume", { method: "POST" }); },
  stop()   {
    fetch("/api/stop", { method: "POST" });
    setStatus("stopped", "Durduruldu");
    State.isRunning = false; State.isPaused = false;
    updateButtons();
    const overlay = document.getElementById("board-overlay");
    if (overlay) overlay.classList.remove("hidden");
    const overlayText = document.querySelector(".board-overlay-text");
    const overlaySub = document.querySelector(".board-overlay-sub");
    if (overlayText) overlayText.textContent = "Bot durduruldu";
    if (overlaySub) overlaySub.textContent = "BAŞLAT'a bas";
  },
};

// ── Settings Modal ───────────────────────────────────────────
const Modal = {
  open() {
    document.getElementById("modal-backdrop").classList.add("open");
    document.getElementById("modal").classList.add("open");

    // Mevcut ayarları yükle
    fetch("/api/config")
      .then(r => r.json())
      .then(d => {
        if (d.has_token) {
          document.getElementById("input-token").placeholder = d.token_preview;
        }
        // Engine durumu göster
        if (d.engine) {
          const dot  = document.getElementById("engine-dot");
          const text = document.getElementById("engine-status-text");
          dot.className = "engine-dot active";
          text.textContent = d.engine.name;

          const isLight = d.engine.is_light;
          const radioVal = isLight ? "tobi_light" : "tobi_mid";
          const rEl = document.querySelector(`input[name="engine_type"][value="${radioVal}"]`);
          if (rEl) rEl.checked = true;

          document.getElementById("rc-engine-light")?.classList.toggle("selected", isLight);
          document.getElementById("rc-engine-mid")?.classList.toggle("selected", !isLight);
        }
      });
  },

  selectEngine(engineType) {
    const isLight = (engineType === "tobi_light");
    document.getElementById("rc-engine-light")?.classList.toggle("selected", isLight);
    document.getElementById("rc-engine-mid")?.classList.toggle("selected", !isLight);
    const rEl = document.querySelector(`input[name="engine_type"][value="${engineType}"]`);
    if (rEl) rEl.checked = true;
  },

  close() {
    document.getElementById("modal-backdrop").classList.remove("open");
    document.getElementById("modal").classList.remove("open");
  },

  save() {
    const token       = document.getElementById("input-token").value.trim();
    const game_mode   = document.querySelector('input[name="game_mode"]:checked')?.value || "auto";
    const vs_mode     = document.querySelector('input[name="vs_mode"]:checked')?.value || "bots";
    const engine_type = document.querySelector('input[name="engine_type"]:checked')?.value || "tobi_light";

    if (token) State.settings.token = token;
    State.settings.game_mode = game_mode;
    State.settings.vs_mode   = vs_mode;

    document.getElementById("val-mode").textContent = game_mode;

    // Motor ayarlarını kaydet
    fetch("/api/engine/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine_type: engine_type }),
    })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        const name = d.engine?.name || "Bilinmiyor";
        Log.add(`Motor güncellendi: ${name}`);
        document.getElementById("val-engine").textContent = name;
        PlayApp.updateEngineInfo();
      }
    }).catch(() => {});

    Log.add("Ayarlar kaydedildi.");
    Modal.close();
  },
};

// ── Radio Card Seçimi ─────────────────────────────────────────
document.querySelectorAll(".radio-card").forEach(card => {
  const radio = card.querySelector("input[type=radio]");
  if (!radio) return;
  card.addEventListener("click", () => {
    document.querySelectorAll(`input[name="${radio.name}"]`).forEach(r => {
      r.closest(".radio-card")?.classList.remove("selected");
    });
    card.classList.add("selected");
    radio.checked = true;
  });
});

// ── UI Yardımcıları ──────────────────────────────────────────
const UI = {
  switchTab() {}
};

// ── Satranç Ses Efektleri (Web Audio API) ──────────────────────
const ChessAudio = {
  ctx: null,
  enabled: true,

  init() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) this.ctx = new AC();
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }
  },

  playMove() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(320, now);
      osc.frequency.exponentialRampToValueAtTime(130, now + 0.08);
      gain.gain.setValueAtTime(0.28, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(now);
      osc.stop(now + 0.08);
    } catch (e) {}
  },

  playCapture() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(460, now);
      osc.frequency.exponentialRampToValueAtTime(80, now + 0.12);
      gain.gain.setValueAtTime(0.4, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.12);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(now);
      osc.stop(now + 0.12);
    } catch (e) {}
  },

  playCheck() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      [587.33, 880].forEach((freq, i) => {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, now + i * 0.09);
        gain.gain.setValueAtTime(0.22, now + i * 0.09);
        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.09 + 0.14);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now + i * 0.09);
        osc.stop(now + i * 0.09 + 0.14);
      });
    } catch (e) {}
  },

  playWin() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      [440, 554.37, 659.25, 880].forEach((freq, i) => {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(freq, now + i * 0.12);
        gain.gain.setValueAtTime(0.25, now + i * 0.12);
        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.12 + 0.28);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now + i * 0.12);
        osc.stop(now + i * 0.12 + 0.3);
      });
    } catch (e) {}
  },

  playLoss() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      [440, 392, 349.23, 293.66].forEach((freq, i) => {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "sawtooth";
        osc.frequency.setValueAtTime(freq, now + i * 0.15);
        gain.gain.setValueAtTime(0.18, now + i * 0.15);
        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.15 + 0.25);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now + i * 0.15);
        osc.stop(now + i * 0.15 + 0.28);
      });
    } catch (e) {}
  },

  playDraw() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      [440, 440].forEach((freq, i) => {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, now + i * 0.14);
        gain.gain.setValueAtTime(0.22, now + i * 0.14);
        gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.14 + 0.2);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now + i * 0.14);
        osc.stop(now + i * 0.14 + 0.22);
      });
    } catch (e) {}
  }
};

// ── Oyun Bitiş Detayları Hesaplayıcı ──────────────────────────
function getGameEndDetails(chessInstance, userColor, action) {
  const isUserWhite = userColor === "white";

  if (action === "resign") {
    return {
      isGameOver: true,
      result: "loss",
      icon: "",
      title: "Terk Edildi",
      reason: "Oyuncu Terk Etti (Bot Kazandı)",
      sub: "Oyunu terk ettiniz, bot kazandı."
    };
  }

  if (action === "draw_agreed") {
    return {
      isGameOver: true,
      result: "draw",
      icon: "",
      title: "Berabere",
      reason: "Karşılıklı Anlaşma ile Berabere",
      sub: "Beraberlik teklifi kabul edildi."
    };
  }

  if (action === "timeout_user") {
    return {
      isGameOver: true,
      result: "loss",
      icon: "",
      title: "Süre Bitti",
      reason: "Zaman Aşımı (Bot Kazandı)",
      sub: "Süreniz tükendi, bot kazandı."
    };
  }

  if (action === "timeout_bot") {
    return {
      isGameOver: true,
      result: "win",
      icon: "",
      title: "Süre Bitti",
      reason: "Zaman Aşımı (Sen Kazandın)",
      sub: "Botun süresi tükendi, kazandınız."
    };
  }

  if (chessInstance.in_checkmate()) {
    const loserColor = chessInstance.turn();
    const userLost = (loserColor === "w" && isUserWhite) || (loserColor === "b" && !isUserWhite);
    if (userLost) {
      return {
        isGameOver: true,
        result: "loss",
        icon: "",
        title: "Şah Mat",
        reason: "Şah Mat (Bot Kazandı)",
        sub: "Şahınız mat oldu, bot kazandı."
      };
    } else {
      return {
        isGameOver: true,
        result: "win",
        icon: "",
        title: "Şah Mat",
        reason: "Şah Mat (Sen Kazandın)",
        sub: "Tebrikler, botu şah mat ettiniz."
      };
    }
  }

  if (chessInstance.in_stalemate()) {
    return {
      isGameOver: true,
      result: "draw",
      icon: "",
      title: "Pat (Berabere)",
      reason: "Pat Durumu ile Berabere",
      sub: "Hamle yapacak yasal kare kalmadı."
    };
  }

  if (chessInstance.insufficient_material()) {
    return {
      isGameOver: true,
      result: "draw",
      icon: "",
      title: "Yetersiz Taş",
      reason: "Yetersiz Taş ile Berabere",
      sub: "Tahtada mat yapmaya yetecek taş kalmadı."
    };
  }

  if (chessInstance.in_threefold_repetition()) {
    return {
      isGameOver: true,
      result: "draw",
      icon: "",
      title: "Üçlü Tekrar",
      reason: "Üçlü Hamle Tekrarı ile Berabere",
      sub: "Aynı pozisyon 3 kez tekrarlandı."
    };
  }

  if (chessInstance.in_draw()) {
    return {
      isGameOver: true,
      result: "draw",
      icon: "",
      title: "50 Hamle Kuralı",
      reason: "50 Hamle Kuralı ile Berabere",
      sub: "50 hamle boyunca piyon sürülmedi veya taş yenmedi."
    };
  }

  return {
    isGameOver: false,
    result: "ongoing",
    icon: "",
    title: "Oyun Bitti",
    reason: "Oyun Sona Erdi",
    sub: ""
  };
}

// ── Bota Karşı Oyna Uygulaması (Lokal & Bot vs Bot) ───────────
const PlayApp = {
  board: null,
  game: new Chess(),
  userColor: "white",
  selectedTimeMinutes: 10,
  userTimeSec: 600,
  botTimeSec: 600,
  timerInterval: null,
  isBotThinking: false,
  isGameOver: false,
  lastSavedGameId: null,
  currentStep: null,     // null = canlı pozisyon; sayı (0 .. N) = incelenen hamle adımı
  playedMovesUci: [],    // Maça ait tüm UCI hamleleri eksiksiz tutulur
  selectedSquare: null,  // Tıklanan / seçilen kare (örn: 'e2')
  lastActionTime: 0,     // Sürükleme sonrası istenmeyen tıklamaları engellemek için zaman damgası

  // Bot vs Bot Modu Değişkenleri
  gameMode: "human_vs_bot",   // "human_vs_bot" | "bot_vs_bot"
  botWhiteEngine: "tobi_light", // "tobi_light" | "tobi_mid"
  botBlackEngine: "tobi_mid",   // "tobi_light" | "tobi_mid"
  botVsBotRunning: false,
  botVsBotDelayMs: 1400,
  botVsBotTimeout: null,

  // Maç Öncesi Ayarlar ve Durum
  isGameStarted: false,
  pendingColor: "white",
  pendingEngine: "tobi_light",
  pendingTime: 10,

  init() {
    if (!this.board) {
      this.board = Chessboard("play-board", {
        position: "start",
        orientation: this.pendingColor || this.userColor,
        draggable: true,
        pieceTheme: "/img/chesspieces/wikipedia/{piece}.png",
        onDragStart: (source, piece) => this.onDragStart(source, piece),
        onDrop: (source, target) => this.onDrop(source, target),
        onSnapEnd: () => this.onSnapEnd(),
      });
      this.bindBoardEvents();
      $(window).on("resize orientationchange", () => {
        if (this.board) this.board.resize();
      });
    }

    // Oyun başlamamışken tahta hafif blurlu olsun
    if (!this.isGameStarted) {
      document.getElementById("play-board")?.classList.add("board-blurred");
      document.getElementById("play-setup-card")?.classList.remove("hidden");
      document.getElementById("play-action-card")?.classList.add("hidden");
    }

    this.updateEngineInfo();
    this.updatePlayerCards();
    this.renderMoves();
    this.updateClockDisplays();
    this.updateReviewUI();
    setTimeout(() => this.board && this.board.resize(), 60);
  },

  selectColor(color) {
    this.pendingColor = color;
    document.querySelectorAll("#setup-color-white, #setup-color-black").forEach(el => el.classList.remove("active"));
    document.getElementById(`setup-color-${color}`)?.classList.add("active");
    if (this.board && !this.isGameStarted) {
      this.board.orientation(color);
    }
    this.updatePlayerCards();
  },

  selectEngine(engine) {
    this.pendingEngine = engine;
    this.selectedEngine = engine;
    document.querySelectorAll("#setup-engine-light, #setup-engine-mid").forEach(el => el.classList.remove("active"));
    document.getElementById(engine === "tobi_light" ? "setup-engine-light" : "setup-engine-mid")?.classList.add("active");
    this.updatePlayerCards();

    fetch("/api/engine/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine_type: engine }),
    }).catch(() => {});
  },

  selectTime(time) {
    this.pendingTime = time;
    document.querySelectorAll(".setup-time-pill").forEach(el => el.classList.remove("active"));
    const elId = time === "unlimited" ? "setup-time-unlimited" : `setup-time-${time}`;
    document.getElementById(elId)?.classList.add("active");
    this.selectedTimeMinutes = time;
    this.updateClockDisplays();
  },

  startGame() {
    this.userColor = this.pendingColor || "white";
    this.selectedEngine = this.pendingEngine || "tobi_light";
    this.selectedTimeMinutes = this.pendingTime !== undefined ? this.pendingTime : 10;
    this.isGameStarted = true;

    // Tahta blur'unu kaldır
    document.getElementById("play-board")?.classList.remove("board-blurred");

    // Setup kartını gizle, aktif aksiyon butonlarını göster
    document.getElementById("play-setup-card")?.classList.add("hidden");
    document.getElementById("play-action-card")?.classList.remove("hidden");
    document.getElementById("play-gameover-card")?.classList.add("hidden");

    this.newGame();
    setTimeout(() => this.board && this.board.resize(), 60);
  },

  openSetupScreen() {
    this.isGameStarted = false;
    this.stopTimer();

    // Tahtayı hafif blurlu yap
    document.getElementById("play-board")?.classList.add("board-blurred");

    // Setup kartını aç, aksiyonları ve oyun bitti kartını gizle
    document.getElementById("play-setup-card")?.classList.remove("hidden");
    document.getElementById("play-action-card")?.classList.add("hidden");
    document.getElementById("play-gameover-card")?.classList.add("hidden");

    this.game = new Chess();
    this.playedMovesUci = [];
    this.currentStep = null;
    this.clearSquareSelection();
    $("#play-board .square-55d63").removeClass("king-check-pulse highlight-last-move");
    if (this.board) {
      this.board.orientation(this.pendingColor || "white");
      this.board.start();
      setTimeout(() => this.board && this.board.resize(), 60);
    }
    this.renderMoves();
    this.updatePlayerCards();
    this.updateClockDisplays();
  },

  getEngineDisplayName(engineType) {
    return engineType === "tobi_light" ? "Tobi Light" : "Tobi Mid";
  },

  getEngineShortName(engineType) {
    return engineType === "tobi_light" ? "Tobi Light" : "Tobi Mid";
  },

  updatePlayerCards() {
    const topAvatar = document.getElementById("play-top-avatar");
    const topName = document.getElementById("play-bot-name");
    const topBadge = document.getElementById("play-engine-badge");
    const bottomAvatar = document.getElementById("play-bottom-avatar");
    const bottomName = document.getElementById("play-bottom-name");
    const bottomBadge = document.getElementById("play-bottom-badge");
    const thWhite = document.getElementById("th-play-white");
    const thBlack = document.getElementById("th-play-black");
    const lblEngine = document.getElementById("play-lbl-engine");

    if (topAvatar) topAvatar.textContent = "";
    if (bottomAvatar) bottomAvatar.textContent = "";

    if (this.gameMode === "bot_vs_bot") {
      const isTopWhite = this.board && this.board.orientation() === "black";
      const topEngine = isTopWhite ? this.botWhiteEngine : this.botBlackEngine;
      const bottomEngine = isTopWhite ? this.botBlackEngine : this.botWhiteEngine;

      if (topName) topName.textContent = this.getEngineShortName(topEngine);
      if (topBadge) {
        topBadge.style.display = "inline-block";
        topBadge.textContent = isTopWhite ? "Beyaz Bot" : "Siyah Bot";
        topBadge.style.background = isTopWhite ? "rgba(59, 130, 246, 0.2)" : "rgba(100, 116, 139, 0.25)";
        topBadge.style.color = isTopWhite ? "#93c5fd" : "#cbd5e1";
      }

      if (bottomName) bottomName.textContent = this.getEngineShortName(bottomEngine);
      if (bottomBadge) {
        bottomBadge.style.display = "inline-block";
        bottomBadge.textContent = isTopWhite ? "Siyah Bot" : "Beyaz Bot";
        bottomBadge.style.background = isTopWhite ? "rgba(100, 116, 139, 0.25)" : "rgba(59, 130, 246, 0.2)";
        bottomBadge.style.color = isTopWhite ? "#cbd5e1" : "#93c5fd";
      }

      if (thWhite) thWhite.textContent = `Beyaz: ${this.getEngineShortName(this.botWhiteEngine)}`;
      if (thBlack) thBlack.textContent = `Siyah: ${this.getEngineShortName(this.botBlackEngine)}`;
      if (lblEngine) lblEngine.textContent = "Aktif Bot";
    } else {
      const activeEngine = this.isGameStarted ? (this.selectedEngine || "tobi_light") : (this.pendingEngine || "tobi_light");
      const isLight = activeEngine === "tobi_light";
      const userCol = this.isGameStarted ? this.userColor : (this.pendingColor || "white");
      const isWhite = userCol === "white";

      if (topName) topName.textContent = isLight ? "Tobi Light" : "Tobi Mid";
      if (topBadge) topBadge.style.display = "none"; // Elo badge gizli

      const currentUsername = (typeof UserModule !== "undefined" && UserModule.getUsername()) || "Oyuncu";
      if (bottomName) bottomName.textContent = currentUsername;
      if (bottomBadge) bottomBadge.style.display = "none";

      if (thWhite) thWhite.textContent = isWhite ? currentUsername : (isLight ? "Tobi Light" : "Tobi Mid");
      if (thBlack) thBlack.textContent = isWhite ? (isLight ? "Tobi Light" : "Tobi Mid") : currentUsername;
      if (lblEngine) lblEngine.textContent = "Aktif Bot";
    }
  },

  isReviewing() {
    return this.currentStep !== null && this.currentStep < this.game.history().length;
  },

  // ── Navigasyon Metotları (Chess.com Stili) ──────────────────
  navToStart() {
    this.navToStep(0);
  },

  navPrev() {
    const total = this.game.history().length;
    if (total === 0) return;
    const current = (this.currentStep === null) ? total : this.currentStep;
    if (current > 0) {
      this.navToStep(current - 1);
    }
  },

  navNext() {
    const total = this.game.history().length;
    if (this.currentStep === null) return;
    if (this.currentStep + 1 >= total) {
      this.navToLive();
    } else {
      this.navToStep(this.currentStep + 1);
    }
  },

  navToLive() {
    this.currentStep = null;
    if (this.board) {
      this.board.position(this.game.fen(), true);
    }
    this.updateReviewUI();
    this.updateCapturedAndCheck();
  },

  navToStep(step) {
    const total = this.game.history().length;
    if (step >= total) {
      this.navToLive();
      return;
    }
    this.currentStep = Math.max(0, step);

    // İlgili hamleye kadar olan pozisyonu oluştur
    const tempGame = new Chess();
    const history = this.game.history({ verbose: true });
    for (let i = 0; i < this.currentStep; i++) {
      tempGame.move(history[i]);
    }

    if (this.board) {
      this.board.position(tempGame.fen(), false);
    }
    this.updateReviewUI(tempGame);
    this.updateCapturedAndCheck(tempGame);
  },

  updateReviewUI(displayGame = null) {
    const total = this.game.history().length;
    const isRev = this.isReviewing();
    const step = isRev ? this.currentStep : total;

    // Buton durumları
    const btnFirst = document.getElementById("btn-play-first");
    const btnPrev  = document.getElementById("btn-play-prev");
    const btnNext  = document.getElementById("btn-play-next");
    const btnLast  = document.getElementById("btn-play-last");

    if (btnFirst) btnFirst.disabled = (step === 0 || total === 0);
    if (btnPrev)  btnPrev.disabled  = (step === 0 || total === 0);
    if (btnNext)  btnNext.disabled  = (!isRev || total === 0);
    if (btnLast)  btnLast.disabled  = (!isRev || total === 0);

    // Pozisyon rozeti
    const dotEl  = document.getElementById("play-nav-dot");
    const textEl = document.getElementById("play-nav-text");
    if (dotEl && textEl) {
      if (!isRev) {
        dotEl.className = "nav-status-dot live";
        textEl.textContent = "Canlı";
      } else {
        dotEl.className = "nav-status-dot review";
        textEl.textContent = `${step} / ${total}`;
      }
    }

    // İnceleme bildirim şeridi
    const bannerEl = document.getElementById("play-review-banner");
    const msgEl    = document.getElementById("play-review-msg");
    if (bannerEl && msgEl) {
      if (isRev) {
        bannerEl.classList.remove("hidden");
        if (step === 0) {
          msgEl.textContent = `Başlangıç pozisyonu inceleniyor (${total} hamle var)`;
        } else {
          const moveNum = Math.ceil(step / 2);
          const colorName = (step % 2 === 1) ? "Beyaz" : "Siyah";
          msgEl.textContent = `Hamle ${moveNum} (${colorName}) inceleniyor (${step}/${total})`;
        }
      } else {
        bannerEl.classList.add("hidden");
      }
    }

    // Hamle tablosundaki aktif hücreyi vurgula
    document.querySelectorAll("#play-moves-tbody .move-cell").forEach(el => {
      el.classList.remove("current", "review-active");
    });

    if (isRev) {
      if (step > 0) {
        const targetCell = document.querySelector(`#play-moves-tbody [data-step="${step}"]`);
        if (targetCell) {
          targetCell.classList.add("review-active");
          const c = targetCell.closest(".moves-table-container");
          if (c) {
            const elTop = targetCell.offsetTop - c.offsetTop;
            const elH = targetCell.offsetHeight;
            if (elTop < c.scrollTop) {
              c.scrollTop = Math.max(0, elTop - 4);
            } else if (elTop + elH > c.scrollTop + c.clientHeight) {
              c.scrollTop = elTop + elH - c.clientHeight + 4;
            }
          }
        }
      }
    } else if (total > 0) {
      const lastCell = document.querySelector(`#play-moves-tbody [data-step="${total}"]`);
      if (lastCell) {
        lastCell.classList.add("current");
        const c = lastCell.closest(".moves-table-container");
        if (c) c.scrollTop = c.scrollHeight;
      }
    }
  },

  updateCapturedAndCheck(activeGame = null) {
    const g = activeGame || this.game;
    renderCapturedPieces(
      g,
      this.userColor === "white" ? "black" : "white",
      this.userColor,
      "play-captured-top",
      "play-captured-bottom"
    );
    highlightKingCheck(g, "#play-board");
  },

  setTime(minutes) {
    this.selectTime(minutes);
  },

  toggleSound() {
    ChessAudio.enabled = !ChessAudio.enabled;
    const btn = document.getElementById("sound-toggle");
    if (btn) {
      btn.textContent = ChessAudio.enabled ? "Ses Açık" : "Sessiz";
      btn.classList.toggle("muted", !ChessAudio.enabled);
    }
  },

  startTimer() {
    this.stopTimer();
    // Süresiz modda saat geri sayımı çalışmaz
    if (this.selectedTimeMinutes === 0 || this.selectedTimeMinutes === "unlimited") {
      this.updateClockDisplays();
      return;
    }

    this.timerInterval = setInterval(() => {
      if (this.isGameOver || this.game.game_over()) {
        this.stopTimer();
        return;
      }
      const isUserTurn = this.game.turn() === (this.userColor === "white" ? "w" : "b");
      if (isUserTurn) {
        this.userTimeSec = Math.max(0, this.userTimeSec - 1);
      } else {
        this.botTimeSec = Math.max(0, this.botTimeSec - 1);
      }
      this.updateClockDisplays();

      if (this.userTimeSec <= 0 || this.botTimeSec <= 0) {
        this.stopTimer();
        this.handleTimeout();
      }
    }, 1000);
    this.updateClockDisplays();
  },

  stopTimer() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
  },

  updateClockDisplays() {
    const topClock = document.getElementById("play-clock-top");
    const botClock = document.getElementById("play-clock-bottom");
    if (!topClock || !botClock) return;

    const isUnlimited = (this.selectedTimeMinutes === 0 || this.selectedTimeMinutes === "unlimited");

    if (!this.isGameStarted) {
      botClock.classList.remove("active", "low-time");
      topClock.classList.remove("active", "low-time");
      if (isUnlimited) {
        topClock.textContent = "∞";
        botClock.textContent = "∞";
      } else {
        const m = (typeof this.selectedTimeMinutes === "number" ? this.selectedTimeMinutes : 10);
        topClock.textContent = `${m}:00`;
        botClock.textContent = `${m}:00`;
      }
      return;
    }

    if (isUnlimited) {
      topClock.textContent = "∞";
      botClock.textContent = "∞";
      const isUserTurn = this.game.turn() === (this.userColor === "white" ? "w" : "b");
      botClock.classList.toggle("active", isUserTurn);
      topClock.classList.toggle("active", !isUserTurn);
      botClock.classList.remove("low-time");
      topClock.classList.remove("low-time");
      return;
    }

    const fmt = (s) => {
      const m = Math.floor(s / 60);
      const sec = s % 60;
      return `${m}:${sec < 10 ? "0" : ""}${sec}`;
    };

    topClock.textContent = fmt(this.botTimeSec);
    botClock.textContent = fmt(this.userTimeSec);

    const isUserTurn = this.game.turn() === (this.userColor === "white" ? "w" : "b");
    botClock.classList.toggle("active", isUserTurn);
    topClock.classList.toggle("active", !isUserTurn);
    botClock.classList.toggle("low-time", this.userTimeSec < 30);
    topClock.classList.toggle("low-time", this.botTimeSec < 30);
  },

  handleTimeout() {
    const isUserTimedOut = this.userTimeSec <= 0;
    this.handleGameEnd(isUserTimedOut ? "timeout_user" : "timeout_bot");
  },

  handleGameEnd(action) {
    if (this.isGameOver) return;
    this.isGameOver = true;
    this.stopTimer();
    this.botVsBotRunning = false;
    if (this.botVsBotTimeout) {
      clearTimeout(this.botVsBotTimeout);
      this.botVsBotTimeout = null;
    }

    // Bot vs bot butonunu güncelle
    const btnPlayPause = document.getElementById("btn-botvsbot-playpause");
    if (btnPlayPause) {
      const iconEl = document.getElementById("btn-botvsbot-icon");
      const textEl = document.getElementById("btn-botvsbot-text");
      if (iconEl) iconEl.textContent = "▶️";
      if (textEl) textEl.textContent = "YENİ BOT MAÇI";
      btnPlayPause.style.background = "linear-gradient(135deg, #10b981, #059669)";
    }

    // Oyun bittiğinde canlı pozisyona dön
    this.navToLive();

    let details;
    if (this.gameMode === "bot_vs_bot") {
      details = this.getBotVsBotEndDetails();
    } else {
      details = getGameEndDetails(this.game, this.userColor, action);
    }

    // Ses çal
    if (details.result === "win") ChessAudio.playWin();
    else if (details.result === "loss") ChessAudio.playLoss();
    else ChessAudio.playDraw();

    // Status kartını güncelle
    const statusEl = document.getElementById("play-status-text");
    if (statusEl) {
      statusEl.textContent = `${details.title} (${details.reason})`;
      statusEl.style.color = details.result === "win" ? "var(--green)" : (details.result === "loss" ? "var(--red)" : "var(--yellow)");
    }

    // Tahta üzerindeki küçük kompakt Oyun Bitti kartını göster (Tahta blurlanmaz!)
    document.getElementById("play-board")?.classList.remove("board-blurred");
    const goCard = document.getElementById("play-gameover-card");
    const goTitle = document.getElementById("go-title");
    const goReason = document.getElementById("go-reason");
    if (goTitle) goTitle.textContent = details.title;
    if (goReason) goReason.textContent = details.reason;
    // Not: Maç hiçbir veritabanına kaydedilmez; sadece mevcut maç hafızada incelenebilir.
  },

  getBotVsBotEndDetails() {
    const whiteBot = this.getEngineDisplayName(this.botWhiteEngine);
    const blackBot = this.getEngineDisplayName(this.botBlackEngine);

    if (this.game.in_checkmate()) {
      const loserColor = this.game.turn();
      const winnerName = loserColor === "w" ? blackBot : whiteBot;
      const loserName  = loserColor === "w" ? whiteBot : blackBot;
      return {
        isGameOver: true,
        result: loserColor === "w" ? "loss" : "win",
        icon: "",
        title: `${winnerName} Kazandı`,
        reason: `Şah Mat (${loserName} mat oldu)`,
        sub: `${winnerName} maçı kazandı.`
      };
    }

    if (this.game.in_stalemate()) {
      return {
        isGameOver: true,
        result: "draw",
        icon: "",
        title: "Pat (Berabere)",
        reason: "Pat Durumu ile Beraberlik",
        sub: "Tahtada yasal hamle kalmadı."
      };
    }

    if (this.game.in_threefold_repetition()) {
      return {
        isGameOver: true,
        result: "draw",
        icon: "",
        title: "Üçlü Tekrar",
        reason: "3 Hamle Tekrarı Kuralı",
        sub: "Aynı pozisyon 3 kez tekrarlandı."
      };
    }

    if (this.game.insufficient_material()) {
      return {
        isGameOver: true,
        result: "draw",
        icon: "",
        title: "Yetersiz Taş",
        reason: "Yetersiz Materyal",
        sub: "Mat etmeye yetecek taş kalmadı."
      };
    }

    if (this.game.in_draw()) {
      return {
        isGameOver: true,
        result: "draw",
        icon: "",
        title: "50 Hamle Kuralı",
        reason: "50 Hamle Kuralı",
        sub: "50 hamle kuralı gerçekleşti."
      };
    }

    return {
      isGameOver: true,
      result: "draw",
      icon: "",
      title: "Maç Sona Erdi",
      reason: "Oyun Bitti",
      sub: ""
    };
  },

  checkGameOver() {
    if (this.game.game_over()) {
      this.handleGameEnd(null);
      return true;
    }
    return false;
  },

  resign() {
    if (this.isGameOver || this.game.game_over()) return;
    if (confirm("Oyunu terk etmek istediğinize emin misiniz?")) {
      this.handleGameEnd("resign");
    }
  },

  offerDraw() {
    if (this.isGameOver || this.game.game_over()) return;
    const movesCount = this.game.history().length;
    if (movesCount < 10) {
      alert("Oyun henüz çok yeni! Bot beraberlik teklifini reddetti.");
      return;
    }
    // Bot teklifi değerlendirir
    const botAccepts = Math.random() < 0.6;
    if (botAccepts) {
      alert("Bot beraberlik teklifinizi kabul etti.");
      this.handleGameEnd("draw_agreed");
    } else {
      alert("Bot beraberlik teklifinizi reddetti! Mücadeleye devam!");
    }
  },

  reviewCurrentGame() {
    document.getElementById("play-gameover-card")?.classList.add("hidden");
  },

  setGameMode(mode) {
    if (this.gameMode === mode) return;
    this.gameMode = mode;

    document.getElementById("btn-mode-human")?.classList.toggle("active", mode === "human_vs_bot");
    document.getElementById("btn-mode-botvsbot")?.classList.toggle("active", mode === "bot_vs_bot");

    const humanSettings = document.getElementById("play-human-settings");
    const botSettings = document.getElementById("play-botvsbot-settings");
    const humanActions = document.getElementById("play-human-actions");
    const botActions = document.getElementById("play-botvsbot-actions");

    if (humanSettings) humanSettings.style.display = mode === "human_vs_bot" ? "block" : "none";
    if (botSettings) botSettings.style.display = mode === "bot_vs_bot" ? "block" : "none";
    if (humanActions) humanActions.style.display = mode === "human_vs_bot" ? "block" : "none";
    if (botActions) botActions.style.display = mode === "bot_vs_bot" ? "block" : "none";

    this.updatePlayerCards();

    if (mode === "bot_vs_bot") {
      this.newBotVsBotGame();
    } else {
      if (this.botVsBotTimeout) clearTimeout(this.botVsBotTimeout);
      this.botVsBotRunning = false;
      this.newGame();
    }
  },

  setBotWhiteEngine(engine) {
    this.botWhiteEngine = engine;
    document.querySelectorAll("#rc-bot-white-light, #rc-bot-white-mid").forEach(el => el.classList.remove("selected"));
    document.getElementById(engine === "tobi_light" ? "rc-bot-white-light" : "rc-bot-white-mid")?.classList.add("selected");
    this.updatePlayerCards();
    this.newBotVsBotGame();
  },

  setBotBlackEngine(engine) {
    this.botBlackEngine = engine;
    document.querySelectorAll("#rc-bot-black-light, #rc-bot-black-mid").forEach(el => el.classList.remove("selected"));
    document.getElementById(engine === "tobi_light" ? "rc-bot-black-light" : "rc-bot-black-mid")?.classList.add("selected");
    this.updatePlayerCards();
    this.newBotVsBotGame();
  },

  setBotDelay(ms) {
    this.botVsBotDelayMs = ms;
    document.querySelectorAll("#rc-bot-delay-fast, #rc-bot-delay-normal, #rc-bot-delay-slow").forEach(el => el.classList.remove("selected"));
    let cardId = "rc-bot-delay-normal";
    if (ms <= 800) cardId = "rc-bot-delay-fast";
    else if (ms >= 2000) cardId = "rc-bot-delay-slow";
    document.getElementById(cardId)?.classList.add("selected");
  },

  newBotVsBotGame() {
    if (this.botVsBotTimeout) {
      clearTimeout(this.botVsBotTimeout);
      this.botVsBotTimeout = null;
    }
    this.botVsBotRunning = false;
    this.isBotThinking = false;
    this.isGameOver = false;

    const btn = document.getElementById("btn-botvsbot-playpause");
    if (btn) {
      const iconEl = document.getElementById("btn-botvsbot-icon");
      const textEl = document.getElementById("btn-botvsbot-text");
      if (iconEl) iconEl.textContent = "▶️";
      if (textEl) textEl.textContent = "BOT MAÇINI BAŞLAT";
      btn.style.background = "linear-gradient(135deg, #10b981, #059669)";
    }

    this.game = new Chess();
    this.playedMovesUci = [];
    this.currentStep = null;
    this.stopTimer();

    this.removeLegalMoveHints();
    $("#play-board .square-55d63").removeClass("king-check-pulse highlight-last-move");
    document.getElementById("play-board-overlay").classList.add("hidden");

    const statusEl = document.getElementById("play-status-text");
    if (statusEl) {
      statusEl.textContent = "Hazır - Başlatın";
      statusEl.style.color = "var(--text-secondary)";
    }
    document.getElementById("play-val-moves").textContent = "0";
    document.getElementById("play-last-move-val").textContent = "—";
    document.getElementById("play-val-engine").textContent = `${this.getEngineShortName(this.botWhiteEngine)} vs ${this.getEngineShortName(this.botBlackEngine)}`;
    document.getElementById("play-captured-top").innerHTML = "";
    document.getElementById("play-captured-bottom").innerHTML = "";
    document.getElementById("play-clock-top").textContent = "∞";
    document.getElementById("play-clock-bottom").textContent = "∞";

    if (this.board) {
      this.board.orientation("white");
      this.board.start();
    }

    this.renderMoves();
    this.updatePlayerCards();
    this.updateReviewUI();
  },

  toggleBotVsBot() {
    if (this.botVsBotRunning) {
      this.pauseBotVsBot();
    } else {
      this.startBotVsBot();
    }
  },

  startBotVsBot() {
    if (this.isGameOver || this.game.game_over()) {
      this.newBotVsBotGame();
    }
    if (this.isReviewing()) {
      this.navToLive();
    }

    this.botVsBotRunning = true;
    const btn = document.getElementById("btn-botvsbot-playpause");
    if (btn) {
      const iconEl = document.getElementById("btn-botvsbot-icon");
      const textEl = document.getElementById("btn-botvsbot-text");
      if (iconEl) iconEl.textContent = "⏸️";
      if (textEl) textEl.textContent = "DURAKLAT";
      btn.style.background = "linear-gradient(135deg, #f59e0b, #d97706)";
    }

    this.runNextBotMove(false);
  },

  pauseBotVsBot() {
    this.botVsBotRunning = false;
    if (this.botVsBotTimeout) {
      clearTimeout(this.botVsBotTimeout);
      this.botVsBotTimeout = null;
    }
    const btn = document.getElementById("btn-botvsbot-playpause");
    if (btn) {
      const iconEl = document.getElementById("btn-botvsbot-icon");
      const textEl = document.getElementById("btn-botvsbot-text");
      if (iconEl) iconEl.textContent = "▶️";
      if (textEl) textEl.textContent = "DEVAM ET";
      btn.style.background = "linear-gradient(135deg, #10b981, #059669)";
    }
    const statusEl = document.getElementById("play-status-text");
    if (statusEl && !this.isGameOver) {
      statusEl.textContent = "Duraklatıldı ⏸️";
      statusEl.style.color = "var(--yellow)";
    }
  },

  stopBotVsBot() {
    this.pauseBotVsBot();
    const btn = document.getElementById("btn-botvsbot-playpause");
    if (btn) {
      const iconEl = document.getElementById("btn-botvsbot-icon");
      const textEl = document.getElementById("btn-botvsbot-text");
      if (iconEl) iconEl.textContent = "▶️";
      if (textEl) textEl.textContent = "BOT MAÇINI BAŞLAT";
      btn.style.background = "linear-gradient(135deg, #10b981, #059669)";
    }
  },

  stepBotVsBot() {
    if (this.isGameOver || this.game.game_over()) return;
    if (this.botVsBotRunning) {
      this.pauseBotVsBot();
    }
    if (this.isReviewing()) {
      this.navToLive();
    }
    this.runNextBotMove(true);
  },

  runNextBotMove(isSingleStep = false) {
    if (this.isGameOver || this.game.game_over() || this.isBotThinking) return;

    const turn = this.game.turn(); // "w" or "b"
    const currentEngine = (turn === "w") ? this.botWhiteEngine : this.botBlackEngine;
    const engineColorText = (turn === "w") ? "⬜ Beyaz" : "⬛ Siyah";

    this.isBotThinking = true;
    const statusEl = document.getElementById("play-status-text");
    if (statusEl) {
      statusEl.textContent = `${engineColorText} (${this.getEngineShortName(currentEngine)}) Düşünüyor... ⏳`;
      statusEl.style.color = "var(--yellow)";
    }

    fetch("/api/play/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fen: this.game.fen(),
        engine: currentEngine
      }),
    })
    .then(r => r.json())
    .then(d => {
      this.isBotThinking = false;
      if (d.ok && d.move) {
        const from = d.move.slice(0, 2);
        const to = d.move.slice(2, 4);
        const promo = d.move.length > 4 ? d.move[4] : undefined;
        const botMove = this.game.move({ from, to, promotion: promo });

        this.playedMovesUci.push(d.move);

        if (!this.isReviewing() && this.board) {
          this.board.position(this.game.fen(), true);
          this.updateCapturedAndCheck();
        }

        if (botMove && botMove.captured) {
          ChessAudio.playCapture();
        } else {
          ChessAudio.playMove();
        }

        if (this.game.in_check()) {
          setTimeout(() => ChessAudio.playCheck(), 100);
        }

        document.getElementById("play-last-move-val").textContent = (botMove && botMove.san) || d.move;

        // Search info gösterimi
        let evalStr = "";
        if (d.search_info && d.search_info.eval_str) {
          evalStr = ` | Skor: ${d.search_info.eval_str} (D:${d.search_info.depth})`;
        }
        document.getElementById("play-val-engine").textContent = `${this.getEngineDisplayName(currentEngine)}${evalStr}`;
        document.getElementById("play-val-moves").textContent = this.game.history().length;

        this.renderMoves();
        this.updateReviewUI();

        const ended = this.checkGameOver();
        if (!ended && this.botVsBotRunning && !isSingleStep) {
          this.botVsBotTimeout = setTimeout(() => {
            this.runNextBotMove(false);
          }, this.botVsBotDelayMs);
        } else if (isSingleStep && !ended) {
          const nextTurn = this.game.turn();
          const nextEngine = (nextTurn === "w") ? this.botWhiteEngine : this.botBlackEngine;
          if (statusEl) {
            statusEl.textContent = `Sıra: ${nextTurn === "w" ? "⬜" : "⬛"} ${this.getEngineShortName(nextEngine)}`;
            statusEl.style.color = "var(--green)";
          }
        }
      } else {
        if (statusEl) {
          statusEl.textContent = "Hata: Hamle alınamadı";
          statusEl.style.color = "var(--red)";
        }
        this.stopBotVsBot();
      }
    })
    .catch(() => {
      this.isBotThinking = false;
      if (statusEl) {
        statusEl.textContent = "Sunucu hatası";
        statusEl.style.color = "var(--red)";
      }
      this.stopBotVsBot();
    });
  },

  setColor(color) {
    this.selectColor(color);
  },

  setEngine(engineType) {
    this.selectEngine(engineType);
  },

  updateEngineInfo() {
    fetch("/api/config")
      .then(r => r.json())
      .then(d => {
        const engineType = d.engine?.engine_type || "tobi_light";
        const isLight = (engineType === "tobi_light");
        const engineName = isLight ? "Tobi Light" : "Tobi Mid";

        const valEngineEl = document.getElementById("play-val-engine");
        if (valEngineEl) valEngineEl.textContent = engineName;
        const badgeEl = document.getElementById("play-engine-badge");
        if (badgeEl) badgeEl.style.display = "none";
        const botNameEl = document.getElementById("play-bot-name");
        if (botNameEl) botNameEl.textContent = engineName;

        document.getElementById("setup-engine-light")?.classList.toggle("active", isLight);
        document.getElementById("setup-engine-mid")?.classList.toggle("active", !isLight);
      })
      .catch(() => {});
  },

  newGame() {
    this.game = new Chess();
    this.playedMovesUci = [];
    this.currentStep = null;
    this.isBotThinking = false;
    this.isGameOver = false;

    if (this.selectedTimeMinutes === "unlimited") {
      this.userTimeSec = 0;
      this.botTimeSec = 0;
    } else {
      const sec = (typeof this.selectedTimeMinutes === "number" ? this.selectedTimeMinutes : 10) * 60;
      this.userTimeSec = sec;
      this.botTimeSec = sec;
    }

    if (this.isGameStarted) {
      this.startTimer();
    } else {
      this.stopTimer();
    }

    this.clearSquareSelection();
    $("#play-board .square-55d63").removeClass("king-check-pulse highlight-last-move");
    document.getElementById("play-gameover-card")?.classList.add("hidden");

    const statusEl = document.getElementById("play-status-text");
    if (statusEl) {
      statusEl.textContent = this.userColor === "white" ? "Senin Sıran" : "Botun Sırası";
      statusEl.style.color = "var(--green)";
    }
    document.getElementById("play-val-moves").textContent = "0";
    document.getElementById("play-last-move-val").textContent = "—";
    document.getElementById("play-captured-top").innerHTML = "";
    document.getElementById("play-captured-bottom").innerHTML = "";

    if (this.board) {
      this.board.orientation(this.userColor);
      this.board.start();
    }
    this.renderMoves();
    this.updateEngineInfo();
    this.updateClockDisplays();
    this.updateReviewUI();

    // Sadece oyun gerçekten başlatıldıysa ve oyuncu Siyah ise Bot ilk hamleyi yapar
    if (this.isGameStarted && this.userColor === "black") {
      setTimeout(() => this.requestBotMove(), 400);
    }
  },

  flipBoard() {
    if (this.board) {
      this.board.flip();
      this.updatePlayerCards();
    }
  },

  undoMove() {
    if (this.isBotThinking || this.isGameOver) return;
    if (this.isReviewing()) {
      this.navToLive();
    }
    this.clearSquareSelection();
    // Hem botun hem oyuncunun hamlesini geri al (2 hamle)
    this.game.undo();
    this.game.undo();
    this.playedMovesUci.pop();
    this.playedMovesUci.pop();
    if (this.board) {
      this.board.position(this.game.fen());
    }
    this.renderMoves();
    this.updateStatus();
    this.updateClockDisplays();
    this.updateReviewUI();
  },

  bindBoardEvents() {
    const boardEl = document.getElementById("play-board");
    if (!boardEl || boardEl.dataset.eventsBound) return;
    boardEl.dataset.eventsBound = "true";

    // Mobil tarayıcılarda tahta üzerinde sürüklerken sayfanın kaymasını kesin olarak engelle
    boardEl.addEventListener("touchmove", (e) => {
      e.preventDefault();
    }, { passive: false });

    // Hem dokunma hem tıklama ile taşa/kareye basıldığında Click-to-Move çalıştır
    $(boardEl).on("click", ".square-55d63", (e) => {
      const square = $(e.currentTarget).data("square");
      if (square) {
        PlayApp.handleSquareClick(square);
      }
    });
  },

  selectSquare(square) {
    this.selectedSquare = square;
    $("#play-board .square-55d63").removeClass("square-selected");
    const squareEl = $(`#play-board [data-square="${square}"]`);
    if (squareEl.length) {
      squareEl.addClass("square-selected");
    }
    this.showLegalMoveHints(square);
  },

  clearSquareSelection() {
    this.selectedSquare = null;
    $("#play-board .square-55d63").removeClass("square-selected");
    this.removeLegalMoveHints();
  },

  showLegalMoveHints(source) {
    this.removeLegalMoveHints();
    const moves = this.game.moves({ square: source, verbose: true });
    moves.forEach(m => {
      const squareEl = $(`#play-board [data-square="${m.to}"]`);
      if (squareEl.length) {
        if (m.captured) {
          squareEl.append('<div class="legal-move-capture"></div>');
        } else {
          squareEl.append('<div class="legal-move-hint"></div>');
        }
      }
    });
  },

  removeLegalMoveHints() {
    $("#play-board .legal-move-hint, #play-board .legal-move-capture").remove();
  },

  handleSquareClick(square) {
    if (!this.isGameStarted) return;
    if (this.gameMode === "bot_vs_bot") return;
    if (this.isGameOver || this.game.game_over() || this.isBotThinking) return;

    // Sürükle-bırak hemen sonrasında tetiklenen sahte tıklamayı engelle
    if (Date.now() - this.lastActionTime < 180) return;

    if (this.isReviewing()) {
      this.navToLive();
      return;
    }

    const isMyTurn = (this.game.turn() === "w" && this.userColor === "white") ||
                     (this.game.turn() === "b" && this.userColor === "black");
    if (!isMyTurn) return;

    const piece = this.game.get(square);
    const isMyPiece = piece && piece.color === (this.userColor === "white" ? "w" : "b");

    // 1. Zaten bir kare seçilmişse
    if (this.selectedSquare) {
      // 1a. Aynı kareye tekrar tıklandıysa: seçimi kaldır
      if (this.selectedSquare === square) {
        this.clearSquareSelection();
        return;
      }

      // 1b. Tıklanan kare yasal bir hedef kare mi?
      const legalMoves = this.game.moves({ square: this.selectedSquare, verbose: true });
      const isLegalDest = legalMoves.some(m => m.to === square);

      if (isLegalDest) {
        // Tıklayarak hamleyi yap!
        this.executeUserMove(this.selectedSquare, square);
        return;
      }

      // 1c. Kendi başka bir taşına tıklandıysa: seçimi o taşa taşı
      if (isMyPiece) {
        this.selectSquare(square);
        return;
      }

      // 1d. Başka boş veya geçersiz yere tıklandıysa: seçimi kaldır
      this.clearSquareSelection();
      return;
    }

    // 2. Henüz seçili kare yoksa ve kendi taşına tıklandıysa: seç ve yuvarlakları göster
    if (isMyPiece) {
      this.selectSquare(square);
    }
  },

  executeUserMove(source, target) {
    const move = this.game.move({
      from: source,
      to: target,
      promotion: "q",
    });

    if (move === null) {
      this.clearSquareSelection();
      return null;
    }

    this.clearSquareSelection();
    this.lastActionTime = Date.now();

    // Hamleyi UCI dizisine kaydet
    const uciMove = move.from + move.to + (move.promotion || "");
    this.playedMovesUci.push(uciMove);

    // Canlı moda geç
    this.currentStep = null;

    if (this.board) {
      this.board.position(this.game.fen(), true);
    }

    // Ses çal
    if (move.captured) {
      ChessAudio.playCapture();
    } else {
      ChessAudio.playMove();
    }

    if (this.game.in_check()) {
      setTimeout(() => ChessAudio.playCheck(), 100);
    }

    document.getElementById("play-last-move-val").textContent = move.san || (source + target);
    this.renderMoves();
    this.updateStatus();
    this.updateReviewUI();

    if (!this.checkGameOver()) {
      setTimeout(() => this.requestBotMove(), 300);
    }

    return move;
  },

  onDragStart(source, piece) {
    if (!this.isGameStarted) return false;
    if (this.gameMode === "bot_vs_bot") return false;
    if (this.isGameOver || this.game.game_over() || this.isBotThinking) return false;

    // Kullanıcı geçmişi inceliyorsa hemen canlıya dön
    if (this.isReviewing()) {
      this.navToLive();
      return false;
    }

    // Sadece kendi rengindeki taşları sürükleyebilir
    if (this.userColor === "white" && piece.search(/^b/) !== -1) return false;
    if (this.userColor === "black" && piece.search(/^w/) !== -1) return false;

    // Sıra oyuncuda mı?
    if ((this.game.turn() === "w" && this.userColor !== "white") ||
        (this.game.turn() === "b" && this.userColor !== "black")) {
      return false;
    }

    // Taşı seç ve yasal hamle yuvarlaklarını göster
    this.selectSquare(source);
    return true;
  },

  onDrop(source, target) {
    this.lastActionTime = Date.now();

    // Eğer aynı kareye bırakıldıysa (sadece taşa tıklanıp bırakıldıysa):
    // Seçimi ve ipucu yuvarlaklarını koru ki kullanıcı sonraki tıklamayla hedef kareyi seçebilsin!
    if (source === target || target === "offboard") {
      this.selectSquare(source);
      return "snapback";
    }

    const move = this.executeUserMove(source, target);
    if (move === null) {
      this.selectSquare(source);
      return "snapback";
    }
  },

  onSnapEnd() {
    // Sadece seçim aktif değilse ipuçlarını kaldır
    if (!this.selectedSquare) {
      this.removeLegalMoveHints();
    }
    if (!this.isReviewing() && this.board) {
      this.board.position(this.game.fen());
    }
  },

  requestBotMove() {
    if (this.isGameOver || this.game.game_over()) return;
    this.isBotThinking = true;
    const statusEl = document.getElementById("play-status-text");
    statusEl.textContent = "Bot Düşünüyor...";
    statusEl.style.color = "var(--yellow)";

    const isLight = (this.selectedEngine || this.pendingEngine) === "tobi_light";
    const engineChoice = isLight ? "tobi_light" : "tobi_mid";

    fetch("/api/play/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fen: this.game.fen(), engine: engineChoice }),
    })
    .then(r => r.json())
    .then(d => {
      this.isBotThinking = false;
      if (d.ok && d.move) {
        const from = d.move.slice(0, 2);
        const to = d.move.slice(2, 4);
        const promo = d.move.length > 4 ? d.move[4] : undefined;
        const botMove = this.game.move({ from, to, promotion: promo });

        // UCI dizisine bot hamlesini kaydet
        this.playedMovesUci.push(d.move);

        // Kullanıcı geçmişi incelemiyorsa tahtayı canlı pozisyona güncelle
        if (!this.isReviewing() && this.board) {
          this.board.position(this.game.fen(), true);
          this.updateCapturedAndCheck();
        }

        if (botMove && botMove.captured) {
          ChessAudio.playCapture();
        } else {
          ChessAudio.playMove();
        }

        if (this.game.in_check()) {
          setTimeout(() => ChessAudio.playCheck(), 100);
        }

        document.getElementById("play-last-move-val").textContent = (botMove && botMove.san) || d.move;
        if (d.engine) {
          document.getElementById("play-val-engine").textContent = d.engine;
          document.getElementById("play-engine-badge").textContent = d.engine;
        }
        this.renderMoves();
        this.updateStatus();
        this.updateReviewUI();
        this.checkGameOver();
      } else {
        statusEl.textContent = "Hata: Hamle alınamadı";
        statusEl.style.color = "var(--red)";
      }
    })
    .catch(() => {
      this.isBotThinking = false;
      statusEl.textContent = "Sunucu hatası";
      statusEl.style.color = "var(--red)";
    });
  },

  updateStatus() {
    const statusEl = document.getElementById("play-status-text");
    document.getElementById("play-val-moves").textContent = this.game.history().length;

    if (!this.isReviewing()) {
      this.updateCapturedAndCheck();
    }

    if (!this.isGameOver) {
      if (this.game.in_check()) {
        statusEl.textContent = "Şah Çekildi!";
        statusEl.style.color = "var(--yellow)";
      } else {
        const isMyTurn = this.game.turn() === (this.userColor === "white" ? "w" : "b");
        statusEl.textContent = isMyTurn ? "Senin Sıran" : "Botun Sırası";
        statusEl.style.color = isMyTurn ? "var(--green)" : "var(--yellow)";
      }
    }
    this.updateClockDisplays();
  },

  renderMoves() {
    const tbody = document.getElementById("play-moves-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    const history = this.game.history();

    for (let i = 0; i < history.length; i += 2) {
      const moveNum = Math.floor(i / 2) + 1;
      const whiteMove = history[i];
      const blackMove = history[i + 1] || "";
      const stepWhite = i + 1;
      const stepBlack = i + 2;

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="move-num">${moveNum}.</td>
        <td><span class="move-cell" data-step="${stepWhite}" onclick="PlayApp.navToStep(${stepWhite})">${whiteMove}</span></td>
        <td>${blackMove ? `<span class="move-cell" data-step="${stepBlack}" onclick="PlayApp.navToStep(${stepBlack})">${blackMove}</span>` : ""}</td>
      `;
      tbody.appendChild(tr);
    }

    this.updateReviewUI();
  }
};

// ── Başlatma ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  UserModule.init();
  PlayApp.init();
});

// ── Klavye Yön Tuşları ile Hamle Navigasyonu (Chess.com Stili) ──
document.addEventListener("keydown", (e) => {
  // Eğer kullanıcı input, textarea veya select alanındaysa engelleme
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;

  if (e.key === "ArrowLeft") {
    e.preventDefault();
    PlayApp.navPrev();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    PlayApp.navNext();
  } else if (e.key === "ArrowUp" || e.key === "Home") {
    e.preventDefault();
    PlayApp.navToStart();
  } else if (e.key === "ArrowDown" || e.key === "End") {
    e.preventDefault();
    PlayApp.navToLive();
  }
});

// ── Ekran Boyutu ve Yön Değişimi (Portrait / Landscape) Dinleyicisi ──
window.addEventListener("resize", () => {
  if (typeof PlayApp !== "undefined" && PlayApp.board) {
    PlayApp.board.resize();
  }
});

window.addEventListener("orientationchange", () => {
  setTimeout(() => {
    if (typeof PlayApp !== "undefined" && PlayApp.board) PlayApp.board.resize();
  }, 150);
});


