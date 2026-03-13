(() => {
  const ready = (fn) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  };

  const scrollToReader = () => {
    const target = document.getElementById("workspace-note");
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    target.scrollTop = 0;
  };

  const bindStart = () => {
    const btn = document.getElementById("start-btn");
    if (!btn || btn.dataset.ncwuBound === "1") return;
    btn.dataset.ncwuBound = "1";
    btn.addEventListener("click", () => {
      setTimeout(scrollToReader, 240);
      setTimeout(scrollToReader, 900);
    });
  };

  const bindReaderAnimation = () => {
    const note = document.getElementById("workspace-note");
    if (!note || note.dataset.ncwuObserve === "1") return;
    note.dataset.ncwuObserve = "1";
    const observer = new MutationObserver(() => {
      note.classList.remove("note-refresh");
      void note.offsetWidth;
      note.classList.add("note-refresh");
    });
    observer.observe(note, { childList: true, subtree: true, characterData: true });
  };

  const watchScreenSwitch = () => {
    const reading = document.getElementById("reading-screen");
    if (!reading || reading.dataset.ncwuWatch === "1") return;
    reading.dataset.ncwuWatch = "1";
    const obs = new MutationObserver(() => {
      const visible = reading.offsetParent !== null;
      if (visible) setTimeout(scrollToReader, 120);
    });
    obs.observe(reading, { attributes: true, attributeFilter: ["style", "class"] });
  };

  ready(() => {
    bindStart();
    bindReaderAnimation();
    watchScreenSwitch();
    setInterval(() => {
      bindStart();
      bindReaderAnimation();
      watchScreenSwitch();
    }, 1500);
  });
})();
