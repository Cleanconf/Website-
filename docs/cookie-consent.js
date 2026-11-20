(function () {
  "use strict";

  var STORAGE_KEY = "oso_site_analytics_consent";
  var GA_ID = "G-0G1BK3V47K";
  var gaLoaded = false;

  function readConsent() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (typeof parsed.analytics !== "boolean") return null;
      return parsed;
    } catch (e) {
      return null;
    }
  }

  function saveConsent(accepted) {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ analytics: accepted, timestamp: new Date().toISOString() })
      );
    } catch (e) {
      /* localStorage unavailable, consent simply won't be remembered */
    }
  }

  function loadGA() {
    if (gaLoaded) return;
    gaLoaded = true;
    window["ga-disable-" + GA_ID] = false;
    var script = document.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_ID;
    document.head.appendChild(script);
    window.dataLayer = window.dataLayer || [];
    function gtag() {
      window.dataLayer.push(arguments);
    }
    window.gtag = gtag;
    gtag("js", new Date());
    gtag("config", GA_ID);
  }

  function deleteGACookies() {
    var names = document.cookie.split(";").map(function (c) {
      return c.split("=")[0].trim();
    });
    names
      .filter(function (name) {
        return name.indexOf("_ga") === 0;
      })
      .forEach(function (name) {
        document.cookie = name + "=; Max-Age=-1; path=/;";
      });
  }

  function disableGA() {
    window["ga-disable-" + GA_ID] = true;
    deleteGACookies();
  }

  function buildBanner() {
    var banner = document.createElement("div");
    banner.className = "cookie-banner";
    banner.setAttribute("role", "region");
    banner.setAttribute("aria-label", "Cookie choices");
    banner.hidden = true;
    banner.innerHTML =
      '<p>We use analytics cookies to understand how people use OSO Organised, but only if you say yes. Read our <a href="/privacy/">Privacy Policy</a>.</p>' +
      '<div class="cookie-banner__actions">' +
      '<button type="button" class="btn" data-cookie-reject>Reject</button>' +
      '<button type="button" class="btn btn--accent" data-cookie-accept>Accept</button>' +
      "</div>";
    document.body.appendChild(banner);
    return banner;
  }

  function init() {
    var banner = buildBanner();
    var acceptBtn = banner.querySelector("[data-cookie-accept]");
    var rejectBtn = banner.querySelector("[data-cookie-reject]");

    function showBanner() {
      banner.hidden = false;
    }
    function hideBanner() {
      banner.hidden = true;
    }

    acceptBtn.addEventListener("click", function () {
      saveConsent(true);
      hideBanner();
      loadGA();
    });
    rejectBtn.addEventListener("click", function () {
      saveConsent(false);
      hideBanner();
      disableGA();
    });

    var consent = readConsent();
    if (consent === null) {
      showBanner();
    } else if (consent.analytics === true) {
      loadGA();
    } else {
      disableGA();
    }

    var settingsButtons = document.querySelectorAll("[data-cookie-settings]");
    for (var i = 0; i < settingsButtons.length; i++) {
      settingsButtons[i].addEventListener("click", function (event) {
        event.preventDefault();
        showBanner();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
