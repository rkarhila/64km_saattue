(() => {
  const $ = (id) => document.getElementById(id);
  const CT = {
    CHOOSE_CARD: 0,
    CHOOSE_ACTION: 1,
    CHOOSE_CARDS_TO_DISCARD: 2,
    CASH_IN_CARDS: 3,
    CHOOSE_QUEUE_TO_SCOUT: 4,
    CHOOSE_PILLAGE_CARD: 5,
    CHOOSE_OFFICER: 6,
    CHOOSE_SERVICE: 7,
    YES_NO: 8,
    PLACE_UNITS: 9,
    CHOOSE_CARDS_TO_SCOUT: 10,
    REORDER_SCOUTED_CARDS: 11,
    LOG_PAUSE: 12,
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

  // On page load, check for imported state in URL
  const urlParams = new URLSearchParams(window.location.search);
  const importState = urlParams.get("state");
  if (importState) {
    (async () => {
      try {
        const res = await fetch("/games/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: importState }),
        });
        if (!res.ok) {
          alert("Pelin lataaminen epäonnistui: " + await res.text());
          return;
        }
        const data = await res.json();
        gameId = data.game_id;
        seatNum = Number(data.human_seat.split("_")[1]);
        $("lobby").classList.add("hidden");
        $("game").classList.remove("hidden");
        if ($("pauseToggle")) {
          $("pauseToggle").checked = data.snapshot.pause_after_actions !== false;
        }
        resetLocal();
        render(data.snapshot);

        // Clean query parameter from address bar
        const cleanUrl = new URL(window.location.href);
        cleanUrl.searchParams.delete("state");
        window.history.replaceState({}, document.title, cleanUrl.toString());
      } catch (err) {
        alert("Virhe pelin latauksessa: " + err);
      }
    })();
  }

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

  $("shareBtn").addEventListener("click", async () => {
    console.log("lastSnap status:", lastSnap);
    if (!lastSnap || !lastSnap.shareable_state) {
      alert("Ei jaettavaa pelitilaa saatavilla. Varmista, että olet käynnistänyt FastAPI-taustapalvelimen (python-palvelimen) uudelleen koodimuutosten jälkeen ja päivittänyt selaimen sivun (Ctrl+F5) tyhjentääksesi välimuistin.");
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("state", lastSnap.shareable_state);

    try {
      await navigator.clipboard.writeText(url.toString());
      const originalText = $("shareBtn").textContent;
      $("shareBtn").textContent = "Kopioitu!";
      $("shareBtn").disabled = true;
      setTimeout(() => {
        $("shareBtn").textContent = originalText;
        $("shareBtn").disabled = false;
      }, 2000);
    } catch (err) {
      alert("Linkin kopiointi epäonnistui: " + err);
    }
  });

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
      available = false,
      onClick = null,
    } = {}
  ) {
    const faceEl = document.createElement(clickable ? "button" : "div");
    if (clickable) faceEl.type = "button";
    faceEl.className =
      `face troop-${face.troop_key || "any"}` +
      (clickable ? " face-clickable" : "") +
      (strikethrough ? " face-strike" : "") +
      (available && !strikethrough ? " face-available" : "") +
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
      legalFaceIndices = null,
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
    const legalSet = Array.isArray(legalFaceIndices)
      ? new Set(legalFaceIndices)
      : null;
    const contrastMode = choosing || Boolean(legalSet) || resolved || frustrated;

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
      } else if (legalSet) {
        // Assign-time preview: strike faces that are not currently legal
        strike = !legalSet.has(faceIndex);
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
          available: contrastMode && !strike,
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

  function isPillagePick(snap) {
    return snap.pending && snap.pending.choicetype === CT.CHOOSE_PILLAGE_CARD;
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

  // 0-based layouts matching core.models._zones_for_players (E = last eCount).
  const ZONE_LAYOUT = {
    2: { A: [0], B: [1, 2], C: [3, 4], eCount: 1 },
    3: { A: [0, 1], B: [2, 3, 4], C: [5, 6], eCount: 2 },
    4: { A: [0, 1, 2], B: [3, 4, 5], C: [6, 7, 8], eCount: 3 },
    5: { A: [0, 1, 2, 3], B: [4, 5, 6, 7], C: [8, 9, 10, 11], eCount: 3 },
  };

  function zoneAtIndex(index, total, numPlayers) {
    const layout = ZONE_LAYOUT[numPlayers];
    if (!layout || total <= 0) return "?";
    if (index >= total - layout.eCount) return "E";
    for (const z of ["A", "B", "C"]) {
      if (layout[z].includes(index)) return z;
    }
    return "?";
  }

  function groupConsecutiveByZone(items) {
    const groups = [];
    items.forEach((item) => {
      if (!groups.length || groups[groups.length - 1].zone !== item.zone) {
        groups.push({ zone: item.zone, items: [item] });
      } else {
        groups[groups.length - 1].items.push(item);
      }
    });
    return groups;
  }

  function appendZoneGroups(el, groups, renderItem) {
    el.style.gridTemplateColumns = "";
    const table = document.createElement("table");
    table.className = "convoy-table";

    const headRow = document.createElement("tr");
    groups.forEach((g) => {
      const th = document.createElement("th");
      th.className = `zone-bar zone-${g.zone}`;
      th.colSpan = Math.max(1, g.items.length);
      th.scope = "colgroup";
      th.setAttribute("aria-label", `Vyöhyke ${g.zone}`);
      th.innerHTML = `<span class="zone-bar-label">${escapeHtml(g.zone)}</span>`;
      headRow.appendChild(th);
    });
    const thead = document.createElement("thead");
    thead.appendChild(headRow);
    table.appendChild(thead);

    const bodyRow = document.createElement("tr");
    groups.forEach((g) => {
      g.items.forEach((item) => {
        const td = document.createElement("td");
        td.className = `zone-${g.zone}`;
        td.appendChild(renderItem(item));
        bodyRow.appendChild(td);
      });
    });
    const tbody = document.createElement("tbody");
    tbody.appendChild(bodyRow);
    table.appendChild(tbody);

    el.appendChild(table);
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
    const numPlayers = (snap.state.players || []).length || 3;

    const items = pattern.map((owner, i) => ({
      zone: zoneAtIndex(i, pattern.length, numPlayers),
      owner,
      i,
    }));

    appendZoneGroups(el, groupConsecutiveByZone(items), ({ owner, i }) => {
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
      return wrap;
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

  function repeatToken(token, n) {
    const count = Math.max(0, Number(n) || 0);
    return token.repeat(count);
  }

  function unitTokenHtml(u) {
    const tired = repeatToken("🟢", u.tiredness);
    const influence = u.under_influence ? "🟡" : "";
    const atrocities = Math.max(0, Number(u.atrocities) || 0);
    const atrocitySpans = Array.from({ length: atrocities }, () =>
      '<span class="atrocity" title="raakuus" aria-label="raakuus"></span>'
    ).join("");
    const bits = [tired, influence, atrocitySpans].filter(Boolean).join("");
    return bits || '<span class="muted">—</span>';
  }

  function renderResistance(snap) {
    const el = $("resistanceBlock");
    if (!el) return;
    el.innerHTML = "";
    const res = (snap.state && snap.state.resistance) || {};
    const card = document.createElement("div");
    if (!res.active || !res.name) {
      card.className = "resistance-card inactive";
      card.innerHTML =
        `<div class="resistance-eyebrow">Vastarinta</div>` +
        `<div class="resistance-empty">Ei aktiivista</div>`;
      el.appendChild(card);
      return;
    }
    card.className = "resistance-card";
    const dmg = res.damage || {};
    const dmgBits = Object.keys(dmg)
      .map((k) => `${escapeHtml(k)} ${escapeHtml(String(dmg[k]))}`)
      .join(" · ");
    card.innerHTML =
      `<div class="resistance-eyebrow">Vastarinta · estää etenemisen</div>` +
      `<div class="resistance-name">${escapeHtml(res.name)}</div>` +
      `<div class="resistance-stats">` +
      `<div>Kestävyys <strong>${escapeHtml(String(res.durability ?? "?"))}</strong></div>` +
      `<div>Hyökkäys <strong>${escapeHtml(String(res.attack ?? "?"))}</strong>` +
      (res.target ? ` → ${escapeHtml(res.target)}` : "") +
      `</div>` +
      (res.loot ? `<div>Ryöstö <strong>${escapeHtml(String(res.loot))}</strong></div>` : "") +
      (dmgBits ? `<div>Vahinko: ${dmgBits}</div>` : "") +
      `</div>`;
    el.appendChild(card);
  }

  function renderConvoy(snap) {
    renderResistance(snap);

    if (isPlaceUnits(snap)) {
      renderSetupConvoy(snap);
      return;
    }

    const el = $("convoy");
    el.innerHTML = "";
    const cats = catalog(snap);
    const assign = isAssignFlow(snap);
    const assignSet = new Set((snap.pending && snap.pending.assign_units || []).map((u) => u.index));
    const convoy = snap.state.convoy || [];
    const numPlayers = (snap.state.players || []).length || 3;

    const items = convoy.map((u, i) => ({
      zone: u.zone || zoneAtIndex(i, convoy.length, numPlayers),
      u,
      i,
    }));

    appendZoneGroups(el, groupConsecutiveByZone(items), ({ u, i }) => {
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
        `<div class="unit-tokens">${unitTokenHtml(u)}</div>` +
        `<div class="unit-meta">carry ${escapeHtml(JSON.stringify(u.carry))}</div>`;
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
          const legality =
            (snap.pending &&
              snap.pending.assign_legality &&
              snap.pending.assign_legality[String(i)] &&
              snap.pending.assign_legality[String(i)][String(cid)]) ||
            null;
          slot.appendChild(
            buildActionCard(cats[String(cid)], {
              compact: true,
              draggable: true,
              legalFaceIndices: legality,
            })
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
        const activeCardId =
          choosing && snap.pending.payload.card_id != null
            ? snap.pending.payload.card_id
            : null;

        const stack = (action.cards && action.cards.length
          ? action.cards
          : action.card != null || action.face_up
            ? [action]
            : []);

        if (!stack.length) {
          slot.appendChild(buildCardBack(u.player));
        } else {
          const stackEl = document.createElement("div");
          stackEl.className =
            "card-stack" + (stack.length > 1 ? ` stack-n-${Math.min(stack.length, 4)}` : "");
          let anyChoosing = false;
          stack.forEach((entry, stackIdx) => {
            const layer = document.createElement("div");
            layer.className = "stack-layer";
            layer.style.setProperty("--stack-i", String(stackIdx));

            if (entry.face_up && entry.card != null && cats[String(entry.card)]) {
              const isActive =
                choosing &&
                (activeCardId == null
                  ? stackIdx === stack.length - 1
                  : entry.card === activeCardId);
              if (isActive) anyChoosing = true;
              layer.appendChild(
                buildActionCard(cats[String(entry.card)], {
                  compact: false,
                  highlightOptions: isActive ? highlight : null,
                  onFaceClick:
                    isActive && highlight
                      ? (option) => sendChoice([option])
                      : null,
                  chosenFaceIndex:
                    entry.resolved && entry.chosen_face_index != null
                      ? entry.chosen_face_index
                      : null,
                  resolved: Boolean(entry.resolved),
                  frustrated: Boolean(entry.frustrated),
                })
              );
            } else {
              layer.appendChild(buildCardBack(u.player));
            }
            stackEl.appendChild(layer);
          });
          slot.appendChild(stackEl);
          if (anyChoosing) slot.classList.add("choosing-action");
        }
      } else {
        slot.classList.add("empty-slot");
        slot.innerHTML = `<div class="slot-placeholder muted">—</div>`;
      }

      wrap.appendChild(slot);
      return wrap;
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

    if (isPillagePick(snap)) {
      title.textContent = "Valitse ryöstökortti";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = "Kortit ovat myös ryöstöjonossa. Napsauta yksi ryöstääksesi sen.";
      opts.appendChild(hint);
      const row = document.createElement("div");
      row.className = "card-row pillage-choices";
      const cards =
        (snap.pending.payload && snap.pending.payload.pillage_cards) || [];
      cards.forEach((c, idx) => {
        const el = document.createElement("button");
        el.type = "button";
        if (c.visible) {
          el.className = "queue-card face-up pillage-choice";
          el.innerHTML =
            `<div class="queue-card-name">${escapeHtml(c.name || `#${c.id}`)}</div>` +
            (c.detail
              ? `<div class="queue-card-detail">${escapeHtml(c.detail)}</div>`
              : "");
        } else {
          el.className = "queue-card face-down pillage-choice";
          el.innerHTML = `<div class="queue-card-mark">🂠</div><div class="queue-card-detail" style="margin-top: 5px; text-align: center;">Tuntematon (Slot ${idx + 1})</div>`;
        }
        el.addEventListener("click", () => sendChoice([c.id]));
        row.appendChild(el);
      });
      opts.appendChild(row);
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

    if (snap.pending.choicetype === CT.CHOOSE_CARDS_TO_SCOUT) {
      title.textContent = "Scout: Select cards to reveal";
      const need = snap.pending.payload.count;
      
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = `Please select exactly ${need} face-down card(s) by clicking on them directly in the queue tracks above. Selected cards will be highlighted with a yellow border.`;
      opts.appendChild(hint);

      const status = document.createElement("p");
      status.style.fontSize = "1.1rem";
      status.style.fontWeight = "bold";
      status.textContent = `Selected: ${payPicks.length} / ${need}`;
      opts.appendChild(status);

      const actions = document.createElement("div");
      actions.className = "choice-actions";
      
      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "secondary";
      clearBtn.textContent = "Clear";
      clearBtn.addEventListener("click", () => {
        payPicks = [];
        render(lastSnap);
      });

      const okBtn = document.createElement("button");
      okBtn.type = "button";
      okBtn.textContent = "Confirm Selection";
      okBtn.disabled = payPicks.length !== need;
      okBtn.addEventListener("click", () => {
        if (payPicks.length === need) {
          const choice = [...payPicks];
          payPicks = []; // clear selection
          sendChoice(choice);
        }
      });

      actions.appendChild(clearBtn);
      actions.appendChild(okBtn);
      opts.appendChild(actions);
      return;
    }

    if (snap.pending.choicetype === CT.REORDER_SCOUTED_CARDS) {
      title.textContent = `Scout: Reorder ${snap.pending.payload.queue} cards`;
      const cards = snap.pending.payload.cards || [];
      const need = cards.length;

      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = `Drag and drop the cards directly over each other in the queue above to rearrange them. First card (leftmost of the scouted ones) will be placed in the frontmost available slot.`;
      opts.appendChild(hint);

      const status = document.createElement("p");
      status.style.fontSize = "1.1rem";
      status.style.fontWeight = "bold";
      status.textContent = `Current Order Configured (Drag cards in the queue to rearrange)`;
      opts.appendChild(status);

      const actions = document.createElement("div");
      actions.className = "choice-actions";
      
      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "secondary";
      clearBtn.textContent = "Reset Order";
      clearBtn.addEventListener("click", () => {
        payPicks = [...snap.pending.options];
        render(lastSnap);
      });

      const okBtn = document.createElement("button");
      okBtn.type = "button";
      okBtn.textContent = "Confirm Order";
      okBtn.disabled = payPicks.length !== need;
      okBtn.addEventListener("click", () => {
        if (payPicks.length === need) {
          const choice = [...payPicks];
          payPicks = []; // clear selection
          sendChoice(choice);
        }
      });

      actions.appendChild(clearBtn);
      actions.appendChild(okBtn);
      opts.appendChild(actions);
      return;
    }

    if (snap.pending.choicetype === CT.LOG_PAUSE) {
      title.textContent = "Peli pysäytetty";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = "Lue loki ja napsauta Seuraava jatkaaksesi peliä.";
      opts.appendChild(hint);

      const actions = document.createElement("div");
      actions.className = "choice-actions";

      const contBtn = document.createElement("button");
      contBtn.type = "button";
      contBtn.textContent = "Seuraava (Continue)";
      contBtn.addEventListener("click", () => sendChoice([0]));

      actions.appendChild(contBtn);
      opts.appendChild(actions);
      return;
    }

    if (snap.pending.choicetype === CT.CASH_IN_CARDS) {
      title.textContent = "Vaihda kortteja rahaksi?";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = "Haluatko vaihtaa 4 toimintakorttia 1 PP/rahaan?";
      opts.appendChild(hint);

      const actions = document.createElement("div");
      actions.className = "choice-actions";

      const yesBtn = document.createElement("button");
      yesBtn.type = "button";
      yesBtn.textContent = "Kyllä (Yes)";
      yesBtn.addEventListener("click", () => sendChoice([1]));

      const noBtn = document.createElement("button");
      noBtn.type = "button";
      noBtn.className = "secondary";
      noBtn.textContent = "Ei (No)";
      noBtn.addEventListener("click", () => sendChoice([0]));

      actions.appendChild(yesBtn);
      actions.appendChild(noBtn);
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

  function renderDeckRows(snap) {
    const el = $("deckRows");
    if (!el) return;
    el.innerHTML = "";
    const rows =
      (snap.state && snap.state.decks && snap.state.decks.rows) || [];

    // Check if we are in CHOOSE_CARDS_TO_SCOUT or REORDER_SCOUTED_CARDS states
    const isScoutingSelection = snap.pending && snap.pending.choicetype === CT.CHOOSE_CARDS_TO_SCOUT;
    const isScoutingReorder = snap.pending && snap.pending.choicetype === CT.REORDER_SCOUTED_CARDS;

    // If reordering, ensure payPicks is initialized correctly
    if (isScoutingReorder) {
      const optsList = snap.pending.options || [];
      if (!Array.isArray(payPicks) || payPicks.length !== optsList.length || !optsList.every(o => payPicks.includes(o))) {
        payPicks = [...optsList];
      }
    }

    rows.forEach((row) => {
      const rowEl = document.createElement("div");
      rowEl.className = `deck-row deck-key-${row.key || "unknown"}`;

      // Left edge: discard pile
      const discard = document.createElement("div");
      discard.className = "pile-box discard";
      discard.innerHTML =
        `<span class="pile-kind">Poisto</span>` +
        `<span class="pile-name">${escapeHtml(row.label || "")}</span>` +
        `<span class="pile-count">${Number(row.discard) || 0}</span>`;
      rowEl.appendChild(discard);

      // Deck (draw pile)
      const draw = document.createElement("div");
      draw.className = "pile-box draw";
      draw.innerHTML =
        `<span class="pile-kind">Pakka</span>` +
        `<span class="pile-name">${escapeHtml(row.label || "")}</span>` +
        `<span class="pile-count">${Number(row.deck) || 0}</span>`;
      rowEl.appendChild(draw);

      // Queue: render back→front so index 0 (front) is rightmost
      const track = document.createElement("div");
      track.className = "queue-track";
      const queue = row.queue || [];

      let queueCode = null;
      if (row.key === "pillage") queueCode = 0;
      else if (row.key === "mauling") queueCode = 1;
      else if (row.key === "resistance") queueCode = 2;

      if (!queue.length) {
        const empty = document.createElement("div");
        empty.className = "queue-empty";
        empty.textContent = "—";
        track.appendChild(empty);
      } else {
        // Reordering specific variables
        const reorderIndices = (isScoutingReorder && row.key === snap.pending.payload.queue)
          ? [...snap.pending.options].sort((a,b) => a-b)
          : [];

        for (let i = queue.length - 1; i >= 0; i--) {
          const isFront = i === 0;

          let cardIdx = i;
          if (isScoutingReorder && row.key === snap.pending.payload.queue && reorderIndices.includes(i)) {
            const pos = reorderIndices.indexOf(i);
            cardIdx = payPicks[pos];
          }

          const card = queue[cardIdx];
          const cardEl = document.createElement("div");

          if (card && card.visible) {
            cardEl.className =
              "queue-card face-up" + (isFront ? " is-front" : "");
            cardEl.innerHTML =
              `<div class="queue-card-name">${escapeHtml(card.name || `#${card.id}`)}</div>` +
              (card.detail
                ? `<div class="queue-card-detail">${escapeHtml(card.detail)}</div>`
                : "");
          } else {
            cardEl.className =
              "queue-card face-down" + (isFront ? " is-front" : "");
            cardEl.innerHTML = `<div class="queue-card-mark">🂠</div>`;
          }

          // --- 1. SELECTION FLOW (Yellow border direct click) ---
          if (isScoutingSelection && queueCode !== null && card && !card.visible) {
            const option = queueCode * 100 + i;
            if ((snap.pending.options || []).includes(option)) {
              cardEl.classList.add("scout-selectable");

              const isSelected = payPicks.includes(option);
              if (isSelected) {
                cardEl.classList.add("scout-selected");
              }

              cardEl.addEventListener("click", () => {
                const need = snap.pending.payload.count;
                if (isSelected) {
                  payPicks = payPicks.filter((x) => x !== option);
                } else if (payPicks.length < need) {
                  payPicks = [...payPicks, option];
                }
                render(lastSnap);
              });
            }
          }

          // --- 2. REORDER FLOW (Drag-and-drop to switch places) ---
          if (isScoutingReorder && row.key === snap.pending.payload.queue && reorderIndices.includes(i)) {
            cardEl.classList.add("scout-reorderable");
            cardEl.draggable = true;

            // Drag Start
            cardEl.addEventListener("dragstart", (ev) => {
              ev.dataTransfer.setData("text/scout-reorder-value", cardIdx);
              cardEl.classList.add("dragging");
            });

            // Drag End
            cardEl.addEventListener("dragend", () => {
              cardEl.classList.remove("dragging");
            });

            // Drag Over
            cardEl.addEventListener("dragover", (ev) => {
              ev.preventDefault();
              cardEl.classList.add("drag-over");
            });

            // Drag Leave
            cardEl.addEventListener("dragleave", () => {
              cardEl.classList.remove("drag-over");
            });

            // Drop
            cardEl.addEventListener("drop", (ev) => {
              ev.preventDefault();
              cardEl.classList.remove("drag-over");

              const fromVal = Number(ev.dataTransfer.getData("text/scout-reorder-value"));
              const toVal = cardIdx;

              if (Number.isInteger(fromVal) && fromVal !== toVal) {
                const idxFrom = payPicks.indexOf(fromVal);
                const idxTo = payPicks.indexOf(toVal);
                if (idxFrom !== -1 && idxTo !== -1) {
                  const temp = payPicks[idxFrom];
                  payPicks[idxFrom] = payPicks[idxTo];
                  payPicks[idxTo] = temp;
                  render(lastSnap);
                }
              }
            });
          }

          track.appendChild(cardEl);
        }
      }
      rowEl.appendChild(track);
      el.appendChild(rowEl);
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

      // Prettify/translate the technical frustrated messages for easier player readability
      let displayText = text;
      if (text.includes(" frustrated on card ")) {
        // Example:
        // "blue panssarit frustrated on card 10 (unit#1 zone=A type=panssarit; resistance:3up/0hid mauling:2up/1hid pillage:0up/0hid): exit:zone ['A'] not in allowed 'E' for P; scout:troop P not in face limits ['I']; promote:troop P not in face limits ['L']"
        // Target format: "blue panssarit frustrated on card 10: wrong zone for "sayonara suckers", wrong troop type for Tiedustele or Ylennä."
        const frustratedRegex = /^(.+? frustrated on card \d+)(?:\s*\(.*?\))?:\s*(.+)$/i;
        const match = text.match(frustratedRegex);
        if (match) {
          const header = match[1];
          const rawReasons = match[2];
          
          // Split reasons by semicolon
          const reasons = rawReasons.split(";").map(r => r.trim()).filter(Boolean);
          const translatedReasons = [];

          let wrongZoneActions = [];
          let wrongTroopActions = [];
          let tooExpensiveActions = [];
          let otherBlockedActions = [];

          reasons.forEach((reason) => {
            const partMatch = reason.match(/^([^:]+):(.*)$/);
            if (partMatch) {
              const actionCode = partMatch[1].trim();
              const actionDetail = partMatch[2].trim();

              // Map action names to human-readable names (Finnish or English/quoted nicknames)
              const actionNames = {
                "exit": '"sayonara suckers" (Pakene)',
                "scout": 'Tiedustele (Scout)',
                "promote": 'Ylennä (Promote)',
                "pillage": 'Ryöstä (Pillage)',
                "attack": 'Hyökkää (Attack)',
                "assault": 'Assault',
                "bypass": 'Ohita (Bypass)',
                "defend": 'Puolusta (Defend)',
                "human shields": 'Ihmiskilvet (Human Shields)',
                "patrol": 'Partioi (Patrol)',
                "rest": 'Lepää (Rest)',
                "retreat": 'Peräänny (Retreat)',
                "search": 'Etsi (Search)',
                "service": 'Huolla (Service)',
                "sober_up": 'Sober Up',
                "wait": 'Wait',
                "suicidal_attack": 'Suicidal Attack'
              };

              const actionName = actionNames[actionCode.toLowerCase()] || actionCode;

              if (actionDetail.includes("zone")) {
                wrongZoneActions.push(actionName);
              } else if (actionDetail.includes("troop") || actionDetail.includes("limits")) {
                wrongTroopActions.push(actionName);
              } else if (actionDetail.includes("cost") || actionDetail.includes("hand")) {
                tooExpensiveActions.push(actionName);
              } else {
                otherBlockedActions.push(`${actionName} (${actionDetail})`);
              }
            } else {
              otherBlockedActions.push(reason);
            }
          });

          if (wrongZoneActions.length > 0) {
            translatedReasons.push(`wrong zone for ${wrongZoneActions.join(" or ")}`);
          }
          if (wrongTroopActions.length > 0) {
            translatedReasons.push(`wrong troop type for ${wrongTroopActions.join(" or ")}`);
          }
          if (tooExpensiveActions.length > 0) {
            translatedReasons.push(`too expensive for ${tooExpensiveActions.join(" or ")}`);
          }
          if (otherBlockedActions.length > 0) {
            translatedReasons.push(otherBlockedActions.join(", "));
          }

      if (translatedReasons.length > 0) {
            displayText = `${header}: ${translatedReasons.join(", ")}.`;
          } else {
            displayText = `${header}: no valid actions available.`;
          }
        }
      }

      // Prettify player color keywords and Player X mentions using HTML
      let html = escapeHtml(displayText);
      const colors = ["red", "green", "blue", "orange", "purple"];
      colors.forEach((color, num) => {
        // Match color word if followed by unit type, position info, or player keyword
        const regex = new RegExp(`\\b(${color})(?=\\s+(?:player|panssarit|jalkaväki|huolto|unit|panssari|logistics|panzer|infantry))`, "gi");
        html = html.replace(regex, `<span class="player-color-${num}" style="color: var(--pc); font-weight: bold;">$1</span>`);

        // Match capitalized colors for score display "Red", "Green", etc.
        const capColor = color.charAt(0).toUpperCase() + color.slice(1);
        const capRegex = new RegExp(`\\b(${capColor})\\b`, "g");
        html = html.replace(capRegex, `<span class="player-color-${num}" style="color: var(--pc); font-weight: bold;">$1</span>`);

        // Also match Player X
        const playerRegex = new RegExp(`\\b(Player\\s+${num})\\b`, "gi");
        html = html.replace(playerRegex, `<span class="player-color-${num}" style="color: var(--pc); font-weight: bold;">$1</span>`);
      });

      line.innerHTML = html;
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

    renderDeckRows(snap);
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
