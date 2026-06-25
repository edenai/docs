/**
 * Cookie consent banner for the Eden AI docs (Mintlify).
 *
 * How it works:
 *   Mintlify only loads analytics/telemetry (Hotjar) when localStorage contains
 *   the key/value declared under `integrations.cookies` in docs.json. This script
 *   shows a GDPR opt-in banner and writes that key only after the visitor accepts
 *   the "analytics" category, so Hotjar stays off until consent is given.
 *
 *   Intercom (support chat) is intentionally NOT gated here — it is treated as a
 *   strictly-necessary, always-available support tool per product decision.
 *
 * Banner library: vanilla-cookieconsent (https://cookieconsent.orestbida.com),
 * loaded from jsDelivr. The site CSP has no script-src restriction, so the CDN
 * load is allowed.
 */
(function () {
  var STORAGE_KEY = "edenai-cookie-consent";
  var STORAGE_VALUE = "accepted";
  var CDN = "https://cdn.jsdelivr.net/npm/vanilla-cookieconsent@3/dist/cookieconsent";

  // Mintlify is a SPA; guard against re-initialising on client-side navigation.
  if (window.__edenaiCookieConsentLoaded) return;
  window.__edenaiCookieConsentLoaded = true;

  function loadCss(href) {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function loadScript(src, onload) {
    var s = document.createElement("script");
    s.src = src;
    s.defer = true;
    s.onload = onload;
    document.head.appendChild(s);
  }

  // Mirror the consent choice into the localStorage key Mintlify reads.
  // Storage access can throw (private mode, disabled storage, quota); on failure
  // the key stays unset, so telemetry simply remains disabled.
  function syncMintlifyConsent() {
    var cc = window.CookieConsent;
    try {
      if (cc && cc.acceptedCategory("analytics")) {
        localStorage.setItem(STORAGE_KEY, STORAGE_VALUE);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch (e) {
      /* storage unavailable; telemetry stays disabled */
    }
  }

  function init() {
    var cc = window.CookieConsent;
    if (!cc) return;

    cc.run({
      guiOptions: {
        consentModal: { layout: "box", position: "bottom right" },
        preferencesModal: { layout: "box" }
      },
      categories: {
        necessary: { enabled: true, readOnly: true },
        analytics: {
          // On withdrawal, delete Hotjar's first-party cookies (_hjid,
          // _hjSession_*, _hjSessionUser_*, etc.) so rejecting analytics
          // actually removes them rather than leaving them behind.
          autoClear: {
            cookies: [{ name: /^_hj/ }]
          }
        }
      },
      language: {
        default: "en",
        translations: {
          en: {
            consentModal: {
              title: "We use cookies",
              description:
                'We use strictly necessary cookies to run this site and our support chat, plus optional analytics cookies (Hotjar) to understand how the documentation is used. See our <a href="https://www.edenai.co/privacy" target="_blank">Privacy Policy</a>.',
              acceptAllBtn: "Accept",
              acceptNecessaryBtn: "Reject",
              showPreferencesBtn: "Manage preferences"
            },
            preferencesModal: {
              title: "Cookie preferences",
              acceptAllBtn: "Accept all",
              acceptNecessaryBtn: "Reject all",
              savePreferencesBtn: "Save preferences",
              closeIconLabel: "Close",
              sections: [
                {
                  title: "Strictly necessary",
                  description:
                    "Required for the site and the Intercom support chat to function. Always on.",
                  linkedCategory: "necessary"
                },
                {
                  title: "Analytics (Hotjar)",
                  description:
                    "Helps us understand how visitors use the documentation so we can improve it.",
                  linkedCategory: "analytics"
                },
                {
                  title: "More information",
                  description:
                    'For details, see our <a href="https://www.edenai.co/privacy" target="_blank">Privacy Policy</a>.'
                }
              ]
            }
          }
        }
      },
      // Fires on every load once a choice exists: keep the Mintlify key in sync
      // (idempotent, no reload).
      onConsent: syncMintlifyConsent,
      // First time the visitor makes a choice.
      onFirstConsent: function () {
        syncMintlifyConsent();
        // Only reload when analytics was accepted, so Mintlify picks up Hotjar
        // on the fresh load. A first-time "Reject" needs no reload (Hotjar was
        // never loaded).
        if (window.CookieConsent.acceptedCategory("analytics")) {
          window.location.reload();
        }
      },
      // Preferences changed after the initial choice: reload to apply.
      onChange: function () {
        syncMintlifyConsent();
        window.location.reload();
      }
    });
  }

  // Persistent "Manage cookies" entry point (GDPR: withdrawing consent must be
  // as easy as giving it). Any link to #manage-cookies — e.g. the footer link
  // declared in docs.json — re-opens the preferences modal. Capture phase so it
  // wins over Mintlify's own anchor handling.
  document.addEventListener(
    "click",
    function (e) {
      var trigger =
        e.target.closest && e.target.closest('a[href$="#manage-cookies"]');
      if (!trigger) return;
      e.preventDefault();
      e.stopPropagation();
      if (window.CookieConsent) window.CookieConsent.showPreferences();
    },
    true
  );

  loadCss(CDN + ".css");
  loadScript(CDN + ".umd.js", init);
})();
