/*
 * Sends the browser to /login when the server rejects a Dash callback for a
 * missing session.
 *
 * The callback transport (POST /_dash-update-component) answers 401 once the
 * session is gone (see src/auth/dash_gate.py). Without this, dash-renderer just
 * marks the callback failed and the page sits there half-rendered showing
 * whatever was on screen before the session expired — the "page comes and goes"
 * symptom. Assets are evaluated before the renderer is constructed, so patching
 * fetch here covers every callback the app will ever make.
 */
(function () {
    "use strict";

    var origFetch = window.fetch;
    if (typeof origFetch !== "function") {
        return;
    }

    var redirecting = false;

    function requestUrl(input) {
        if (typeof input === "string") return input;
        if (input && typeof input.url === "string") return input.url;
        return "";
    }

    function goToLogin() {
        if (redirecting) return;
        var here = window.location.pathname + window.location.search;
        // Never bounce the login page at itself.
        if (window.location.pathname === "/login") return;
        redirecting = true;
        window.location.href = "/login?next=" + encodeURIComponent(here);
    }

    window.fetch = function (input) {
        return origFetch.apply(this, arguments).then(function (response) {
            try {
                if (
                    response &&
                    response.status === 401 &&
                    requestUrl(input).indexOf("_dash-update-component") !== -1
                ) {
                    goToLogin();
                }
            } catch (err) {
                /* never let the guard break a real response */
            }
            return response;
        });
    };
})();
