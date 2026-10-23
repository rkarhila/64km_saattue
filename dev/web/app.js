(() => {
  const $ = (id) => document.getElementById(id);

  let gameId = null;
  let humanSeat = "player_0";
  let seatNum = 0;

  $("startBtn").addEventListener("click", async () => {
    const body = {
      num_players: Number($("numPlayers").value),
      human_seat: 0,
      seed: Number($("seed").value),
    };
    const res = await fetch("/games", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    const data = await res.json();
    gameId = data.game_id;
    humanSeat = data.human_seat;
    seatNum = Number(humanSeat.split("_")[1]);
    $("lobby").classList.add("hidden");
    $("game").classList.remove("hidden");
    render(data.snapshot);
  });

  async function sendChoice(choice) {
    const res = await fetch(`/games/${gameId}/choice?seat=${seatNum}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choice }),
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    render(await res.json());
  }

  function render(snap) {
    const state = snap.state || {};
    $("roundInfo").textContent = `Round ${state.round ?? "?"} · stage ${state.stage ?? "?"}`;
    $("message").textContent = state.message || "";

    const res = state.resistance || {};
    $("resistance").textContent = res.in_progress || (res.active ? JSON.stringify(res) : "None active");

    const convoyEl = $("convoy");
    convoyEl.innerHTML = "";
    (state.convoy || []).forEach((u, i) => {
      const div = document.createElement("div");
      div.className = "unit" + (u.player === seatNum ? " yours" : "");
      div.innerHTML = `<strong>#${i}</strong> P${u.player} ${u.unit_type}<br/>T${u.tiredness}${u.under_influence ? "U" : ""} A${u.atrocities}<br/>carry ${JSON.stringify(u.carry)}<br/>zone ${u.zone || "?"}`;
      convoyEl.appendChild(div);
    });

    const playersEl = $("players");
    playersEl.innerHTML = "";
    (state.players || []).forEach((p) => {
      const div = document.createElement("div");
      div.className = "player" + (p.number === seatNum ? " you" : "");
      const cards = p.cards ? p.cards.join(", ") : `(${p.card_count})`;
      div.innerHTML = `<strong>Player ${p.number}</strong><br/>PP ${p.promotion_points} · cash ${p.total_cash} (+${p.cash_this_round})<br/>cards: ${cards}`;
      playersEl.appendChild(div);
    });

    const queues = (state.decks && state.decks.queues) || {};
    $("queues").textContent = JSON.stringify(queues, null, 2);

    const choicePanel = $("choicePanel");
    const endPanel = $("endPanel");
    if (snap.terminal) {
      choicePanel.classList.add("hidden");
      endPanel.classList.remove("hidden");
      $("ranking").textContent = JSON.stringify(snap.ranking || snap.stats, null, 2);
      return;
    }
    endPanel.classList.add("hidden");

    if (snap.pending && snap.legal_actions && snap.legal_actions.length) {
      choicePanel.classList.remove("hidden");
      $("choiceDesc").textContent = snap.pending.description || "";
      const opts = $("choiceOptions");
      opts.innerHTML = "";
      snap.legal_actions.slice(0, 80).forEach((vec, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "secondary";
        btn.textContent = `[${idx}] ${JSON.stringify(vec)}`;
        btn.addEventListener("click", () => sendChoice(vec));
        opts.appendChild(btn);
      });
    } else {
      choicePanel.classList.add("hidden");
    }
  }
})();
