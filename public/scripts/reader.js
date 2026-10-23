// 筆記 reader: citation popovers, the docked YouTube player with a follow-along transcript, TOC highlight.
(() => {
  const art = document.querySelector("article[data-transcript]");
  if (!art) return;
  const videoId = art.dataset.video;

  // ---------- transcript data (lazy) ----------
  let dataP = null;
  const loadData = () => (dataP ??= fetch(art.dataset.transcript).then((r) => r.json()).catch(() => null));

  const fmt = (sec) => {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = Math.floor(sec % 60);
    const p = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${p(m)}:${p(s)}` : `${m}:${p(s)}`;
  };
  // time of line n: its own, else the nearest timed line at or before it, else after
  function timeOf(data, n) {
    if (data.t[n]) return data.t[n];
    for (let k = n - 1; k > n - 12 && k > 0; k--) if (data.t[k]) return [data.t[k][0], 1];
    for (let k = n + 1; k < n + 12; k++) if (data.t[k]) return [data.t[k][0], 1];
    return null;
  }
  function excerpt(data, s, e) {
    const out = [];
    for (let n = s; n <= Math.min(e, s + 6); n++) {
      const t = (data.lines[n - 1] || "").trim();
      if (t) out.push(t.replace(/\*\*/g, ""));
    }
    return out.join(" ");
  }
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // ---------- popover ----------
  let pop = null, popFor = null, hoverTimer = null;
  function closePop() {
    pop?.remove(); pop = null;
    popFor?.classList.remove("on"); popFor = null;
  }
  function place(el) {
    const r = popFor.getBoundingClientRect();
    const w = el.offsetWidth, vw = document.documentElement.clientWidth;
    let left = r.left + window.scrollX - w / 2 + r.width / 2;
    left = Math.max(window.scrollX + 16, Math.min(left, window.scrollX + vw - w - 16));
    let top = r.bottom + window.scrollY + 6;
    if (r.bottom + el.offsetHeight + 12 > window.innerHeight && r.top > el.offsetHeight + 12)
      top = r.top + window.scrollY - el.offsetHeight - 6;
    el.style.left = left + "px"; el.style.top = top + "px";
  }
  async function openPop(a) {
    if (popFor === a) return;
    closePop();
    popFor = a; a.classList.add("on");
    pop = document.createElement("div");
    pop.className = "pop"; pop.setAttribute("role", "dialog");
    pop.innerHTML = '<div class="pop-head">載入中…</div>';
    document.body.appendChild(pop); place(pop);
    const mine = pop;
    const data = await loadData();
    if (pop !== mine) return;
    const ranges = a.dataset.r.split(",").map((x) => x.split("-").map(Number));
    let html = a.dataset.note ? `<div class="pop-note">${esc(a.dataset.note)}</div>` : "";
    for (const [s, e0] of ranges) {
      const e = e0 || s;
      const t = data && timeOf(data, s);
      const label = `行${s}${e !== s ? "–" + e : ""}`;
      const time = t ? `${t[1] ? "≈" : ""}${fmt(t[0])}` : "";
      html += `<div class="pop-row"><div class="pop-head"><span>${label}${time ? " · " + time : ""}</span>` +
        (t && videoId ? `<button class="play" data-seek="${t[0]}">▶ 播放</button>` : "") + `</div>` +
        (data ? `<p class="pop-text">${esc(excerpt(data, s, e))}</p>` : "") + `</div>`;
    }
    html += `<div class="pop-foot"><a href="transcript/#L${ranges[0][0]}">在逐字稿中看 →</a></div>`;
    pop.innerHTML = html;
    place(pop);
  }

  const body = art.querySelector(".prose");
  body.addEventListener("click", (ev) => {
    const a = ev.target.closest("a.c");
    if (!a) return;
    ev.preventDefault();
    popFor === a ? closePop() : openPop(a);
  });
  if (matchMedia("(hover: hover)").matches) {
    body.addEventListener("mouseover", (ev) => {
      const a = ev.target.closest("a.c");
      if (!a) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => openPop(a), 250);
    });
    body.addEventListener("mouseout", (ev) => {
      if (ev.target.closest("a.c")) clearTimeout(hoverTimer);
    });
  }
  document.addEventListener("click", (ev) => {
    if (!pop) return;
    const seek = ev.target.closest("[data-seek]");
    if (seek) { play(Number(seek.dataset.seek)); closePop(); return; }
    if (!ev.target.closest(".pop, a.c")) closePop();
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closePop(); });
  window.addEventListener("resize", () => pop && place(pop));

  // ---------- citation toggle ----------
  const tog = document.querySelector("[data-toggle-cites]");
  const setCites = (on) => {
    body.classList.toggle("hide-cites", !on);
    tog.setAttribute("aria-pressed", String(on));
    tog.textContent = `出處標記：${on ? "開" : "關"}`;
    try { localStorage.setItem("cites", on ? "1" : "0"); } catch (e) {}
  };
  try { if (localStorage.getItem("cites") === "0") setCites(false); } catch (e) {}
  tog.addEventListener("click", () => { closePop(); setCites(body.classList.contains("hide-cites")); });

  // ---------- player (open by default) + follow-along transcript ----------
  const box = document.getElementById("player");
  const player = box && videoId ? window.notesPlayer(box, videoId) : null;
  const play = (sec) => player?.play(sec);
  if (player) {
    player.ensure();
    document.querySelector("[data-open-player]")?.addEventListener("click", async () => {
      box.scrollIntoView({ behavior: notesScroll(), block: "nearest" });
      (await player.ensure()).playVideo();
    });

    const follow = box.querySelector("[data-follow]");
    const followBtn = box.querySelector("[data-toggle-follow]");
    let rows = null, active = [], userScrolled = 0;
    const setFollow = (on) => {
      box.classList.toggle("no-follow", !on);
      followBtn.setAttribute("aria-pressed", String(on));
      try { localStorage.setItem("follow", on ? "1" : "0"); } catch (e) {}
    };
    try { if (localStorage.getItem("follow") === "0") setFollow(false); } catch (e) {}
    followBtn.addEventListener("click", () => setFollow(box.classList.contains("no-follow")));

    // paragraphs after the title block; each keeps its own time or inherits the last one
    loadData().then((data) => {
      if (!data) { follow.innerHTML = '<p class="muted">逐字稿載入失敗。</p>'; return; }
      const title = data.lines.findIndex((x) => x.startsWith("# "));
      const start = data.lines.findIndex((x, i) => i > title && x.trim() === "---") + 1;
      let last = null, html = "";
      rows = [];
      data.lines.forEach((raw, i) => {
        const text = raw.trim().replace(/^> /, "").replace(/\*\*/g, "");
        if (i < start || !text) return;
        const own = data.t[i + 1];
        if (own) last = own[0];
        if (last == null) return;
        rows.push({ t: last, own: !!own });
        html += `<p data-i="${rows.length - 1}"><span class="tm">${own ? fmt(own[0]) : ""}</span>${esc(text)}</p>`;
      });
      follow.innerHTML = html || '<p class="muted">這一講沒有時間對照的逐字稿。</p>';
    });
    follow.addEventListener("click", (ev) => {
      const p = ev.target.closest("p[data-i]");
      if (p) play(rows[p.dataset.i].t);
    });
    notesOnManualScroll(follow, () => { userScrolled = Date.now(); });

    // video -> note: the citation whose time is the latest at or before now (else the earliest)
    box.querySelector("[data-to-note]")?.addEventListener("click", async () => {
      const [data, yt] = await Promise.all([loadData(), player.ensure()]);
      if (!data) return;
      const now = yt.getCurrentTime?.() ?? 0;
      let best = null, bestT = -1, first = null, firstT = Infinity;
      for (const a of body.querySelectorAll("a.c")) {
        const t = timeOf(data, Number(a.dataset.r.split(/[-,]/)[0]))?.[0];
        if (t == null) continue;
        if (t <= now && t > bestT) { best = a; bestT = t; }
        if (t < firstT) { first = a; firstT = t; }
      }
      const a = best ?? first;
      if (!a) return;
      const block = a.closest("p, li, blockquote, h2, h3, h4, td") ?? a;
      const top = block.getBoundingClientRect().top + window.scrollY - box.offsetHeight - 24;
      window.scrollTo({ top, behavior: notesScroll() });
      block.classList.remove("flash"); void block.offsetWidth; block.classList.add("flash");
    });

    player.onTime((now) => {
      if (!rows?.length || box.classList.contains("no-follow")) return;
      // last row starting at or before now (rows are in time order)
      let lo = 0, hi = rows.length - 1, k = -1;
      while (lo <= hi) { const m = (lo + hi) >> 1; if (rows[m].t <= now) { k = m; lo = m + 1; } else hi = m - 1; }
      if (k < 0) return;
      let s = k; while (s > 0 && rows[s - 1].t === rows[k].t) s--;
      if (active[0] === s) return;
      active.forEach((i) => follow.children[i]?.classList.remove("on"));
      active = [];
      for (let i = s; i <= k; i++) { follow.children[i].classList.add("on"); active.push(i); }
      if (Date.now() - userScrolled > 5000)
        follow.scrollTo({ top: follow.children[s].offsetTop - follow.clientHeight / 4, behavior: notesScroll() });
    });
  }

  // ---------- TOC highlight ----------
  const links = [...document.querySelectorAll(".toc a")];
  if (links.length && "IntersectionObserver" in window) {
    const byId = new Map(links.map((l) => [l.hash.slice(1), l]));
    const io = new IntersectionObserver((ents) => {
      for (const e of ents) if (e.isIntersecting) {
        links.forEach((l) => l.classList.remove("on"));
        byId.get(e.target.id)?.classList.add("on");
      }
    }, { rootMargin: `-${box?.offsetHeight ?? 0}px 0px -60% 0px` });
    body.querySelectorAll("h2[id]").forEach((h) => io.observe(h));
  }
})();
