/* Hallenplan: Anzeige (alle) und grafischer Editor (Admins). Koordinaten in Metern, SVG-viewBox = Halle. */
(() => {
  "use strict";

  const data = JSON.parse(document.getElementById("plan-data").textContent);
  const urls = window.PLAN_URLS;
  const editable = data.editable;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const SNAP = 0.05;
  const KIND_COLORS = {
    area: "#e9ecef",
    cabinet: "#ffffff",
    workstation: "#ffffff",
    test_rig: "#fff3cd",
    marking: "#ffff00",
    other: "#dee2e6",
  };

  const svg = document.getElementById("plan-svg");
  const canvas = document.getElementById("plan-canvas");
  const form = document.getElementById("props-form");

  const plan = { ...data.plan };
  let elements = data.elements.map(withKey);
  let deleted = [];
  let selectedKey = null;
  let dirty = false;
  let zoom = 1;
  let drag = null;
  let tempCounter = 0;

  function withKey(item) {
    return { ...item, key: item.id ? String(item.id) : `neu-${++tempCounter}` };
  }

  const snap = (v) => Math.round(Math.round(v / SNAP) * SNAP * 100) / 100;
  const current = () => elements.find((item) => item.key === selectedKey) || null;

  function node(name, attrs = {}, parent = null) {
    const n = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs)) n.setAttribute(key, value);
    if (parent) parent.appendChild(n);
    return n;
  }

  function textColor(hex) {
    if (!/^#[0-9a-f]{6}$/i.test(hex || "")) return "#212529";
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#212529" : "#ffffff";
  }

  /* ---------- Darstellung ---------- */

  function render() {
    svg.replaceChildren();
    const pad = 0.5;
    svg.setAttribute("viewBox", `${-pad} ${-pad} ${plan.width + 2 * pad} ${plan.height + 2 * pad}`);
    node("rect", { x: 0, y: 0, width: plan.width, height: plan.height, class: "plan-floor" }, svg);
    const grid = node("g", { class: "plan-grid" }, svg);
    for (let x = 1; x < plan.width; x++) {
      node("line", { x1: x, y1: 0, x2: x, y2: plan.height, class: x % 5 ? "" : "major" }, grid);
    }
    for (let y = 1; y < plan.height; y++) {
      node("line", { x1: 0, y1: y, x2: plan.width, y2: y, class: y % 5 ? "" : "major" }, grid);
    }
    const layer = node("g", {}, svg);
    [...elements].sort((a, b) => a.z - b.z).forEach((item) => drawElement(layer, item));
    applyZoom();
  }

  function drawElement(layer, item) {
    const classes = ["plan-el", `kind-${item.kind}`];
    if (item.key === selectedKey) classes.push("is-selected");
    if (item.id && item.id === data.highlight) classes.push("is-highlighted");
    const g = node("g", { class: classes.join(" "), "data-key": item.key }, layer);
    const cx = item.x + item.width / 2;
    const cy = item.y + item.height / 2;
    if (item.rotation) g.setAttribute("transform", `rotate(${item.rotation} ${cx} ${cy})`);

    const title = node("title", {}, g);
    title.textContent = [item.label.replace(/\n/g, " ") || data.kinds[item.kind], item.items ? `${item.items} Gerät(e)` : ""]
      .filter(Boolean)
      .join(" – ");
    node("rect", { x: item.x, y: item.y, width: item.width, height: item.height, fill: item.color || "none", class: "plan-shape" }, g);
    drawLabel(g, item, cx, cy);

    if (item.items) {
      const r = Math.min(0.22, item.width / 3, item.height / 3);
      const badge = node("g", { class: "plan-badge" }, g);
      node("circle", { cx: item.x + item.width - r * 0.9, cy: item.y + r * 0.9, r }, badge);
      const t = node("text", { x: item.x + item.width - r * 0.9, y: item.y + r * 0.9, "font-size": r * 1.2, "text-anchor": "middle", "dominant-baseline": "central" }, badge);
      t.textContent = item.items;
    }
    if (editable && item.key === selectedKey) {
      const size = 0.25;
      node("rect", { x: item.x + item.width - size / 2, y: item.y + item.height - size / 2, width: size, height: size, class: "plan-handle" }, g);
    }
  }

  function drawLabel(g, item, cx, cy) {
    const lines = item.label.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return;
    // Schmale, hohe Objekte (z. B. Schränke an der Wand) senkrecht beschriften
    const vertical = item.height > item.width * 1.4;
    const [boxW, boxH] = vertical ? [item.height, item.width] : [item.width, item.height];
    const longest = Math.max(...lines.map((l) => l.length));
    const size = Math.max(0.07, Math.min(0.32, boxH / (lines.length * 1.25), (boxW * 0.92) / (longest * 0.58)));
    const text = node("text", {
      x: cx,
      y: cy - ((lines.length - 1) * size * 1.15) / 2,
      "font-size": size,
      fill: textColor(item.color || "#ffffff"),
      class: "plan-label",
      "text-anchor": "middle",
      "dominant-baseline": "central",
    }, g);
    if (vertical) text.setAttribute("transform", `rotate(-90 ${cx} ${cy})`);
    lines.forEach((line, i) => {
      const span = node("tspan", { x: cx, dy: i === 0 ? 0 : size * 1.15 }, text);
      span.textContent = line;
    });
  }

  function renderLegend() {
    const legend = document.getElementById("plan-legend");
    const entries = Object.entries(data.kinds).map(
      ([kind, label]) => `<li class="mb-1"><span class="plan-swatch" style="background:${KIND_COLORS[kind]}"></span>${label}</li>`
    );
    entries.push('<li class="mt-2"><span class="plan-swatch plan-swatch-badge">3</span>Anzahl Geräte im Objekt</li>');
    entries.push('<li><span class="plan-swatch plan-swatch-highlight"></span>Gesuchtes Objekt</li>');
    legend.innerHTML = entries.join("");
  }

  /* ---------- Zoom ---------- */

  function applyZoom() {
    svg.style.width = `${zoom * 100}%`;
  }

  function fitZoom() {
    const aspect = (plan.height + 1) / (plan.width + 1);
    zoom = Math.min(1, canvas.clientHeight / (canvas.clientWidth * aspect));
    applyZoom();
  }

  document.querySelectorAll("[data-zoom]").forEach((button) =>
    button.addEventListener("click", () => {
      const step = Number(button.dataset.zoom);
      if (step === 0) fitZoom();
      else {
        zoom = Math.min(6, Math.max(0.2, zoom * (step > 0 ? 1.25 : 0.8)));
        applyZoom();
      }
    })
  );

  /* ---------- Auswahl ---------- */

  function select(key, { scroll = false } = {}) {
    selectedKey = key;
    render();
    const item = current();
    if (editable) fillForm();
    else if (item && item.id) {
      htmx.ajax("GET", urls.element.replace("/0/", `/${item.id}/`), { target: "#plan-panel", swap: "innerHTML" });
    }
    if (scroll && item) scrollToElement(item);
  }

  function scrollToElement(item) {
    const g = svg.querySelector(`[data-key="${item.key}"]`);
    if (!g) return;
    const box = g.getBoundingClientRect();
    const frame = canvas.getBoundingClientRect();
    canvas.scrollBy({
      left: box.left - frame.left - frame.width / 2 + box.width / 2,
      top: box.top - frame.top - frame.height / 2 + box.height / 2,
      behavior: "smooth",
    });
  }

  function svgPoint(evt) {
    const point = svg.createSVGPoint();
    point.x = evt.clientX;
    point.y = evt.clientY;
    return point.matrixTransform(svg.getScreenCTM().inverse());
  }

  svg.addEventListener("pointerdown", (evt) => {
    const g = evt.target.closest(".plan-el");
    if (!g) {
      if (selectedKey) select(null);
      return;
    }
    const resizing = evt.target.classList.contains("plan-handle");
    if (g.dataset.key !== selectedKey) select(g.dataset.key);
    if (!editable) return;
    evt.preventDefault();
    const item = current();
    drag = {
      mode: resizing ? "resize" : "move",
      item,
      start: svgPoint(evt),
      orig: { x: item.x, y: item.y, width: item.width, height: item.height },
      moved: false,
    };
    svg.setPointerCapture(evt.pointerId);
  });

  svg.addEventListener("pointermove", (evt) => {
    if (!drag) return;
    const point = svgPoint(evt);
    const dx = point.x - drag.start.x;
    const dy = point.y - drag.start.y;
    if (!drag.moved && Math.hypot(dx, dy) < SNAP) return;
    drag.moved = true;
    const { item, orig } = drag;
    if (drag.mode === "move") {
      item.x = snap(orig.x + dx);
      item.y = snap(orig.y + dy);
    } else {
      // Mausbewegung in das (evtl. gedrehte) Koordinatensystem des Objekts umrechnen
      const angle = (-item.rotation * Math.PI) / 180;
      const lx = dx * Math.cos(angle) - dy * Math.sin(angle);
      const ly = dx * Math.sin(angle) + dy * Math.cos(angle);
      item.width = Math.max(SNAP, snap(orig.width + lx));
      item.height = Math.max(SNAP, snap(orig.height + ly));
    }
    markDirty();
    render();
    fillForm();
  });

  const endDrag = () => {
    drag = null;
  };
  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", endDrag);

  // Suchergebnisse (Ansicht): Objekt auf dem Plan anzeigen
  document.addEventListener("click", (evt) => {
    const button = evt.target.closest("[data-show-element]");
    if (!button) return;
    const item = elements.find((e) => String(e.id) === button.dataset.showElement);
    if (item) {
      data.highlight = item.id;
      select(item.key, { scroll: true });
    }
  });

  /* ---------- Editor ---------- */

  function markDirty(value = true) {
    dirty = value;
    const status = document.getElementById("plan-status");
    if (status) {
      status.textContent = value ? "Ungespeicherte Änderungen" : "Gespeichert";
      status.className = `small ${value ? "text-warning-emphasis" : "text-success"}`;
    }
  }

  function fillForm() {
    if (!form) return;
    const item = current();
    document.getElementById("props-empty").classList.toggle("d-none", Boolean(item));
    form.classList.toggle("d-none", !item);
    document.querySelectorAll("[data-needs-selection]").forEach((b) => (b.disabled = !item));
    if (!item) return;
    const active = document.activeElement;
    for (const field of ["label", "kind", "x", "y", "width", "height", "rotation"]) {
      const input = form.elements[field];
      if (input !== active) input.value = item[field];
    }
    form.elements.nofill.checked = !item.color;
    if (form.elements.color !== active) form.elements.color.value = item.color || "#ffffff";
    const hint = document.getElementById("prop-location-hint");
    const holds = data.holdingKinds.includes(item.kind) && item.label.trim();
    hint.textContent = holds
      ? `Wird als Ablageort „${item.label.split(/\s+/).join(" ")}“ angeboten.`
      : "Kein Ablageort – dafür Art Bereich, Schrank, Tisch oder Versuchsstand wählen und beschriften.";
    if (item.items) hint.textContent += ` Enthält ${item.items} Gerät(e).`;
  }

  form?.addEventListener("input", () => {
    const item = current();
    if (!item) return;
    const f = form.elements;
    item.label = f.label.value;
    item.kind = f.kind.value;
    for (const field of ["x", "y", "width", "height", "rotation"]) {
      const value = parseFloat(f[field].value);
      if (!Number.isNaN(value)) item[field] = field === "width" || field === "height" ? Math.max(SNAP, value) : value;
    }
    item.color = f.nofill.checked ? "" : f.color.value;
    markDirty();
    render();
    fillForm();
  });

  function maxZ() {
    return elements.reduce((max, item) => Math.max(max, item.z), 0);
  }

  const actions = {
    add() {
      const item = withKey({
        id: null,
        kind: "cabinet",
        label: "Neues Objekt",
        x: snap(plan.width / 2 - 0.5),
        y: snap(plan.height / 2 - 0.25),
        width: 1,
        height: 0.5,
        rotation: 0,
        color: KIND_COLORS.cabinet,
        z: maxZ() + 1,
        items: 0,
        location: null,
      });
      elements.push(item);
      markDirty();
      select(item.key, { scroll: true });
      form.elements.label.select();
    },
    duplicate() {
      const source = current();
      const item = withKey({ ...source, id: null, x: snap(source.x + 0.5), y: snap(source.y + 0.5), z: maxZ() + 1, items: 0, location: null });
      elements.push(item);
      markDirty();
      select(item.key);
    },
    delete() {
      const item = current();
      if (item.items) {
        window.alert(`In „${item.label || "diesem Objekt"}“ liegen noch ${item.items} Gerät(e). Bitte zuerst einen anderen Ablageort zuweisen.`);
        return;
      }
      if (!window.confirm(`„${item.label.replace(/\n/g, " ") || data.kinds[item.kind]}“ löschen?`)) return;
      elements = elements.filter((e) => e !== item);
      if (item.id) deleted.push(item.id);
      markDirty();
      select(null);
    },
    front() {
      current().z = maxZ() + 1;
      markDirty();
      render();
    },
    back() {
      current().z = elements.reduce((min, item) => Math.min(min, item.z), 0) - 1;
      markDirty();
      render();
    },
    async save() {
      const errorBox = document.getElementById("plan-error");
      errorBox.classList.add("d-none");
      const payload = {
        plan: { width: plan.width, height: plan.height },
        elements: elements.map(({ key, items, location, ...rest }) => rest),
        deleted,
      };
      const csrf = JSON.parse(document.body.getAttribute("hx-headers"))["X-CSRFToken"];
      try {
        const response = await fetch(urls.save, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Speichern fehlgeschlagen.");
        const selected = current();
        elements = result.elements.map(withKey);
        deleted = [];
        selectedKey = selected && selected.id ? String(selected.id) : null;
        markDirty(false);
        render();
        fillForm();
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.classList.remove("d-none");
      }
    },
  };

  document.querySelectorAll("[data-action]").forEach((button) =>
    button.addEventListener("click", () => actions[button.dataset.action]())
  );

  ["width", "height"].forEach((field) => {
    document.getElementById(`plan-${field}`)?.addEventListener("input", (evt) => {
      const value = parseFloat(evt.target.value);
      if (value >= 1) {
        plan[field] = value;
        markDirty();
        render();
      }
    });
  });

  document.addEventListener("keydown", (evt) => {
    if (!editable || !current() || evt.target.closest?.("input, textarea, select, button")) return;
    const step = evt.shiftKey ? 1 : 0.1;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[evt.key]) {
      evt.preventDefault();
      const item = current();
      item.x = snap(item.x + moves[evt.key][0]);
      item.y = snap(item.y + moves[evt.key][1]);
      markDirty();
      render();
      fillForm();
    } else if (evt.key === "Delete") {
      actions.delete();
    }
  });

  window.addEventListener("beforeunload", (evt) => {
    if (dirty) evt.preventDefault();
  });

  /* ---------- Start ---------- */

  if (editable) svg.classList.add("editing");
  renderLegend();
  render();
  fitZoom();
  if (data.highlight) {
    const item = elements.find((e) => e.id === data.highlight);
    if (item) select(item.key, { scroll: true });
  }
  fillForm();
})();
