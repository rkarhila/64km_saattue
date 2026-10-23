(() => {
  const $ = (id) => document.getElementById(id);
  const CT = {
    CHOOSE_CARD: 0,
    CHOOSE_ACTION: 1,
    CHOOSE_CARDS_TO_DISCARD: 2,
    CASH_IN_CARDS: 3,
    PLACE_UNITS: 9,
  };

  let gameId = null;
  let seatNum = 0;
  /** @type {Record<number, number|null>} unitIndex -> cardId */
  let slotCards = {};
  /** @type {Record<number, number|null>} convoySlot -> unit_type */
  let placementMap = {};
  /** @type {number[]} */
  let payPicks = [];
  /** @type {any} */
  let lastSnap = null;

  $("startBtn").addEventListener("click", async () => {
    const body = {
      num_players: Number($("numPlayers").value),
      human_seat: 0,
      seed: Number($("seed").value),
      pause_after_actions: $("lobbyPauseToggle")
        ? $("lobbyPauseToggle").checked
        : true,
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
    seatNum = Number(data.human_seat.split("_")[1]);
    $("lobby").classList.add("hidden");
    $("game").classList.remove("hidden");
    if ($("pauseToggle")) $("pauseToggle").checked = data.snapshot.pause_after_actions !== false;
    resetLocal();
    render(data.snapshot);
  });

  $("continueBtn").addEventListener("click", () => sendContinue());

  $("pauseToggle").addEventListener("change", async () => {
    if (!gameId) return;
    const res = await fetch(`/games/${gameId}/settings?seat=${seatNum}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pause_after_actions: $("pauseToggle").checked }),
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    resetLocal();
    render(await res.json());
  });

  function resetLocal() {
    slotCards = {};
    placementMap = {};
    payPicks = [];
  }

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
    resetLocal();
    render(await res.json());
  }

  async function sendContinue() {
    const res = await fetch(`/games/${gameId}/continue?seat=${seatNum}`, {
      method: "POST",
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    resetLocal();
    render(await res.json());
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function catalog(snap) {
    return {
      ...(snap.hand_cards || {}),
      ...(snap.placed_cards || {}),
      ...((snap.pending && snap.pending.card_catalog) || {}),
    };
  }

  function playerColorClass(playerNum) {
    return `player-color-${playerNum}`;
  }

  function buildFaceEl(
    face,
    {
      clickable = false,
      strikethrough = false,
      chosen = false,
      onClick = null,
    } = {}
  ) {
    const faceEl = document.createElement(clickable ? "button" : "div");
    if (clickable) faceEl.type = "button";
    faceEl.className =
      `face troop-${face.troop_key || "any"}` +
      (clickable ? " face-clickable" : "") +
      (strikethrough ? " face-strike" : "") +
      (chosen ? " face-chosen" : "");

    const head = document.createElement("div");
    head.className = "face-head";
    head.innerHTML = `<span>${escapeHtml(face.troop_label)}</span><span>${escapeHtml(face.zone || "")}</span>`;

    const title = document.createElement("div");
    title.className = "face-title";
    title.textContent = face.title;

    const meta = document.createElement("div");
    meta.className = "face-meta";
    meta.innerHTML =
      `<span class="cost">${escapeHtml(face.cost || "")}</span>` +
      `<span class="effects">${escapeHtml(face.effects || "")}</span>`;

    faceEl.appendChild(head);
    faceEl.appendChild(title);
    faceEl.appendChild(meta);
    if (onClick && clickable) faceEl.addEventListener("click", onClick);
    return faceEl;
  }

  function buildCardBack(playerNum) {
    const el = document.createElement("div");
    el.className = `action-card card-back ${playerColorClass(playerNum)}`;
    el.innerHTML =
      `<div class="card-back-inner">` +
      `<div class="card-back-mark">🂠</div>` +
      `<div class="card-back-label">P${playerNum}</div>` +
      `</div>`;
    return el;
  }

  function buildActionCard(
    cardData,
    {
      draggable = false,
      selectable = false,
      selected = false,
      disabled = false,
      compact = false,
      highlightOptions = null,
      chosenFaceIndex = null,
      resolved = false,
      frustrated = false,
      onFaceClick = null,
      onClick = null,
    } = {}
  ) {
    const el = document.createElement(selectable && !onFaceClick ? "button" : "div");
    if (el.tagName === "BUTTON") el.type = "button";
    el.className =
      "action-card" +
      (selected ? " selected" : "") +
      (compact ? " compact" : "") +
      (draggable ? " draggable" : "") +
      (frustrated ? " frustrated" : "");
    if (disabled && el.tagName === "BUTTON") el.disabled = true;

    if (draggable) {
      el.draggable = true;
      el.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.setData("text/card-id", String(cardData.id));
        ev.dataTransfer.effectAllowed = "move";
        el.classList.add("dragging");
      });
      el.addEventListener("dragend", () => el.classList.remove("dragging"));
    }

    const idBar = document.createElement("div");
    idBar.className = "card-id";
    idBar.textContent = `#${cardData.id}`;
    el.appendChild(idBar);

    const choosing = Boolean(onFaceClick && highlightOptions);

    (cardData.faces || []).forEach((face, faceIndex) => {
      let clickable = false;
      let strike = false;
      let chosen = false;
      let handler = null;

      if (choosing) {
        const match = highlightOptions.find(
          (a) => a.kind === "card" && a.face_index === faceIndex
        );
        if (match) {
          clickable = true;
          handler = () => onFaceClick(match.option);
        } else {
          strike = true; // impossible
        }
      } else if (resolved && !frustrated) {
        if (chosenFaceIndex != null && faceIndex === chosenFaceIndex) {
          chosen = true;
        } else {
          strike = true; // not chosen
        }
      } else if (frustrated) {
        strike = true;
      }

      el.appendChild(
        buildFaceEl(face, {
          clickable,
          strikethrough: strike,
          chosen,
          onClick: handler,
        })
      );
    });

    if (choosing && highlightOptions) {
      highlightOptions
        .filter((a) => a.kind === "officer")
        .forEach((a) => {
          const wrap = document.createElement("div");
          wrap.className = "officer-action";
          const tag = document.createElement("div");
          tag.className = "officer-tag";
          tag.textContent = "Upseeri";
          wrap.appendChild(tag);
          wrap.appendChild(
            buildFaceEl(a.face, {
              clickable: true,
              onClick: () => onFaceClick(a.option),
            })
          );
          el.appendChild(wrap);
        });
    }

    if (onClick && !onFaceClick) el.addEventListener("click", onClick);
    return el;
  }

  function isPlaceUnits(snap) {
    return snap.pending && snap.pending.choicetype === CT.PLACE_UNITS;
  }

  function isAssignFlow(snap) {
    const p = snap.pending;
    return (
      p &&
      p.choicetype === CT.CHOOSE_CARD &&
      (p.assign_units || []).length === p.num_choice &&
      p.num_choice >= 2
    );
  }

  function isActionSelect(snap) {
    return snap.pending && snap.pending.choicetype === CT.CHOOSE_ACTION;
  }

  function isPayCost(snap) {
    const p = snap.pending;
    return (
      p &&
      p.choicetype === CT.CHOOSE_CARDS_TO_DISCARD &&
      (p.payload || {}).reason === "pay_cost"
    );
  }

  function isDiscardPick(snap) {
    const p = snap.pending;
    return p && p.choicetype === CT.CHOOSE_CARDS_TO_DISCARD && !isPayCost(snap);
  }

  function isSingleCardPick(snap) {
    const p = snap.pending;
    return (
      p &&
      p.choicetype === CT.CHOOSE_CARD &&
      p.num_choice === 1 &&
      Array.isArray(p.options) &&
      p.options.every((o) => typeof o === "number")
    );
  }

  function assignedCardIds() {
    return new Set(Object.values(slotCards).filter((v) => v != null));
  }

  function wireDropZone(zoneEl, unitIndex, snap) {
    zoneEl.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
      zoneEl.classList.add("drag-over");
    });
    zoneEl.addEventListener("dragleave", () => zoneEl.classList.remove("drag-over"));
    zoneEl.addEventListener("drop", (ev) => {
      ev.preventDefault();
      zoneEl.classList.remove("drag-over");
      const cid = Number(ev.dataTransfer.getData("text/card-id"));
      if (!Number.isFinite(cid)) return;
      if (!(snap.pending.options || []).includes(cid)) return;
      const fromUnit = ev.dataTransfer.getData("text/from-unit");
      if (fromUnit !== "") slotCards[Number(fromUnit)] = null;
      Object.keys(slotCards).forEach((k) => {
        if (Number(k) !== unitIndex && slotCards[k] === cid) slotCards[k] = null;
      });
      slotCards[unitIndex] = cid;
      render(lastSnap);
    });
    zoneEl.addEventListener("click", () => {
      if (slotCards[unitIndex] != null) {
        slotCards[unitIndex] = null;
        render(lastSnap);
      }
    });
  }

  function renderSetupConvoy(snap) {
    const el = $("convoy");
    el.innerHTML = "";
    const pattern = (snap.pending && snap.pending.payload && snap.pending.payload.pattern) ||
      snap.setup_pattern ||
      [];
    const mySlots = new Set(
      (snap.pending && snap.pending.payload && snap.pending.payload.slots) || []
    );
    const troops = (snap.pending && snap.pending.payload && snap.pending.payload.troops) || [];
    const labelByType = Object.fromEntries(
      troops.map((t) => [t.unit_type, t.unit_type_label])
    );

    pattern.forEach((owner, i) => {
      const wrap = document.createElement("div");
      wrap.className =
        "unit-wrap setup-slot" +
        (owner === seatNum ? " yours" : "") +
        ` ${playerColorClass(owner)}`;

      const unit = document.createElement("div");
      unit.className =
        "unit" +
        (owner === seatNum ? " yours" : "") +
        ` ${playerColorClass(owner)}`;
      unit.innerHTML = `<strong>#${i}</strong><br/>Pelaaja ${owner}`;
      wrap.appendChild(unit);

      const slot = document.createElement("div");
      slot.className = "card-slot troop-slot";
      if (mySlots.has(i)) {
        slot.classList.add("drop-target");
        wireTroopDropZone(slot, i);
        const ut = placementMap[i];
        if (ut != null) {
          slot.appendChild(buildTroopChip(ut, labelByType[ut] || String(ut), true));
        } else {
          slot.innerHTML =
            `<div class="slot-placeholder">Pudota joukko<br/><small>paikka ${i}</small></div>`;
        }
      } else {
        slot.classList.add("empty-slot");
        slot.innerHTML = `<div class="slot-placeholder muted">P${owner}</div>`;
      }
      wrap.appendChild(slot);
      el.appendChild(wrap);
    });
  }

  function buildTroopChip(unitType, label, draggable) {
    const chip = document.createElement("div");
    chip.className = `troop-chip troop-type-${unitType}`;
    chip.textContent = label;
    chip.dataset.unitType = String(unitType);
    if (draggable) {
      chip.draggable = true;
      chip.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.setData("text/unit-type", String(unitType));
        const from = Object.keys(placementMap).find(
          (k) => placementMap[k] === unitType
        );
        if (from != null) ev.dataTransfer.setData("text/from-slot", from);
        ev.dataTransfer.effectAllowed = "move";
      });
    }
    return chip;
  }

  function wireTroopDropZone(zoneEl, slotIndex) {
    zoneEl.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      zoneEl.classList.add("drag-over");
    });
    zoneEl.addEventListener("dragleave", () => zoneEl.classList.remove("drag-over"));
    zoneEl.addEventListener("drop", (ev) => {
      ev.preventDefault();
      zoneEl.classList.remove("drag-over");
      const ut = Number(ev.dataTransfer.getData("text/unit-type"));
      if (![0, 1, 2].includes(ut)) return;
      const from = ev.dataTransfer.getData("text/from-slot");
      if (from !== "") placementMap[Number(from)] = null;
      Object.keys(placementMap).forEach((k) => {
        if (Number(k) !== slotIndex && placementMap[k] === ut) {
          placementMap[k] = null;
        }
      });
      placementMap[slotIndex] = ut;
      render(lastSnap);
    });
    zoneEl.addEventListener("click", () => {
      if (placementMap[slotIndex] != null) {
        placementMap[slotIndex] = null;
        render(lastSnap);
      }
    });
  }

  function renderConvoy(snap) {
    if (isPlaceUnits(snap)) {
      renderSetupConvoy(snap);
      return;
    }

    const el = $("convoy");
    el.innerHTML = "";
    const cats = catalog(snap);
    const assign = isAssignFlow(snap);
    const assignSet = new Set((snap.pending && snap.pending.assign_units || []).map((u) => u.index));

    (snap.state.convoy || []).forEach((u, i) => {
      const wrap = document.createElement("div");
      wrap.className =
        "unit-wrap" +
        (u.player === seatNum ? " yours" : "") +
        ` ${playerColorClass(u.player)}`;

      const unit = document.createElement("div");
      unit.className =
        "unit" +
        (u.player === seatNum ? " yours" : "") +
        ` ${playerColorClass(u.player)}`;
      const typeLabel = u.unit_type_label || u.unit_type;
      unit.innerHTML =
        `<strong>#${i}</strong> P${u.player} ${escapeHtml(typeLabel)}` +
        `<br/>T${u.tiredness}${u.under_influence ? " · 🟡" : ""} A${u.atrocities}` +
        `<br/>carry ${escapeHtml(JSON.stringify(u.carry))} · ${escapeHtml(u.zone || "?")}`;
      wrap.appendChild(unit);

      const slot = document.createElement("div");
      slot.className = "card-slot";
      const isDropTarget = assign && assignSet.has(i);
      const action = u.action || {};

      if (isDropTarget) {
        slot.classList.add("drop-target");
        wireDropZone(slot, i, snap);
        const cid = slotCards[i];
        if (cid != null && cats[String(cid)]) {
          slot.appendChild(
            buildActionCard(cats[String(cid)], { compact: true, draggable: true })
          );
          const inner = slot.querySelector(".action-card");
          if (inner) {
            inner.addEventListener("dragstart", (ev) => {
              ev.dataTransfer.setData("text/card-id", String(cid));
              ev.dataTransfer.setData("text/from-unit", String(i));
              ev.dataTransfer.effectAllowed = "move";
            });
          }
        } else {
          slot.innerHTML = `<div class="slot-placeholder">Pudota kortti<br/><small>${escapeHtml(typeLabel)}</small></div>`;
        }
      } else if (action.has_card) {
        const choosing =
          isActionSelect(snap) &&
          snap.pending.payload &&
          snap.pending.payload.unit_index === i;
        const highlight = choosing ? snap.pending.payload.actions : null;

        if (action.face_up && action.card != null && cats[String(action.card)]) {
          slot.appendChild(
            buildActionCard(cats[String(action.card)], {
              compact: false,
              highlightOptions: highlight,
              onFaceClick: highlight ? (option) => sendChoice([option]) : null,
              chosenFaceIndex:
                action.resolved && action.chosen_face_index != null
                  ? action.chosen_face_index
                  : null,
              resolved: Boolean(action.resolved),
              frustrated: Boolean(action.frustrated),
            })
          );
          if (choosing) slot.classList.add("choosing-action");
        } else {
          // Face-down for opponents until they act
          slot.appendChild(buildCardBack(u.player));
        }
      } else {
        slot.classList.add("empty-slot");
        slot.innerHTML = `<div class="slot-placeholder muted">—</div>`;
      }

      wrap.appendChild(slot);
      el.appendChild(wrap);
    });
  }

  function renderHand(snap) {
    const handEl = $("handCards");
    handEl.innerHTML = "";
    const cats = catalog(snap);
    const used = assignedCardIds();
    const payMode = isPayCost(snap) || isDiscardPick(snap);
    const need = snap.pending ? snap.pending.num_choice : 0;
    const payOpts = new Set((snap.pending && snap.pending.options) || []);

    Object.keys(snap.hand_cards || {})
      .map(Number)
      .sort((a, b) => a - b)
      .forEach((cid) => {
        if (used.has(cid)) return; // shown under a unit slot
        const selected = payPicks.includes(cid);
        const card = buildActionCard(cats[String(cid)] || snap.hand_cards[String(cid)], {
          draggable: isAssignFlow(snap),
          selectable: payMode,
          selected,
          disabled: payMode && !payOpts.has(cid),
          onClick: payMode
            ? () => {
                if (!payOpts.has(cid)) return;
                if (selected) {
                  payPicks = payPicks.filter((x) => x !== cid);
                } else if (payPicks.length < need) {
                  payPicks = [...payPicks, cid];
                }
                render(lastSnap);
              }
            : null,
        });
        handEl.appendChild(card);
      });
  }

  function renderContinuePanel(snap) {
    const panel = $("continuePanel");
    if (!panel) return;
    if (snap.awaiting_continue && !snap.terminal) {
      panel.classList.remove("hidden");
      const log = (snap.state && snap.state.log) || [];
      const last = log.length ? log[log.length - 1] : "";
      $("continueHint").textContent = last
        ? `Loki: ${last}`
        : "Toiminto kirjattu lokiin.";
    } else {
      panel.classList.add("hidden");
    }
  }

  function renderChoicePanel(snap) {
    const panel = $("choicePanel");
    const opts = $("choiceOptions");
    const title = $("choiceTitle");
    opts.innerHTML = "";

    if (snap.awaiting_continue || !snap.pending || snap.terminal) {
      panel.classList.add("hidden");
      return;
    }
    panel.classList.remove("hidden");
    $("choiceDesc").textContent = snap.pending.description || "";

    if (isPlaceUnits(snap)) {
      title.textContent = "Sijoita joukot";
      const slots = snap.pending.payload.slots || [];
      const troops = snap.pending.payload.troops || [];
      const used = new Set(
        Object.values(placementMap).filter((v) => v != null)
      );
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        "Vedä panssarit, jalkaväki ja huolto omiin korostettuihin paikkoihisi (yksi jokaiseen kolmannekseen).";
      opts.appendChild(hint);

      const tray = document.createElement("div");
      tray.className = "troop-tray";
      troops.forEach((t) => {
        if (used.has(t.unit_type)) return;
        tray.appendChild(
          buildTroopChip(t.unit_type, t.unit_type_label, true)
        );
      });
      opts.appendChild(tray);

      const allFilled = slots.every((s) => placementMap[s] != null);
      const actions = document.createElement("div");
      actions.className = "choice-actions";
      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "secondary";
      clearBtn.textContent = "Tyhjennä";
      clearBtn.addEventListener("click", () => {
        placementMap = {};
        render(lastSnap);
      });
      const okBtn = document.createElement("button");
      okBtn.type = "button";
      okBtn.textContent = "Vahvista";
      okBtn.disabled = !allFilled;
      okBtn.addEventListener("click", () => {
        const choice = slots.map((s) => placementMap[s]);
        sendChoice(choice);
      });
      actions.appendChild(clearBtn);
      actions.appendChild(okBtn);
      opts.appendChild(actions);
      return;
    }

    if (isAssignFlow(snap)) {
      title.textContent = "Jaa toimintakortit";
      const units = snap.pending.assign_units;
      const allFilled = units.every((u) => slotCards[u.index] != null);
      const actions = document.createElement("div");
      actions.className = "choice-actions";
      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "secondary";
      clearBtn.textContent = "Tyhjennä";
      clearBtn.addEventListener("click", () => {
        slotCards = {};
        render(lastSnap);
      });
      const okBtn = document.createElement("button");
      okBtn.type = "button";
      okBtn.textContent = "Vahvista";
      okBtn.disabled = !allFilled;
      okBtn.addEventListener("click", () => {
        const choice = units.map((u) => slotCards[u.index]);
        sendChoice(choice);
      });
      actions.appendChild(clearBtn);
      actions.appendChild(okBtn);
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = "Vedä kortteja kädestä yksiköiden alle.";
      opts.appendChild(hint);
      opts.appendChild(actions);
      return;
    }

    if (isActionSelect(snap)) {
      title.textContent = "Valitse toiminto";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = `Napsauta toimintoa kortilla (${(snap.pending.payload || {}).unit_type_label || "yksikkö"}).`;
      opts.appendChild(hint);
      // Card is also shown under the unit with clickable faces
      return;
    }

    if (isPayCost(snap) || isDiscardPick(snap)) {
      const need = snap.pending.num_choice;
      const payload = snap.pending.payload || {};
      title.textContent = isPayCost(snap) ? "Maksa hinta" : "Valitse kortit";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = isPayCost(snap)
        ? `Valitse ${need} korttia kädestä maksaaksesi: ${payload.action_name || ""}`
        : `Valitse ${need} korttia.`;
      opts.appendChild(hint);
      const status = document.createElement("p");
      status.textContent = `Valittu: ${payPicks.length} / ${need}`;
      opts.appendChild(status);
      const actions = document.createElement("div");
      actions.className = "choice-actions";
      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "secondary";
      clearBtn.textContent = "Tyhjennä";
      clearBtn.addEventListener("click", () => {
        payPicks = [];
        render(lastSnap);
      });
      const okBtn = document.createElement("button");
      okBtn.type = "button";
      okBtn.textContent = "Vahvista";
      okBtn.disabled = payPicks.length !== need;
      okBtn.addEventListener("click", () => {
        if (payPicks.length === need) sendChoice([...payPicks]);
      });
      actions.appendChild(clearBtn);
      actions.appendChild(okBtn);
      opts.appendChild(actions);
      return;
    }

    if (isSingleCardPick(snap)) {
      title.textContent = "Valitse kortti";
      const row = document.createElement("div");
      row.className = "card-row";
      const cats = catalog(snap);
      snap.pending.options.forEach((cid) => {
        const card = cats[String(cid)];
        if (!card) return;
        row.appendChild(
          buildActionCard(card, {
            selectable: true,
            onClick: () => sendChoice([cid]),
          })
        );
      });
      opts.appendChild(row);
      return;
    }

    // Fallback: legal action buttons (yes/no, cash-in, etc.)
    title.textContent = "Valintasi";
    (snap.legal_actions || []).slice(0, 80).forEach((vec, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "plain-opt secondary";
      btn.textContent = `[${idx}] ${JSON.stringify(vec)}`;
      btn.addEventListener("click", () => sendChoice(vec));
      opts.appendChild(btn);
    });
  }

  function renderLog(snap) {
    const logEl = $("gameLog");
    if (!logEl) return;
    const lines = (snap.state && snap.state.log) || [];
    const atBottom =
      logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
    logEl.innerHTML = "";
    lines.forEach((text) => {
      const line = document.createElement("div");
      line.className = "log-line";
      if (/kierros|alkaa|päättyy|——|=====/i.test(text)) {
        line.classList.add("round-marker");
      }
      line.textContent = text;
      logEl.appendChild(line);
    });
    if (atBottom || lines.length) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  }

  function render(snap) {
    lastSnap = snap;
    const state = snap.state || {};
    $("roundInfo").textContent = `Kierros ${state.round ?? "?"} · vaihe ${state.stage ?? "?"}`;
    $("message").textContent = state.message || "";

    const res = state.resistance || {};
    $("resistance").textContent =
      res.in_progress || (res.active ? JSON.stringify(res) : "Ei aktiivista");

    if ($("pauseToggle") && typeof snap.pause_after_actions === "boolean") {
      $("pauseToggle").checked = snap.pause_after_actions;
    }

    renderConvoy(snap);
    renderHand(snap);
    renderContinuePanel(snap);
    renderChoicePanel(snap);

    const playersEl = $("players");
    playersEl.innerHTML = "";
    (state.players || []).forEach((p) => {
      const div = document.createElement("div");
      div.className =
        "player" +
        (p.number === seatNum ? " you" : "") +
        ` ${playerColorClass(p.number)}`;
      const cards = p.cards ? p.cards.join(", ") : `(${p.card_count})`;
      div.innerHTML =
        `<strong>Pelaaja ${p.number}</strong>` +
        (p.number === seatNum ? " (sinä)" : "") +
        `<br/>PP ${p.promotion_points} · cash ${p.total_cash} (+${p.cash_this_round})` +
        `<br/>kortit: ${cards}`;
      playersEl.appendChild(div);
    });

    const queues = (state.decks && state.decks.queues) || {};
    $("queues").textContent = JSON.stringify(queues, null, 2);

    renderLog(snap);

    if (snap.terminal) {
      $("choicePanel").classList.add("hidden");
      $("endPanel").classList.remove("hidden");
      $("ranking").textContent = JSON.stringify(snap.ranking || snap.stats, null, 2);
    } else {
      $("endPanel").classList.add("hidden");
    }
  }
})();
