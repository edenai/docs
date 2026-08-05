/**
 * "Chat with us" launcher for the Eden AI docs (Mintlify).
 *
 * How it works:
 *   Mintlify boots the Intercom messenger itself from `integrations.intercom`
 *   in docs.json, which means it owns `window.intercomSettings` — so Intercom's
 *   usual `custom_launcher_selector` option is not available to us. Instead we
 *   delegate clicks: any link ending in #chat opens the messenger through the
 *   global `Intercom()` API. Same pattern as the #manage-cookies link handled in
 *   cookie-consent.js.
 *
 *   Used by the "Chat with us" navbar link (docs.json) and the Live Chat section
 *   of v3/general/support.mdx.
 *
 *   Intercom is not consent-gated (see cookie-consent.js), so the messenger is
 *   available on first load. It can still be missing when a privacy extension
 *   blocks the widget or the snippet is mid-boot, so we poll briefly and then
 *   give up quietly rather than leaving a dead click that throws.
 */
(function () {
  var SELECTOR = 'a[href$="#chat"]';
  var BOOT_TIMEOUT_MS = 5000;
  var POLL_INTERVAL_MS = 150;

  // Mintlify is a SPA; guard against re-registering the listener on
  // client-side navigation.
  if (window.__edenaiChatLauncherLoaded) return;
  window.__edenaiChatLauncherLoaded = true;

  function show() {
    if (typeof window.Intercom !== "function") return false;
    window.Intercom("show");
    return true;
  }

  // The click can land before Mintlify's Intercom snippet has finished booting,
  // so retry until it does or the deadline passes.
  function showWhenReady(deadline) {
    if (show()) return;
    if (Date.now() > deadline) return;
    setTimeout(function () {
      showWhenReady(deadline);
    }, POLL_INTERVAL_MS);
  }

  // Capture phase so this wins over Mintlify's own anchor handling, which would
  // otherwise treat #chat as an on-page heading link.
  document.addEventListener(
    "click",
    function (e) {
      var trigger = e.target.closest && e.target.closest(SELECTOR);
      if (!trigger) return;
      e.preventDefault();
      e.stopPropagation();
      showWhenReady(Date.now() + BOOT_TIMEOUT_MS);
    },
    true
  );
})();
