(() => {
  const DATA = JSON.parse(document.getElementById("report-data").textContent);
  const NS = "http://www.w3.org/2000/svg";
  const root = document.documentElement;

  const toggle = document.querySelector(".theme-toggle");
  const MODES = ["light", "dark"];
  let mode = "light";
  try { mode = localStorage.getItem("nba-report-theme") || "light"; } catch (e) {}
  if (!MODES.includes(mode)) mode = "light";
  const applyMode = () => { root.setAttribute("data-theme", mode); toggle.textContent = mode; };
  toggle.addEventListener("click", () => {
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    try { localStorage.setItem("nba-report-theme", mode); } catch (e) {}
    applyMode();
  });
  applyMode();

  const signed = d => v => (v > 0 ? "+" : v < 0 ? "-" : "") + Math.abs(v).toFixed(d);
  const FORMAT = {
    text: v => String(v),
    int: v => Math.round(v).toLocaleString("en-US"),
    num1: v => v.toFixed(1),
    num2: v => v.toFixed(2),
    num3: v => v.toFixed(3),
    signed1: signed(1),
    signed2: signed(2),
    pct1: v => `${(v * 100).toFixed(1)}%`,
    rate3: v => v.toFixed(3).replace(/^0\./, ".").replace(/^-0\./, "-."),
    season: v => `${v - 1}-${String(v).slice(2)}`,
    date: v => v,
  };
  const show = (format, v) => (v === null || v === undefined ? "" : FORMAT[format](v));
  const withUnit = (format, v, unit) => `${show(format, v)}${unit ? ` ${unit}` : ""}`;
  const decade = season => Math.floor((season - 1) / 10) * 10;
  const present = (rows, ...keys) => rows.filter(r => keys.every(k => r[k] !== null && r[k] !== undefined));

  function svg(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }

  function niceStep(span, target) {
    const raw = span / target, mag = 10 ** Math.floor(Math.log10(raw));
    const n = raw / mag;
    return (n >= 5 ? 10 : n >= 2 ? 5 : n >= 1 ? 2 : 1) * mag;
  }

  function domain(values, target, withZero) {
    let lo = Math.min(...values), hi = Math.max(...values);
    if (withZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    const step = niceStep(hi - lo || Math.abs(hi) || 1, target);
    return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step };
  }

  function tickLabel(format, v, step) {
    if (format === "season") return String(Math.round(v));
    if (format === "pct1") return `${(v * 100).toFixed(Math.max(0, -Math.floor(Math.log10(step * 100))))}%`;
    const d = Math.max(0, -Math.floor(Math.log10(step)));
    if (format.startsWith("signed") && Math.abs(v) > step / 2) return signed(d)(v);
    return (Math.abs(v) < step / 2 ? 0 : v).toFixed(d);
  }

  function frame(fig) {
    const tip = document.createElement("div");
    tip.className = "tooltip";
    fig.appendChild(tip);
    return {
      tip,
      show(lines, x, y, width) {
        tip.replaceChildren(...lines.map(([cls, text]) => {
          const d = document.createElement("div");
          d.className = cls; d.textContent = text;
          return d;
        }));
        tip.style.display = "block";
        tip.style.left = `${Math.max(0, Math.min(x + 12, width - tip.offsetWidth - 4))}px`;
        tip.style.top = `${Math.max(0, y - 44)}px`;
      },
      hide() { tip.style.display = "none"; },
    };
  }

  function redrawOnResize(fig, draw) {
    draw();
    new ResizeObserver(draw).observe(fig);
  }

  const firstTick = d => Math.ceil(d.lo / d.step - 1e-9) * d.step;

  function yAxis(s, d, sy, x0, x1, format, zeroRule) {
    for (let t = firstTick(d); t <= d.hi + d.step / 2; t += d.step) {
      const v = Math.abs(t) < d.step / 2 ? 0 : t;
      svg("line", { x1: x0, x2: x1, y1: sy(v), y2: sy(v), class: v === 0 && zeroRule ? "zero" : "grid" }, s);
      svg("text", { x: x0 - 8, y: sy(v) + 4, class: "tick", "text-anchor": "end" }, s).textContent = tickLabel(format, v, d.step);
    }
  }

  function xTicks(s, d, sx, y, format) {
    for (let t = firstTick(d); t <= d.hi + d.step / 2; t += d.step)
      svg("text", { x: sx(t), y, class: "tick", "text-anchor": "middle" }, s).textContent = tickLabel(format, t, d.step);
  }

  function linePanel(fig, rows, spec, yd, height, label) {
    const box = frame(fig);
    const draw = () => {
      fig.querySelector("svg")?.remove();
      const W = fig.clientWidth, H = height(W);
      const m = { t: 12, r: 16, b: 28, l: 48 };
      const xs = rows.map(r => r[spec.x]);
      const xd = { lo: Math.min(...xs), hi: Math.max(...xs) };
      const steps = xs.slice(1).map((v, i) => v - xs[i]).filter(d => d > 0);
      const gap = steps.length ? Math.min(...steps) * 1.5 : Infinity;
      const sx = v => m.l + (xd.hi === xd.lo ? 0.5 : (v - xd.lo) / (xd.hi - xd.lo)) * (W - m.l - m.r);
      const sy = v => m.t + (yd.hi - v) / (yd.hi - yd.lo || 1) * (H - m.t - m.b);
      const s = svg("svg", { width: W, height: H, role: "img", "aria-label": label }, null);
      fig.insertBefore(s, box.tip);
      yAxis(s, yd, sy, m.l, W - m.r, spec.y_format, Boolean(spec.baseline));
      const xStep = niceStep(xd.hi - xd.lo || 1, Math.max(2, Math.floor((W - m.l - m.r) / 90)));
      xTicks(s, { lo: Math.ceil(xd.lo / xStep) * xStep, hi: Math.floor(xd.hi / xStep) * xStep, step: xStep }, sx, H - 8, spec.x_format === "season" ? "season" : "num1");
      svg("path", { d: rows.map((r, i) => `${i && xs[i] - xs[i - 1] <= gap ? "L" : "M"}${sx(r[spec.x])},${sy(r[spec.y])}`).join(""), class: "series" }, s);
      if (spec.baseline) svg("text", { x: m.l + 6, y: sy(0) - 6, class: "annotation" }, s).textContent = spec.baseline;
      const cross = svg("line", { y1: m.t, y2: H - m.b, class: "crosshair", visibility: "hidden" }, s);
      const dot = svg("circle", { r: 5, class: "dot", visibility: "hidden" }, s);
      const hit = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, s);
      hit.addEventListener("pointermove", ev => {
        const r = rows.reduce((a, b) => (Math.abs(sx(b[spec.x]) - ev.offsetX) < Math.abs(sx(a[spec.x]) - ev.offsetX) ? b : a));
        const cx = sx(r[spec.x]), cy = sy(r[spec.y]);
        for (const [k, v] of [["x1", cx], ["x2", cx], ["visibility", "visible"]]) cross.setAttribute(k, v);
        for (const [k, v] of [["cx", cx], ["cy", cy], ["visibility", "visible"]]) dot.setAttribute(k, v);
        box.show([["tip-key", show(spec.x_format, r[spec.x])], ["tip-value", withUnit(spec.y_format, r[spec.y], spec.y_unit)]], cx, cy, W);
      });
      hit.addEventListener("pointerleave", () => {
        cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); box.hide();
      });
    };
    redrawOnResize(fig, draw);
  }

  function lineChart(section, block) {
    const fig = section.querySelector(".chart");
    const rows = present(block.rows, block.x, block.y);
    if (!rows.length) { fig.textContent = "No rows."; return; }
    const yd = domain(rows.map(r => r[block.y]), 5, Boolean(block.baseline));
    linePanel(fig, rows, block, yd, W => Math.max(220, Math.min(320, W * 0.42)), section.querySelector("h2").textContent);
  }

  function multiples(section, block) {
    const grid = section.querySelector(".multiples");
    const rows = present(block.rows, block.facet, block.x, block.y);
    if (!rows.length) { grid.textContent = "No rows."; return; }
    const yd = domain(rows.map(r => r[block.y]), 4, Boolean(block.baseline));
    const facets = [...new Set(rows.map(r => r[block.facet]))];
    for (const f of facets) {
      const panel = document.createElement("div");
      panel.className = "panel";
      const title = document.createElement("div");
      title.className = "panel-title";
      title.textContent = String(f);
      const fig = document.createElement("figure");
      fig.className = "chart";
      panel.append(title, fig);
      grid.appendChild(panel);
      linePanel(fig, rows.filter(r => r[block.facet] === f), block, yd, () => 150, `${section.querySelector("h2").textContent}: ${f}`);
    }
  }

  function barChart(section, block) {
    const fig = section.querySelector(".chart");
    const rows = present(block.rows, block.label, block.value);
    if (!rows.length) { fig.textContent = "No rows."; return; }
    const box = frame(fig);
    const draw = () => {
      fig.querySelector("svg")?.remove();
      const W = fig.clientWidth, band = 24;
      const longest = Math.max(...rows.map(r => String(r[block.label]).length));
      const m = { t: 4, r: 64, b: 24, l: Math.min(200, Math.max(80, longest * 8 + 12)) };
      const H = m.t + m.b + rows.length * band;
      const d = domain(rows.map(r => r[block.value]), Math.max(2, Math.floor((W - m.l - m.r) / 90)), true);
      const sx = v => m.l + (v - d.lo) / (d.hi - d.lo || 1) * (W - m.l - m.r);
      const s = svg("svg", { width: W, height: H, role: "img", "aria-label": section.querySelector("h2").textContent }, null);
      fig.insertBefore(s, box.tip);
      for (let t = d.lo; t <= d.hi + d.step / 2; t += d.step) {
        const v = Math.abs(t) < d.step / 2 ? 0 : t;
        svg("line", { x1: sx(v), x2: sx(v), y1: m.t, y2: H - m.b, class: v === 0 ? "zero" : "grid" }, s);
        svg("text", { x: sx(v), y: H - 6, class: "tick", "text-anchor": "middle" }, s).textContent = tickLabel(block.value_format, v, d.step);
      }
      rows.forEach((r, i) => {
        const y = m.t + i * band, v = r[block.value];
        const x0 = sx(Math.min(0, v)), x1 = sx(Math.max(0, v));
        svg("text", { x: m.l - 10, y: y + band / 2 + 5, class: "bar-label", "text-anchor": "end" }, s).textContent = String(r[block.label]);
        svg("rect", { x: x0, y: y + 5, width: Math.max(1, x1 - x0), height: band - 10, class: "bar" }, s);
        svg("text", { x: x1 + 6, y: y + band / 2 + 4, class: "bar-value", "text-anchor": "start" }, s).textContent = show(block.value_format, v);
        const hit = svg("rect", { x: 0, y, width: W, height: band, fill: "transparent", class: "bar-hit" }, s);
        hit.addEventListener("pointermove", () => box.show([["tip-key", String(r[block.label])], ["tip-value", withUnit(block.value_format, v, block.value_unit)]], x1, y + band / 2, W));
        hit.addEventListener("pointerleave", () => box.hide());
      });
    };
    redrawOnResize(fig, draw);
  }

  function scatterChart(section, block) {
    const fig = section.querySelector(".chart");
    const rows = present(block.rows, block.x, block.y);
    if (!rows.length) { fig.textContent = "No rows."; return; }
    const name = r => String(r[block.label] ?? "");
    const values = r => `${withUnit(block.x_format, r[block.x], block.x_unit)} · ${withUnit(block.y_format, r[block.y], block.y_unit)}`;
    const LIST_MAX = 40, LABEL_MAX = 12;
    let view = null, selected = null, brushing = false, query = "";

    const controls = document.createElement("div");
    controls.className = "controls scatter-controls";
    const search = document.createElement("input");
    search.type = "search"; search.className = "filter"; search.placeholder = "Find a dot";
    const zoom = document.createElement("button");
    zoom.type = "button"; zoom.textContent = "Zoom";
    const reset = document.createElement("button");
    reset.type = "button"; reset.textContent = "Reset"; reset.hidden = true;
    const count = document.createElement("span");
    count.className = "count";
    controls.append(...(block.label ? [search] : []), zoom, reset, count);
    const readout = document.createElement("div");
    readout.className = "readout"; readout.setAttribute("aria-live", "polite");
    const list = document.createElement("ol");
    list.className = "scatter-list";
    fig.before(controls);
    fig.prepend(readout);
    fig.after(list);

    const say = r => {
      if (r) readout.replaceChildren(...[["readout-key", name(r)], ["readout-value", values(r)]].map(([cls, text]) => {
        const d = document.createElement("div");
        d.className = cls; d.textContent = text;
        return d;
      }));
      else readout.replaceChildren(Object.assign(document.createElement("div"), {
        className: "readout-hint",
        textContent: brushing ? "Drag across the dots you want to see." : "Tap a dot to see it. Zoom to look closer.",
      }));
    };

    let draw;
    const select = r => { selected = r; draw(); };
    search.addEventListener("input", () => {
      query = search.value.trim().toLowerCase();
      const hits = query ? rows.filter(r => name(r).toLowerCase().includes(query)) : [];
      selected = hits.length === 1 ? hits[0] : selected;
      draw();
    });
    zoom.addEventListener("click", () => { brushing = !brushing; draw(); });
    reset.addEventListener("click", () => { view = null; brushing = false; draw(); });

    draw = () => {
      fig.querySelector("svg")?.remove();
      zoom.setAttribute("aria-pressed", String(brushing));
      reset.hidden = !view;
      const W = fig.clientWidth, H = Math.round(Math.max(300, Math.min(460, W * 0.85)));
      const m = { t: 16, r: 16, b: block.x_unit ? 44 : 28, l: block.y_unit ? 64 : 48 };
      const xTarget = Math.max(3, Math.floor((W - m.l - m.r) / 90));
      const exact = (lo, hi, target) => ({ lo, hi, step: niceStep(hi - lo, target) });
      const xd = view ? exact(view.x0, view.x1, xTarget) : domain(rows.map(r => r[block.x]), xTarget, false);
      const yd = view ? exact(view.y0, view.y1, 5) : domain(rows.map(r => r[block.y]), 5, false);
      const sx = v => m.l + (v - xd.lo) / (xd.hi - xd.lo || 1) * (W - m.l - m.r);
      const sy = v => m.t + (yd.hi - v) / (yd.hi - yd.lo || 1) * (H - m.t - m.b);
      const ix = px => xd.lo + (px - m.l) / (W - m.l - m.r) * (xd.hi - xd.lo);
      const iy = py => yd.hi - (py - m.t) / (H - m.t - m.b) * (yd.hi - yd.lo);
      const shown = rows.filter(r => r[block.x] >= xd.lo && r[block.x] <= xd.hi && r[block.y] >= yd.lo && r[block.y] <= yd.hi);
      const matches = new Set(query ? shown.filter(r => name(r).toLowerCase().includes(query)) : []);

      const s = svg("svg", { width: W, height: H, role: "img", "aria-label": section.querySelector("h2").textContent }, null);
      s.style.touchAction = brushing ? "none" : "pan-y";
      fig.appendChild(s);
      yAxis(s, yd, sy, m.l, W - m.r, block.y_format, false);
      xTicks(s, xd, sx, H - m.b + 20, block.x_format);
      if (block.x_unit) svg("text", { x: (m.l + W - m.r) / 2, y: H - 4, class: "axis-title", "text-anchor": "middle" }, s).textContent = block.x_unit;
      if (block.y_unit) svg("text", { x: 12, y: (m.t + H - m.b) / 2, class: "axis-title", "text-anchor": "middle", transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, s).textContent = block.y_unit;

      const radius = shown.length <= LIST_MAX ? 5 : 4;
      const dim = matches.size > 0;
      for (const r of shown)
        svg("circle", { cx: sx(r[block.x]), cy: sy(r[block.y]), r: radius, class: dim && !matches.has(r) ? "point point-dim" : "point" }, s);

      const cx = shown.reduce((a, r) => a + sx(r[block.x]), 0) / shown.length;
      const cy = shown.reduce((a, r) => a + sy(r[block.y]), 0) / shown.length;
      const reach = r => (sx(r[block.x]) - cx) ** 2 + (sy(r[block.y]) - cy) ** 2;
      const rest = [...shown].filter(r => r !== selected && !matches.has(r)).sort((a, b) => reach(b) - reach(a));
      const candidates = [
        ...(selected && shown.includes(selected) ? [selected] : []),
        ...[...matches].filter(r => r !== selected),
        ...rest.slice(0, shown.length <= LIST_MAX ? rest.length : LABEL_MAX),
      ];
      const placed = shown.map(r => ({ x0: sx(r[block.x]) - radius, x1: sx(r[block.x]) + radius, y0: sy(r[block.y]) - radius, y1: sy(r[block.y]) + radius }));
      const overlaps = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
      for (const r of candidates) {
        const px = sx(r[block.x]), py = sy(r[block.y]), forced = r === selected || matches.has(r);
        const t = svg("text", { class: r === selected ? "point-label point-label-selected" : "point-label" }, s);
        t.textContent = name(r);
        const w = t.getComputedTextLength(), h = 13, gap = radius + 3;
        const clamp = x0 => Math.min(Math.max(x0, m.l), W - m.r - w);
        const above = py - gap - 2, below = py + gap + h - 2;
        const spots = [
          [px + gap, py + 4], [px - gap - w, py + 4],
          [clamp(px - w / 2), above], [clamp(px - w / 2), below],
          [clamp(px - w), above], [clamp(px), above], [clamp(px - w), below], [clamp(px), below],
        ].map(([x0, y]) => ({ x: x0, y, box: { x0: x0 - 2, x1: x0 + w + 2, y0: y - h + 2, y1: y + 3 } }))
          .filter(c => c.box.x0 >= m.l - 2 && c.box.x1 <= W - m.r + 2 && c.box.y0 >= m.t - 4 && c.box.y1 <= H - m.b);
        const hits = c => placed.filter(p => overlaps(p, c.box)).length;
        const spot = spots.find(c => hits(c) === 0)
          ?? (forced && spots.length ? spots.reduce((a, b) => (hits(b) < hits(a) ? b : a)) : null);
        if (!spot) { t.remove(); continue; }
        for (const [k, v] of [["x", spot.x], ["y", spot.y]]) t.setAttribute(k, v);
        placed.push(spot.box);
      }
      if (selected && shown.includes(selected))
        svg("circle", { cx: sx(selected[block.x]), cy: sy(selected[block.y]), r: radius + 4, class: "point-ring" }, s);

      const local = ev => { const b = s.getBoundingClientRect(); return { x: ev.clientX - b.left, y: ev.clientY - b.top }; };
      const nearest = (ev, within) => {
        const p = local(ev);
        const d = r => (sx(r[block.x]) - p.x) ** 2 + (sy(r[block.y]) - p.y) ** 2;
        const r = shown.reduce((a, b) => (d(b) < d(a) ? b : a), shown[0]);
        return r && d(r) <= within ** 2 ? r : null;
      };
      const box = svg("rect", { class: "brush", visibility: "hidden" }, s);
      const at = ev => { const p = local(ev); return { x: Math.max(m.l, Math.min(W - m.r, p.x)), y: Math.max(m.t, Math.min(H - m.b, p.y)) }; };
      let start = null;
      s.addEventListener("pointerdown", ev => {
        if (!brushing) return;
        start = at(ev);
        s.setPointerCapture(ev.pointerId);
      });
      s.addEventListener("pointermove", ev => {
        if (brushing && start) {
          const p = at(ev);
          for (const [k, v] of [["x", Math.min(start.x, p.x)], ["y", Math.min(start.y, p.y)], ["width", Math.abs(p.x - start.x)], ["height", Math.abs(p.y - start.y)], ["visibility", "visible"]]) box.setAttribute(k, v);
        } else if (!brushing && ev.pointerType === "mouse") say(nearest(ev, 24) ?? selected);
      });
      s.addEventListener("pointerup", ev => {
        if (brushing && start) {
          const p = at(ev);
          if (Math.abs(p.x - start.x) > 12 && Math.abs(p.y - start.y) > 12) {
            view = { x0: ix(Math.min(start.x, p.x)), x1: ix(Math.max(start.x, p.x)), y0: iy(Math.max(start.y, p.y)), y1: iy(Math.min(start.y, p.y)) };
            brushing = false;
          }
          start = null;
          draw();
        } else if (!brushing) select(nearest(ev, ev.pointerType === "mouse" ? 16 : 28));
      });
      s.addEventListener("pointerleave", ev => { if (ev.pointerType === "mouse") say(selected); });

      say(selected && shown.includes(selected) ? selected : null);
      count.textContent = shown.length === rows.length ? `${rows.length} dots` : `${shown.length} of ${rows.length} dots`;
      const listed = shown.length <= LIST_MAX ? [...shown].sort((a, b) => b[block.y] - a[block.y]) : [];
      list.hidden = !listed.length;
      const cell = (cls, text) => Object.assign(document.createElement("span"), { className: cls, textContent: text });
      const head = document.createElement("li");
      head.className = "head";
      head.append(cell("list-rank", ""), cell("list-key", ""), cell("list-value", block.x_unit || block.x), cell("list-value", block.y_unit || block.y));
      list.replaceChildren(head, ...listed.map((r, i) => {
        const li = document.createElement("li");
        if (r === selected) li.className = "selected";
        const b = document.createElement("button");
        b.type = "button";
        b.append(cell("list-rank", String(i + 1)), cell("list-key", name(r)), cell("list-value", show(block.x_format, r[block.x])), cell("list-value", show(block.y_format, r[block.y])));
        b.addEventListener("click", () => select(r === selected ? null : r));
        li.appendChild(b);
        return li;
      }));
    };
    redrawOnResize(fig, draw);
  }

  function table(section, block) {
    const t = section.querySelector("table");
    const wrap = t.parentElement;
    const filter = section.querySelector(".filter"), decades = section.querySelector(".decade");
    const count = section.querySelector(".count");
    const rows = block.rows.map((r, i) => ({ row: r, order: i }));
    const cols = block.columns;
    if (decades)
      for (const d of [...new Set(rows.map(r => decade(r.row[block.decades])))].sort((a, b) => a - b))
        decades.add(new Option(`${d}s`, d));
    const barMax = {};
    const barWidth = {};
    for (const c of cols.filter(c => c.bar)) {
      barMax[c.key] = Math.max(...rows.map(r => Math.abs(r.row[c.key] ?? 0))) || 1;
      barWidth[c.key] = Math.max(...rows.map(r => r.row[c.key] === null ? 0 : show(c.format, r.row[c.key]).length));
    }
    let key = null, dir = 1, folded = new Set();
    const expanded = new Set();

    let controls = section.querySelector(".controls");
    if (!controls) {
      controls = document.createElement("div");
      controls.className = "controls";
      wrap.before(controls);
    }
    const sortBy = document.createElement("select");
    sortBy.setAttribute("aria-label", "Sort by");
    sortBy.add(new Option("Sort by", ""));
    cols.forEach((c, i) => sortBy.add(new Option(c.label, i)));
    controls.insertBefore(sortBy, count ?? null);
    const note = document.createElement("p");
    note.className = "fold-note";
    wrap.before(note);

    const sortOn = c => {
      dir = key === c.key ? -dir : c.format === "text" ? 1 : -1;
      key = c.key;
      render();
    };
    sortBy.addEventListener("change", () => {
      if (sortBy.value !== "") sortOn(cols[Number(sortBy.value)]);
      sortBy.value = "";
    });

    const head = t.createTHead().insertRow();
    const body = t.createTBody();
    cols.forEach((c, i) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.dataset.col = i;
      if (c.format !== "text") th.className = "numeric";
      const b = document.createElement("button");
      b.type = "button"; b.textContent = c.label;
      b.addEventListener("click", () => sortOn(c));
      th.appendChild(b);
      head.appendChild(th);
    });
    const toggleHead = document.createElement("th");
    toggleHead.className = "toggle";
    toggleHead.setAttribute("aria-label", "More");
    head.appendChild(toggleHead);

    const compare = (a, b) => {
      if (key === null) return a.order - b.order;
      const x = a.row[key], y = b.row[key];
      if (x === y) return a.order - b.order;
      if (x === null) return 1;
      if (y === null) return -1;
      return (x > y ? 1 : -1) * dir;
    };

    function cellContent(td, c, row) {
      if (c.bar && row[c.key] !== null) {
        const track = document.createElement("span"), fill = document.createElement("span"), value = document.createElement("span");
        track.className = "cell-bar"; fill.className = "cell-bar-fill"; value.className = "cell-bar-value";
        fill.style.width = `${Math.max(0, row[c.key]) / barMax[c.key] * 100}%`;
        value.textContent = show(c.format, row[c.key]);
        value.style.minWidth = `${barWidth[c.key]}ch`;
        track.appendChild(fill);
        td.append(track, value);
      } else td.textContent = show(c.format, row[c.key]);
    }

    function apply() {
      for (const el of t.querySelectorAll("[data-col]")) el.hidden = folded.has(Number(el.dataset.col));
      for (const el of t.querySelectorAll(".fold-item")) el.hidden = !folded.has(Number(el.dataset.fold));
      const any = folded.size > 0;
      for (const el of t.querySelectorAll(".toggle")) el.hidden = !any;
      for (const el of t.querySelectorAll("tr.detail")) el.hidden = !any || !expanded.has(Number(el.dataset.order));
      for (const el of t.querySelectorAll("tr.row")) el.setAttribute("aria-expanded", String(any && expanded.has(Number(el.dataset.order))));
      t.classList.toggle("foldable", any);
      sortBy.hidden = !any;
      note.hidden = !any;
      note.textContent = any ? `Tap a row for ${folded.size} more ${folded.size === 1 ? "column" : "columns"}: ${[...folded].sort((a, b) => a - b).map(i => cols[i].label).join(" · ")}.` : "";
    }

    function fit() {
      folded = new Set();
      apply();
      for (let i = cols.length - 1; i > 0 && wrap.scrollWidth > wrap.clientWidth + 1; i--) {
        folded.add(i);
        apply();
      }
    }

    function render() {
      const q = filter ? filter.value.trim().toLowerCase() : "";
      const d = decades ? decades.value : "";
      const shown = rows
        .filter(r => !q || String(r.row[block.search] ?? "").toLowerCase().includes(q))
        .filter(r => !d || decade(r.row[block.decades]) === Number(d))
        .sort(compare);
      [...head.cells].slice(0, cols.length).forEach((th, i) =>
        th.setAttribute("aria-sort", cols[i].key === key ? (dir > 0 ? "ascending" : "descending") : "none"));
      body.replaceChildren(...shown.flatMap(({ row, order }) => {
        const tr = document.createElement("tr");
        tr.className = "row";
        tr.dataset.order = order;
        cols.forEach((c, i) => {
          const td = tr.insertCell();
          td.className = c.format === "text" ? "text" : "numeric";
          td.dataset.col = i;
          cellContent(td, c, row);
        });
        const toggle = tr.insertCell();
        toggle.className = "toggle";
        const detail = document.createElement("tr");
        detail.className = "detail";
        detail.dataset.order = order;
        const dc = detail.insertCell();
        dc.colSpan = cols.length + 1;
        const dl = document.createElement("dl");
        cols.forEach((c, i) => {
          const item = document.createElement("div");
          item.className = "fold-item";
          item.dataset.fold = i;
          const dt = document.createElement("dt"), dd = document.createElement("dd");
          dt.textContent = c.label;
          cellContent(dd, c, row);
          item.append(dt, dd);
          dl.appendChild(item);
        });
        dc.appendChild(dl);
        tr.addEventListener("click", () => {
          if (!folded.size) return;
          expanded.has(order) ? expanded.delete(order) : expanded.add(order);
          apply();
        });
        return [tr, detail];
      }));
      if (count) count.textContent = `${shown.length} of ${rows.length}`;
      fit();
    }
    filter?.addEventListener("input", render);
    decades?.addEventListener("change", render);
    render();
    let width = wrap.clientWidth;
    new ResizeObserver(() => { if (wrap.clientWidth !== width) { width = wrap.clientWidth; fit(); } }).observe(wrap);
    document.fonts?.ready.then(fit);
  }

  const DRAW = { line: lineChart, multiples, bar: barChart, scatter: scatterChart, table };
  DATA.blocks.forEach((block, i) => DRAW[block.type]?.(document.querySelector(`[data-block="${i}"]`), block));
})();
