// The Console page (/console): the library the way a console shows it, after
// the Switch Master theme. Its first screen is the systems as big square tiles;
// opening one shows that system's games in the Library's own game list
// (src/common/game-list.jsx) beside the chosen game's details
// (src/common/game-details.jsx). Above the systems are the games played most
// recently, and Favourites and each collection as tiles of their own. A game
// controller works throughout. Nothing here edits: that's the Library's job.
// Loaded by console.html after those two shared files.

const { useEffect } = React;
const API_BASE = window.location.origin;
// Who made each system and its console generation (common/systems.js)
const { makerOf, generationGroup } = RM.systems;
const systemName = (s) => s.full_name || s.name;
const SYSTEM_SORTS = {
    name: (a, b) => systemName(a).localeCompare(systemName(b)),
    roms: (a, b) => b.rom_count - a.rom_count,
    missing: (a, b) => (b.missing_metadata_count || 0) - (a.missing_metadata_count || 0) || b.rom_count - a.rom_count,
    maker: (a, b) => makerOf(a.name).localeCompare(makerOf(b.name)) || systemName(a).localeCompare(systemName(b)),
    generation: (a, b) => generationGroup(a.name).rank - generationGroup(b.name).rank || systemName(a).localeCompare(systemName(b)),
};
const systemOf = (game, system) => game._system || (system && system.name);
// The address follows what's open (?system=<folder>&game=<rom path>, or
// ?list=<favourites or a collection's id>), so a reload, a bookmark or the
// Library's "Open in Console" lands in the same place. On a narrow screen a
// game picked on the list but not open is &at= instead of &game=.
const consoleParams = () => new URLSearchParams(window.location.search);
const setConsoleAddress = (params) => {
    const query = new URLSearchParams(Object.entries(params || {}).filter(([, v]) => v)).toString();
    try { window.history.replaceState(null, '', `/console${query ? `?${query}` : ''}`); } catch (e) {}
};

const SYSTEM_SORT_LABELS = [['roms', 'Most games'], ['name', 'Name'], ['missing', 'Most missing metadata'], ['maker', 'Maker'], ['generation', 'Generation']];
// Sort choices are the Library's own (the same keys in this browser's storage),
// so both pages agree
const rememberedChoice = (key, valid, fallback) => {
    try { const saved = localStorage.getItem(key); return saved && valid(saved) ? saved : fallback; } catch (e) { return fallback; }
};
const rememberChoice = (key, value) => { try { localStorage.setItem(key, value); } catch (e) {} };
// Keys that move around: arrows, or W A S D
const consoleKey = (e) => ({ arrowleft: 'left', a: 'left', arrowright: 'right', d: 'right', arrowup: 'up', w: 'up', arrowdown: 'down', s: 'down',
    enter: 'open', ' ': 'open', escape: 'back', backspace: 'back', e: 'edit', pageup: 'pageup', pagedown: 'pagedown', home: 'first', end: 'last' })[e.key.toLowerCase()];
// Not while typing, with a dropdown open, holding a modifier, or with a popup open.
// (A tick box or a button having the focus doesn't count as typing.)
const consoleTyping = (el) => el && (el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable
    || (el.tagName === 'INPUT' && !['checkbox', 'radio', 'button', 'submit'].includes(el.type)));
const consoleKeysBlocked = (e) => e.ctrlKey || e.metaKey || e.altKey || consoleTyping(e.target)
    || document.querySelector('[role="dialog"], [role="menu"]');

// The phone's Back, in the app (which calls this and leaves only if it says
// false): a popup or a menu closes, as Escape closes it; a game's page goes
// back to the list, and the list to the systems ("retromanager:back", which
// the screen that can go back cancels). On the systems there's nowhere back to.
window.RMBack = () => {
    const focus = document.activeElement;
    if (document.querySelector('[role="dialog"], [role="menu"]') || consoleTyping(focus)) {
        (focus || document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        if (consoleTyping(focus)) focus.blur();
        return true;
    }
    return !window.dispatchEvent(new Event('retromanager:back', { cancelable: true }));
};

// How the tiles are laid out: one long row, or a row per generation or maker.
// (A view, not a sort: within each row the tiles keep the chosen sort order.)
// How many of the phone's games their row shows (each is a picture to draw)
const INSTALLED_SHOWN = 60;
const SYSTEM_VIEWS = [['row', 'One row'], ['generation', 'Rows by generation'], ['maker', 'Rows by maker']];
const MAKER_ORDER = (maker) => (maker === 'Other' ? 'zzz' : maker);

// --- A game controller ---
// The pad's buttons are turned into the keys the page already answers to, so
// everything a keyboard does a controller does too. Standard layout: the
// D-pad or left stick moves, A opens or plays, B goes back, X edits, the
// shoulder buttons page through a list, Start plays.
// A press from a controller. With a popup or a menu open it moves between that
// one's buttons and presses them (B closes it); otherwise it's the key the
// screen underneath already knows. The phone app sends its controller's
// presses here too (RMPad), since a page inside it isn't given them.
const padPress = (key) => {
    document.documentElement.classList.add('rm-pad');
    const focus = document.activeElement;
    const layers = document.querySelectorAll('[role="dialog"], [role="menu"]');
    const layer = layers[layers.length - 1];
    if (!layer) {
        // A button or link left focused by the mouse would take Enter for itself
        if (focus && focus !== document.body && !consoleTyping(focus)) focus.blur();
        window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
        return;
    }
    if (key === 'Escape') {
        (layer.contains(focus) ? focus : layer).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
        return;
    }
    const items = [...layer.querySelectorAll('button, a[href], input, select, textarea')].filter(el => !el.disabled && el.type !== 'file' && el.getClientRects().length);
    const at = items.indexOf(focus);
    if (key === 'Enter') {
        const el = items[at];
        if (!el) { if (items[0]) items[0].focus(); }
        else if (el.tagName === 'INPUT' && el.form && !['checkbox', 'radio'].includes(el.type)) el.form.requestSubmit();
        else el.click();
        return;
    }
    const step = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1, PageUp: -5, PageDown: 5 }[key];
    if (!step || !items.length) return;
    const next = items[at < 0 ? (step > 0 ? 0 : items.length - 1) : Math.min(Math.max(at + step, 0), items.length - 1)];
    next.focus();
    next.scrollIntoView({ block: 'nearest' });
};
// (a finger or the mouse takes over again: no ring round what the controller chose)
window.addEventListener('pointerdown', () => document.documentElement.classList.remove('rm-pad'), true);

const PAD_BUTTONS = { 12: 'ArrowUp', 13: 'ArrowDown', 14: 'ArrowLeft', 15: 'ArrowRight', 0: 'Enter', 1: 'Escape', 2: 'e', 4: 'PageUp', 5: 'PageDown', 9: 'Enter' };
const PAD_REPEATS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown']);
function useGamepad() {
    const [connected, setConnected] = React.useState(false);
    useEffect(() => {
        // In the phone app the app itself passes the controller on
        window.RMPad = (key) => { setConnected(true); padPress(key); };
        if (window.RMApp || !navigator.getGamepads) return;
        let frame = null;
        const held = {};   // key -> when it next repeats
        const press = padPress;
        const poll = () => {
            const pads = [...navigator.getGamepads()].filter(Boolean);
            setConnected(pads.length > 0);
            if (pads.length && !document.hidden) {
                const down = new Set();
                pads.forEach(pad => {
                    Object.entries(PAD_BUTTONS).forEach(([index, key]) => { if (pad.buttons[index] && pad.buttons[index].pressed) down.add(key); });
                    const [x = 0, y = 0] = pad.axes;
                    if (x < -0.6) down.add('ArrowLeft'); else if (x > 0.6) down.add('ArrowRight');
                    if (y < -0.6) down.add('ArrowUp'); else if (y > 0.6) down.add('ArrowDown');
                });
                const now = performance.now();
                down.forEach(key => {
                    if (!(key in held)) { held[key] = now + 380; press(key); }
                    else if (PAD_REPEATS.has(key) && now >= held[key]) { held[key] = now + 110; press(key); }
                });
                Object.keys(held).forEach(key => { if (!down.has(key)) delete held[key]; });
            }
            frame = pads.length ? requestAnimationFrame(poll) : null;
        };
        const start = () => { if (frame === null) frame = requestAnimationFrame(poll); };
        window.addEventListener('gamepadconnected', start);
        window.addEventListener('gamepaddisconnected', start);
        start();
        return () => {
            window.removeEventListener('gamepadconnected', start);
            window.removeEventListener('gamepaddisconnected', start);
            if (frame !== null) cancelAnimationFrame(frame);
        };
    }, []);
    return connected;
}
// In place of a game's path: start a system's screen on one of its games, picked at random
const SURPRISE = '*surprise*';

const playedAgo = (seconds) => {
    const s = Math.max(0, Date.now() / 1000 - seconds);
    if (s < 3600) return 'in the last hour';
    if (s < 86400 * 1.5) return `${Math.round(s / 3600)} hours ago`;
    if (s < 86400 * 60) return `${Math.round(s / 86400)} days ago`;
    if (s < 86400 * 365 * 1.5) return `${Math.round(s / (86400 * 30))} months ago`;
    return `${Math.round(s / (86400 * 365))} years ago`;
};

// The chosen tile's name, in a bubble under it (above it, near the bottom of
// the screen). It follows the tile as its row scrolls.
function ConsoleBubble({ el, children }) {
    const [pos, setPos] = React.useState(null);
    const own = React.useRef(null);
    React.useLayoutEffect(() => {
        if (!el) { setPos(null); return; }
        let frame = null, until = performance.now() + 700;
        const place = () => {
            const box = el.getBoundingClientRect();
            const below = box.bottom + 64 < window.innerHeight;
            // Centred on the tile, but kept on the screen; the pointer stays on the tile
            const half = (own.current ? own.current.offsetWidth : 220) / 2 + 6;
            const centre = box.left + box.width / 2;
            const left = Math.round(Math.min(Math.max(centre, half), Math.max(half, window.innerWidth - half)));
            const next = { left, top: Math.round(below ? box.bottom + 12 : box.top - 12), below, point: Math.round(centre - left) };
            setPos(prev => (prev && prev.left === next.left && prev.top === next.top && prev.below === next.below && prev.point === next.point ? prev : next));
        };
        // The row glides to the tile, so keep up with it for a moment, then only when something scrolls
        const follow = () => { place(); frame = performance.now() < until ? requestAnimationFrame(follow) : null; };
        const nudge = () => { until = performance.now() + 300; if (frame === null) follow(); };
        follow();
        window.addEventListener('scroll', nudge, true);
        window.addEventListener('resize', nudge);
        return () => {
            if (frame !== null) cancelAnimationFrame(frame);
            window.removeEventListener('scroll', nudge, true);
            window.removeEventListener('resize', nudge);
        };
    }, [el]);
    if (!pos) return null;
    return <div ref={own} className={`console-bubble${pos.below ? '' : ' above'}`} role="status" style={{ left: pos.left, top: pos.top, '--point': `${pos.point}px` }}>{children}</div>;
}

// How the first screen is laid out, behind the button by the search (drawn
// like the phone app's own settings, whose styles it borrows)
function ConsoleSettings({ onClose, sortMode, setSortMode, view, setView, tilePicture, tileShape, setTileShape, systemPictures, hidden, toggleRow, rows }) {
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); onClose(); } };
        document.addEventListener('keydown', onKey, true);
        return () => document.removeEventListener('keydown', onKey, true);
    }, []);
    // Which system pictures there are to choose between: {default, theme, credit}
    const [about, setAbout] = React.useState(null);
    useEffect(() => {
        fetch(`${API_BASE}/api/system-pictures`).then(r => r.json()).then(d => { if (d.success) setAbout(d); }).catch(() => {});
    }, []);
    const pick = (key, label, on, onClick, note) => (
        <button key={key} className={`rm-set-row${on ? ' on' : ''}`} role="menuitemradio" aria-checked={!!on} onClick={onClick}>
            <span className="rm-set-label">{label}{note && <span className="rm-set-note">{note}</span>}</span>
            <span className="rm-set-mark" aria-hidden="true">{on ? '✓' : ''}</span>
        </button>
    );
    return ReactDOM.createPortal(
        <div className="rm-set" role="dialog" aria-modal="true" aria-label="Console settings" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <div className="rm-set-panel">
                <div className="rm-set-head">
                    <button className="rm-btn" onClick={onClose} aria-label="Close">✕</button>
                    <h2>Console settings</h2>
                </div>
                <div className="rm-set-body">
                    <section className="rm-set-group"><h3>Rows</h3>
                        <div className="rm-set-rows">{rows.map(([key, label, count]) => pick(key, label, !hidden[key], () => toggleRow(key), count ? null : 'nothing to show in it yet'))}</div>
                    </section>
                    {/* (only where the theme's pictures or the logos are installed is there a choice) */}
                    {about && (about.theme || about.logos) && (
                        <section className="rm-set-group"><h3>System tiles show</h3>
                            <div className="rm-set-rows">{RM.systems.systemPictures.available(about).map(([key, label]) => pick(key, label, key === (systemPictures || about.default), () => RM.systems.systemPictures.set(key), key === 'theme' ? about.credit : key === 'logos' ? about.logos_credit : null))}</div>
                            <p className="rm-set-empty">Here and on the Library and Bookcase pages. A system the theme has no picture for shows its drawn tile.</p>
                        </section>
                    )}
                    <section className="rm-set-group"><h3>Game tiles show</h3>
                        <div className="rm-set-rows">{RM.consolePicture.OPTIONS.map(([key, label]) => pick(key, label, key === tilePicture, () => RM.consolePicture.set(key)))}</div>
                        <p className="rm-set-empty">A game without that picture shows another it has.</p>
                    </section>
                    <section className="rm-set-group"><h3>Game tiles are</h3>
                        <div className="rm-set-rows">
                            {pick('square', 'Square', tileShape !== 'picture', () => setTileShape('square'), 'every tile the same, the picture fitted inside')}
                            {pick('picture', 'As wide as the picture', tileShape === 'picture', () => setTileShape('picture'), 'all the same height; a box is narrow, a screenshot wide')}
                        </div>
                    </section>
                    <section className="rm-set-group"><h3>Sort the systems by</h3>
                        <div className="rm-set-rows">{SYSTEM_SORT_LABELS.map(([key, label]) => pick(key, label, key === sortMode, () => setSortMode(key)))}</div>
                    </section>
                    <section className="rm-set-group"><h3>Show the systems as</h3>
                        <div className="rm-set-rows">{SYSTEM_VIEWS.map(([key, label]) => pick(key, label, key === view, () => setView(key)))}</div>
                    </section>
                </div>
            </div>
        </div>, document.body);
}

// The first screen: rows of tiles. Each tile is a system, a list (Favourites
// or a collection) or, in "Continue playing", a game.
function ConsoleSystems({ systems, home, installed, pad }) {
    // What's open: { system } or { list }, with the game to start on
    const [open, setOpen] = React.useState(() => {
        const system = systems.find(s => s.name === consoleParams().get('system'));
        return system ? { system, game: consoleParams().get('game') || consoleParams().get('at'), show: !!consoleParams().get('game') } : null;
    });
    // A list named in the address opens once the lists have arrived
    const wantedList = React.useRef(consoleParams().get('list'));
    useEffect(() => {
        const list = wantedList.current && home && home.lists.find(l => l.id === wantedList.current);
        if (list && !open) { wantedList.current = null; setOpen({ list, game: consoleParams().get('game') || consoleParams().get('at'), show: !!consoleParams().get('game') }); }
    }, [home]);
    const [sortMode, setSortModeState] = React.useState(() => rememberedChoice('retromanager.systemSort', k => SYSTEM_SORTS[k], 'roms'));
    const setSortMode = (mode) => { setSortModeState(mode); rememberChoice('retromanager.systemSort', mode); };
    // In the phone app: how many of each system's games are on the phone. With no
    // connection, the systems with none come last (and are greyed).
    const phone = gdUsePhone();
    const onPhone = (system) => (gdPhone && phone.counts[system.name]) || 0;
    const away = (system) => !!gdPhone && phone.offline && !onPhone(system);
    const shown = React.useMemo(() => {
        const sorted = systems.filter(s => s.rom_count > 0).sort(SYSTEM_SORTS[sortMode] || SYSTEM_SORTS.name);
        return gdPhone && phone.offline ? [...sorted.filter(s => !away(s)), ...sorted.filter(away)] : sorted;
    }, [systems, sortMode, phone.offline, phone.counts]);
    // The chosen tile is remembered by its key, so it stays chosen when the order changes
    const [chosen, setChosen] = React.useState(() => (consoleParams().get('system') ? `s:${consoleParams().get('system')}` : null));
    const [view, setViewState] = React.useState(() => rememberedChoice('retromanager.console.view', v => SYSTEM_VIEWS.some(x => x[0] === v), 'row'));
    const setView = (v) => { setViewState(v); rememberChoice('retromanager.console.view', v); };
    // The rows that are turned off (in the Console settings), and whether those are open
    const [hidden, setHiddenState] = React.useState(() => { try { return JSON.parse(localStorage.getItem('retromanager.console.hidden')) || {}; } catch (e) { return {}; } });
    const toggleRow = (key) => setHiddenState(was => {
        const now = { ...was, [key]: !was[key] };
        try { localStorage.setItem('retromanager.console.hidden', JSON.stringify(now)); } catch (e) {}
        return now;
    });
    const [settingsOpen, setSettingsOpen] = React.useState(false);
    // The rows of tiles: [{ label, big, items: [{ key, type, ... }] }]
    const rows = React.useMemo(() => {
        const out = [];
        const recent = (home && home.recent) || [];
        const lists = (home && home.lists) || [];
        const added = (home && home.added) || [];
        if (recent.length && !hidden.recent) out.push({ label: 'Continue playing', items: recent.map(game => ({ key: `g:${game._system}/${game.path}`, type: 'game', game, note: `played ${playedAgo(game._last_played)}` })) });
        if (added.length && !hidden.added) out.push({ label: 'Recently added', items: added.map(game => ({ key: `n:${game._system}/${game.path}`, type: 'game', game, note: `added ${playedAgo(game._added)}` })) });
        // In the phone app: what's on the phone, the ones played lately first, then by name
        if (gdPhone && installed && installed.length && !hidden.installed) {
            const played = new Map(recent.map((game, i) => [`${game._system}/${game.path}`, i]));
            const order = (game) => (played.has(`${game._system}/${game.path}`) ? played.get(`${game._system}/${game.path}`) : Infinity);
            const sorted = [...installed].sort((a, b) => (order(a) - order(b)) || gdTitle(a.name).localeCompare(gdTitle(b.name)));
            out.push({ label: installed.length > INSTALLED_SHOWN ? `Installed games (${INSTALLED_SHOWN} of ${installed.length})` : 'Installed games',
                items: sorted.slice(0, INSTALLED_SHOWN).map(game => ({ key: `i:${game._system}/${game.path}`, type: 'game', game, note: 'on this phone' })) });
        }
        // Playing, Backlog, Favourites, each collection, and a tile that picks a game for you
        const picks = lists.map(list => ({ key: `l:${list.id}`, type: 'list', list }));
        if (shown.length) picks.push({ key: 'surprise', type: 'surprise' });
        if (picks.length) out.push({ label: lists.length ? 'Your lists' : 'Something to play', items: picks });
        const item = (system) => ({ key: `s:${system.name}`, type: 'system', system });
        if (view === 'row') out.push({ label: out.length ? 'Systems' : null, big: true, items: shown.map(item) });
        else {
            const groups = {};
            shown.forEach(s => {
                const g = view === 'maker' ? { rank: MAKER_ORDER(makerOf(s.name)), label: makerOf(s.name) } : generationGroup(s.name);
                (groups[g.label] = groups[g.label] || { ...g, items: [] }).items.push(item(s));
            });
            out.push(...Object.values(groups).sort((a, b) => (typeof a.rank === 'number' ? a.rank - b.rank : String(a.rank).localeCompare(String(b.rank)))));
        }
        return out.filter(row => row.items.length);
    }, [shown, view, home, installed, hidden]);
    // Where the chosen tile is: its row, and its place along it
    let rowAt = 0, at = 0;
    rows.forEach((row, r) => { const i = row.items.findIndex(it => it.key === chosen); if (i >= 0) { rowAt = r; at = i; } });
    const current = rows[rowAt] && rows[rowAt].items[at];
    const rowRef = React.useRef(null);
    const tileRefs = React.useRef({});
    // The mouse resting on a tile shows that tile's bubble, without choosing it
    // (choosing scrolls the row, which under a moving mouse sends it racing along)
    const [hovered, setHovered] = React.useState(null);
    const shownItem = rows.flatMap(row => row.items).find(it => it.key === hovered) || current;
    // The bubble's tile, once drawn
    const [currentEl, setCurrentEl] = React.useState(null);
    React.useLayoutEffect(() => { setCurrentEl((shownItem && tileRefs.current[shownItem.key]) || null); });
    const single = rows.length === 1 && !rows[0].label;

    // Which pictures the systems have (chosen in the Console settings too): drawn again when that changes
    const [systemPictures, setSystemPictures] = React.useState(() => RM.systems.systemPictures.get());
    useEffect(() => {
        const changed = () => setSystemPictures(RM.systems.systemPictures.get());
        window.addEventListener('retromanager:system-pictures', changed);
        return () => window.removeEventListener('retromanager:system-pictures', changed);
    }, []);
    // Which of a game's pictures its tile shows (chosen in the Console settings)
    // A game's tile square, or as wide as its picture (Console settings; kept by the browser)
    const [tileShape, setTileShapeState] = React.useState(() => rememberedChoice('retromanager.console.tileShape', v => v === 'square' || v === 'picture', 'square'));
    const setTileShape = (shape) => { setTileShapeState(shape); rememberChoice('retromanager.console.tileShape', shape); };
    const [tilePicture, setTilePicture] = React.useState(() => RM.consolePicture.get());
    useEffect(() => {
        const changed = () => setTilePicture(RM.consolePicture.get());
        window.addEventListener('retromanager:console-picture', changed);
        return () => window.removeEventListener('retromanager:console-picture', changed);
    }, []);
    // Every system's games at once: the ones that match open as a list, like a collection
    const [query, setQuery] = React.useState('');
    const [searching, setSearching] = React.useState(false);
    const everything = React.useRef(null);
    const search = async () => {
        const q = query.trim().toLowerCase();
        if (q.length < 2 || searching) return;
        setSearching(true);
        try {
            if (!everything.current) {
                const d = await (await fetch(`${API_BASE}/api/shelf`)).json();
                everything.current = d.success ? d.shelves.flatMap(s => s.games.map(g => ({ ...g, rom_exists: true, _system: s.system, _system_label: s.full_name }))) : [];
            }
            const text = (v) => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
            const wanted = text(q);
            // Names starting with it first, then names with it in, then a developer or genre that matches
            const games = everything.current.map(g => { const n = text(gdTitle(g.name)); return [n.startsWith(wanted) ? 0 : n.includes(wanted) ? 1 : [g.developer, g.genre].some(v => text(v).includes(wanted)) ? 2 : 3, g]; })
                .filter(([rank]) => rank < 3).sort((a, b) => a[0] - b[0] || String(a[1].name).localeCompare(String(b[1].name))).map(([, g]) => g);
            setOpen({ list: { id: `search:${wanted}`, name: `“${query.trim()}”: ${games.length} game${games.length === 1 ? '' : 's'}`, kind: 'search', games } });
        } catch (e) {
            setOpen({ list: { id: 'search:failed', name: `“${query.trim()}” couldn't be looked for`, kind: 'search', games: [] } });
        }
        setSearching(false);
    };

    const activate = (item, details) => {
        setChosen(item.key);
        if (item.type === 'system') setOpen({ system: item.system });
        else if (item.type === 'list') setOpen({ list: item.list });
        else if (item.type === 'surprise') {
            // A system picked by how many games it has, then one of its games (once they've loaded)
            let n = Math.random() * shown.reduce((sum, s) => sum + s.rom_count, 0);
            const system = shown.find(s => (n -= s.rom_count) < 0) || shown[0];
            setOpen({ system, game: SURPRISE, fromHome: true });
        }
        else if (gdCanPlay(item.game) && !details) gdPlay(item.game._system, item.game.path);
        else {
            const system = systems.find(s => s.name === item.game._system);
            // (from a row on the first screen: Back from its page goes straight back there)
            if (system) setOpen({ system, game: item.game.path, fromHome: true });
        }
    };

    // A finger landing on a tile chooses it (the bubble moves to it) without
    // opening it: that's the start of dragging the row along, or of a tap, which
    // opens it as a click does. The row is left where the finger has it.
    const touched = React.useRef(false);
    const touchChoose = (item) => (e) => {
        if (e.pointerType === 'mouse' || (current && item.key === current.key)) return;
        touched.current = true;
        setChosen(item.key);
    };
    // The chosen tile stays in view; its row scrolls sideways under it
    useEffect(() => {
        if (touched.current) { touched.current = false; return; }
        const el = current && tileRefs.current[current.key];
        if (el && !open) el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }, [current?.key, sortMode, view, open]);
    useEffect(() => {
        if (open) return;
        const onKey = (e) => {
            const key = consoleKey(e);
            if (!key || consoleKeysBlocked(e)) return;
            setHovered(null);   // the keyboard takes over from a resting mouse
            const row = rows[rowAt] ? rows[rowAt].items : [];
            const pick = (list, i) => { e.preventDefault(); if (list.length) setChosen(list[Math.min(Math.max(i, 0), list.length - 1)].key); };
            const along = { left: at - 1, right: at + 1, first: 0, last: row.length - 1 }[key];
            // Up and down change row, keeping the place along it
            const across = { up: rowAt - 1, down: rowAt + 1 }[key];
            if (along !== undefined) pick(row, along);
            else if (across !== undefined && rows.length > 1) { if (rows[across]) pick(rows[across].items, at); else e.preventDefault(); }
            else if (key === 'open' && current) { e.preventDefault(); activate(current); }
            else if (key === 'edit' && current && current.type === 'game') { e.preventDefault(); activate(current, true); }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [rows, rowAt, at, current, open]);
    // With one row, the mouse wheel moves along it
    useEffect(() => {
        const el = rowRef.current;
        if (!el) return;
        const onWheel = (e) => {
            if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { el.scrollLeft += e.deltaY; e.preventDefault(); }
        };
        el.addEventListener('wheel', onWheel, { passive: false });
        return () => el.removeEventListener('wheel', onWheel);
    }, [open, single]);

    const labelOf = (item) => item.type === 'system' ? systemName(item.system) : item.type === 'list' ? item.list.name : item.type === 'surprise' ? 'Surprise me' : gdTitle(item.game.name);
    const tile = (item) => {
        const active = current && item.key === current.key;
        const common = {
            key: item.key, ref: el => { tileRefs.current[item.key] = el; }, role: 'option', 'aria-selected': !!active, title: labelOf(item),
            tabIndex: active ? 0 : -1,
            // Pointing at a tile doesn't choose it: the row moves under the mouse
            // as it scrolls, which would send the choice racing along. A click opens it.
            onClick: () => activate(item, item.type === 'game'),
            onPointerDown: touchChoose(item),
            onMouseEnter: () => setHovered(item.key),
            onMouseLeave: () => setHovered(h => (h === item.key ? null : h)),
        };
        if (item.type === 'system') {
            return (
                <button {...common} className={`console-tile console-tile-system${active ? ' active' : ''}${away(item.system) ? ' away' : ''}`}>
                    <img src={RM.systems.imageOf(item.system.name)} alt="" draggable={false}
                        onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }} />
                    <span className="console-tile-name" style={{display: 'none'}}>{systemName(item.system)}</span>
                    {onPhone(item.system) > 0 && <span className="console-tile-phone" aria-hidden="true">📱 {onPhone(item.system)}</span>}
                    {gdNeedsEmulator(item.system.name) && <span className="console-tile-needs" aria-hidden="true">⚠ No emulator</span>}
                </button>
            );
        }
        if (item.type === 'list') {
            const cover = item.list.games.map(g => g.screenshot || g.fanart || g.screenshottitle).find(Boolean);
            return (
                <button {...common} className={`console-tile console-tile-list${active ? ' active' : ''}`}>
                    {cover && <img src={gdThumb(cover, 320)} alt="" draggable={false} onError={e => { e.target.style.display = 'none'; }} />}
                    <span className="console-tile-label">
                        <span className="console-tile-icon" aria-hidden="true">{item.list.kind === 'favourites' ? '★' : item.list.kind === 'status' ? (item.list.status === 'playing' ? '⏵' : '🕓') : '📁'}</span>
                        <span>{item.list.name}</span>
                        <span className="console-tile-count">{item.list.games.length} game{item.list.games.length === 1 ? '' : 's'}</span>
                    </span>
                </button>
            );
        }
        if (item.type === 'surprise') {
            return (
                <button {...common} className={`console-tile console-tile-list${active ? ' active' : ''}`}>
                    <span className="console-tile-label">
                        <span className="console-tile-icon" aria-hidden="true">🎲</span>
                        <span>Surprise me</span>
                        <span className="console-tile-count">A game picked at random</span>
                    </span>
                </button>
            );
        }
        const picture = gdPictureField(item.game, tilePicture);
        return (
            <button {...common} className={`console-tile console-tile-game${active ? ' active' : ''}${gdPhone && phone.offline && !gdHere(item.game._system, item.game.path) ? ' away' : ''}`}>
                {picture ? <img src={gdThumb(item.game[picture], 320)} alt="" draggable={false} onError={e => { e.target.style.visibility = 'hidden'; }} /> : <span className="console-tile-name" style={{display: 'flex'}}>{gdTitle(item.game.name)}</span>}
                {gdCanPlay(item.game) && <span className={`console-tile-play${gdPlayMark(item.game) !== '▶' ? ' fetch' : ''}`} aria-hidden="true">{gdPlayMark(item.game)}</span>}
            </button>
        );
    };
    // What the bubble says: a game's console (its picture, small) and name; a
    // system's or a list's name and how many games it has
    const bubble = () => {
        const current = shownItem;
        if (!current) return null;
        const games = (n) => `${n} game${n === 1 ? '' : 's'}`;
        if (current.type === 'system') return <><span className="console-bubble-text"><b>{systemName(current.system)}</b><span>{games(current.system.rom_count)}{gdPhone ? ` · ${onPhone(current.system) || 'none'} on this phone${gdNeedsEmulator(current.system.name) ? ' · nothing here plays it yet' : ''}` : current.system.missing_metadata_count > 0 && ` · ${current.system.missing_metadata_count} missing metadata`}</span></span></>;
        if (current.type === 'list') return <span className="console-bubble-text"><b>{current.list.name}</b><span>{games(current.list.games.length)}</span></span>;
        if (current.type === 'surprise') return <span className="console-bubble-text"><b>Surprise me</b><span>A game from any system</span></span>;
        return (
            <>
                <img className="console-bubble-logo" src={RM.systems.imageOf(current.game._system)} alt="" onError={e => { e.target.style.display = 'none'; }} />
                <span className="console-bubble-text"><b>{gdTitle(current.game.name)}</b><span>{current.game._system_label} · {current.note}{gdPhone && !gdHere(current.game._system, current.game.path) ? ' · not on this phone' : ''}</span></span>
            </>
        );
    };

    if (open) {
        return <ConsoleGames key={open.system ? `s:${open.system.name}` : `l:${open.list.id}`} system={open.system} list={open.list} startOn={open.game} startShowing={open.show !== false} fromHome={!!open.fromHome} pad={pad}
            onBack={() => { setOpen(null); setConsoleAddress(null); }} />;
    }
    if (!rows.length) return <div className="console-screen"><div className="console-empty">No systems with games yet.</div></div>;
    const onGame = current && current.type === 'game';
    return (
        <div className={`console-screen${single ? '' : ' grouped'}${tileShape === 'picture' ? ' fit-pictures' : ''}`}>
            <div className="console-top">
                <form className="console-search" role="search" onSubmit={e => { e.preventDefault(); search(); }}>
                    <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search every system" aria-label="Search every system's games" />
                    <button className="gd-btn small" disabled={query.trim().length < 2 || searching}>{searching ? '…' : '🔍'}</button>
                    <button type="button" className="gd-btn small console-settings-button" onClick={() => setSettingsOpen(true)} aria-label="Console settings" title="Rows, sorting, layout and which picture the game tiles show">⚙</button>
                </form>
            </div>
            {single ? (
                <div className="console-row" ref={rowRef} role="listbox" aria-label="Systems">{rows[0].items.map(tile)}</div>
            ) : (
                <div className="console-groups">
                    {rows.map(row => (
                        <section key={row.label}>
                            <h2 className="console-group-name">{row.label}</h2>
                            <div className={`console-row${row.big ? ' big' : ''}`} role="listbox" aria-label={row.label}>{row.items.map(tile)}</div>
                        </section>
                    ))}
                </div>
            )}
            {settingsOpen && <ConsoleSettings onClose={() => setSettingsOpen(false)} sortMode={sortMode} setSortMode={setSortMode} view={view} setView={setView}
                tilePicture={tilePicture} tileShape={tileShape} setTileShape={setTileShape} systemPictures={systemPictures} hidden={hidden} toggleRow={toggleRow}
                rows={[['recent', 'Continue playing', home && home.recent && home.recent.length], ['added', 'Recently added', home && home.added && home.added.length],
                    ...(gdPhone ? [['installed', 'Installed games', installed && installed.length]] : [])]} />}
            <ConsoleBubble el={currentEl}>{bubble()}</ConsoleBubble>
            <div className="console-rule" />
            <div className="console-hint">
                {pad ? <>🎮 D-pad choose · <kbd>A</kbd> {onGame ? (gdCanPlay(current.game) ? 'play' : 'open') : 'open'}{onGame && <> · <kbd>X</kbd> details</>}</> : <>
                    <kbd>←</kbd> <kbd>→</kbd> or <kbd>A</kbd> <kbd>D</kbd> choose{rows.length > 1 && <> · <kbd>↑</kbd> <kbd>↓</kbd> or <kbd>W</kbd> <kbd>S</kbd> change row</>} · <kbd>Enter</kbd> {onGame ? (gdCanPlay(current.game) ? 'play' : 'open') : 'open'}{onGame && <> · <kbd>E</kbd> details</>}
                </>}
            </div>
        </div>
    );
}

// A system's games, or a list's (Favourites, a collection): the shared game
// list, and the chosen game's details
function ConsoleGames({ system, list, startOn, startShowing = true, fromHome, onBack, pad }) {
    const [games, setGames] = React.useState(list ? list.games : null);
    const [error, setError] = React.useState(null);
    // A list's games come from several systems, so each is known by system and path
    const keyOf = (g) => (g._system ? `${g._system}/` : '') + String(g.path).replace(/^(\.\/)+/, '');
    const [chosen, setChosen] = React.useState(() => (startOn ? String(startOn).replace(/^(\.\/)+/, '') : null));
    // On a narrow screen the list and the details take turns: picking a game shows its details
    const [narrow, setNarrow] = React.useState(() => window.innerWidth < 900);
    const narrowNow = React.useRef(narrow);
    narrowNow.current = narrow;
    const [showing, setShowing] = React.useState(() => !!startOn && startShowing);
    // A game opened from the first screen (Continue playing, Recently added...) goes back
    // there, not to its system's list, until that list has been looked at
    const [sawList, setSawList] = React.useState(false);
    useEffect(() => { if (!showing) setSawList(true); }, [showing]);
    const homeFirst = fromHome && !sawList;
    useEffect(() => {
        const onResize = () => setNarrow(window.innerWidth < 900);
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);

    useEffect(() => {
        if (list) return;
        let cancelled = false;
        let shown = false;
        gdKeptFirst(`${API_BASE}/api/systems/${encodeURIComponent(system.name)}/games`, (d, kept) => {
            if (cancelled || (kept && !d.success)) return;
            if (d.success) { shown = true; setGames(d.games.filter(g => g.rom_exists)); }
            else if (!shown) setError(d.error || 'Could not load the games');
        }).catch(e => { if (!cancelled && !shown) setError(e.message); });
        return () => { cancelled = true; };
    }, [system?.name, list?.id]);

    // "Surprise me": once the games are here, one of them (one the browser can play, if any)
    useEffect(() => {
        if (chosen !== SURPRISE || !games || !games.length) return;
        const playable = games.filter(g => gdCanPlay(g, system && system.name));
        const pool = playable.length ? playable : games;
        setChosen(keyOf(pool[Math.floor(Math.random() * pool.length)]));
    }, [games, chosen]);
    const game = (games || []).find(g => keyOf(g) === chosen) || null;
    const title = list ? list.name : systemName(system);
    // What the shared list takes for a system: a list is one without a folder
    const listSystem = React.useMemo(() => system || { name: null, key: `list:${list.id}`, full_name: list.name }, [system, list]);
    useEffect(() => {
        const open = !narrow || showing;
        const where = game && (list ? keyOf(game) : game.path);
        setConsoleAddress({ ...(list ? { list: list.id } : { system: system.name }), [open ? 'game' : 'at']: where });
    }, [system?.name, list?.id, game && keyOf(game), narrow, showing]);
    const select = React.useCallback((g, how) => {
        // Not without asking, when the open game has edits that aren't saved
        if (gdUnsaved.dirty && !window.confirm('Leave this game without saving your changes?')) return;
        setChosen(keyOf(g));
        // (on a narrow screen, moving down the list with the keys or a controller stays on the list)
        if (!(how && (how.auto || (how.keys && narrowNow.current)))) setShowing(true);
    }, []);
    // E edits the open game where it is (the Game Details panel listens)
    const edit = React.useCallback(() => { window.dispatchEvent(new Event('retromanager:edit-game')); }, []);
    // The panel saved or removed a game: the list here follows
    const saved = (fields) => setGames(all => all && all.map(g => (keyOf(g) === chosen ? { ...g, ...fields } : g)));
    // Favourite or collections changed on the game's page: the list it came from follows (the
    // game stays in view here until you leave, so a slip can be undone; the list's tile and the
    // list opened next time are right at once)
    const statusChanged = (fields) => {
        saved(fields);
        if (!list || !game) return;
        const belongs = list.kind === 'favourites' ? (fields.favorite === undefined ? null : !!fields.favorite)
            : list.kind === 'status' ? (fields.play_status === undefined ? null : fields.play_status === list.status)
            : (fields.collections ? fields.collections.includes(list.id) : null);
        if (belongs === null) return;
        const others = list.games.filter(g => keyOf(g) !== keyOf(game));
        list.games = belongs ? [...others, { ...game, ...fields }] : others;
        window.dispatchEvent(new Event('retromanager:console-lists'));
    };
    const removed = () => { setGames(all => all && all.filter(g => keyOf(g) !== chosen)); setShowing(false); };
    // The panel moved on to another game (a patched ROM added as a new game, a ROM file renamed):
    // that one, fetched and put in the list if it's new, is the one shown
    const movedTo = async (path, fields) => {
        const bare = String(path || '').replace(/^(\.\/)+/, '');
        if (!game || !bare || bare === String(game.path).replace(/^(\.\/)+/, '')) { saved(fields); return; }
        const where = game._system || (system && system.name);
        try {
            const d = await (await fetch(`${API_BASE}/api/systems/${encodeURIComponent(where)}/games/${bare.split('/').map(encodeURIComponent).join('/')}`)).json();
            if (!d.success) return;
            const next = { ...d.game, ...(game._system ? { _system: game._system, _system_label: game._system_label } : {}) };
            setGames(all => [...(all || []).filter(g => keyOf(g) !== keyOf(next)), next]);
            setChosen(keyOf(next));
        } catch (e) { /* stays on the game it was */ }
    };

    // Esc, Backspace or left goes back (the list has the other keys)
    useEffect(() => {
        const onKey = (e) => {
            const key = consoleKey(e);
            if (consoleKeysBlocked(e)) return;
            // With a game's page over the list (a narrow screen), Enter plays that game
            if (key === 'open' && narrow && showing && game && !['BUTTON', 'A', 'SUMMARY'].includes(e.target && e.target.tagName)) {
                e.preventDefault();
                if (gdCanPlay(game, system && system.name)) gdPlay(game._system || system.name, game.path);
                return;
            }
            if (key !== 'back' && key !== 'left') return;
            e.preventDefault();
            narrow && showing && !homeFirst ? setShowing(false) : onBack();
        };
        // (the phone's Back does the same: see RMBack)
        const onPhoneBack = (e) => { e.preventDefault(); narrow && showing && !homeFirst ? setShowing(false) : onBack(); };
        window.addEventListener('keydown', onKey);
        window.addEventListener('retromanager:back', onPhoneBack);
        return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('retromanager:back', onPhoneBack); };
    }, [onBack, narrow, showing, homeFirst, game && keyOf(game)]);

    return (
        <div className="console-screen console-games">
            {/* On a narrow screen a game's details have the whole page: "‹ Games" leads back to this bar */}
            {!(narrow && showing && game) && <>
                <div className="console-top">
                    <button className="gd-btn small" onClick={onBack} title="Back to the systems (Esc)">‹ Systems</button>
                    <div className="console-name">{title}</div>
                </div>
                <div className="console-rule top" />
            </>}
            {error && <div className="console-empty">{error}</div>}
            {!error && (
                <div className={`console-columns${narrow ? (showing && game ? ' details-only' : ' list-only') : ''}`}>
                    <div className="console-list">
                        <SharedGameList games={games || []} loading={!games} system={listSystem} selectedGame={game} onGameSelect={select}
                            autoSelect={!narrow && chosen !== SURPRISE} onEdit={edit} />
                    </div>
                    <div className="console-details">
                        {narrow && (homeFirst
                            ? <button className="gd-btn small" style={{marginBottom: 12}} onClick={onBack}>‹ Home</button>
                            : <button className="gd-btn small" style={{marginBottom: 12}} onClick={() => setShowing(false)}>‹ Games</button>)}
                        {game && (
                            <GameDetails system={systemOf(game, system)} systemLabel={game._system_label || systemName(system)} game={game}
                                onSaved={movedTo} onChanged={statusChanged} onDeleted={removed} />
                        )}
                    </div>
                </div>
            )}
            <div className="console-rule" />
            <div className="console-hint">
                {pad ? <>🎮 D-pad choose · <kbd>A</kbd> {game && !gdCanPlay(game, system && system.name) ? 'edit' : 'play'} · <kbd>X</kbd> edit · <kbd>LB</kbd> <kbd>RB</kbd> page · <kbd>B</kbd> back</> : <>
                    <kbd>↑</kbd> <kbd>↓</kbd> or <kbd>W</kbd> <kbd>S</kbd> choose · <kbd>Enter</kbd> {game && !gdCanPlay(game, system && system.name) ? 'edit' : 'play'} · <kbd>E</kbd> edit · <kbd>/</kbd> search · <kbd>Esc</kbd> systems
                </>}
            </div>
        </div>
    );
}

function ConsoleApp() {
    const [systems, setSystems] = React.useState(null);
    const [home, setHome] = React.useState(null);
    const [error, setError] = React.useState(null);
    // In the phone app: the games that are on the phone, for their row
    const [installed, setInstalled] = React.useState([]);
    const installedNow = React.useRef([]);
    const pad = useGamepad();
    useEffect(() => {
        // (in the phone app, what was there last time shows at once, then the server's own)
        let shown = false;
        gdKeptFirst(`${API_BASE}/api/systems`, (d, kept) => {
            if (kept && !d.success) return;
            if (d.success) { shown = true; setSystems(d.systems); }
            else if (!shown) setError(d.error || 'Could not load the systems');
        }).catch(e => { if (!shown) setError(e.message); });
        // The recent games and the lists arrive after the systems (they take longer to work out)
        let stopped = false, tries = 0, fresh = false;
        const loadHome = () => fetch(`${API_BASE}/api/console/home`).then(r => r.json()).then(d => {
            if (stopped || !d.success) return;
            if (d.pending && tries++ < 40) setTimeout(loadHome, 3000);
            else { fresh = true; setHome(d); }
        }).catch(() => {});
        if (gdPhone) {
            fetch(`${API_BASE}/api/console/home`, { headers: { 'X-RetroManager-Kept': '1' } }).then(r => (r.ok ? r.json() : null))
                .then(d => { if (d && d.success && !d.pending && !fresh && !stopped) setHome(d); }).catch(() => {});
        }
        loadHome();
        // A list changed here (a game's page): its tile is drawn again with the new count
        const listsChanged = () => setHome(h => (h ? { ...h } : h));
        window.addEventListener('retromanager:console-lists', listsChanged);
        return () => { stopped = true; window.removeEventListener('retromanager:console-lists', listsChanged); };
    }, []);
    // In the phone app: how many of each system's games are on the phone, for the
    // tiles. Only the systems with files there are asked about, and asking keeps
    // their game lists on the phone for when there's no connection.
    useEffect(() => {
        if (!gdPhone || !systems) return undefined;
        let run = 0;
        const count = async () => {
            const mine = ++run, phone = gdPhoneState(), counts = {}, installed = [];
            let complete = true;
            for (const system of systems) {
                const files = phone.roms[system.name];
                if (!files || !files.size) continue;
                try {
                    const d = await (await fetch(`${API_BASE}/api/systems/${encodeURIComponent(system.name)}/games`)).json();
                    if (mine !== run) return;
                    const here = d.success ? d.games.filter(g => g.rom_exists && files.has(gdEncodeless(g.path))) : null;
                    counts[system.name] = here ? here.length : (phone.counts[system.name] || 0);
                    if (here) installed.push(...here.map(g => ({ ...g, _system: system.name, _system_label: systemName(system) })));
                    else complete = false;
                } catch (e) {
                    counts[system.name] = phone.counts[system.name] || 0;
                    complete = false;
                }
            }
            // (a list that couldn't be had leaves the row as it was, not short of that system's games)
            if (complete || !installedNow.current.length) { installedNow.current = installed; setInstalled(installed); }
            phone.counts = counts;
            try { localStorage.setItem('retromanager.phone.counts', JSON.stringify(counts)); } catch (e) {}
            window.dispatchEvent(new Event('retromanager:phone'));
        };
        // (after the page's own first requests: the counts from last time show meanwhile)
        const soon = setTimeout(count, 2500);
        window.addEventListener('retromanager:phone-roms', count);
        return () => { run++; clearTimeout(soon); window.removeEventListener('retromanager:phone-roms', count); };
    }, [systems]);
    return (
        <>
            <RM.Header active="console" />
            {error && <div className="console-screen"><div className="console-empty">{error}</div></div>}
            {!systems && !error && <div className="console-screen"><div className="console-empty">Loading the systems...</div></div>}
            {systems && <ConsoleSystems systems={systems} home={home} installed={installed} pad={pad} />}
        </>
    );
}

ReactDOM.createRoot(document.getElementById('root')).render(<ConsoleApp />);
