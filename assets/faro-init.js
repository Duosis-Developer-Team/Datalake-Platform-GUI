/**
 * Grafana Faro Web SDK bootstrap for Dash (datalake-webui).
 * Sends RUM to the **same OTEL Collector** via OTLP HTTP (:4318), with
 * browser-specific labels (app.name / telemetry.source=faro).
 * Config: GET /telemetry/faro-config.json — no-op when disabled.
 */
(function () {
  "use strict";

  var SDK_SRC = "https://cdn.jsdelivr.net/npm/@grafana/faro-web-sdk@2/dist/bundle/faro-web-sdk.iife.js";
  var TRACING_SRC =
    "https://cdn.jsdelivr.net/npm/@grafana/faro-web-tracing@2/dist/bundle/faro-web-tracing.iife.js";
  var OTLP_SRC =
    "https://cdn.jsdelivr.net/npm/@grafana/faro-transport-otlp-http@2/dist/bundle/faro-transport-otlp-http.iife.js";

  var queue = [];
  var faroInstance = null;

  function drainQueue() {
    while (queue.length && faroInstance) {
      var item = queue.shift();
      try {
        item(faroInstance);
      } catch (e) {
        console.warn("[faro] queued call failed", e);
      }
    }
  }

  window.__datalakeFaro = {
    ready: false,
    pushEvent: function (name, attributes, domain) {
      var run = function (faro) {
        if (faro && faro.api && typeof faro.api.pushEvent === "function") {
          if (domain) {
            faro.api.pushEvent(name, attributes || {}, domain);
          } else {
            faro.api.pushEvent(name, attributes || {});
          }
        }
      };
      if (faroInstance) {
        run(faroInstance);
      } else {
        queue.push(run);
      }
    },
    setView: function (name) {
      var run = function (faro) {
        if (faro && faro.api && typeof faro.api.setView === "function") {
          faro.api.setView({ name: String(name || "/") });
        }
      };
      if (faroInstance) {
        run(faroInstance);
      } else {
        queue.push(run);
      }
    },
  };

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error("Failed to load " + src));
      };
      document.head.appendChild(s);
    });
  }

  function scrubPayloadUrls(item) {
    if (!item || typeof item !== "object") {
      return item;
    }
    try {
      var raw = JSON.stringify(item);
      var scrubbed = raw.replace(
        /"(https?:\/\/[^"?\\]+)\?[^"]*"/g,
        function (_m, base) {
          return '"' + base + '"';
        }
      );
      return JSON.parse(scrubbed);
    } catch (e) {
      return item;
    }
  }

  function readCookie(name) {
    var match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : "";
  }

  function clearCookie(name) {
    document.cookie = name + "=; Max-Age=0; path=/; SameSite=Lax";
  }

  function flushLoginEvent() {
    if (readCookie("faro_evt_login") !== "1") {
      return;
    }
    clearCookie("faro_evt_login");
    window.__datalakeFaro.pushEvent("user_logged_in", {}, "auth");
  }

  function initFromConfig(cfg) {
    if (!cfg || !cfg.enabled || !cfg.tracesURL || !cfg.logsURL) {
      return;
    }
    if (!window.GrafanaFaroWebSdk || typeof window.GrafanaFaroWebSdk.initializeFaro !== "function") {
      console.warn("[faro] GrafanaFaroWebSdk not available");
      return;
    }
    var OtlpHttpTransport =
      window.GrafanaFaroTransportOtlpHttp &&
      window.GrafanaFaroTransportOtlpHttp.OtlpHttpTransport;
    if (!OtlpHttpTransport) {
      console.warn("[faro] OtlpHttpTransport not available");
      return;
    }

    var ignoreUrls = [
      /\/telemetry\/faro-config\.json/,
      /\/v1\/traces/,
      /\/v1\/logs/,
      /cdn\.jsdelivr\.net/,
      /unpkg\.com/,
    ];

    var transportOpts = {
      tracesURL: cfg.tracesURL,
      logsURL: cfg.logsURL,
    };
    if (cfg.apiKey) {
      transportOpts.apiKey = cfg.apiKey;
    }

    var options = {
      app: cfg.app || { name: "datalake-webui-browser" },
      ignoreUrls: ignoreUrls,
      ignoreErrors: [
        /^ResizeObserver loop limit exceeded$/,
        /^ResizeObserver loop completed with undelivered notifications$/,
        /^Script error$/,
        /chrome-extension:\/\//,
        /moz-extension:\/\//,
      ],
      beforeSend: function (item) {
        return scrubPayloadUrls(item);
      },
      transports: [new OtlpHttpTransport(transportOpts)],
    };
    if (typeof window.GrafanaFaroWebSdk.getWebInstrumentations === "function") {
      options.instrumentations = window.GrafanaFaroWebSdk.getWebInstrumentations({
        captureConsole: false,
      });
    }

    faroInstance = window.GrafanaFaroWebSdk.initializeFaro(options);
    window.__datalakeFaro.ready = true;

    if (cfg.attributes && faroInstance && faroInstance.api && faroInstance.api.setSession) {
      try {
        faroInstance.api.setSession({
          attributes: cfg.attributes,
        });
      } catch (e) {
        /* optional session labels */
      }
    }

    drainQueue();

    var pathname = (window.location && window.location.pathname) || "/";
    window.__datalakeFaro.setView(pathname);
    flushLoginEvent();

    if (window.GrafanaFaroWebTracing && window.GrafanaFaroWebTracing.TracingInstrumentation) {
      try {
        faroInstance.instrumentations.add(
          new window.GrafanaFaroWebTracing.TracingInstrumentation()
        );
      } catch (e) {
        console.warn("[faro] TracingInstrumentation failed", e);
      }
    }
  }

  function boot() {
    fetch("/telemetry/faro-config.json", { credentials: "same-origin", cache: "no-store" })
      .then(function (res) {
        if (!res.ok) {
          throw new Error("faro-config HTTP " + res.status);
        }
        return res.json();
      })
      .then(function (cfg) {
        if (!cfg || !cfg.enabled) {
          return null;
        }
        return loadScript(SDK_SRC)
          .then(function () {
            return loadScript(OTLP_SRC);
          })
          .then(function () {
            return loadScript(TRACING_SRC);
          })
          .then(function () {
            initFromConfig(cfg);
          });
      })
      .catch(function (err) {
        console.warn("[faro] init skipped:", err && err.message ? err.message : err);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
