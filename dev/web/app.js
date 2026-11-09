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
  /** @type {Record<string, boolean[]>} deckKey -> visibility flags */
  let prevQueueVis = {};
  /** @type {Record<string, {tired:number,influence:number,damage:number,atrocity:number}>} */
  let prevStatus = {};
  /** Round number for which marker/action halos are kept. */
  let fxRound = null;
  /**
   * Static halo kinds gained this round: targetKey -> Set(kind).
   * Survives continue; cleared when the round advances.
   * @type {Record<string, Set<string>>}
   */
  let markerHalo = {};
  /**
   * Blink FX only while awaiting continue for the latest pause.
   * @type {Record<string, {addedKinds:string[], removedCounts:Record<string,number>}>}
   */
  let markerBlink = {};
  /**
   * Chosen action face halo this round: `${unitIdx}:${cardId}` -> {faceIndex, frustrated}.
   * @type {Record<string, {faceIndex:number|null, frustrated:boolean}>}
   */
  let actionHalo = {};
  /** Unit/card keys whose chosen action is currently blinking. */
  let actionBlink = new Set();
  /**
   * Last seen resolution signature per unit stack entry, to detect new resolves.
   * @type {Record<string, string>}
   */
  let prevActionSig = {};
  /** Just-revealed queue keys for flip animation: "pillage:0" */
  let pendingReveals = new Set();

  function syncBotLobbyUi() {
    const kind = $("botKind") ? $("botKind").value : "random";
    const sel = $("botId");
    if (sel) {
      const hasBots = [...sel.options].some((o) => o.value);
      sel.disabled = kind !== "rl" || !hasBots;
    }
  }

  async function loadLeagueBots() {
    const hint = $("botHint");
    const sel = $("botId");
    if (!sel) return;
    try {
      const res = await fetch("/league/bots");
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      sel.innerHTML = "";
      const bots = data.bots || [];
      if (data.error) {
        if (hint) hint.textContent = data.error;
      }
      if (!bots.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "(ei checkpointteja)";
        sel.appendChild(opt);
        if (hint && !data.error) {
          const searched = (data.searched || []).slice(0, 3).join(" · ");
          hint.textContent = data.exists
            ? `League ${data.league}: ei aktiivisia botteja.`
            : `Leaguea ei löydy (${data.league}). Etsittiin: ${searched}. Aja convoy-train tai CONVOY_LEAGUE.`;
        }
        syncBotLobbyUi();
        return;
      }
      bots.forEach((b) => {
        const opt = document.createElement("option");
        opt.value = b.id;
        opt.textContent = b.label || b.name;
        sel.appendChild(opt);
      });
      if ($("botKind") && $("botKind").value === "random") {
        $("botKind").value = "rl";
      }
      if (hint) {
        hint.textContent = `League: ${data.league} — ${bots.length} bottia.`;
      }
      syncBotLobbyUi();
    } catch (err) {
      sel.innerHTML = "";
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(lataus epäonnistui)";
      sel.appendChild(opt);
      if (hint) hint.textContent = "League-botteja ei voitu ladata: " + err;
      syncBotLobbyUi();
    }
  }

  if ($("botKind")) {
    $("botKind").addEventListener("change", syncBotLobbyUi);
    syncBotLobbyUi();
    loadLeagueBots();
  }

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
    const botKind = $("botKind") ? $("botKind").value : "random";
    const body = {
      num_players: Number($("numPlayers").value),
      human_seat: 0,
      seed: Number($("seed").value),
      pause_after_actions: $("lobbyPauseToggle")
        ? $("lobbyPauseToggle").checked
        : true,
      bot_kind: botKind,
    };
    if (botKind === "rl") {
      const botId = $("botId") ? $("botId").value : "";
      if (!botId) {
        alert("Valitse league-botti tai vaihda satunnaisiin.");
        return;
      }
      body.bot_id = botId;
    }
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
  $("randomChoiceBtn").addEventListener("click", () => sendRandomChoice());

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

  function clearRoundFx() {
    markerHalo = {};
    markerBlink = {};
    actionHalo = {};
    actionBlink = new Set();
  }

  function demoteBlinkToHalo() {
    // Continue clicked (or pause ended): stop blinking; static halo remains.
    markerBlink = {};
    actionBlink = new Set();
  }

  function resetPicks() {
    slotCards = {};
    placementMap = {};
    payPicks = [];
  }

  function resetLocal() {
    resetPicks();
    prevQueueVis = {};
    prevStatus = {};
    prevActionSig = {};
    fxRound = null;
    clearRoundFx();
    pendingReveals = new Set();
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
    resetPicks();
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
    resetPicks();
    // Stop prior blinks; static round halos stay. New pause in this snap can blink again.
    demoteBlinkToHalo();
    render(await res.json());
  }

  async function sendRandomChoice() {
    if (!lastSnap || lastSnap.terminal) return;
    if (lastSnap.awaiting_continue) {
      await sendContinue();
      return;
    }
    const legal = lastSnap.legal_actions || [];
    if (!legal.length) {
      alert("Ei laillisia valintoja.");
      return;
    }
    const pick = legal[Math.floor(Math.random() * legal.length)];
    await sendChoice(Array.isArray(pick) ? [...pick] : [pick]);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Client-side Finnish strings (mirror core/i18n.py keys).
  const I18N = {
    "deck.resistance": "Vastarinta",
    "deck.pillage": "Ryöstö",
    "deck.mauling": "Moukarointi",
    "resistance.ambush": "Väijytys",
    "resistance.counterattack": "Vastahyökkäys",
    "resistance.hitpoints": "Osumapisteet",
    "resistance.durability": "Kestävyys",
    "resistance.pillage_cards": "Ryöstökortteja",
    "resistance.damage": "Vahinko",
    "mauling.target_type": "Kohde / tyyppi",
    "mauling.target": "Kohde",
    "mauling.type": "Tyyppi",
    "mauling.damage": "Vahinko",
    "mauling.hit_category": "Osumaluokka",
    "mauling.discard": "Korttien poisto",
    "mauling.must_discard": "Poista {n} korttia.",
    "mauling.fail_hit": "Jos kortteja ei ole tarpeeksi, ota osumaluokan {m} vahinko.",
    "attack.A": "A (ilma)",
    "attack.G": "G (maa)",
    "attack.S": "S (sabotaasi)",
    "attack.R": "R (vastarinta)",
    "pillage.cash": "Rahaa",
    "pillage.loot": "Ryöstösaalis",
    "pillage.atrocities": "Hirmutekoja",
    "pillage.atrocities_if_under_influence": "Hirmuteko, jos humalassa",
    "pillage.cards": "Kortteja",
    "pillage.intoxicate": "Humalaannuttaa",
    "deck.officer": "Upseeri",
    "officer.always_on": "Aina päällä",
    "officer.discard": "Poista",
    "officer.troop": "Joukko",
    "officer.zone": "Alue",
    "officer.cost": "Hinta",
    "resistance.destroy_cash": "Tuhoaminen",
  };

  function t(key, vars) {
    let s = I18N[key] || key;
    if (vars) {
      Object.keys(vars).forEach((k) => {
        s = s.replaceAll(`{${k}}`, String(vars[k]));
      });
    }
    return s;
  }

  function attackTypeLabel(atype) {
    const letter = String(atype || "G").charAt(0).toUpperCase();
    return t(`attack.${letter}`) !== `attack.${letter}`
      ? t(`attack.${letter}`)
      : letter;
  }

  function fancyBox(title, linesHtml) {
    return (
      `<div class="fancy-section-box">` +
      (title ? `<span class="section-title">${escapeHtml(title)}</span>` : "") +
      linesHtml +
      `</div>`
    );
  }

  function renderResistanceFancyHtml(data, { eyebrow } = {}) {
    const name = data.name || "?";
    const ambushName = data.ambush_attack_name || data.effect?.ambush_attack || "-";
    const ambushDmg = data.ambush_damage ?? data.effect?.ambush_damage ?? "?";
    const ambushTarget =
      data.ambush_target_label ||
      data.effect?.ambush_target_label ||
      data.ambush_target ||
      data.effect?.ambush_target ||
      "";
    const counterName =
      data.resistance_attack_name || data.effect?.resistance_attack || "-";
    const counterDmg =
      data.resistance_damage ?? data.effect?.resistance_damage ?? "?";
    const durability = data.durability ?? data.effect?.durability ?? "?";
    const loot = data.loot ?? data.effect?.loot ?? 0;

    const ambushBox = fancyBox(
      t("resistance.ambush"),
      `<span><strong>${escapeHtml(String(ambushName))}</strong></span>` +
        `<span>${escapeHtml(t("resistance.damage"))}: <strong>${escapeHtml(String(ambushDmg))}</strong></span>` +
        (ambushTarget
          ? `<span>${escapeHtml(t("mauling.target"))}: <strong>${escapeHtml(String(ambushTarget))}</strong></span>`
          : "")
    );
    const counterBox = fancyBox(
      t("resistance.counterattack"),
      `<span><strong>${escapeHtml(String(counterName))}</strong></span>` +
        `<span>${escapeHtml(t("resistance.damage"))}: <strong>${escapeHtml(String(counterDmg))}</strong></span>`
    );
    const destroyCash = Number(
      data.cash_for_destroying ?? data.effect?.cash_for_destroying ?? 0
    );
    const destroyLabel = destroyCash > 0 ? `(+${destroyCash})` : "";
    const durBox = fancyBox(
      t("resistance.hitpoints"),
      `<span>${escapeHtml(t("resistance.durability"))}: <strong>${escapeHtml(String(durability))}</strong></span>` +
        (loot
          ? `<span>${escapeHtml(t("resistance.pillage_cards"))}: <strong>${escapeHtml(String(loot))} kpl</strong></span>`
          : "") +
        (destroyLabel
          ? `<span>${escapeHtml(t("resistance.destroy_cash"))}: <strong class="reward-chip contingent">${escapeHtml(destroyLabel)}</strong></span>`
          : "")
    );

    return (
      (eyebrow
        ? `<div class="fancy-eyebrow">${escapeHtml(eyebrow)}</div>`
        : `<div class="fancy-eyebrow">${escapeHtml(t("deck.resistance"))}</div>`) +
      `<div class="fancy-title">${escapeHtml(name)}` +
      (destroyLabel
        ? `<span class="reward-chip contingent title-cash" title="Vain jos vastarinta tuhotaan">${escapeHtml(destroyLabel)}</span>`
        : "") +
      `</div>` +
      `<div class="fancy-body">${ambushBox}${counterBox}${durBox}</div>`
    );
  }

  function formationMarginHtml(order) {
    const digits = String(order || "");
    if (!digits) return "";
    const players = 5;
    const cells = [...digits].map((ch, i) => {
      const seat = Number(ch) - 1;
      const third = i > 0 && i % players === 0 ? " formation-third" : "";
      return (
        `<span class="formation-cell player-color-${seat}${third}">` +
        `<span class="formation-digit">${escapeHtml(ch)}</span></span>`
      );
    }).join("");
    return (
      `<div class="formation-margin formation-left formation-full" aria-label="Lähtöjärjestys alhaalta ylös, ${escapeHtml(digits)}">` +
      cells +
      `</div>`
    );
  }

  function renderMaulingFancyHtml(card) {
    const effect = card.effect || {};
    const target = effect.target_label || effect.target || "?";
    const atype = effect.attack_type || "G";
    const hitCat = Number(effect.hit_category || 0);
    const discardN = Number(effect.discard || 0);
    const failHit = Number(effect.fail_hit_category || 0);
    const forms = card.formations || {};

    const targetBox = fancyBox(
      t("mauling.target_type"),
      `<span>${escapeHtml(t("mauling.target"))}: <strong>${escapeHtml(String(target))}</strong></span>` +
        `<span>${escapeHtml(t("mauling.type"))}: <strong>${escapeHtml(attackTypeLabel(atype))}</strong></span>`
    );

    let effectBox = "";
    if (discardN > 0) {
      effectBox = fancyBox(
        t("mauling.discard"),
        `<span>${escapeHtml(t("mauling.must_discard", { n: discardN }))}</span>` +
          (failHit > 0
            ? `<span>${escapeHtml(t("mauling.fail_hit", { m: failHit }))}</span>`
            : "")
      );
    } else if (hitCat > 0) {
      effectBox = fancyBox(
        t("mauling.damage"),
        `<span>${escapeHtml(t("mauling.hit_category"))}: <strong>${escapeHtml(String(hitCat))}</strong></span>`
      );
    }

    return (
      `<div class="formation-mid">` +
      formationMarginHtml(forms["5"]) +
      `<div class="formation-core">` +
      `<div class="fancy-eyebrow">${escapeHtml(t("deck.mauling"))}</div>` +
      `<div class="fancy-title">${escapeHtml(card.name || "?")}</div>` +
      `<div class="fancy-body">${targetBox}${effectBox}</div>` +
      `</div>` +
      `</div>`
    );
  }

  function renderPillageFancyHtml(card) {
    const reward = card.reward || {};
    const cash = Number(reward.cash || 0);
    const loot = Array.isArray(reward.loot) ? reward.loot : [];
    const atrocities = Number(reward.atrocities || 0);
    const atrocitiesIfDrunk = Number(reward.atrocities_if_under_influence || 0);
    const cards = Number(reward.cards || 0);
    const intoxicate = Number(reward.intoxicate || 0);
    const lootChips = loot.filter((v) => Number(v) > 0);
    const lines = [];
    if (cash > 0) {
      lines.push(
        `<span>${escapeHtml(t("pillage.cash"))}: <strong>${cash}</strong></span>`
      );
    }
    if (lootChips.length) {
      lines.push(
        `<span>${escapeHtml(t("pillage.loot"))}: <strong>${escapeHtml(lootChips.join(" · "))}</strong></span>`
      );
    }
    if (atrocities > 0) {
      lines.push(
        `<span>${escapeHtml(t("pillage.atrocities"))}: <strong>${atrocities}</strong></span>`
      );
    }
    if (atrocitiesIfDrunk > 0) {
      lines.push(
        `<span>${escapeHtml(t("pillage.atrocities_if_under_influence"))}: <strong>${atrocitiesIfDrunk}</strong></span>`
      );
    }
    if (cards > 0) {
      lines.push(
        `<span>${escapeHtml(t("pillage.cards"))}: <strong>${cards}</strong></span>`
      );
    }
    if (intoxicate > 0) {
      lines.push(
        `<span>${escapeHtml(t("pillage.intoxicate"))}</span>`
      );
    }
    const body = lines.length
      ? fancyBox("", lines.join(""))
      : fancyBox("", `<span class="muted">—</span>`);

    return (
      `<div class="fancy-eyebrow">${escapeHtml(t("deck.pillage"))}</div>` +
      `<div class="fancy-title">${escapeHtml(card.name || "?")}</div>` +
      `<div class="fancy-body">${body}</div>`
    );
  }

  function officerMode(card) {
    const hasDiscard = Boolean(
      card.discard_effect || card.action_type || card.discard_description
    );
    const hasPassive = Boolean(card.passive_effect || card.passive_description);
    if (hasDiscard && !hasPassive) return "discard";
    if (hasPassive && !hasDiscard) return "always_on";
    // Prefer discard if both somehow present; else always-on.
    if (hasDiscard) return "discard";
    return "always_on";
  }

  function officerActionDescription(card) {
    const mode = officerMode(card);
    if (mode === "discard") {
      return (
        card.discard_description ||
        card.action_type ||
        card.discard_effect ||
        "—"
      );
    }
    return card.passive_description || card.passive_effect || "—";
  }

  function officerTroopLabel(troop) {
    const raw = String(troop || "A").toUpperCase();
    if (raw === "A") return "P/I/L";
    return raw.split("").join("/");
  }

  function officerFaceHtml(card) {
    const face = card.display || {};
    const troop = face.troop_label || officerTroopLabel(card.troop_type);
    const zone = face.zone || card.zone || "";
    const title = face.title || card.name || "Upseeri";
    const cost = face.cost || "";
    const effects = face.effects || (face.mode === "passive" ? "✦" : "");
    const detail = face.detail || "";
    const mark =
      face.mode === "passive"
        ? `<span class="passive-clue" title="Muokkaa toista toimintoa">✦</span>`
        : "";
    return (
      `<div class="face officer-face troop-${escapeHtml(face.troop_key || "any")}">` +
      `<div class="face-head"><span>${escapeHtml(troop)}</span><span>${escapeHtml(zone)}</span></div>` +
      `<div class="face-title">${escapeHtml(title)}${mark}</div>` +
      `<div class="face-meta">` +
      `<span class="cost">${escapeHtml(cost)}</span>` +
      `<span class="effects">${escapeHtml(effects)}</span>` +
      `</div>` +
      (detail ? `<div class="officer-detail">${escapeHtml(detail)}</div>` : "") +
      `</div>`
    );
  }

  function renderOfficerFancyHtml(card) {
    return (
      `<div class="fancy-eyebrow">${escapeHtml(t("deck.officer"))}</div>` +
      officerFaceHtml(card)
    );
  }

  function renderOfficerTuckHtml(card) {
    const face = card.display || {};
    const title = face.title || card.name || "Upseeri";
    const cost = face.cost || "";
    const effects = face.effects || (officerMode(card) === "always_on" ? "✦" : "");
    const detail = face.detail || officerActionDescription(card);
    return (
      `<div class="officer-tuck-name">${escapeHtml(title)}</div>` +
      `<div class="face-meta officer-tuck-meta">` +
      `<span class="cost">${escapeHtml(cost)}</span>` +
      `<span class="effects">${escapeHtml(effects)}</span>` +
      `</div>` +
      (detail ? `<div class="officer-tuck-action">${escapeHtml(detail)}</div>` : "")
    );
  }

  function fillFancyQueueCard(el, card, deckKey) {
    el.classList.add("fancy-queue-card", `fancy-${deckKey}`);
    if (deckKey === "resistance" && (card.effect || card.ambush_attack_name != null)) {
      el.innerHTML = renderResistanceFancyHtml(card);
    } else if (deckKey === "mauling" && card.effect) {
      if (card.formations) el.classList.add("has-formation");
      el.innerHTML = renderMaulingFancyHtml(card);
    } else if (deckKey === "pillage" && card.reward) {
      el.innerHTML = renderPillageFancyHtml(card);
    } else if (
      deckKey === "officer" &&
      (card.officer_id != null ||
        card.passive_effect != null ||
        card.discard_effect != null ||
        card.passive_description ||
        card.action_type)
    ) {
      el.innerHTML = renderOfficerFancyHtml(card);
    } else {
      el.classList.remove("fancy-queue-card", `fancy-${deckKey}`);
      el.innerHTML =
        `<div class="queue-card-name">${escapeHtml(card.name || `#${card.id}`)}</div>` +
        (card.detail
          ? `<div class="queue-card-detail">${escapeHtml(card.detail)}</div>`
          : "");
    }
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
      halo = false,
      blink = false,
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
      (chosen ? " face-chosen" : "") +
      (halo ? " halo" : "") +
      (blink ? " blink" : "");

    const head = document.createElement("div");
    head.className = "face-head";
    head.innerHTML = `<span>${escapeHtml(face.troop_label)}</span><span>${escapeHtml(face.zone || "")}</span>`;

    const title = document.createElement("div");
    title.className = "face-title";
    const reward = face.reward || {};
    const rewardLabel =
      reward.label ||
      (Number(face.cash_bonus || 0) > 0 ? `(+${face.cash_bonus})` : "");
    if (rewardLabel) {
      title.innerHTML =
        `${escapeHtml(face.title)}` +
        `<span class="reward-chip contingent" title="Vain jos toiminto onnistuu / on merkityksellinen">${escapeHtml(
          rewardLabel
        )}</span>`;
    } else {
      title.textContent = face.title;
    }
    const clues = Array.isArray(face.passive_clues) ? face.passive_clues : [];
    if (clues.length) {
      const clue = document.createElement("span");
      clue.className = "passive-clue";
      clue.textContent = "✦";
      clue.title = clues
        .map((c) => c.name || c.effect || "Upseeri")
        .join(", ");
      title.appendChild(clue);
    }

    const meta = document.createElement("div");
    meta.className = "face-meta";
    meta.innerHTML =
      `<span class="cost">${escapeHtml(face.cost || "")}</span>` +
      `<span class="effects">${escapeHtml(face.effects || "")}</span>`;

    faceEl.appendChild(head);
    faceEl.appendChild(title);
    faceEl.appendChild(meta);
    if (onClick && clickable) faceEl.addEventListener("click", onClick);
    bindActionTip(faceEl, face.help);
    return faceEl;
  }

  const actionTipHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  let actionTipEl = null;

  function actionTip() {
    if (actionTipEl) return actionTipEl;
    actionTipEl = document.createElement("div");
    actionTipEl.id = "actionTip";
    actionTipEl.className = "action-tip hidden";
    actionTipEl.setAttribute("role", "tooltip");
    document.body.appendChild(actionTipEl);
    return actionTipEl;
  }

  function hideActionTip() {
    const tip = actionTip();
    tip.classList.add("hidden");
    tip.innerHTML = "";
  }

  function showActionTip(anchor, help) {
    const tip = actionTip();
    tip.innerHTML =
      `<div class="tip-fi-title">${escapeHtml(help.finnish_title || "")}</div>` +
      `<p class="tip-fi">${escapeHtml(help.finnish_explanation || "")}</p>`;
    tip.classList.remove("hidden");
    const rect = anchor.getBoundingClientRect();
    const width = tip.offsetWidth;
    const height = tip.offsetHeight;
    let left = rect.right + 10;
    if (left + width > window.innerWidth - 8) left = rect.left - width - 10;
    if (left < 8) left = 8;
    let top = rect.top;
    if (top + height > window.innerHeight - 8) top = window.innerHeight - height - 8;
    if (top < 8) top = 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }

  function bindActionTip(faceEl, help) {
    if (!actionTipHover || !help) return;
    if (!help.finnish_explanation) return;
    faceEl.classList.add("has-action-tip");
    faceEl.addEventListener("mouseenter", () => showActionTip(faceEl, help));
    faceEl.addEventListener("mouseleave", hideActionTip);
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
      chosenHalo = false,
      chosenBlink = false,
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
      (frustrated ? " frustrated" : "") +
      (frustrated && chosenHalo ? " halo" : "") +
      (frustrated && chosenBlink ? " blink" : "");
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

    const facesList = cardData.faces || [];
    const troopSlots = facesInTroopSlots(facesList);
    const faceEntries = troopSlots
      ? troopSlots.map((slot, slotIndex) =>
          slot
            ? { face: slot.face, faceIndex: slot.faceIndex }
            : { emptyKey: TROOP_SLOT_ORDER[slotIndex] }
        )
      : facesList.map((face, faceIndex) => ({ face, faceIndex }));

    faceEntries.forEach((entry) => {
      if (entry.emptyKey) {
        const emptyFaceEl = document.createElement("div");
        emptyFaceEl.className = `face empty-face troop-${entry.emptyKey}`;
        emptyFaceEl.setAttribute("aria-hidden", "true");
        el.appendChild(emptyFaceEl);
        return;
      }
      const face = entry.face;
      const faceIndex = entry.faceIndex;
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

      const faceEl = buildFaceEl(face, {
        clickable,
        strikethrough: strike,
        chosen,
        available: contrastMode && !strike,
        halo: Boolean(chosen && chosenHalo),
        blink: Boolean(chosen && chosenBlink),
        onClick: handler,
      });

      if (!troopSlots && facesList.length === 1) {
        faceEl.classList.add("single-action-face");
      }

      el.appendChild(faceEl);
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
      p.num_choice >= 1
    );
  }

  const TROOP_SLOT_ORDER = ["panzer", "infantry", "logistics", "any"];

  function facesInTroopSlots(faces) {
    if (!Array.isArray(faces) || faces.length !== 3) return null;
    const slots = TROOP_SLOT_ORDER.map(() => null);
    for (let faceIndex = 0; faceIndex < faces.length; faceIndex++) {
      const face = faces[faceIndex];
      const slot = TROOP_SLOT_ORDER.indexOf(face.troop_key || "");
      if (slot < 0 || slots[slot]) return null;
      slots[slot] = { face, faceIndex };
    }
    return slots;
  }

  function isActionSelect(snap) {
    return snap.pending && snap.pending.choicetype === CT.CHOOSE_ACTION;
  }

  function isPillagePick(snap) {
    return snap.pending && snap.pending.choicetype === CT.CHOOSE_PILLAGE_CARD;
  }

  function isOfficerPick(snap) {
    return snap.pending && snap.pending.choicetype === CT.CHOOSE_OFFICER;
  }

  function normalizeOfficers(raw) {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((o) => {
        if (o && typeof o === "object") return o;
        if (typeof o === "string") return { name: o };
        return null;
      })
      .filter(Boolean);
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

  function statusCountsForUnit(u) {
    return {
      tired: Math.max(0, Number(u.tiredness) || 0),
      influence: Number(u.under_influence) > 0 ? 1 : 0,
      atrocity: Math.max(0, Number(u.atrocities) || 0),
    };
  }

  function statusCountsForResistance(_res) {
    return { tired: 0, influence: 0, atrocity: 0 };
  }

  function chipsHtml(
    counts,
    { haloKinds, blinkKinds, removedCounts, damageMarkers, blinkDamage } = {}
  ) {
    const parts = [];
    const order = [
      ["tired", counts.tired],
      ["influence", counts.influence],
      ["atrocity", counts.atrocity],
    ];
    order.forEach(([kind, n]) => {
      for (let i = 0; i < n; i++) {
        const classes = ["status-chip", kind];
        if (haloKinds && haloKinds.has(kind)) {
          classes.push("halo");
          if (blinkKinds && blinkKinds.has(kind)) classes.push("blink");
        }
        parts.push(`<span class="${classes.join(" ")}"></span>`);
      }
    });
    // Ghost chips with blinking red X only while this pause is awaiting continue.
    if (removedCounts) {
      ["tired", "influence", "atrocity"].forEach((kind) => {
        const n = removedCounts[kind] || 0;
        for (let i = 0; i < n; i++) {
          parts.push(
            `<span class="status-chip ${kind} removed blink" aria-hidden="true">` +
              `<span class="chip-x">×</span></span>`
          );
        }
      });
    }
    const cards = damageCardsHtml(damageMarkers, {
      blinkFresh: Boolean(blinkDamage),
    });
    const body = parts.join("") + cards;
    return body
      ? `<div class="status-overlay">${body}</div>`
      : `<div class="status-overlay"><span class="muted">—</span></div>`;
  }

  function moneyCardsHtml(counters, blink) {
    return (counters || [])
      .map((counter) => {
        const value = Number(counter.value);
        const shown = Number.isFinite(value) ? value : "";
        const fresh = blink && counter.fresh ? " blink" : "";
        return `<span class="money-card money-${shown}${fresh}">${shown}$</span>`;
      })
      .join("");
  }

  function damageCardsHtml(markers, { blinkFresh } = {}) {
    return (markers || [])
      .map((marker) => {
        const damage = Number(marker.damage);
        const blink = blinkFresh && marker.fresh ? " blink" : "";
        const shown = Number.isFinite(damage) ? damage : "";
        return (
          `<span class="dmg-card${blink}" title="vahinko">` +
          `<span class="dmg-boom" aria-hidden="true">💥</span>` +
          `<span class="dmg-num">${shown}</span></span>`
        );
      })
      .join("");
  }

  function unitTokenHtml(u, opts) {
    return chipsHtml(statusCountsForUnit(u), {
      ...opts,
      damageMarkers: u.damage_markers || [],
    });
  }

  function pileOrigin(kind) {
    const pile = document.querySelector(`#markerTray .marker-pile[data-kind="${kind}"]`);
    if (!pile) return null;
    const r = pile.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }

  function flyChipsTo(targetEl, kind, count) {
    if (!targetEl || count <= 0) return;
    const origin = pileOrigin(kind);
    const destBox = targetEl.getBoundingClientRect();
    if (!origin || !destBox.width) return;
    for (let i = 0; i < count; i++) {
      const chip = document.createElement("span");
      chip.className = `status-chip ${kind} flying`;
      const jitter = (Math.random() - 0.5) * 10;
      chip.style.left = `${origin.x - 6}px`;
      chip.style.top = `${origin.y - 6}px`;
      document.body.appendChild(chip);
      // Force layout then animate to target.
      void chip.offsetWidth;
      const dx = destBox.left + destBox.width * 0.35 + jitter - 6;
      const dy = destBox.top + 8 + i * 3;
      chip.style.left = `${dx}px`;
      chip.style.top = `${dy}px`;
      setTimeout(() => chip.remove(), 600);
    }
  }

  function syncFxRound(snap) {
    const round = snap.state && snap.state.round;
    if (fxRound != null && round != null && round !== fxRound) {
      clearRoundFx();
      prevActionSig = {};
    }
    if (round != null) fxRound = round;
  }

  function animateStatusDeltas(key, nextCounts, targetEl, { pauseActive, trackHalo } = {}) {
    // First sighting: baseline only (avoid flying/haloing every existing marker).
    if (prevStatus[key] == null) {
      prevStatus[key] = { ...nextCounts };
      return {
        haloKinds: new Set(markerHalo[key] || []),
        blinkKinds: new Set(),
        removedCounts: null,
      };
    }
    const prev = prevStatus[key];
    const addedKinds = new Set();
    const removedCounts = { tired: 0, influence: 0, atrocity: 0 };
    ["tired", "influence", "atrocity"].forEach((kind) => {
      const delta = (nextCounts[kind] || 0) - (prev[kind] || 0);
      if (delta > 0) {
        addedKinds.add(kind);
        flyChipsTo(targetEl, kind, delta);
      } else if (delta < 0) {
        removedCounts[kind] = -delta;
      }
    });
    prevStatus[key] = { ...nextCounts };

    if (trackHalo) {
      if (!markerHalo[key]) markerHalo[key] = new Set();
      addedKinds.forEach((kind) => markerHalo[key].add(kind));
    }

    if (pauseActive) {
      if (addedKinds.size || Object.values(removedCounts).some((n) => n > 0)) {
        markerBlink[key] = {
          addedKinds: [...addedKinds],
          removedCounts: { ...removedCounts },
        };
      }
    }

    const blink = markerBlink[key];
    return {
      haloKinds: new Set(markerHalo[key] || []),
      blinkKinds: new Set((blink && blink.addedKinds) || []),
      removedCounts: blink ? { ...blink.removedCounts } : null,
    };
  }

  function noteResolvedAction(unitIdx, entry, pauseActive) {
    if (!entry || !entry.resolved || entry.card == null) return;
    const key = `${unitIdx}:${entry.card}`;
    const sig = [
      entry.resolved ? 1 : 0,
      entry.frustrated ? 1 : 0,
      entry.chosen_face_index == null ? "x" : entry.chosen_face_index,
    ].join(":");
    const prev = prevActionSig[key];
    prevActionSig[key] = sig;
    if (prev === sig) {
      // Unchanged; keep existing halo/blink state.
      return;
    }
    if (prev == null && !pauseActive) {
      // First sighting outside a pause (e.g. page load) — no FX.
      return;
    }
    if (entry.resolved && (prev == null || prev !== sig)) {
      actionHalo[key] = {
        faceIndex:
          entry.chosen_face_index != null ? entry.chosen_face_index : null,
        frustrated: Boolean(entry.frustrated),
      };
      if (pauseActive) actionBlink.add(key);
    }
  }

  function actionFxFor(unitIdx, cardId) {
    const key = `${unitIdx}:${cardId}`;
    const halo = actionHalo[key];
    if (!halo) return { chosenHalo: false, chosenBlink: false };
    return {
      chosenHalo: true,
      chosenBlink: actionBlink.has(key),
      haloFaceIndex: halo.faceIndex,
      haloFrustrated: halo.frustrated,
    };
  }

  function noteQueueReveals(snap) {
    const rows =
      (snap.state && snap.state.decks && snap.state.decks.rows) || [];
    rows.forEach((row) => {
      if (!row || !row.key) return;
      const queue = row.queue || [];
      const prev = prevQueueVis[row.key] || [];
      queue.forEach((card, i) => {
        const vis = !!(card && card.visible);
        if (vis && prev[i] === false) {
          pendingReveals.add(`${row.key}:${i}`);
        }
      });
      prevQueueVis[row.key] = queue.map((c) => !!(c && c.visible));
    });
  }

  function renderResistance(snap) {
    const el = $("resistanceBlock");
    if (!el) return;
    el.innerHTML = "";
    const res = (snap.state && snap.state.resistance) || {};
    const struck = Boolean(snap.awaiting_continue && snap.state && snap.state.resistance_struck);
    const card = document.createElement("div");
    if ((!res.active || !res.name) && !struck) {
      card.className = "resistance-card inactive";
      card.innerHTML =
        `<div class="resistance-eyebrow">Vastarinta</div>` +
        `<div class="resistance-empty">Ei aktiivista</div>`;
      el.appendChild(card);
      return;
    }
    const destroyed = struck && !res.active;
    card.className =
      "resistance-card fancy-queue-card fancy-resistance" +
      (struck ? " hit-halo" : "") +
      (destroyed ? " destroyed-wait" : "");
    card.dataset.statusTarget = "resistance";
    card.innerHTML = renderResistanceFancyHtml(res, {
      eyebrow: `${t("deck.resistance")} · este`,
    });
    el.appendChild(card);
    const counts = statusCountsForResistance(res);
    const pauseActive = Boolean(
      snap.pause_after_actions && snap.awaiting_continue
    );
    const deltaOpts = animateStatusDeltas("resistance", counts, card, {
      pauseActive,
      trackHalo: Boolean(snap.pause_after_actions),
    });
    const overlay = document.createElement("div");
    overlay.innerHTML = chipsHtml(counts, {
      ...deltaOpts,
      damageMarkers: res.damage_markers || [],
      blinkDamage: pauseActive,
    });
    card.appendChild(overlay.firstChild);
    if (destroyed) {
      const cross = document.createElement("div");
      cross.className = "resistance-cross";
      cross.setAttribute("aria-hidden", "true");
      cross.textContent = "✕";
      card.appendChild(cross);
    }
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
    const struckUnits = new Set(
      snap.awaiting_continue ? (snap.state.struck_units || []) : []
    );

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
        ` ${playerColorClass(u.player)}` +
        (struckUnits.has(i) ? " unit-hit" : "");
      const typeLabel = u.unit_type_label || u.unit_type;
      unit.dataset.statusTarget = `unit-${i}`;
      const counts = statusCountsForUnit(u);
      // Animate after element is in DOM (below).
      unit.innerHTML =
        `<strong>#${i}</strong> P${u.player} ${escapeHtml(typeLabel)}` +
        `<div class="unit-tokens"></div>` +
        `<div class="unit-meta">carry ${escapeHtml(JSON.stringify(u.carry))}</div>`;
      wrap.appendChild(unit);
      const pauseActive = Boolean(
        snap.pause_after_actions && snap.awaiting_continue
      );
      const deltaOpts = animateStatusDeltas(`unit-${i}`, counts, unit, {
        pauseActive,
        trackHalo: Boolean(snap.pause_after_actions),
      });
      unit.querySelector(".unit-tokens").innerHTML = unitTokenHtml(u, {
        ...deltaOpts,
        blinkDamage: pauseActive,
      });

      const slot = document.createElement("div");
      slot.className = "card-slot";
      const officers = normalizeOfficers(u.officers);
      if (officers.length) slot.classList.add("has-officer");
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
              noteResolvedAction(i, entry, pauseActive);
              const fx = actionFxFor(i, entry.card);
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
                      : fx.haloFaceIndex != null
                        ? fx.haloFaceIndex
                        : null,
                  resolved: Boolean(entry.resolved) || Boolean(fx.chosenHalo),
                  frustrated:
                    Boolean(entry.frustrated) || Boolean(fx.haloFrustrated),
                  chosenHalo: Boolean(fx.chosenHalo),
                  chosenBlink: Boolean(fx.chosenBlink),
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
      } else if (!officers.length) {
        slot.classList.add("empty-slot");
        slot.innerHTML = `<div class="slot-placeholder muted">—</div>`;
      } else {
        slot.innerHTML = `<div class="slot-placeholder muted">—</div>`;
      }

      if (officers.length) {
        const tuckRow = document.createElement("div");
        tuckRow.className = "officer-tucks";
        officers.forEach((off) => {
          const tuck = document.createElement("div");
          tuck.className = "officer-tuck";
          tuck.title = [
            off.name,
            off.passive_description || off.passive_effect,
            officerActionDescription(off) || off.discard_description,
          ]
            .filter(Boolean)
            .join(" — ");
          tuck.innerHTML = renderOfficerTuckHtml(off);
          tuckRow.appendChild(tuck);
        });
        slot.appendChild(tuckRow);
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
    const singlePick = isSingleCardPick(snap);
    const need = snap.pending ? snap.pending.num_choice : 0;
    const payOpts = new Set((snap.pending && snap.pending.options) || []);
    const singleOpts = singlePick ? new Set(snap.pending.options) : null;

    Object.keys(snap.hand_cards || {})
      .map(Number)
      .sort((a, b) => a - b)
      .forEach((cid) => {
        if (used.has(cid)) return; // shown under a unit slot
        const selected = payPicks.includes(cid);
        const canSingle = Boolean(singleOpts && singleOpts.has(cid));
        const card = buildActionCard(cats[String(cid)] || snap.hand_cards[String(cid)], {
          draggable: isAssignFlow(snap),
          selectable: payMode || canSingle,
          selected,
          disabled: (payMode && !payOpts.has(cid)) || (singlePick && !canSingle),
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
            : canSingle
              ? () => sendChoice([cid])
              : null,
        });
        handEl.appendChild(card);
      });
  }

  function prettifyLogLine(text) {
    let displayText = text;
    if (text.includes(" frustrated on card ")) {
      // Example:
      // "blue panssarit frustrated on card 10 (...): exit:zone ['A'] not in allowed 'E' for P; ..."
      // Target: "blue panssarit frustrated on card 10: wrong zone for "sayonara suckers", ..."
      const frustratedRegex =
        /^(.+? frustrated on card \d+)(?:\s*\(.*?\))?:\s*(.+)$/i;
      const match = text.match(frustratedRegex);
      if (match) {
        const header = match[1];
        const rawReasons = match[2];
        const reasons = rawReasons
          .split(";")
          .map((r) => r.trim())
          .filter(Boolean);
        const translatedReasons = [];
        let wrongZoneActions = [];
        let wrongTroopActions = [];
        let tooExpensiveActions = [];
        let otherBlockedActions = [];

        const actionNames = {
          exit: '"sayonara suckers" (Pakene)',
          scout: "Tiedustele (Scout)",
          sigint: "Signaalitiedustelu (Sigint)",
          promote: "Ylennä (Promote)",
          pillage: "Ryöstä (Pillage)",
          attack: "Hyökkää (Attack)",
          assault: "Assault",
          bypass: "Ohita (Bypass)",
          defend: "Puolusta (Defend)",
          "human shields": "Ihmiskilvet (Human Shields)",
          patrol: "Partioi (Patrol)",
          rest: "Lepää (Rest)",
          retreat: "Peräänny (Retreat)",
          search: "Etsi (Search)",
          service: "Huolla (Service)",
          sober_up: "Sober Up",
          wait: "Wait",
          suicidal_attack: "Suicidal Attack",
        };

        reasons.forEach((reason) => {
          const partMatch = reason.match(/^([^:]+):(.*)$/);
          if (partMatch) {
            const actionCode = partMatch[1].trim();
            const actionDetail = partMatch[2].trim();
            const actionName =
              actionNames[actionCode.toLowerCase()] || actionCode;
            if (actionDetail.includes("zone")) {
              wrongZoneActions.push(actionName);
            } else if (
              actionDetail.includes("troop") ||
              actionDetail.includes("limits")
            ) {
              wrongTroopActions.push(actionName);
            } else if (
              actionDetail.includes("cost") ||
              actionDetail.includes("hand")
            ) {
              tooExpensiveActions.push(actionName);
            } else {
              otherBlockedActions.push(`${actionName} (${actionDetail})`);
            }
          } else {
            otherBlockedActions.push(reason);
          }
        });

        if (wrongZoneActions.length > 0) {
          translatedReasons.push(
            `wrong zone for ${wrongZoneActions.join(" or ")}`
          );
        }
        if (wrongTroopActions.length > 0) {
          translatedReasons.push(
            `wrong troop type for ${wrongTroopActions.join(" or ")}`
          );
        }
        if (tooExpensiveActions.length > 0) {
          translatedReasons.push(
            `too expensive for ${tooExpensiveActions.join(" or ")}`
          );
        }
        if (otherBlockedActions.length > 0) {
          translatedReasons.push(otherBlockedActions.join(", "));
        }

        displayText =
          translatedReasons.length > 0
            ? `${header}: ${translatedReasons.join(", ")}.`
            : `${header}: no valid actions available.`;
      }
    }
    return displayText;
  }

  function renderContinuePanel(snap) {
    const panel = $("continuePanel");
    if (!panel) return;
    // Sidebar stays visible during the game; only the continue action block toggles.
    panel.classList.remove("hidden");
    const actions = $("continueActions");
    const awaiting = Boolean(snap.awaiting_continue && !snap.terminal);
    panel.classList.toggle("awaiting", awaiting);
    const randomBtn = $("randomChoiceBtn");
    if (randomBtn) {
      const canRandom =
        !snap.terminal &&
        (awaiting || (Array.isArray(snap.legal_actions) && snap.legal_actions.length > 0));
      randomBtn.disabled = !canRandom;
      randomBtn.classList.toggle("hidden", snap.terminal);
      randomBtn.textContent = awaiting ? "Satunnainen (jatka)" : "Satunnainen";
    }
    if (actions) {
      if (awaiting) {
        actions.classList.remove("hidden");
        const raw =
          snap.continue_hint ||
          ((snap.state && snap.state.log && snap.state.log.length)
            ? snap.state.log[snap.state.log.length - 1]
            : "");
        $("continueHint").textContent = raw
          ? prettifyLogLine(String(raw).replace(/\s*Jatka\.?\s*$/i, "").trim())
          : "Toiminto kirjattu lokiin. Klikkaa jatkaaksesi.";
      } else {
        actions.classList.add("hidden");
      }
    }
  }

  function syncPlayerPrompt() {
    const box = $("playerPrompt");
    const panel = $("choicePanel");
    if (!box || !panel) return;
    if (panel.classList.contains("hidden")) {
      box.classList.add("hidden");
      $("playerPromptTitle").textContent = "";
      $("playerPromptBody").textContent = "";
      return;
    }
    const title = ($("choiceTitle").textContent || "").trim();
    const desc = ($("choiceDesc").textContent || "").trim();
    const hints = [...panel.querySelectorAll(".hint")]
      .map((el) => (el.textContent || "").trim())
      .filter(Boolean);
    const body = hints.length ? hints.join("\n\n") : desc;
    $("playerPromptTitle").textContent = title;
    $("playerPromptBody").textContent = body;
    box.classList.toggle("hidden", !title && !body);
    panel.querySelectorAll(".hint").forEach((el) => el.classList.add("hidden"));
    const opts = $("choiceOptions");
    const hasControls = opts
      ? [...opts.children].some((el) => !el.classList.contains("hidden"))
      : false;
    panel.classList.toggle("hidden", !hasControls);
  }

  function clearSideChoice() {
    const el = $("sideChoice");
    if (el) el.innerHTML = "";
  }

  function mountSide(node) {
    const el = $("sideChoice");
    if (el) el.appendChild(node);
    else $("choiceOptions").appendChild(node);
  }

  function renderChoicePanel(snap) {
    const panel = $("choicePanel");
    const opts = $("choiceOptions");
    const title = $("choiceTitle");
    opts.innerHTML = "";
    clearSideChoice();

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
      mountSide(tray);

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
      mountSide(actions);
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
      mountSide(actions);
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        units.length === 1
          ? "Vedä kortti kädestä yksikön alle."
          : "Vedä kortteja kädestä yksiköiden alle.";
      opts.appendChild(hint);
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

    if (isOfficerPick(snap)) {
      title.textContent = "Ylennä upseeri";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        "Napsauta upseerikorttia upseerijonossa ylentääksesi sen tälle yksikölle.";
      opts.appendChild(hint);
      return;
    }

    if (isPillagePick(snap)) {
      const payload = snap.pending.payload || {};
      const deckPick = payload.reason === "scout_deck_pick";
      const queueKey = payload.queue || "pillage";
      title.textContent = deckPick
        ? `Valitse kortti jonoon (${queueKey})`
        : "Valitse ryöstökortti";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = deckPick
        ? `Napsauta yksi nostetuista korteista — se menee ${queueKey}-jonoon kuvapuoli ylöspäin; muut poistetaan.`
        : "Napsauta jonon ensimmäistä korttia tai mitä tahansa paljastettua korttia.";
      opts.appendChild(hint);
      const row = document.createElement("div");
      row.className = "card-row pillage-choices";
      const cards = payload.pillage_cards || [];
      cards.forEach((c, idx) => {
        const el = document.createElement("button");
        el.type = "button";
        if (c.visible) {
          el.className = "queue-card face-up pillage-choice";
          fillFancyQueueCard(el, c, queueKey);
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

    if (snap.pending.choicetype === CT.CHOOSE_QUEUE_TO_SCOUT) {
      const payload = snap.pending.payload || {};
      const verb = payload.verb || "scout";
      const need = payload.count || 2;
      title.textContent = `${verb}: Valitse pakka`;
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        `Kaikki jonokortit on jo paljastettu. Valitse pakka, josta nostetaan ${need} korttia; yksi niistä menee jonoon kuvapuoli ylöspäin.`;
      opts.appendChild(hint);
      const actions = document.createElement("div");
      actions.className = "choice-actions";
      (payload.queues || []).forEach((q) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = `${q.queue} (pakka ${q.deck}, poisto ${q.discard})`;
        btn.addEventListener("click", () => sendChoice([q.option]));
        actions.appendChild(btn);
      });
      mountSide(actions);
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
      status.className = "pick-status";
      status.textContent = `Valittu: ${payPicks.length} / ${need}`;
      mountSide(status);
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
      mountSide(actions);
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
      status.className = "pick-status";
      status.textContent = `Selected: ${payPicks.length} / ${need}`;
      mountSide(status);

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
      mountSide(actions);
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
      status.className = "pick-status";
      status.textContent = `Current Order Configured (Drag cards in the queue to rearrange)`;
      mountSide(status);

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
      mountSide(actions);
      return;
    }

    if (snap.pending.choicetype === CT.LOG_PAUSE) {
      const payload = snap.pending.payload || {};
      const isReveal = payload.reason === "reveal_pause";
      title.textContent = isReveal ? "Kortti paljastettu" : "Peli pysäytetty";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = isReveal
        ? snap.pending.description || "Katso paljastettu kortti ja jatka."
        : "Lue loki ja napsauta Seuraava jatkaaksesi peliä.";
      opts.appendChild(hint);

      const actions = document.createElement("div");
      actions.className = "choice-actions";

      const contBtn = document.createElement("button");
      contBtn.type = "button";
      contBtn.textContent = "Seuraava (Continue)";
      contBtn.addEventListener("click", () => sendChoice([0]));

      actions.appendChild(contBtn);
      mountSide(actions);
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
      mountSide(actions);
      return;
    }

    if (isSingleCardPick(snap)) {
      const reason = (snap.pending.payload || {}).reason;
      const waiting = /WAIT/i.test(snap.pending.description || "");
      title.textContent = reason === "order_assign_card" ? "Käskytä" : "Valitse kortti";
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        reason === "order_assign_card"
          ? "Napsauta kädestä kortti, joka annetaan odottavalle naapurille."
          : waiting
            ? "Napsauta kädestä kortti, joka lisätään tälle yksikölle."
            : "Napsauta korttia kädestä.";
      opts.appendChild(hint);
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

  function renderHitDecks(snap) {
    const el = $("hitDecks");
    if (!el) return;
    el.innerHTML = "";
    const decks = (snap.state && snap.state.hit_decks) || [];
    const showDrawn = Boolean(snap.awaiting_continue);
    decks.forEach((deck) => {
      const pair = document.createElement("div");
      pair.className = `hit-pair hit-cat-${deck.category}`;

      const pile = document.createElement("div");
      pile.className = "pile-box draw hit-pile";
      pile.innerHTML =
        `<span class="pile-kind">Vahinko</span>` +
        `<span class="pile-name">${escapeHtml(deck.label || "")}</span>` +
        `<span class="pile-count">${Number(deck.deck) || 0}</span>`;
      pair.appendChild(pile);

      const slot = document.createElement("div");
      slot.className = "hit-drawn-slot";
      if (showDrawn) {
        (deck.drawn || []).forEach((card) => {
          const face = document.createElement("div");
          face.className = "hit-drawn blink";
          const damage = Number(card.damage);
          face.innerHTML =
            `<div class="hit-drawn-damage"><span class="hit-boom" aria-hidden="true">💥</span>${Number.isFinite(damage) ? damage : ""}</div>` +
            `<div class="hit-drawn-caption">vahinko</div>`;
          slot.appendChild(face);
        });
      }
      pair.appendChild(slot);
      el.appendChild(pair);
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

      const setupOrder =
        row.key === "mauling" && snap.state && snap.state.setup_order_card
          ? snap.state.setup_order_card
          : null;

      if (!queue.length && !setupOrder) {
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
            const revealKey = `${row.key}:${i}`;
            const justRevealed = pendingReveals.has(revealKey);
            cardEl.className =
              "queue-card face-up" +
              (isFront ? " is-front" : "") +
              (justRevealed ? " revealing" : "");
            if (justRevealed) pendingReveals.delete(revealKey);
            if (
              row.key === "resistance" ||
              row.key === "mauling" ||
              row.key === "pillage" ||
              row.key === "officer"
            ) {
              fillFancyQueueCard(cardEl, card, row.key);
            } else {
              cardEl.innerHTML =
                `<div class="queue-card-name">${escapeHtml(card.name || `#${card.id}`)}</div>` +
                (card.detail
                  ? `<div class="queue-card-detail">${escapeHtml(card.detail)}</div>`
                  : "");
            }
          } else {
            cardEl.className =
              "queue-card face-down" + (isFront ? " is-front" : "");
            cardEl.innerHTML = `<div class="queue-card-mark">🂠</div>`;
          }

          if (
            isPillagePick(snap) &&
            row.key === "pillage" &&
            (snap.pending.payload || {}).reason === "pillage"
          ) {
            const offered = (snap.pending.payload || {}).pillage_cards || [];
            const match = offered.find((c) => c.index === i);
            if (match) {
              cardEl.classList.add("scout-selectable");
              cardEl.setAttribute("role", "button");
              cardEl.tabIndex = 0;
              cardEl.addEventListener("click", () => sendChoice([match.id]));
            }
          }

          // --- 0. OFFICER PROMOTE: click queue card (option = queue index) ---
          if (isOfficerPick(snap) && row.key === "officer" && card && card.visible) {
            const optsList = snap.pending.options || [];
            if (optsList.includes(i)) {
              cardEl.classList.add("officer-selectable");
              cardEl.setAttribute("role", "button");
              cardEl.tabIndex = 0;
              cardEl.addEventListener("click", () => sendChoice([i]));
              cardEl.addEventListener("keydown", (ev) => {
                if (ev.key === "Enter" || ev.key === " ") {
                  ev.preventDefault();
                  sendChoice([i]);
                }
              });
            } else {
              // Wrong troop type for this promote — not a legal target.
              cardEl.classList.add("officer-ineligible");
            }
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
        if (setupOrder) {
          const orderEl = document.createElement("div");
          orderEl.className = "queue-card face-up setup-order-halo";
          fillFancyQueueCard(orderEl, setupOrder, "mauling");
          track.appendChild(orderEl);
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

      const displayText = prettifyLogLine(text);

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
    hideActionTip();
    noteQueueReveals(snap);
    lastSnap = snap;
    const state = snap.state || {};
    const botMeta = snap.bots || {};
    let botLine = "";
    if (botMeta.bot_kind === "rl" && botMeta.bot_name) {
      botLine = ` · vs ${botMeta.bot_name}`;
    } else if (botMeta.bot_kind === "random") {
      botLine = " · vs random";
    }
    $("roundInfo").textContent =
      `Kierros ${state.round ?? "?"} · vaihe ${state.stage ?? "?"}${botLine}`;
    $("message").textContent = state.message || "";

    if ($("pauseToggle") && typeof snap.pause_after_actions === "boolean") {
      $("pauseToggle").checked = snap.pause_after_actions;
    }

    syncFxRound(snap);
    // If pause ended without going through continueBtn (e.g. settings), stop blinks.
    if (!snap.awaiting_continue) demoteBlinkToHalo();

    renderConvoy(snap);
    renderHand(snap);
    renderContinuePanel(snap);
    renderChoicePanel(snap);
    syncPlayerPrompt();

    const playersEl = $("players");
    playersEl.innerHTML = "";
    (state.players || []).forEach((p) => {
      const div = document.createElement("div");
      div.className =
        "player" +
        (p.number === seatNum ? " you" : "") +
        ` ${playerColorClass(p.number)}`;
      const cards = p.cards ? p.cards.join(", ") : `(${p.card_count})`;
      const bank = Math.max(0, Number(p.total_cash) - Number(p.cash_this_round || 0));
      const blink = Boolean(snap.awaiting_continue);
      div.innerHTML =
        `<strong>Pelaaja ${p.number}</strong>` +
        (p.number === seatNum ? " (sinä)" : "") +
        `<div class="pp-line">PP ${p.promotion_points}</div>` +
        `<div class="cash-piles">` +
        `<div class="cash-pile">` +
        `<span class="cash-label">Kierros ${Number(p.cash_this_round) || 0}</span>` +
        `<div class="cash-cards">${moneyCardsHtml(p.round_counters, blink)}</div>` +
        `</div>` +
        `<div class="cash-pile cash-bank">` +
        `<span class="cash-label">Kassa ${bank}</span>` +
        `<div class="cash-cards">${moneyCardsHtml(p.bank_counters, blink)}</div>` +
        `</div>` +
        `</div>` +
        `<div class="hand-line">kortit: ${escapeHtml(cards)}</div>`;
      playersEl.appendChild(div);
    });

    renderDeckRows(snap);
    renderHitDecks(snap);
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
