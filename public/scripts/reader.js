// 筆記 reader: citation popovers, the docked YouTube player, TOC highlight.
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

  // ---------- player ----------
  const box = document.getElementById("player");
  let yt = null, ytReady = null, pending = null;
  function ensurePlayer() {
    if (ytReady) return ytReady;
    box.classList.add("open");
    ytReady = new Promise((resolve) => {
      const make = () => {
        yt = new YT.Player("yt", {
          videoId, playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
          events: { onReady: () => resolve(yt) },
        });
      };
      if (window.YT?.Player) return make();
      window.onYouTubeIframeAPIReady = make;
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(s);
    });
    return ytReady;
  }
  async function play(sec) {
    if (!videoId) return;
    box.classList.add("open");
    const p = await ensurePlayer();
    p.seekTo(sec, true); p.playVideo();
  }
  if (box) {
    document.querySelector("[data-open-player]")?.addEventListener("click", () => {
      box.classList.add("open"); ensurePlayer();
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    box.querySelector("[data-close-player]").addEventListener("click", () => {
      yt?.pauseVideo(); box.classList.remove("open");
    });
    const mini = box.querySelector("[data-mini]");
    mini.addEventListener("click", () => {
      mini.textContent = box.classList.toggle("mini") ? "放大" : "縮小";
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
    }, { rootMargin: "0px 0px -75% 0px" });
    body.querySelectorAll("h2[id]").forEach((h) => io.observe(h));
  }
})();
