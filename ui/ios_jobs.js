(() => {
  const ready = (fn) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  };

  const smoothScrollToNote = () => {
    const note = document.getElementById("workspace-note");
    if (!note) return;
    note.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const bindStartScroll = () => {
    const startBtn = document.getElementById("start-btn");
    if (!startBtn || startBtn.dataset.ncwuBound === "1") return;

    startBtn.dataset.ncwuBound = "1";
    startBtn.addEventListener("click", () => {
      setTimeout(smoothScrollToNote, 120);
      setTimeout(smoothScrollToNote, 550);
    });
  };

  const bindRealtimeNoteFollow = () => {
    const note = document.getElementById("workspace-note");
    if (!note || note.dataset.ncwuObserve === "1") return;

    note.dataset.ncwuObserve = "1";
    const observer = new MutationObserver(() => {
      note.classList.remove("ios-note-updated");
      void note.offsetWidth;
      note.classList.add("ios-note-updated");
      note.scrollTo({ top: note.scrollHeight, behavior: "smooth" });
    });
    observer.observe(note, { childList: true, subtree: true, characterData: true });
  };

  ready(() => {
    bindStartScroll();
    bindRealtimeNoteFollow();
    // Gradio may rerender nodes, so keep rebinding lightweight listeners.
    setInterval(() => {
      bindStartScroll();
      bindRealtimeNoteFollow();
    }, 1200);
  });
})();
