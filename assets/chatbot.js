/* Bulutistan AI Assistant — client-side UX helpers (auto-scroll, Enter-to-send,
   clickable suggestions). No secrets here; all network calls stay server-side. */
(function () {
  "use strict";

  function messagesEl() { return document.getElementById("chatbot-messages"); }
  function inputRow() { return document.querySelector(".chatbot-input-row"); }
  function inputEl() { var r = inputRow(); return r ? r.querySelector("textarea") : null; }
  function sendBtn() { return document.getElementById("chatbot-send-button"); }

  // Set a React-controlled textarea's value so Dash's State registers it.
  function setReactValue(el, value) {
    try {
      var setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, "value"
      ).set;
      setter.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } catch (e) {
      el.value = value;
    }
  }

  // 1) Auto-scroll the messages area to the bottom whenever content changes.
  function attachAutoScroll() {
    var el = messagesEl();
    if (!el || el.__cbScroll) return;
    var toBottom = function () { el.scrollTop = el.scrollHeight; };
    var obs = new MutationObserver(toBottom);
    obs.observe(el, { childList: true, subtree: true });
    el.__cbScroll = obs;
    toBottom();
  }

  // 2) Enter sends, Shift+Enter inserts a newline.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.shiftKey) return;
    if (!e.target || !e.target.closest || !e.target.closest(".chatbot-input-row")) return;
    e.preventDefault();
    var btn = sendBtn();
    if (btn) btn.click();
  }, true);

  // 3) Clicking a suggestion chip fills the input (user reviews, then sends).
  document.addEventListener("click", function (e) {
    var chip = e.target && e.target.closest ? e.target.closest(".chatbot-suggestion") : null;
    if (!chip) return;
    var text = chip.getAttribute("data-suggestion") || chip.textContent || "";
    var ta = inputEl();
    if (ta) { setReactValue(ta, text.trim()); ta.focus(); }
  }, true);

  // The panel mounts after initial load and survives re-renders; keep trying to
  // attach the observer until the messages element exists.
  setInterval(attachAutoScroll, 700);
  document.addEventListener("DOMContentLoaded", attachAutoScroll);
})();
