// Docked YouTube player shared by the note reader and the transcript page.
// window.notesPlayer(box, videoId) -> { ensure, play, onTime }
// scrolls the reader triggers itself: instant when the user asks for reduced motion
window.notesScroll = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
// the reader moved the page or panel by hand: wheel, touch, scroll keys
window.notesOnManualScroll = (el, f) => {
  for (const ev of ["wheel", "touchmove"]) el.addEventListener(ev, f, { passive: true });
  el.addEventListener("keydown", (e) => {
    if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(e.key)) f();
  });
};
window.notesPlayer = (box, videoId) => {
  let yt = null, ready = null, timer = null;
  const listeners = [];

  function ensure() {
    if (ready) return ready;
    box.classList.add("open");
    ready = new Promise((resolve) => {
      const make = () => {
        yt = new YT.Player(box.querySelector("[data-yt]"), {
          videoId, playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
          events: {
            onReady: () => resolve(yt),
            // poll the clock only while playing
            onStateChange: (e) => {
              clearInterval(timer);
              if (e.data === YT.PlayerState.PLAYING) timer = setInterval(tick, 500);
              tick();
            },
          },
        });
      };
      if (window.YT?.Player) return make();
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => { prev?.(); make(); };
      if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
        const s = document.createElement("script");
        s.src = "https://www.youtube.com/iframe_api";
        document.head.appendChild(s);
      }
    });
    return ready;
  }
  function tick() {
    const t = yt?.getCurrentTime?.();
    if (typeof t === "number") listeners.forEach((f) => f(t));
  }
  async function play(sec) {
    box.classList.add("open");
    const p = await ensure();
    p.seekTo(sec, true); p.playVideo();
  }

  // anchors (#heading, #L123) scroll to just below the docked player, not behind it
  const root = document.documentElement;
  const setH = () => root.style.setProperty("--player-h", box.offsetHeight + "px");
  setH();
  new ResizeObserver(setH).observe(box);
  if (location.hash) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();

  box.querySelector("[data-close-player]")?.addEventListener("click", () => {
    yt?.pauseVideo(); box.classList.remove("open");
  });
  const mini = box.querySelector("[data-mini]");
  mini?.addEventListener("click", () => {
    const on = box.classList.toggle("mini"), label = on ? "放大播放器" : "縮小播放器";
    mini.setAttribute("aria-pressed", String(on));
    mini.setAttribute("aria-label", label); mini.title = label;
  });
  const hintBtn = box.querySelector("[data-hint]"), hint = box.querySelector(".player-hint");
  hintBtn?.addEventListener("click", () => {
    hint.hidden = !hint.hidden;
    hintBtn.setAttribute("aria-expanded", String(!hint.hidden));
  });

  return { ensure, play, onTime: (f) => listeners.push(f) };
};
