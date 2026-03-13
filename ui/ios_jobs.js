(() => {
  const ready = (fn) => {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      fn();
    }
  };

  const animateScreen = (el) => {
    if (!el) return;
    el.classList.remove('ios-screen-enter');
    // force reflow for replay
    void el.offsetWidth;
    el.classList.add('ios-screen-enter');
  };

  ready(() => {
    const upload = document.getElementById('upload-screen');
    const chat = document.getElementById('chat-screen');

    const obs = new MutationObserver(() => {
      const uploadVisible = upload && upload.offsetParent !== null;
      const chatVisible = chat && chat.offsetParent !== null;
      if (uploadVisible) animateScreen(upload);
      if (chatVisible) animateScreen(chat);
      document.body.classList.toggle('ios-in-chat', Boolean(chatVisible));
    });

    if (upload) obs.observe(upload, { attributes: true, attributeFilter: ['style', 'class'] });
    if (chat) obs.observe(chat, { attributes: true, attributeFilter: ['style', 'class'] });

    [upload, chat].forEach((el) => {
      if (!el) return;
      el.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('pointerdown', () => btn.classList.add('ios-press'));
        btn.addEventListener('pointerup', () => btn.classList.remove('ios-press'));
        btn.addEventListener('pointerleave', () => btn.classList.remove('ios-press'));
      });

      el.querySelectorAll('textarea, input').forEach((input) => {
        input.addEventListener('focus', () => input.classList.add('ios-focus'));
        input.addEventListener('blur', () => input.classList.remove('ios-focus'));
      });
    });

    if (upload && upload.offsetParent !== null) animateScreen(upload);
  });
})();
