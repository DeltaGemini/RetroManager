// Small helpers every page with the header shares. Plain JavaScript, loaded before the
// page's own scripts:
//     RM.bytes(1536)                          "1.5 KB"
//     await RM.sendJson(url, 'POST', body)    the server's JSON answer, with its HTTP status
//     await RM.getJson(url)                   the server's JSON answer, or null if it failed
(function () {
    window.RM = window.RM || {};

    window.RM.bytes = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB`
        : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`);

    // A body sent as JSON. An answer that isn't JSON (a proxy's error page, say) comes back as
    // {success: false, error}; a connection that fails throws, as fetch does.
    window.RM.sendJson = async (url, method, body) => {
        const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body === undefined ? {} : body) });
        const data = await res.json().catch(() => ({ success: false, error: `The server answered ${res.status} ${res.statusText}`.trim() }));
        return { status: res.status, ...data };
    };

    window.RM.getJson = (url) => fetch(url).then(r => r.json()).catch(() => null);
})();
