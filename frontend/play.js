// The play page (play.html): a game in the browser with EmulatorJS, with your saves and save states.
// Plain JavaScript, loaded where its <script> tag is in the page, so it runs just where it did inline.

// Plays one game with EmulatorJS (?system=<folder>&game=<rom path>). The
// chosen person's battery save is loaded when the game starts and written
// back whenever the game saves.
const params = new URLSearchParams(window.location.search);
const system = params.get('system') || '';
const rom = (params.get('game') || '').replace(/^(\.\/)+/, '');
const session = Math.random().toString(36).slice(2);
const $ = (id) => document.getElementById(id);
const setStatus = (text, error) => { $('status').textContent = text; $('status').className = error ? 'error' : ''; };
const query = (extra) => new URLSearchParams({ system, rom, ...extra });
// Back to where the game was started from: the Console page, or the Library
const fromConsole = params.get('from') === 'console';
$('back').href = `${fromConsole ? '/console' : '/'}?${new URLSearchParams({ system, game: `./${rom}` })}`;

let info = null;
let pendingSave = null;   // the save to load when the game starts
let lastSent = null;
let piStates = [];       // the game's RetroArch save states (made on the Pi)
let padLayouts = [];     // touch-control layouts (frontend/overlays/layouts.json)
let pad = null;          // the one in use, once the game has started
let chosenState = null;  // the one to start from, if any

const profile = () => $('profile').value;
// ("shared" is the saves that are nobody's in particular: all there is until profiles are added)
const describe = (p) => `${p.name === 'shared' ? 'Everyone (the shared saves)' : p.name} ${p.has_save ? '(has a save)' : '(no save yet)'}`;
const who = () => (profile() === 'shared' ? 'everyone' : profile());
const whose = () => (profile() === 'shared' ? 'the shared' : `${profile()}'s`);

async function load() {
    if (!system || !rom) { $('title').textContent = 'No game chosen'; return; }
    let d;
    try { d = await (await fetch(`/api/play/info?${query()}`)).json(); }
    catch (e) { setStatus(`Couldn't reach RetroManager: ${e.message}`, true); return; }
    if (!d.success || !d.playable) {
        $('title').textContent = rom;
        $('intro').innerHTML = "<p>This game can't be played in the browser.</p><p class='small'>Browser play covers the systems EmulatorJS plays. A system that needs a BIOS plays once its BIOS file is in the BIOS folder; multi-disc playlists (.m3u) and .7z or .rar archives can't be played.</p>";
        return;
    }
    info = d;
    document.title = `${d.name} · RetroManager`;
    $('title').textContent = d.name;
    if (d.profiles.length) {
        const remembered = (() => { try { return localStorage.getItem('retromanager.play.profile'); } catch (e) { return null; } })();
        $('profile').innerHTML = '';
        $('profile').appendChild(new Option("Nobody: don't keep a save", ''));
        d.profiles.forEach(p => $('profile').appendChild(new Option(describe(p), p.name)));
        // The shared saves unless someone was chosen here before (with no profiles, they're all there is)
        $('profile').value = 'shared';
        if (remembered !== null && [...$('profile').options].some(o => o.value === remembered)) $('profile').value = remembered;
        // With login on, it's the signed-in person's save (an admin may still pick another's)
        const me = await RM.me;
        if (me.enabled && me.profile) {
            if ([...$('profile').options].some(o => o.value === me.profile)) $('profile').value = me.profile;
            if (!me.admin) [...$('profile').options].forEach(o => { o.disabled = o.value !== me.profile; });
        }
        $('profile').hidden = false;
        $('profile-label').hidden = false;
    }
    $('intro').innerHTML = "<p>Choose whose save to use, then press <b>Start</b>.</p>"
        + "<p class='small'>The save is the same file the Pi uses. It's loaded when the game starts and written back each time the game saves; the first time this session changes it, the old file is copied to the save backups folder. Don't play the same game on the Pi at the same time.</p>"
        + (d.states ? "<p class='small'>The emulator's <b>save state</b> and <b>load state</b> buttons keep one state per game for the person you pick, on the server. They're the browser emulator's own: the Pi can't load them.</p>" : '')
        + "<p class='small'>On a phone the game fills the screen: the round button in the corner brings this bar back. With a controller, holding <b>Select</b> and <b>Start</b> together for a second leaves the game.</p>"
        + "<p class='small'>The emulator for each system is fetched the first time it's played and kept, so after that it plays without the internet.</p>";
    $('start').disabled = false;
    if (d.states) loadPiStates();
    offerPadLayouts();
}

// --- Touch controls from a RetroArch overlay (play-overlay.js) ---
// Chosen before Start. On a touch screen a system's own layout is the
// default; the choice is remembered for the system in this browser.
const padKey = () => `retromanager.play.pad.${info.core}`;
async function offerPadLayouts() {
    padLayouts = await RMOverlay.layouts();
    if (!padLayouts.length) return;
    const row = $('intro').appendChild(Object.assign(document.createElement('p'), { id: 'pad-row' }));
    const menu = Object.assign(document.createElement('select'), { id: 'pad' });
    menu.setAttribute('aria-label', 'Touch controls');
    menu.appendChild(new Option("EmulatorJS's own", ''));
    padLayouts.forEach(layout => menu.appendChild(new Option(layout.name, layout.id)));
    let remembered = null;
    try { remembered = localStorage.getItem(padKey()); } catch (e) {}
    const usual = padLayouts.find(layout => (layout.systems || []).includes(info.core));
    const touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    menu.value = remembered !== null && [...menu.options].some(o => o.value === remembered) ? remembered : (touch && usual ? usual.id : '');
    menu.addEventListener('change', () => { try { localStorage.setItem(padKey(), menu.value); } catch (e) {} });
    row.append('Touch controls', menu);
}
// The layout chosen, read and ready, or null
async function chosenPadLayout() {
    const chosen = padLayouts.find(layout => layout.id === ($('pad') || {}).value);
    if (!chosen) return null;
    try { return await RMOverlay.load(chosen); } catch (e) { return null; }
}
// A DS layout with its controls between the two screens needs the core to
// leave a gap there: how tall (in DS pixels), for this screen. 0 otherwise.
function screenGapFor(layout) {
    const stage = $('stage');
    const width = stage.clientWidth, height = stage.clientHeight;
    const upright = layout.overlays.find(o => o.name === 'portrait');
    if (info.core !== 'nds' || !upright || height <= width) return 0;
    const bands = RMOverlay.freeBands(upright);
    if (bands.length < 2) return 0;
    const screen = width * 0.75;   // each DS screen is 4:3, the full width
    return Math.max(0, Math.min(126, Math.round((bands[1][0] * height - screen) / (width / 256))));
}
// --- Sending this moment to the Pi ---
// The emulator's state, written where RetroArch on the Pi finds it: the
// game's auto state (what the Pi starts from, if it loads those) or a slot.
function offerSendToPi(manager) {
    if (!profile() || !info.states) return;
    const menu = $('pi-send');
    menu.innerHTML = '';
    menu.appendChild(new Option('Send to the Pi…', ''));
    menu.appendChild(new Option('As the auto save state', 'auto'));
    [1, 2, 3, 4, 5].forEach(n => menu.appendChild(new Option(`As slot ${n}`, String(n))));
    menu.onchange = async () => {
        const slot = menu.value;
        menu.value = '';
        menu.blur();
        if (!slot) return;
        try {
            setStatus('Sending to the Pi...');
            const state = await manager.getState();
            const res = await fetch(`/api/play/pi-state?${query({ profile: profile(), slot })}`, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: state });
            const d = await res.json();
            if (!d.success) { setStatus(`Not sent: ${d.error}`, true); return; }
            const mismatch = d.pi_cores.length && d.made_by && !d.pi_cores.includes(d.made_by);
            setStatus(`Sent to the Pi as ${slot === 'auto' ? 'the auto save state' : `slot ${slot}`} for ${who()}${d.backup ? ' (the one there was backed up)' : ''}.`
                + (mismatch ? ` It was made with ${d.made_by}; the Pi's other states for this game are ${d.pi_cores.join(', ')}, so the Pi must run ${d.made_by} to load it.` : ''), mismatch);
        } catch (e) { setStatus(`Not sent: ${e.message}`, true); }
    };
    menu.hidden = false;
}

// --- Full screen, and leaving with a controller ---
const wantsFullScreen = () => window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
function enterFullScreen() {
    document.body.classList.add('fs');
    document.body.classList.remove('bar-open');
    $('bar-toggle').hidden = false;
    // Not every browser can (an iPhone's can't): the bar is put away either way
    try { const asked = document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); if (asked && asked.catch) asked.catch(() => {}); } catch (e) {}
    window.dispatchEvent(new Event('resize'));
}
function leaveFullScreen() {
    document.body.classList.remove('fs', 'bar-open');
    $('bar-toggle').hidden = true;
    try { if (document.fullscreenElement) document.exitFullscreen(); } catch (e) {}
    window.dispatchEvent(new Event('resize'));
}
$('fullscreen').addEventListener('click', () => (document.body.classList.contains('fs') ? leaveFullScreen() : enterFullScreen()));
$('bar-toggle').addEventListener('click', () => { document.body.classList.toggle('bar-open'); window.dispatchEvent(new Event('resize')); });
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && document.body.classList.contains('fs') && !wantsFullScreen()) leaveFullScreen(); });
function leaveGame(manager) {
    try { manager.saveSaveFiles(); } catch (e) {}
    setStatus('Leaving...');
    // (where they stopped kept first, a few seconds at most)
    Promise.race([keepWhereStopped(manager), new Promise(r => setTimeout(r, 4000))])
        .finally(() => setTimeout(() => { window.location.href = $('back').href; }, 300));
}
// Where they stopped: a save state made as they leave the game (or the page is put away),
// kept apart from the one they save themselves, to carry on from next time (Start's list)
let keptAt = 0;
async function keepWhereStopped(manager) {
    if (!profile() || !info || !info.states || !manager || Date.now() - keptAt < 3000) return;
    keptAt = Date.now();
    try {
        const state = await manager.getState();
        if (!state || !state.length) return;
        await fetch(`/api/play/state?${query({ profile: profile(), auto: '1' })}`, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' },
            body: state, keepalive: state.length < 60000 });
    } catch (e) {}
}
// EmulatorJS's own menu button (☰) only flips its menu bar, which also comes and goes
// with the mouse and hides itself after 3 seconds: a click could close what the
// mouse had just opened. Here it opens the bar and keeps it open until pressed again.
function pinMenuBar(emulator) {
    let button = emulator.elements.menuToggle;
    // EmulatorJS only makes its button where it thinks there's a touch screen: elsewhere, the same one of ours
    if (!button) {
        button = document.createElement('div');
        button.className = 'ejs_virtualGamepad_open rm-menu-button';
        button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512"><path d="M0 96c0-17.7 14.3-32 32-32h384c17.7 0 32 14.3 32 32s-14.3 32-32 32H32C14.3 128 0 113.7 0 96zm0 160c0-17.7 14.3-32 32-32h384c17.7 0 32 14.3 32 32s-14.3 32-32 32H32c-17.7 0-32-14.3-32-32zm448 160c0 17.7-14.3 32-32 32H32c-17.7 0-32-14.3-32-32s14.3-32 32-32h384c17.7 0 32 14.3 32 32z"/></svg>';
        button.setAttribute('role', 'button');
        button.tabIndex = 0;
        button.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); button.click(); } });
        emulator.elements.parent.appendChild(button);
        emulator.elements.menuToggle = button;
    }
    // (touches aren't cancelled, so the tap still ends in a click)
    const swallow = (e) => { e.stopImmediatePropagation(); if (e.type === 'mousedown' || e.type === 'click') e.preventDefault(); };
    ['touchstart', 'touchend', 'mousedown', 'mouseup', 'pointerdown', 'pointerup'].forEach(type => button.addEventListener(type, swallow, { capture: true, passive: false }));
    button.addEventListener('click', (e) => {
        swallow(e);
        const pinned = document.body.classList.toggle('rm-menu-pinned');
        try { pinned ? emulator.menu.open(true) : emulator.menu.close(); } catch (err) {}
    }, { capture: true });
    button.title = 'Menu';
}

// The browser's copies of this game from before the file was replaced (EmulatorJS
// keeps each version under its own address, the old ones taking room for nothing)
async function forgetOldCopies(emulator) {
    try {
        const current = String(window.EJS_gameUrl).split('/').pop();
        const name = current.split('?')[0];
        const kept = await emulator.storage.rom.getSizes();
        for (const key of Object.keys(kept || {})) {
            if (key !== current && key.split('?')[0] === name) await emulator.storage.rom.remove(key);
        }
    } catch (e) {}
}

// Select and Start held together for a second on a controller leaves the game
function watchForExit(manager) {
    if (!navigator.getGamepads) return;
    let since = null;
    setInterval(() => {
        const both = [...navigator.getGamepads()].filter(Boolean).some(p => p.buttons[8] && p.buttons[8].pressed && p.buttons[9] && p.buttons[9].pressed);
        if (!both) { since = null; return; }
        if (since === null) since = Date.now();
        else if (Date.now() - since >= 1000) { since = -Infinity; leaveGame(manager); }
    }, 150);
}

function startPad(layout, manager) {
    let fast = false;
    document.body.classList.add('rm-pad-on');
    pad = RMOverlay.attach({
        stage: $('stage'), game: $('game'), layout,
        press: (input, value) => manager.simulateInput(0, input, value),
        actions: {
            menu: () => { const bar = document.querySelector('.ejs_menu_bar'); if (bar) bar.classList.toggle('ejs_menu_bar_hidden'); },
            fastForward: () => { fast = !fast; try { manager.toggleFastForward(fast ? 1 : 0); } catch (e) {} setStatus(fast ? 'Fast forward on' : 'Fast forward off'); },
            saveState: async () => {
                if (!window.EJS_onSaveState) { setStatus('Pick a person before Start to keep save states'); return; }
                try { window.EJS_onSaveState({ state: await manager.getState() }); } catch (e) { setStatus(`Save state not kept: ${e.message}`, true); }
            },
            exit: () => leaveGame(manager),
        },
    });
}

// --- Starting from a save state made on the Pi ---
// RetroArch's states load here when the browser has the same emulator
// core (the server says which, per state); the game then starts on that
// core. The Pi's files are only read.
const ago = (iso) => {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
    if (s < 86400 * 1.5) return `${Math.round(s / 3600)} h ago`;
    if (s < 86400 * 60) return `${Math.round(s / 86400)} days ago`;
    if (s < 86400 * 365 * 1.5) return `${Math.round(s / (86400 * 30))} months ago`;
    return `${Math.round(s / (86400 * 365))} years ago`;
};
async function loadPiStates() {
    try {
        const d = await (await fetch(`/api/play/pi-states?${query()}`)).json();
        if (d.success) piStates = d.states;
    } catch (e) {}
    // (where they stopped, chosen to begin with: carrying on is what's wanted most often)
    if (!chosenState && stoppedState()) chosenState = stoppedState();
    renderPiStates(false);
    $('profile').addEventListener('change', () => {
        if (!chosenState || chosenState.stopped) chosenState = stoppedState();
        renderPiStates(false);
    });
}
// The chosen person's state from when they last left the game, as one more to start from
function stoppedState() {
    const mine = info && (info.profiles || []).find(p => p.name === profile());
    if (!mine || !mine.stopped) return null;
    return { stopped: true, label: 'Where you stopped', profile: mine.name, modified: mine.stopped, core: info.core, made_by: 'the browser',
        url: `/api/play/state?${query({ profile: mine.name, auto: '1' })}` };
}
function renderPiStates(showAll) {
    const stopped = stoppedState();
    // (the same one kept chosen as the list is drawn again)
    if (chosenState && chosenState.stopped) chosenState = stopped;
    const usable = [...(stopped ? [stopped] : []), ...piStates.filter(s => s.core)];
    const others = piStates.filter(s => !s.core);
    if (!usable.length && !others.length) { const old = $('pi-states'); if (old) old.remove(); $('stage').classList.remove('with-states'); return; }
    $('stage').classList.add('with-states');
    const box = $('pi-states') || $('intro').appendChild(Object.assign(document.createElement('div'), { id: 'pi-states' }));
    box.innerHTML = '';
    box.appendChild(Object.assign(document.createElement('h2'), { textContent: stopped ? 'Or carry on from a save state' : 'Or carry on from a save state made on the Pi' }));
    box.appendChild(Object.assign(document.createElement('p'), { className: 'small',
        textContent: (stopped ? "Where you stopped is kept each time you leave a game here. " : '') + "Pick one and press Start. A state from the Pi loads if the browser's emulator matches the one that made it, which is checked once the game is running. A save state also brings back the in-game save as it was at that moment. The Pi's save states themselves aren't changed." }));
    const list = box.appendChild(Object.assign(document.createElement('div'), { className: 'pi-list' }));
    list.setAttribute('role', 'radiogroup');
    list.setAttribute('aria-label', 'Where to start');
    const option = (state, title, detail) => {
        const button = Object.assign(document.createElement('button'), { className: 'pi-state', type: 'button' });
        button.setAttribute('role', 'radio');
        button.setAttribute('aria-checked', String(chosenState === state));
        if (state && state.stopped) {
            button.appendChild(Object.assign(document.createElement('span'), { className: 'no-shot', textContent: '⏯' }));
        } else if (state && state.screenshot) {
            button.appendChild(Object.assign(document.createElement('img'), { alt: '', loading: 'lazy',
                src: `/api/save-screenshot/savestates/${state.screenshot.split('/').map(encodeURIComponent).join('/')}` }));
        } else {
            button.appendChild(Object.assign(document.createElement('span'), { className: 'no-shot', textContent: state ? '⏸' : '▶' }));
        }
        const text = button.appendChild(document.createElement('span'));
        text.appendChild(Object.assign(document.createElement('b'), { textContent: title }));
        text.appendChild(Object.assign(document.createElement('span'), { className: 'small', textContent: detail }));
        button.addEventListener('click', () => { chosenState = state; renderPiStates(showAll); });
        list.appendChild(button);
    };
    option(null, 'Start normally', 'From the beginning, or the in-game save');
    const PREVIEW = 6;
    (showAll ? usable : usable.slice(0, PREVIEW)).forEach(state => option(state,
        `${state.label}${state.profile !== 'shared' ? ` · ${state.profile}` : ''}`,
        `${ago(state.modified)} · ${new Date(state.modified).toLocaleDateString()} · ${state.stopped ? 'in the browser' : `made with ${state.made_by}`}`));
    if (usable.length > PREVIEW) {
        const more = list.appendChild(Object.assign(document.createElement('button'), { className: 'pi-more', type: 'button',
            textContent: showAll ? 'Show fewer' : `Show all ${usable.length}` }));
        more.addEventListener('click', () => renderPiStates(!showAll));
    }
    if (others.length) {
        const makers = [...new Set(others.map(s => s.made_by).filter(Boolean))];
        box.appendChild(Object.assign(document.createElement('p'), { className: 'small', style: 'margin-top: 8px',
            textContent: `${others.length} more save state${others.length === 1 ? '' : 's'} can't be used here: `
                + (makers.length ? `made with ${makers.join(', ')}, which the browser doesn't have.` : "made by an emulator the browser doesn't have.") }));
    }
}
// A save state without RetroArch's wrapper (the browser's own states have it; the server takes it off the Pi's)
const unwrapped = (s) => (s && s.length > 16 && String.fromCharCode(...s.slice(0, 7)) === 'RASTATE'
    ? s.slice(16, 16 + (s[12] | s[13] << 8 | s[14] << 16 | s[15] << 24 >>> 0)) : s);
// The emulator's snapshot of the game right now, without the wrapper (null if it can't give one)
async function snapshotNow(manager) {
    try {
        const s = await manager.getState();
        return s && s.length ? unwrapped(s) : null;
    } catch (e) { return null; }
}
const alike = (a, b) => {
    if (!a || !b || !a.length || !b.length) return null;
    const n = Math.min(a.length, b.length);
    let same = 0;
    for (let i = 0; i < n; i++) if (a[i] === b[i]) same++;
    return same / Math.max(a.length, b.length);
};
// midGame: picked from the bar while playing, not before Start
async function loadPiState(manager, state, midGame) {
    const what = state.stopped ? 'where you stopped' : `${state.profile !== 'shared' ? `${state.profile}'s ` : 'the '}${state.label.toLowerCase()}`;
    try {
        setStatus(`Loading ${what}...`);
        const res = await fetch(state.url || `/api/play/pi-state?${query({ path: state.path })}`);
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'the server refused it');
        const snapshot = new Uint8Array(await res.arrayBuffer());
        const bare = unwrapped(snapshot);
        const before = alike(await snapshotNow(manager), bare);
        manager.loadState(snapshot);
        await new Promise(r => setTimeout(r, 1500));
        // Did it take? The emulator's snapshot should now be nearly the one it was given
        const after = alike(await snapshotNow(manager), bare);
        if (after === null) setStatus(`Sent ${what} to the emulator`);
        else if (after >= 0.97 || (before !== null && after - before >= 0.03)) setStatus(`Carried on from ${what}`);
        else setStatus(state.stopped ? `Where you stopped didn't load (the browser's emulator may have been updated since). ${midGame ? 'The game carries on as it was.' : 'Playing from the start.'}`
            : `That save state didn't load: it was made with a different version of ${state.made_by} from the browser's. ${midGame ? 'The game carries on as it was.' : 'Playing from the start.'}`, true);
    } catch (e) {
        setStatus(`Couldn't load the save state: ${e.message}`, true);
    }
}
// While playing: a menu in the bar of the Pi's save states, to jump to
// one. Only those made by the core that's running can load; the others
// say which core they'd need (pick them before Start instead).
function offerPiStates(manager) {
    const usable = piStates.filter(s => s.core);
    if (!usable.length) return;
    let running = null;
    try { running = window.EJS_emulator.getCore(); } catch (e) {}
    const menu = $('pi-load');
    menu.innerHTML = '';
    menu.appendChild(new Option('Load a Pi save state…', ''));
    usable.forEach((state, index) => {
        const fits = !running || state.core === running;
        const option = new Option(`${state.label}${state.profile !== 'shared' ? ` · ${state.profile}` : ''} · ${ago(state.modified)}${fits ? '' : ` (made with ${state.made_by}: choose it before Start)`}`, String(index));
        option.disabled = !fits;
        menu.appendChild(option);
    });
    menu.onchange = () => {
        const state = usable[Number(menu.value)];
        menu.value = '';
        menu.blur();
        if (state) loadPiState(manager, state, true);
    };
    menu.hidden = false;
}

async function sendSave(bytes) {
    if (!profile() || !bytes || !bytes.length) return;
    const key = `${bytes.length}:${bytes[0]}:${bytes[bytes.length - 1]}:${bytes.reduce((n, b) => (n * 31 + b) >>> 0, 7)}`;
    if (key === lastSent) return;
    // The save as it was loaded hasn't changed yet: nothing to send
    if (pendingSave && lastSent === null && bytes.length === pendingSave.length && bytes.every((b, i) => b === pendingSave[i])) { lastSent = key; return; }
    try {
        const res = await fetch(`/api/play/save?${query({ profile: profile(), session })}`, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: bytes });
        const d = await res.json();
        if (!d.success) { setStatus(`Save not kept: ${d.error}`, true); return; }
        lastSent = key;
        setStatus(`Saved for ${who()} at ${new Date().toLocaleTimeString()}${d.backup ? ' (old save backed up)' : ''}`);
    } catch (e) {
        setStatus(`Save not kept: ${e.message}`, true);
    }
}

async function start() {
    $('start').disabled = true;
    // On a phone the game takes the whole screen straight away (asked for now, while the tap on Start still counts)
    if (wantsFullScreen()) enterFullScreen();
    $('profile').disabled = true;
    try { localStorage.setItem('retromanager.play.profile', profile()); } catch (e) {}
    if (profile()) {
        setStatus('Fetching the save...');
        try {
            const res = await fetch(`/api/play/save?${query({ profile: profile() })}`);
            if (res.ok) pendingSave = new Uint8Array(await res.arrayBuffer());
        } catch (e) { setStatus(`Couldn't fetch the save: ${e.message}`, true); }
    }
    setStatus(pendingSave ? `Loaded ${whose()} save` : profile() ? `There's no save for ${who()} for this game yet` : "Playing without keeping a save");
    const padLayout = await chosenPadLayout();
    document.body.classList.add('playing');
    $('fullscreen').hidden = false;
    $('intro').hidden = true;
    $('stage').classList.remove('with-states');
    $('game').hidden = false;

    window.EJS_player = '#game';
    // A Pi save state only loads on the emulator core that made it
    window.EJS_core = chosenState ? chosenState.core : info.core;
    // (with the file's version: EmulatorJS keeps ROMs in the browser under this address's last
    // part, and a replaced ROM is often the same size, which is all it checks)
    window.EJS_gameUrl = info.rom_url.split('/').map(encodeURIComponent).join('/') + (info.rom_version ? `?v=${info.rom_version}` : '');
    window.EJS_gameName = info.name;
    if (info.bios_url) window.EJS_biosUrl = info.bios_url.split('/').map(encodeURIComponent).join('/');
    window.EJS_pathtodata = info.emulatorjs_url;
    // Keeps the browser's own copies of this game's saves apart from other games'
    window.EJS_gameID = [...`${system}/${rom}`].reduce((n, c) => (n * 31 + c.charCodeAt(0)) >>> 0, 7);
    window.EJS_startOnLoaded = true;
    if (padLayout) {
        padLayout.screenGap = screenGapFor(padLayout);
        // Both DS cores' names for the space between the screens
        if (padLayout.screenGap) window.EJS_defaultOptions = { melonds_screen_gap: String(padLayout.screenGap), desmume_screens_gap: String(Math.min(100, padLayout.screenGap)) };
    }
    window.EJS_backgroundColor = '#000';
    window.EJS_onGameStart = () => {
        const manager = window.EJS_emulator.gameManager;
        offerPiStates(manager);
        offerSendToPi(manager);
        watchForExit(manager);
        pinMenuBar(window.EJS_emulator);
        forgetOldCopies(window.EJS_emulator);
        if (padLayout) startPad(padLayout, manager);
        if (pendingSave) {
            try {
                const path = manager.getSaveFilePath();
                const folder = path.slice(0, path.lastIndexOf('/'));
                if (folder) manager.FS.mkdirTree(folder);
                manager.FS.writeFile(path, pendingSave);
                manager.loadSaveFiles();
            } catch (e) {
                setStatus(`Couldn't load the save into the emulator: ${e.message}`, true);
                if (chosenState) setTimeout(() => loadPiState(manager, chosenState), 1500);
                return;   // don't write back over a save that didn't load
            }
        }
        if (chosenState) setTimeout(() => loadPiState(manager, chosenState), 1500);
        if (!profile()) return;
        // EmulatorJS reports the save each time it writes it to its own disk;
        // ask it to every 20 seconds, and when the page is left
        window.EJS_emulator.on('saveSaveFiles', (save) => sendSave(save));
        const flush = () => { try { manager.saveSaveFiles(); } catch (e) {} };
        setInterval(flush, 20000);
        window.addEventListener('pagehide', flush);
        document.addEventListener('visibilitychange', () => { if (document.hidden) { flush(); keepWhereStopped(manager); } });
        // Back, while playing: where they stopped kept on the way
        $('back').addEventListener('click', (e) => { e.preventDefault(); leaveGame(manager); });
    };
    // The emulator's own "save file" button sends it straight away
    window.EJS_onSaveSave = (e) => sendSave(e && e.save);
    // Its save state and load state buttons keep one state per game on the server
    if (profile() && info.states) {
        window.EJS_onSaveState = async (e) => {
            if (!e || !e.state) return;
            try {
                const res = await fetch(`/api/play/state?${query({ profile: profile() })}`, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: e.state });
                const d = await res.json();
                setStatus(d.success ? `Save state kept for ${who()} at ${new Date().toLocaleTimeString()}` : `Save state not kept: ${d.error}`, !d.success);
            } catch (err) { setStatus(`Save state not kept: ${err.message}`, true); }
        };
        window.EJS_onLoadState = async () => {
            try {
                const res = await fetch(`/api/play/state?${query({ profile: profile() })}`);
                if (!res.ok) { setStatus(`There's no save state for ${who()} for this game yet`); return; }
                window.EJS_emulator.gameManager.loadState(new Uint8Array(await res.arrayBuffer()));
                setStatus(`Loaded ${whose()} save state`);
            } catch (err) { setStatus(`Couldn't load the save state: ${err.message}`, true); }
        };
    }

    const script = document.createElement('script');
    script.src = `${info.emulatorjs_url}loader.js`;
    script.onerror = () => setStatus("Couldn't load EmulatorJS. The first time each system is played it's fetched from the address in Tools › Settings, which needs the internet.", true);
    document.body.appendChild(script);
}

$('start').addEventListener('click', start);
load();
