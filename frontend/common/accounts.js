// Who's using this device (backend/accounts.py). Loaded in each page's <head>
// after theme.js. With login on and nobody signed in, the page goes to the
// "Who's playing?" screen (/login) and comes back afterwards.
//
//     RM.me                a promise of { enabled, profile, role, admin, profiles: [...] }
//     RM.switchTo(name)    sign in as another profile (an admin's PIN is asked for on /login)
//     RM.signOut()
//     RM.avatar(profile)   { photo: url or null, initial, colour } for drawing a profile
//
// A signed-in person's preferences (theme, sort orders, which picture, touch
// layouts...) are kept on the server as well as in this browser, so they
// follow them to another device: whatever the page stores under a synced
// "retromanager." key is sent along, and a newer set from the server is taken
// (the page reloads once to show it).
(function () {
    window.RM = window.RM || {};
    // What follows a person. (Not: when this browser last scanned a system, or who "Play as" was.)
    const SYNCED = /^retromanager\.(theme|gameSort|systemSort|details\.|bookcase\.options|shelf\.|console\.view|play\.pad\.|achievements\.who)/;
    const OWNER = 'retromanager.prefs.owner', APPLIED = 'retromanager.prefs.at';
    const setItem = Storage.prototype.setItem, removeItem = Storage.prototype.removeItem;
    const read = (key) => { try { return localStorage.getItem(key); } catch (e) { return null; } };
    const write = (key, value) => { try { setItem.call(localStorage, key, value); } catch (e) {} };

    const collect = () => {
        const prefs = {};
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (SYNCED.test(key)) prefs[key] = localStorage.getItem(key);
            }
        } catch (e) {}
        return prefs;
    };
    let me = null, timer = null;
    const send = () => {
        if (!me || !me.profile) return;
        fetch('/api/accounts/prefs', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prefs: collect() }) })
            .then(r => r.json()).then(d => { if (d.success) write(APPLIED, String(d.prefs_at)); }).catch(() => {});
    };
    const changed = (storage, key) => {
        if (storage !== window.localStorage || !SYNCED.test(String(key)) || !me || !me.profile) return;
        clearTimeout(timer);
        timer = setTimeout(send, 800);
    };
    Storage.prototype.setItem = function (key, value) { setItem.apply(this, arguments); changed(this, key); };
    Storage.prototype.removeItem = function (key) { removeItem.apply(this, arguments); changed(this, key); };

    // Take the server's set if it's newer than what this browser last had, or
    // if what's here was someone else's. True if anything changed.
    const adopt = (d) => {
        const mine = read(OWNER) === d.profile;
        if (!d.prefs_at) {
            // Nothing kept for them yet: what's here becomes theirs
            write(OWNER, d.profile);
            setTimeout(send, 0);
            return false;
        }
        if (mine && Number(read(APPLIED) || 0) >= d.prefs_at) return false;
        const before = JSON.stringify(collect());
        try {
            Object.keys(collect()).forEach(key => { if (!(key in d.prefs)) removeItem.call(localStorage, key); });
            Object.entries(d.prefs).forEach(([key, value]) => setItem.call(localStorage, key, value));
        } catch (e) {}
        write(OWNER, d.profile);
        write(APPLIED, String(d.prefs_at));
        return JSON.stringify(collect()) !== before;
    };

    const onLogin = window.location.pathname === '/login';
    RM.me = fetch('/api/accounts/me').then(r => r.json()).then(d => {
        me = d;
        if (d.enabled && !d.profile && !onLogin) {
            window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
            return new Promise(() => {});   // the page is leaving
        }
        // Players don't see what only an admin can use (common/header.css)
        document.documentElement.classList.toggle('rm-player', !!d.enabled && !d.admin);
        if (d.profile && !onLogin && adopt(d)) {
            window.location.reload();
            return new Promise(() => {});
        }
        return d;
    }).catch(() => ({ success: false, enabled: false, admin: true, profile: null, profiles: [] }));

    RM.switchTo = async (name) => {
        const here = window.location.pathname + window.location.search;
        try {
            const d = await (await fetch('/api/accounts/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile: name }) })).json();
            if (d.success) { window.location.reload(); return; }
        } catch (e) {}
        // An admin: the PIN is asked for there
        window.location.href = `/login?profile=${encodeURIComponent(name)}&next=${encodeURIComponent(here)}`;
    };
    RM.signOut = async () => {
        try { await fetch('/api/accounts/logout', { method: 'POST' }); } catch (e) {}
        window.location.href = '/login';
    };
    // A colour of their own for someone without a photo
    const COLOURS = ['#e0457b', '#3aa5ab', '#fa6122', '#7c6cf0', '#3ccf91', '#d9a13a', '#4fb3d9', '#ac42bf'];
    RM.avatar = (profile) => ({
        photo: profile.photo ? `/api/accounts/photo/${encodeURIComponent(profile.photo)}` : null,
        initial: (profile.name || '?')[0].toUpperCase(),
        colour: COLOURS[[...(profile.name || '')].reduce((n, c) => n + c.charCodeAt(0), 0) % COLOURS.length],
    });
})();
