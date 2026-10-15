// The header every RetroManager page shares: brand, Library / Bookcase /
// Timeline, and the actions (library-scrape progress, Add games, Tools, theme).
// Plain JavaScript (no JSX) so any page can load it after React:
//     <RM.Header active="timeline" />
// On the library page, pass onTool to open a Tools panel in place; elsewhere
// the Tools menu goes to the library with ?tool=<name>.
(function () {
    const h = React.createElement;
    const { useState, useEffect, useRef } = React;

    const PAGES = [
        { key: 'library', label: 'Library', icon: '🎮', href: '/' },
        { key: 'console', label: 'Console', icon: '🕹️', href: '/console' },
        { key: 'bookcase', label: 'Bookcase', icon: '📚', href: '/shelf' },
        { key: 'timeline', label: 'Timeline', icon: '🕰️', href: '/timeline' },
        { key: 'stats', label: 'Stats', icon: '📊', href: '/stats' },
    ];

    const TOOLS = [
        { key: 'health', icon: '🩺', label: 'Library health', help: 'Every system’s Scan in one place' },
        { key: 'scrape', icon: '🔎', label: 'Library scrape', help: 'Scrape every system in the background' },
        { key: 'media', icon: '🖼️', label: 'Missing media', help: 'Which games lack a box, screenshot, spine...' },
        { key: 'history', icon: '🕹️', label: 'Play history', help: 'What’s been played, and by whom' },
        { key: 'achievements', icon: '🏆', label: 'Achievement overview', help: 'Games ranked by how much you’ve completed' },
        { key: 'series', icon: '🧩', label: 'Missing in series', help: 'What you have of each series, and your want list' },
        { key: 'collections', icon: '📁', label: 'Collections', help: 'Your own lists of games: rename, delete, tidy' },
        { key: 'roms', icon: '🔬', label: 'ROM check', help: 'Verified dumps, duplicates and mislabelled files' },
        { key: 'saves', icon: '💾', label: 'Saves', help: 'Sync conflicts and save backups' },
        { key: 'backups', icon: '🗂️', label: 'Gamelist backups', help: 'See what changed and restore' },
        { key: 'settings', icon: '⚙️', label: 'Settings', help: 'Accounts and keys for the scraping sources' },
        { key: 'profiles', icon: '👤', label: 'Profiles and login', help: 'Who uses RetroManager, and who can change it' },
    ];

    // Inside the phone app (android/), which puts RMApp on the page: what the phone
    // has, for every page's use.
    //   RM.phone.offline   RetroManager can't be reached (the pages are the phone's kept copies)
    //   RM.phone.roms      {system folder: Set of the game files in the phone's roms folder}
    //   RM.phone.counts    {system folder: how many of its games are on the phone} (the Console page fills it)
    //   RM.phone.needs     Set of the system folders nothing on the phone plays yet (no emulator, or no core)
    // "retromanager:phone" is sent when any of it changes. The app itself sends
    // "retromanager:phone-roms" when the files may have (a game arrived, or the app came back).
    const app = window.RMApp || null;
    const phone = { offline: false, roms: {}, counts: {}, needs: new Set() };
    // On a touch screen (and in the app) the header is for fingers: common/header.css
    try {
        if (app || window.matchMedia('(pointer: coarse)').matches) document.documentElement.classList.add('rm-touch');
    } catch (e) {}
    if (app) {
        const changed = () => window.dispatchEvent(new Event('retromanager:phone'));
        const readRoms = () => {
            try { phone.roms = Object.fromEntries(Object.entries(JSON.parse(app.localSystems())).map(([system, paths]) => [system, new Set(paths)])); } catch (e) {}
            try { phone.needs = new Set(app.unplayable ? JSON.parse(app.unplayable()) : []); } catch (e) {}
            changed();
        };
        const readOffline = () => {
            let offline = phone.offline;
            try { offline = !!app.offline(); } catch (e) {}
            if (offline !== phone.offline) { phone.offline = offline; changed(); }
        };
        try { phone.counts = JSON.parse(localStorage.getItem('retromanager.phone.counts')) || {}; } catch (e) {}
        try { phone.offline = !!app.offline(); } catch (e) {}
        readRoms();
        window.addEventListener('retromanager:phone-roms', readRoms);
        setInterval(readOffline, 3000);

        // A favourite or a play status set with no connection is kept, and sent
        // when RetroManager is back. Meanwhile the page is answered as if it had
        // gone through, and the game lists it loads (the app's kept copies) show
        // it that way.
        const QUEUE = 'retromanager.phone.queue';
        const waiting = () => { try { return JSON.parse(localStorage.getItem(QUEUE)) || []; } catch (e) { return []; } };
        const keep = (queue) => { try { localStorage.setItem(QUEUE, JSON.stringify(queue)); } catch (e) {} };
        const plain = (path) => String(path || '').replace(/^(\.\/)+/, '');
        const ask = window.fetch.bind(window);
        const json = (data) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
        const later = (path, body) => {
            keep([...waiting().filter(q => !(q.path === path && q.body.system === body.system && plain(q.body.rom_path) === plain(body.rom_path))), { path, body }]);
            return json(path === '/api/favorite' ? { success: true, favorite: !!body.favorite, waiting: true } : { success: true, play_status: body.status || null, waiting: true });
        };
        const withWaiting = (system, game) => {
            waiting().forEach(q => {
                if (q.body.system !== system || plain(q.body.rom_path) !== plain(game.path)) return;
                if (q.path === '/api/favorite') game.favorite = !!q.body.favorite; else game.play_status = q.body.status || null;
            });
        };
        window.fetch = (input, init) => {
            let url;
            try { url = new URL(typeof input === 'string' ? input : input.url, window.location.origin); } catch (e) { return ask(input, init); }
            const method = ((init && init.method) || 'GET').toUpperCase();
            if (url.origin !== window.location.origin) return ask(input, init);
            if (method === 'PUT' && (url.pathname === '/api/favorite' || url.pathname === '/api/play-status') && init && typeof init.body === 'string') {
                let body;
                try { body = JSON.parse(init.body); } catch (e) { return ask(input, init); }
                if (phone.offline) return Promise.resolve(later(url.pathname, body));
                return ask(input, init).catch(() => later(url.pathname, body));
            }
            const games = method === 'GET' && /^\/api\/systems\/([^/]+)\/games(\/|$)/.exec(url.pathname);
            if (!games || !waiting().length) return ask(input, init);
            return ask(input, init).then(async (response) => {
                if (!response.ok) return response;
                const data = await response.json();
                const system = decodeURIComponent(games[1]);
                (data.games || (data.game ? [data.game] : [])).forEach(game => withWaiting(system, game));
                return json(data);
            });
        };
        let sending = false;
        const send = async () => {
            if (sending || phone.offline || !waiting().length) return;
            sending = true;
            try {
                for (const q of waiting()) {
                    const response = await ask(q.path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q.body) });
                    // (sent, or turned down for good: either way it isn't waiting any more)
                    if (response.status >= 500) break;
                    keep(waiting().filter(w => w !== q && JSON.stringify(w) !== JSON.stringify(q)));
                }
            } catch (e) { /* still no connection */ }
            sending = false;
        };
        window.addEventListener('retromanager:phone', send);
        setTimeout(send, 2000);
    }
    // The app's questions, messages and "fetching" box, drawn here so they have the
    // page's colours: the app calls RMDialog.show({id, kind, title, message, ...})
    // and is answered with app.dialogAnswer(id, index, text); RMDialog.progress({text,
    // done, total, amount}) shows how a fetch is going (null: put it away). Each
    // says true if it could, and the app uses the phone's own boxes if not.
    if (app) {
        const state = { ask: null, progress: null };
        let root = null;
        const draw = () => {
            if (!root) {
                const holder = document.createElement('div');
                document.body.appendChild(holder);
                root = ReactDOM.createRoot(holder);
            }
            root.render(h(Asked, { ask: state.ask, progress: state.progress }));
        };
        const answer = (index, text) => {
            const ask = state.ask;
            if (!ask) return;
            state.ask = null;
            draw();
            try { app.dialogAnswer(String(ask.id), index, text == null ? '' : String(text)); } catch (e) {}
        };
        const Asked = ({ ask, progress }) => {
            const [typed, setTyped] = useState('');
            useEffect(() => { setTyped(ask && ask.value ? ask.value : ''); }, [ask && ask.id]);
            const closes = !!ask && ask.cancel !== false;
            useEffect(() => {
                if (!ask) return undefined;
                // (before the page's own Escapes: this is on top of whatever else is open)
                const onKey = (e) => { if (e.key !== 'Escape') return; e.stopImmediatePropagation(); e.preventDefault(); if (ask.kind === 'alert') answer(0); else if (closes) answer(-1); };
                window.addEventListener('keydown', onKey, true);
                return () => window.removeEventListener('keydown', onKey, true);
            }, [ask && ask.id]);
            if (ask) {
                return h('div', { className: 'rm-ask', role: 'dialog', 'aria-modal': true, 'aria-label': ask.title, onClick: (e) => { if (e.target === e.currentTarget && closes && ask.kind !== 'input') answer(ask.kind === 'alert' ? 0 : -1); } },
                    h('form', { className: 'rm-ask-box', onSubmit: (e) => { e.preventDefault(); if (ask.kind !== 'choose') answer(0, typed); } },
                        h('h2', null, ask.title),
                        ask.message && h('p', null, ask.message),
                        ask.kind === 'choose' && h('div', { className: 'rm-set-rows' }, (ask.options || []).map((option, i) =>
                            h('button', { key: i, type: 'button', className: 'rm-set-row', onClick: () => answer(i) }, h('span', { className: 'rm-set-label' }, option)))),
                        ask.kind === 'input' && h('input', { value: typed, onChange: e => setTyped(e.target.value), placeholder: ask.hint || '', autoFocus: true, autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false }),
                        h('div', { className: 'rm-ask-buttons' },
                            closes && ask.kind !== 'alert' && h('button', { type: 'button', className: 'rm-btn', onClick: () => answer(-1) }, 'Cancel'),
                            ask.other && h('button', { type: 'button', className: 'rm-btn', onClick: () => answer(1, typed) }, ask.other),
                            ask.kind !== 'choose' && h('button', { className: 'rm-btn primary' }, ask.yes || 'OK'))));
            }
            if (progress) {
                const part = progress.total > 0 ? Math.min(100, progress.done * 100 / progress.total) : null;
                return h('div', { className: 'rm-ask', role: 'status' },
                    h('div', { className: 'rm-ask-box' },
                        h('p', { className: 'rm-ask-doing' }, progress.text),
                        progress.amount && h('p', { className: 'rm-ask-amount' }, progress.amount),
                        h('div', { className: `rm-task-bar${part === null ? ' unknown' : ''}` }, h('span', { style: { width: part === null ? '100%' : `${part}%` } })),
                        h('div', { className: 'rm-ask-buttons' }, h('button', { type: 'button', className: 'rm-btn', onClick: () => app.cancelFetch() }, 'Cancel'))));
            }
            return null;
        };
        window.RMDialog = {
            show(spec) {
                if (!document.body || !app.dialogAnswer || !spec) return false;
                if (state.ask) answer(-1);
                state.ask = spec;
                draw();
                return true;
            },
            progress(now) {
                if (!document.body || !app.cancelFetch) return false;
                state.progress = now || null;
                draw();
                return true;
            },
        };
    }

    // Which of a game's pictures its tile on the Console page shows (Continue
    // playing, Recently added). Kept in this browser; a game without that one
    // shows another it has. Chosen in the phone app's settings.
    const consolePicture = {
        KEY: 'retromanager.console.picture',
        OPTIONS: [['mix', 'Mix'], ['box2d', '2D box'], ['box3d', '3D box'], ['wheel', 'Logo'], ['screenshot', 'Screenshot'],
            ['screenshottitle', 'Title screen'], ['images', 'Image'], ['fanart', 'Fan art'], ['posters', 'Poster']],
        get() {
            let chosen = null;
            try { chosen = localStorage.getItem(this.KEY); } catch (e) {}
            return this.OPTIONS.some(o => o[0] === chosen) ? chosen : 'mix';
        },
        set(key) {
            try { localStorage.setItem(this.KEY, key); } catch (e) {}
            window.dispatchEvent(new Event('retromanager:console-picture'));
        },
    };

    // Redraws a component when what the phone has changes
    function usePhone() {
        const [, redraw] = useState(0);
        useEffect(() => {
            if (!app) return undefined;
            const on = () => redraw(n => n + 1);
            window.addEventListener('retromanager:phone', on);
            return () => window.removeEventListener('retromanager:phone', on);
        }, []);
        return phone;
    }

    // The tools a player may use: the rest change the library, or its settings
    const PLAYER_TOOLS = ['history', 'achievements', 'series'];
    // Who's signed in (common/accounts.js), once known
    function useMe() {
        const [me, setMe] = useState(null);
        useEffect(() => { let on = true; (window.RM.me || Promise.resolve(null)).then(d => { if (on) setMe(d); }); return () => { on = false; }; }, []);
        return me;
    }
    function Face({ profile, size }) {
        const look = window.RM.avatar(profile);
        return h('span', { className: 'rm-face', style: { width: size, height: size, fontSize: Math.round(size * 0.46), background: look.photo ? 'none' : look.colour }, 'aria-hidden': true },
            look.photo ? h('img', { src: look.photo, alt: '' }) : look.initial);
    }
    // The signed-in profile's photo, and the others to switch to (shown with login on)
    function ProfileMenu({ me, onTool }) {
        const [open, setOpen] = useState(false);
        const ref = useRef(null);
        useEffect(() => {
            if (!open) return;
            const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
            const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
            document.addEventListener('mousedown', close);
            document.addEventListener('keydown', esc);
            return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
        }, [open]);
        const mine = me.profiles.find(p => p.name === me.profile);
        const profiles = () => { setOpen(false); if (onTool) onTool('profiles'); else window.location.href = '/?tool=profiles'; };
        if (!mine) {
            // Nobody's signed in (login is off, or there are no profiles yet): the
            // button is still there, as the way in to setting profiles up
            const none = !me.profiles.length;
            return h('div', { ref, className: 'rm-menu-wrap' },
                h('button', { className: 'rm-profile', onClick: () => setOpen(o => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': 'Profiles', title: none ? 'No profiles yet' : 'Profiles' },
                    h('span', { className: 'rm-face rm-face-none', style: { width: 30, height: 30, fontSize: 16 }, 'aria-hidden': true }, '👤')),
                open && h('div', { role: 'menu', className: 'rm-menu rm-profile-menu' },
                    h('div', { className: 'rm-profile-me' }, h('span', { className: 'rm-face rm-face-none', style: { width: 44, height: 44, fontSize: 22 }, 'aria-hidden': true }, '👤'),
                        h('span', null, h('b', null, none ? 'No profiles' : 'Nobody signed in'),
                            h('span', { className: 'rm-help' }, none ? 'Saves, favourites and play status are shared by everyone' : 'Login is off: everyone shares one set of everything'))),
                    me.admin && h('button', { role: 'menuitem', onClick: profiles },
                        h('span', { style: { fontSize: 16, width: 32, textAlign: 'center' }, 'aria-hidden': true }, '👤'),
                        h('span', null, h('span', { style: { display: 'block' } }, 'Profiles and login'), h('span', { className: 'rm-help' }, none ? 'Add the people who play, to keep their saves apart' : 'Who plays, and whether they sign in')))));
        }
        return h('div', { ref, className: 'rm-menu-wrap' },
            h('button', { className: 'rm-profile', onClick: () => setOpen(o => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': `Signed in as ${mine.name}. Switch profile`, title: `${mine.name}: switch profile` },
                h(Face, { profile: mine, size: 30 })),
            open && h('div', { role: 'menu', className: 'rm-menu rm-profile-menu' },
                h('div', { className: 'rm-profile-me' }, h(Face, { profile: mine, size: 44 }),
                    h('span', null, h('b', null, mine.name), h('span', { className: 'rm-help' }, mine.role === 'admin' ? 'Admin' : 'Player'))),
                me.profiles.filter(p => p.name !== me.profile).map(p => h('button', { key: p.name, role: 'menuitem', onClick: () => { setOpen(false); window.RM.switchTo(p.name); } },
                    h(Face, { profile: p, size: 32 }),
                    h('span', null, h('span', { style: { display: 'block' } }, p.name), p.role === 'admin' && h('span', { className: 'rm-help' }, 'Asks for the PIN')))),
                me.admin && h('button', { role: 'menuitem', onClick: profiles },
                    h('span', { style: { fontSize: 16, width: 32, textAlign: 'center' }, 'aria-hidden': true }, '👤'), h('span', null, 'Profiles and login')),
                h('button', { role: 'menuitem', onClick: () => window.RM.signOut() },
                    h('span', { style: { fontSize: 16, width: 32, textAlign: 'center' }, 'aria-hidden': true }, '⎋'), h('span', null, 'Sign out'))));
    }

    // Picks the site's colour theme (common/theme.js, loaded in each page's <head>)
    function ThemeMenu() {
        const [open, setOpen] = useState(false);
        const [theme, setTheme] = useState(() => window.RMTheme.current().key);
        const ref = useRef(null);
        useEffect(() => {
            if (!open) return;
            const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
            const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
            document.addEventListener('mousedown', close);
            document.addEventListener('keydown', esc);
            return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
        }, [open]);
        return h('div', { ref, className: 'rm-menu-wrap' },
            h('button', { className: 'rm-btn', onClick: () => setOpen(o => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': 'Theme', title: 'Colour theme' },
                '🎨', h('span', { className: 'rm-label' }, 'Theme')),
            open && h('div', { role: 'menu', className: 'rm-menu', style: { width: 200 } },
                window.RMTheme.THEMES.map(t => h('button', {
                    key: t.key, role: 'menuitemradio', 'aria-checked': t.key === theme,
                    onClick: () => setTheme(window.RMTheme.set(t.key).key),
                },
                    h('span', { className: 'rm-swatch', 'aria-hidden': true }, t.swatch.map(color => h('span', { key: color, style: { background: color } }))),
                    h('span', null, t.label),
                    t.key === theme && h('span', { className: 'rm-check', 'aria-hidden': true }, '✓')))));
    }

    function ToolsMenu({ onTool, me }) {
        const [open, setOpen] = useState(false);
        const tools = TOOLS.filter(t => !me || me.admin || PLAYER_TOOLS.includes(t.key));
        const ref = useRef(null);
        useEffect(() => {
            if (!open) return;
            const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
            const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
            document.addEventListener('mousedown', close);
            document.addEventListener('keydown', esc);
            return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
        }, [open]);
        const pick = (key) => {
            setOpen(false);
            if (onTool) onTool(key);
            else window.location.href = `/?tool=${encodeURIComponent(key)}`;
        };
        return h('div', { ref, className: 'rm-menu-wrap' },
            h('button', { className: 'rm-btn', onClick: () => setOpen(o => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': 'Tools', title: 'Tools' },
                '🧰', h('span', { className: 'rm-label' }, 'Tools')),
            open && h('div', { role: 'menu', className: 'rm-menu' },
                tools.map(t => h('button', { key: t.key, role: 'menuitem', onClick: () => pick(t.key) },
                    h('span', { style: { fontSize: 16 }, 'aria-hidden': true }, t.icon),
                    h('span', null, h('span', { style: { display: 'block' } }, t.label), h('span', { className: 'rm-help' }, t.help))))));
    }

    // What's running in the background (the library scrape, the ROM check, series
    // matching): asked every minute, every 3 s while something runs, and at once
    // when a page says it started or stopped something (RM.tasksChanged).
    const TASKS_EVENT = 'retromanager:tasks';
    function useTasks(enabled) {
        const [tasks, setTasks] = useState([]);
        useEffect(() => {
            if (!enabled) { setTasks([]); return; }
            let timer, stopped = false;
            const tick = async () => {
                clearTimeout(timer);
                let wait = 60000;
                try {
                    const d = await (await fetch('/api/tasks')).json();
                    if (d.success && !stopped) {
                        setTasks(d.tasks);
                        wait = d.tasks.some(t => t.running) ? 3000 : d.tasks.length ? 10000 : 60000;
                    }
                } catch (e) {}
                if (!stopped) timer = setTimeout(tick, wait);
            };
            // A moment later, so what was just started has begun
            const soon = () => { clearTimeout(timer); timer = setTimeout(tick, 600); };
            tick();
            window.addEventListener(TASKS_EVENT, soon);
            return () => { stopped = true; clearTimeout(timer); window.removeEventListener(TASKS_EVENT, soon); };
        }, [enabled]);
        return tasks;
    }

    // One task: its name, a bar, how far along it is and what it's on now; or,
    // just after it ended, how it went. Opens the task's tool.
    function Task({ task, onOpen }) {
        const known = task.total > 0;
        const state = task.running ? (task.stopping ? 'Stopping…' : known ? `${task.done} of ${task.total}` : 'Starting…')
            : task.problem ? 'Stopped' : task.stopped ? `Stopped at ${task.done} of ${task.total}` : 'Done';
        const detail = task.running ? task.current : (task.problem || task.summary);
        return h('button', { className: `rm-task${task.running ? '' : task.problem ? ' problem' : ' done'}`, onClick: () => onOpen(task.tool),
            title: `${task.label}: open it` },
            h('span', { 'aria-hidden': true }, task.running ? '⏳' : task.problem ? '⚠' : '✓'),
            h('b', null, task.label),
            task.running && h('span', { className: `rm-task-bar${known ? '' : ' unknown'}`, 'aria-hidden': true },
                h('span', { style: { width: known ? `${Math.min(100, 100 * task.done / task.total)}%` : '100%' } })),
            h('span', { className: 'rm-task-state' }, state),
            detail && h('span', { className: 'rm-task-detail' }, detail));
    }

    // The strip under the header: there only while something is running or has
    // just ended. One line; with more than one task, the rest unfold from it.
    function TaskStrip({ tasks, onTool }) {
        const [open, setOpen] = useState(false);
        const ref = useRef(null);
        const showing = tasks.length > 0;
        useEffect(() => {
            // Pages that stick something under the header (the Bookcase's bar) make room
            document.documentElement.style.setProperty('--rm-tasks-h', showing ? '30px' : '0px');
            return () => document.documentElement.style.setProperty('--rm-tasks-h', '0px');
        }, [showing]);
        useEffect(() => {
            if (!open) return;
            const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
            document.addEventListener('mousedown', close);
            return () => document.removeEventListener('mousedown', close);
        }, [open]);
        if (!showing) return null;
        const go = (tool) => { setOpen(false); if (onTool) onTool(tool); else window.location.href = `/?tool=${encodeURIComponent(tool)}`; };
        // What's running comes before what has ended
        const ordered = tasks.slice().sort((x, y) => Number(y.running) - Number(x.running));
        return h('div', { ref, className: 'rm-tasks', role: 'status', 'aria-label': 'Background tasks' },
            h(Task, { task: ordered[0], onOpen: go }),
            ordered.length > 1 && h('button', { className: 'rm-task-more', onClick: () => setOpen(o => !o), 'aria-expanded': open },
                `+${ordered.length - 1} more ${open ? '▴' : '▾'}`),
            open && ordered.length > 1 && h('div', { className: 'rm-tasks-all' },
                ordered.slice(1).map(task => h(Task, { key: task.key, task, onOpen: go }))));
    }

    // In the phone app: "This phone", the app's own settings, drawn by the page so
    // they look like the rest of it. The app says what's set (settingsInfo,
    // emulatorsInfo, scanStorage) and does what's pressed (setting, setEmulator...).
    // Screens: the groups; Emulators and one system's; Games on this phone and one system's files.
    function PhoneSettings({ me, onClose }) {
        const read = (what, empty) => { try { return JSON.parse(app[what]()); } catch (e) { return empty; } };
        const [info, setInfo] = useState(() => read('settingsInfo', {}));
        const [emulators, setEmulators] = useState(() => read('emulatorsInfo', []));
        const [storage, setStorage] = useState(null);
        const [screen, setScreen] = useState({ name: 'main' });
        const [theme, setTheme] = useState(() => window.RMTheme.current().key);
        const [core, setCore] = useState('');
        // The RetroArch setup kept in RetroManager, if there is one ({device, at, files})
        const [kept, setKept] = useState(null);
        const askKept = () => fetch('/api/phone/setup').then(r => r.json()).then(d => setKept(d.success && d.saved ? d : null)).catch(() => {});
        useEffect(() => { askKept(); }, []);
        const here = usePhone();
        const back = () => {
            if (screen.name === 'main') onClose();
            else setScreen(screen.system ? { name: screen.name === 'emulator' ? 'emulators' : 'storage' } : { name: 'main' });
        };
        useEffect(() => {
            // (the app says when something it was asked to change has)
            const changed = () => { setInfo(read('settingsInfo', {})); setEmulators(read('emulatorsInfo', [])); askKept(); if (screen.name.startsWith('storage')) app.scanStorage(); };
            const found = (e) => setStorage(e.detail);
            const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); back(); } };
            window.addEventListener('retromanager:phone-roms', changed);
            window.addEventListener('retromanager:phone-storage', found);
            document.addEventListener('keydown', onKey, true);
            return () => { window.removeEventListener('retromanager:phone-roms', changed); window.removeEventListener('retromanager:phone-storage', found); document.removeEventListener('keydown', onKey, true); };
        }, [screen]);
        useEffect(() => { if (screen.name === 'storage') { setStorage(null); app.scanStorage(); } }, [screen.name === 'storage']);

        const row = (key, label, value, onClick, more = {}) => h(onClick ? 'button' : 'div', { key, className: `rm-set-row${more.on ? ' on' : ''}${more.warn ? ' warn' : ''}`, onClick, role: more.radio ? 'menuitemradio' : undefined, 'aria-checked': more.radio ? !!more.on : undefined },
            h('span', { className: 'rm-set-label' }, label, more.note && h('span', { className: 'rm-set-note' }, more.note)),
            value !== undefined && value !== null && h('span', { className: 'rm-set-value' }, value),
            more.radio ? h('span', { className: 'rm-set-mark', 'aria-hidden': true }, more.on ? '✓' : '') : onClick && h('span', { className: 'rm-set-mark', 'aria-hidden': true }, '›'));
        const group = (title, ...rows) => h('section', { key: title, className: 'rm-set-group' }, h('h3', null, title), h('div', { className: 'rm-set-rows' }, rows));

        let title = 'This phone', body;
        if (screen.name === 'emulators') {
            title = 'Emulators';
            body = emulators.length
                ? group('What plays each system', ...emulators.map(e => row(e.name, e.label, e.plays ? e.plays + (e.chosen ? ' (chosen)' : '') : 'nothing yet', () => { setCore(''); setScreen({ name: 'emulator', system: e.name }); }, { warn: !e.plays })))
                : h('p', { className: 'rm-set-empty' }, 'The list of systems comes from RetroManager, which hasn’t been reached yet.');
        } else if (screen.name === 'emulator') {
            const system = emulators.find(e => e.name === screen.system) || { label: screen.system, options: [] };
            const pick = (id) => app.setEmulator(system.name, id);
            title = system.label;
            body = h(React.Fragment, null,
                group('Play it with',
                    row('auto', 'Automatic', null, () => pick(''), { radio: true, on: !system.chosen, note: system.plays ? `now: ${system.plays}` : 'nothing on this phone plays it yet' }),
                    ...system.options.map(o => o.get
                        ? row(o.id, `Get ${o.label}`, null, () => app.setting('open', o.get), { note: o.note })
                        : row(o.id, o.label, null, () => pick(o.id), { radio: true, on: system.chosen === o.id, note: o.note }))),
                group('Another RetroArch core',
                    h('form', { key: 'core', className: 'rm-set-row rm-set-form', onSubmit: (e) => { e.preventDefault(); const name = core.trim().replace('_libretro_android.so', ''); if (name) { pick(`retroarch:${name}`); setCore(''); } } },
                        h('input', { value: core, onChange: e => setCore(e.target.value), placeholder: 'snes9x', 'aria-label': 'The core’s file name, without _libretro_android.so', autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false }),
                        h('button', { className: 'rm-btn', disabled: !core.trim() }, 'Use'))),
                h('p', { className: 'rm-set-empty' }, 'A core’s name is its file name in RetroArch, without “_libretro_android.so”. An emulator of its own keeps its saves to itself.'));
        } else if (screen.name === 'storage') {
            title = 'Games on this phone';
            body = !storage ? h('p', { className: 'rm-set-empty' }, 'Looking through the roms folder…')
                : group(`${storage.total} in the roms folder${storage.free ? ` · ${storage.free} free` : ''}`,
                    ...(storage.systems.length ? storage.systems.slice().sort((a, b) => b.bytes - a.bytes).map(s => row(s.name, s.label, `${s.count} file${s.count === 1 ? '' : 's'} · ${s.size}`, () => setScreen({ name: 'storage-system', system: s.name })))
                        : [h('p', { key: 'none', className: 'rm-set-empty' }, 'Nothing there yet.')]));
        } else if (screen.name === 'storage-system') {
            const system = ((storage && storage.systems) || []).find(s => s.name === screen.system);
            title = system ? system.label : screen.system;
            body = !system ? h('p', { className: 'rm-set-empty' }, 'Nothing of it is on the phone now.')
                : group(`${system.size} · largest first · press one to take it off the phone`,
                    ...system.files.map(([path, size]) => row(path, path, size, () => app.removeLocal(system.name, path, path.split('/').pop()))));
        } else {
            const signedIn = me && me.enabled && me.profile;
            body = h(React.Fragment, null,
                group('Connection',
                    row('server', 'RetroManager', info.server, () => app.setting('server', '')),
                    row('status', 'Now', here.offline ? 'Offline: press to look again' : 'Online', here.offline && app.checkOnline ? () => app.checkOnline() : null, { warn: here.offline }),
                    app.openBrowser && row('browser', 'Open RetroManager in the browser', null, () => app.openBrowser()),
                    row('reload', 'Reload this page', null, () => { onClose(); app.setting('reload', ''); })),
                group('RetroArch',
                    row('folder', 'Folder', info.folder || 'not chosen', () => app.setting('folder', ''), { warn: !info.folder }),
                    ...((info.retroArchs || []).length > 1
                        ? info.retroArchs.map(name => row(name, 'App', name, () => app.setting('retroarch', name), { radio: true, on: name === info.retroArch }))
                        : [row('app', 'App', info.retroArch || 'not installed', null, { warn: !info.retroArch })]),
                    row('emulators', 'Emulators', `${emulators.filter(e => !e.plays).length ? `${emulators.filter(e => !e.plays).length} with nothing to play them` : 'what plays each system'}`, () => setScreen({ name: 'emulators' }), { warn: emulators.some(e => !e.plays) })),
                // (an app from before it could carry a setup has none of this)
                'pinSaves' in info && group('RetroArch setup',
                    row('check', 'Check this phone', null, () => app.setting('setup-check', ''), { note: 'the folders, the cores it has used, where saves go' }),
                    row('apply', 'Apply the saved setup', kept ? `from ${kept.device}` : 'none saved yet', kept ? () => app.setting('setup-apply', '') : null,
                        { note: kept ? `${kept.files.length} files, saved ${new Date(kept.at * 1000).toLocaleDateString()}: overrides, core options, shader presets, overlays` : 'save one from a phone that is set up as you like it' }),
                    (!me || me.admin) && row('save', 'Save this phone’s setup', null, () => app.setting('setup-save', ''), { note: 'to RetroManager, for other phones to apply' }),
                    row('pin', 'Same save folders on every phone', null, () => app.setting('setup-pin', info.pinSaves ? 'off' : 'on'),
                        { radio: true, on: !!info.pinSaves, note: 'saves/<system> and states/<system>, whatever RetroArch is set to: written into each core’s override as it’s played' })),
                group('Saves and save states',
                    ...(signedIn ? [row('me', 'Kept as', `${me.profile}’s (signed in)`)]
                        : [
                            // (with no profiles there's only the shared set, which is what's used unless "nobody" is chosen)
                            row('shared', 'Everyone’s', null, () => app.setting('profile', 'shared'), { radio: true, on: info.profile === 'shared' || (info.profile == null && !(info.profiles || []).length), note: 'the shared saves, as RetroArch keeps them' }),
                            ...(info.profiles || []).map(name => row(name, name, null, () => app.setting('profile', name), { radio: true, on: info.profile === name })),
                            row('nobody', 'Nobody', null, () => app.setting('profile', ''), { radio: true, on: info.profile === '', note: 'they stay on this phone' }),
                        ])),
                // RetroArch keeps one save for a game whoever plays, so the app has to know whose the phone's are
                (info.profiles || []).length > 1 && group('The saves on this phone are',
                    ...(info.profiles || []).map(name => row(`own-${name}`, `${name}’s`, null, () => app.setting('unclaimed', name),
                        { radio: true, on: info.unclaimed === name, note: info.unclaimed === name ? 'the ones that were here before the app, and every game’s that is on it now' : null })),
                    h('p', { key: 'own-note', className: 'rm-set-empty' }, 'When someone else starts a game, these are put by for this person and their own brought back. Choosing a name again takes every save now on the phone to be theirs.')),
                group('Storage',
                    row('games', 'Games on this phone', 'by system and size', () => setScreen({ name: 'storage' })),
                    row('kept', 'Pages kept for offline', info.kept, () => app.setting('forget', ''), { note: 'press to forget them' })),
                // (an admin's: a player can't add to the library)
                (!me || me.admin) && group('Library',
                    row('add', 'Add games to RetroManager', null, () => { window.location.href = '/import'; }, { note: 'from this phone’s files; or share a file to RetroManager from another app' })),
                h('section', { className: 'rm-set-group' }, h('h3', null, 'Colours'),
                    h('div', { className: 'rm-set-themes' }, window.RMTheme.THEMES.map(t => h('button', { key: t.key, className: t.key === theme ? 'on' : '', 'aria-pressed': t.key === theme, onClick: () => setTheme(window.RMTheme.set(t.key).key) },
                        h('span', { className: 'rm-swatch', 'aria-hidden': true }, t.swatch.map(color => h('span', { key: color, style: { background: color } }))),
                        h('span', null, t.label))))),
                group('About',
                    row('version', 'App version', info.version, () => app.setting('update', ''), { note: 'press to look for a newer one' })));
        }
        // On the page itself, not inside the header: a theme that blurs what's behind
        // the header would keep the panel inside the header's own strip
        return ReactDOM.createPortal(h('div', { className: 'rm-set', role: 'dialog', 'aria-modal': true, 'aria-label': title, onClick: (e) => { if (e.target === e.currentTarget) onClose(); } },
            h('div', { className: 'rm-set-panel' },
                h('div', { className: 'rm-set-head' },
                    h('button', { className: 'rm-btn', onClick: back, 'aria-label': screen.name === 'main' ? 'Close' : 'Back' }, screen.name === 'main' ? '✕' : '‹'),
                    h('h2', null, title)),
                h('div', { className: 'rm-set-body' }, body))), document.body);
    }

    function Header({ active, onTool }) {
        const me = useMe();
        const admin = !me || me.admin;
        // Background tasks are an admin's: a player can't open their tools
        const tasks = useTasks(admin && !app);
        const here = usePhone();
        const [settings, setSettings] = useState(false);
        // In the phone app the Console page is all there is: no other views, and
        // nothing that changes the library. It says whether the server's there instead.
        if (app) {
            return h('header', { className: 'rm-header' },
                h('a', { className: 'rm-brand', href: '/console', 'aria-label': 'RetroManager' },
                    h('img', { src: '/icons/icon-192.png', alt: '' }), h('span', null, 'RetroManager')),
                h('div', { className: 'rm-actions' },
                    // (pressed while connected, it opens the whole of RetroManager in the phone's browser)
                    h('button', { className: `rm-phone-status${here.offline ? ' off' : ''}`,
                        // (offline: looks for RetroManager again, and offers to start Tailscale if it still isn't there)
                        onClick: () => { if (here.offline) { if (app.checkOnline) app.checkOnline(); } else if (app.openBrowser) app.openBrowser(); },
                        title: here.offline ? "RetroManager can't be reached: press to look for it again" : 'Connected: open RetroManager in the browser' },
                        h('span', { className: 'rm-phone-dot', 'aria-hidden': true }), here.offline ? 'Offline' : 'Online',
                        here.offline && h('span', { className: 'rm-label' }, ': this phone’s games')),
                    // (its settings, the colours among them; an app from before it had this panel shows its own list)
                    h('button', { className: 'rm-btn', onClick: () => (app.settingsInfo ? setSettings(true) : app.openSettings()), title: 'This phone', 'aria-label': 'This phone' },
                        '📱', h('span', { className: 'rm-label' }, 'This phone')),
                    !app.settingsInfo && h(ThemeMenu),
                    me && h(ProfileMenu, { me, onTool })),
                settings && h(PhoneSettings, { me, onClose: () => setSettings(false) }));
        }
        return h(React.Fragment, null, h('header', { className: 'rm-header' },
            h('a', { className: 'rm-brand', href: '/', 'aria-label': 'RetroManager library' },
                h('img', { src: '/icons/icon-192.png', alt: '' }), h('span', null, 'RetroManager')),
            h('nav', { className: 'rm-nav', 'aria-label': 'Views' },
                PAGES.map(p => h('a', { key: p.key, href: p.href, 'aria-current': active === p.key ? 'page' : undefined, title: p.label, 'aria-label': p.label },
                    h('span', { 'aria-hidden': true }, p.icon), h('span', { className: 'rm-label' }, p.label)))),
            h('div', { className: 'rm-actions' },
                admin && h('a', { className: 'rm-btn', href: '/import', 'aria-current': active === 'import' ? 'page' : undefined, title: 'Add games', 'aria-label': 'Add games' },
                    '➕', h('span', { className: 'rm-label' }, 'Add games')),
                h(ToolsMenu, { onTool, me }),
                h(ThemeMenu),
                me && h(ProfileMenu, { me, onTool }))),
            h(TaskStrip, { tasks, onTool }));
    }

    // (added to RM, which common/accounts.js has already started)
    //   RM.tasksChanged()  a page started or stopped a background task: the strip asks again now
    const tasksChanged = () => window.dispatchEvent(new Event(TASKS_EVENT));
    window.RM = Object.assign(window.RM || {}, { Header, ThemeMenu, TOOLS, PAGES, tasksChanged, phone, usePhone, consolePicture });
})();
