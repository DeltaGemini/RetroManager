// The Game Details panel every page shows for a game: the Library (beside the
// game list and on the Home screen) and, in a popup, the Bookcase and the
// Timeline. Styled by common/game-details.css.
// Loaded before each page's own scripts, which share one global scope with it,
// so everything here is named gd.../GD... except the two components pages use:
// GameDetails and GameDetailsPopup.

const GD_API = window.location.origin;
// Inside the Android app (android/) a game starts in the phone's own RetroArch
// instead of the browser: the app puts RMApp on the page, and its play() fetches
// whatever the phone hasn't got, brings the save over and starts the game.
const gdPhone = window.RMApp || null;
// What the phone has (common/header.js keeps it): whether RetroManager can be
// reached, and the game files in the phone's roms folder
const gdPhoneState = () => (window.RM && window.RM.phone) || { offline: false, roms: {}, counts: {}, needs: new Set() };
// Nothing on the phone plays the system yet (pressing play says what to do about it)
const gdNeedsEmulator = (system) => !!gdPhone && !!gdPhoneState().needs && gdPhoneState().needs.has(system);
const gdUsePhone = () => (window.RM && window.RM.usePhone ? window.RM.usePhone() : gdPhoneState());
const gdHere = (system, path) => { const files = gdPhoneState().roms[system]; return !!files && files.has(gdEncodeless(path)); };
// A game from a list drawn from several systems names its own (game._system).
// With no connection, only a game that's on the phone can be played.
const gdCanPlay = (game, system) => !!game && !!(gdPhone
    ? game.phone_playable && (!gdPhoneState().offline || gdHere(game._system || system, game.path))
    : game.playable);
// Line drawings for a menu's rows, in the text's own colour (emoji differ in size and colour from one to the next)
const GD_ICONS = {
    home: 'M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z',
    sliders: 'M4 7h8m4 0h4M4 12h3m4 0h9M4 17h9m4 0h3M14 5v4M9 10v4M15 15v4',
    book: 'M5 5a2 2 0 0 1 2-2h12v16H7a2 2 0 0 0-2 2zm0 0v16m4-14h6',
    phone: 'M9 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm1 7l4 4m0-4l-4 4',
    pencil: 'M4 20l1-4L16 5l3 3L8 19zM14 7l3 3',
    bin: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10 11v6m4-6v6',
};
const gdIcon = (name) => (
    <svg className="gd-icon-line" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={GD_ICONS[name]} />
    </svg>
);
// Fetches JSON, and in the phone app gives what the server said last time first
// (the app keeps a copy of every answer), so a page is there at once and then
// brought up to date. use(data, kept) is called once or twice; the promise is
// the server's own answer.
const gdKeptFirst = (url, use) => {
    let answered = false;
    if (gdPhone) {
        fetch(url, { headers: { 'X-RetroManager-Kept': '1' } }).then(r => (r.ok ? r.json() : null))
            .then(d => { if (d && !answered) use(d, true); }).catch(() => {});
    }
    return fetch(url).then(r => r.json()).then(d => { answered = true; use(d, false); return d; });
};
// ▶ for a game that starts as it is; ⬇ for one the phone has to fetch first
// ...and ⚠ for one nothing on the phone plays yet
const gdPlayMark = (game, system) => (gdNeedsEmulator(game._system || system) ? '⚠' : gdPhone && !gdHere(game._system || system, game.path) ? '⬇' : '▶');
const gdPlayUrl = (system, romPath) => `/play?${new URLSearchParams({ system, game: romPath, ...(window.location.pathname.startsWith('/console') ? { from: 'console' } : {}) })}`;
const gdPlay = (system, romPath) => { if (gdPhone) gdPhone.play(system, romPath); else window.location.href = gdPlayUrl(system, romPath); };
// (on a link, so it still opens in a new tab on a computer)
const gdPlayClick = (system, romPath) => (e) => { if (gdPhone) { e.preventDefault(); gdPhone.play(system, romPath); } };
const gdEncode = (path) => String(path || '').replace(/^(\.\/)+/, '').split('/').map(encodeURIComponent).join('/');
const gdEncodeless = (path) => String(path || '').replace(/^(\.\/)+/, '');
const gdThumb = (mediaPath, height, version) => `${GD_API}/api/thumb/${height}/${gdEncode(mediaPath)}${version ? `?v=${version}` : ''}`;
const gdMedia = (mediaPath) => `${GD_API}/api/media/${gdEncode(mediaPath)}`;
// "Sonic (USA) [!]" -> "Sonic"
const gdTitle = (name) => (name || '').replace(/\s*[\(\[][^\)\]]*[\)\]]/g, '').replace(/\s+/g, ' ').trim() || name || '';
const gdBytes = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`;
const gdAgo = (ms) => {
    const s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 90) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)} minutes ago`;
    if (s < 86400 * 1.5) return `${Math.round(s / 3600)} hour${Math.round(s / 3600) === 1 ? '' : 's'} ago`;
    if (s < 86400 * 60) return `${Math.round(s / 86400)} days ago`;
    if (s < 86400 * 365 * 1.5) return `${Math.round(s / (86400 * 30))} months ago`;
    return `${Math.round(s / (86400 * 365))} years ago`;
};
// A gamelist date (19910101T000000) as "1 Jan 1991"
const gdReleased = (game) => {
    const d = game.releasedate;
    if (d && d.length >= 8) {
        const date = new Date(`${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}T00:00:00`);
        if (!isNaN(date)) return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    }
    return game.year ? String(game.year) : null;
};

// Which picture the panel shows: the Mix image unless changed (the choice
// under the picture), kept in this browser and shared by every page. A game
// without the chosen picture shows another one it has.
const GD_PICTURES = [['mix', 'Mix'], ['box2d', '2D box'], ['box3d', '3D box'], ['images', 'Image'], ['screenshot', 'Screenshot'],
    ['screenshottitle', 'Title screen'], ['fanart', 'Fan art'], ['posters', 'Poster']];
const GD_PICTURE_KEY = 'retromanager.details.picture';
const gdPicturePref = () => {
    try { const v = localStorage.getItem(GD_PICTURE_KEY); return GD_PICTURES.some(p => p[0] === v) ? v : 'mix'; } catch (e) { return 'mix'; }
};
const gdPictureField = (game, preferred) =>
    [preferred || gdPicturePref(), 'mix', 'box2d', 'box3d', 'images', 'screenshot', 'screenshottitle', 'posters', 'fanart'].find(f => game && game[f]);
function useGdPicture() {
    const [pref, setPref] = React.useState(gdPicturePref);
    React.useEffect(() => {
        const sync = () => setPref(gdPicturePref());
        window.addEventListener('retromanager:details-picture', sync);
        window.addEventListener('storage', sync);
        return () => { window.removeEventListener('retromanager:details-picture', sync); window.removeEventListener('storage', sync); };
    }, []);
    const choose = (value) => {
        try { localStorage.setItem(GD_PICTURE_KEY, value); } catch (e) {}
        setPref(value);
        window.dispatchEvent(new Event('retromanager:details-picture'));
    };
    return [pref, choose];
}

// A folded row with a one-line summary; whether it's open is remembered
function GDSection({ id, title, summary, children }) {
    const key = `retromanager.details.open.${id}`;
    const [open, setOpen] = React.useState(() => { try { return localStorage.getItem(key) === '1'; } catch (e) { return false; } });
    const toggle = () => setOpen(o => { try { localStorage.setItem(key, o ? '0' : '1'); } catch (e) {} return !o; });
    return (
        <section className="gd-section">
            <button className="gd-section-head" onClick={toggle} aria-expanded={open}>
                <span className="gd-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
                <span className="gd-section-title">{title}</span>
                <span className="gd-section-summary">{summary}</span>
            </button>
            {open && <div className="gd-section-body">{children}</div>}
        </section>
    );
}

const GD_STATUSES = [['playing', 'Playing', '⏵'], ['backlog', 'Backlog', '🕓'], ['finished', 'Finished', '✔']];

// Favourite, play status and collections
function GDStatus({ system, game, notify, onChanged }) {
    const [status, setStatus] = React.useState(game.play_status || null);
    const [favorite, setFavorite] = React.useState(!!game.favorite);
    const [member, setMember] = React.useState(game.collections || []);
    const [collections, setCollections] = React.useState(null);
    const [newName, setNewName] = React.useState('');
    const [menuOpen, setMenuOpen] = React.useState(false);
    const [find, setFind] = React.useState('');
    const menuRef = React.useRef(null);
    React.useEffect(() => {
        if (!menuOpen) return;
        const close = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
        const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); setMenuOpen(false); } };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', esc, true);
        return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc, true); };
    }, [menuOpen]);
    React.useEffect(() => {
        setStatus(game.play_status || null);
        setFavorite(!!game.favorite);
        setMember(game.collections || []);
        setMenuOpen(false);
        setFind('');
        setNewName('');
    }, [system, game.path]);
    // Fetched at first, and again each time the checklist opens (the Collections tool may have changed them)
    React.useEffect(() => {
        fetch(`${GD_API}/api/library-state`).then(r => r.json()).then(d => { if (d.success) setCollections(d.collections); }).catch(() => {});
    }, [menuOpen]);

    const who = { system, rom_path: game.path };
    const send = async (url, body, method = 'PUT') => {
        try {
            const res = await fetch(`${GD_API}${url}`, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            const d = await res.json();
            if (!d.success && notify) notify(d.error || 'That didn\'t work', 'error');
            return d;
        } catch (e) {
            if (notify) notify(e.message, 'error');
            return { success: false };
        }
    };
    // The game object is the page's own, so lists drawn from it follow
    const changed = (patch) => {
        Object.assign(game, patch);
        if (onChanged) onChanged(patch);
        window.dispatchEvent(new Event('retromanager:game-changed'));
    };
    const pickStatus = async (key) => {
        const next = status === key ? null : key;
        const d = await send('/api/play-status', { ...who, status: next });
        if (d.success) { setStatus(next); changed({ play_status: next }); }
    };
    const toggleFavorite = async () => {
        const d = await send('/api/favorite', { ...who, favorite: !favorite });
        if (d.success) { setFavorite(d.favorite); changed({ favorite: d.favorite, has_metadata: true }); }
    };
    const toggleCollection = async (id) => {
        const d = await send(`/api/collections/${id}/games`, { ...who, member: !member.includes(id) });
        if (d.success) {
            setMember(d.collections);
            const key = `${system}/${String(game.path).replace(/^(\.\/)+/, '')}`;
            setCollections(prev => (prev || []).map(c => c.id !== id ? c : { ...c, games: d.collections.includes(id) ? [...new Set([...c.games, key])] : c.games.filter(g => g !== key) }));
            changed({ collections: d.collections });
        }
    };
    const createCollection = async () => {
        const name = newName.trim();
        if (!name) return;
        const d = await send('/api/collections', { name }, 'POST');
        if (!d.success) return;
        setCollections(prev => [...(prev || []), d.collection]);
        setNewName('');
        toggleCollection(d.collection.id);
    };

    return (
        <div className="gd-status">
            <button className={`gd-chip${favorite ? ' on gd-fav' : ''}`} onClick={toggleFavorite} aria-pressed={favorite}
                title={favorite ? 'Remove from favourites' : 'Add to favourites (EmulationStation shows these too)'}>{favorite ? '★' : '☆'} Favourite</button>
            <span role="group" aria-label="Play status" className="gd-chip-group">
                {GD_STATUSES.map(([key, label, icon]) => (
                    <button key={key} className={`gd-chip${status === key ? ' on' : ''}`} onClick={() => pickStatus(key)} aria-pressed={status === key}>{icon} {label}</button>
                ))}
            </span>
            <span ref={menuRef} className="gd-menu-wrap admin-only">
                <button className={`gd-chip${member.length ? ' on' : ''}`} onClick={() => setMenuOpen(o => !o)} aria-haspopup="dialog" aria-expanded={menuOpen}
                    title="Choose which collections this game is in">
                    📁 {member.length === 0 ? 'Collections' : member.length === 1 ? ((collections || []).find(c => c.id === member[0]) || {}).name || '1 collection' : `${member.length} collections`} ▾
                </button>
                {menuOpen && (
                    <div role="dialog" aria-label="Collections" className="gd-menu">
                        {(collections || []).length > 6 && (
                            <input type="search" autoFocus value={find} placeholder="Find a collection" onChange={e => setFind(e.target.value)} />
                        )}
                        <div className="gd-menu-list">
                            {collections && !collections.length && <div className="gd-note">No collections yet. Name one below to start it with this game.</div>}
                            {(collections || []).filter(c => c.name.toLowerCase().includes(find.trim().toLowerCase())).map(c => (
                                <label key={c.id}>
                                    <input type="checkbox" checked={member.includes(c.id)} onChange={() => toggleCollection(c.id)} />
                                    <span className="gd-menu-name">{c.name}</span>
                                    <span className="gd-note">{c.games.length}</span>
                                </label>
                            ))}
                        </div>
                        <div className="gd-menu-new">
                            <input type="text" value={newName} placeholder="New collection..." maxLength={60} onChange={e => setNewName(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') createCollection(); }} />
                            <button className="gd-btn small" onClick={createCollection} disabled={!newName.trim()}>Add</button>
                        </div>
                    </div>
                )}
            </span>
        </div>
    );
}

// The game's RetroAchievements: completion, then every achievement with the
// earned ones in colour. Not shown at all without a RetroAchievements API key (Tools > Settings).
function GDAchievements({ system, game }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [loading, setLoading] = React.useState(false);
    // Whose progress to show (a name from Settings; '' is the main user), remembered in this browser
    const [who, setWhoState] = React.useState(() => { try { return localStorage.getItem('retromanager.achievements.who') || ''; } catch (e) { return ''; } });
    const setWho = (name) => { setWhoState(name); try { localStorage.setItem('retromanager.achievements.who', name); } catch (e) {} };
    const [filter, setFilter] = React.useState('all'); // all | earned | locked
    const [showAll, setShowAll] = React.useState(false);
    const PREVIEW_COUNT = 12;

    const load = React.useCallback((refresh) => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        const params = new URLSearchParams({ rom: game.path, ...(who ? { who } : {}), ...(refresh ? { refresh: '1' } : {}) });
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/achievements?${params}`)
            .then(r => r.json())
            .then(d => { if (!cancelled) d.success ? setData(d) : setError(d.error || 'Could not load achievements'); })
            .catch(err => { if (!cancelled) setError(err.message); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [system, game.path, who]);

    React.useEffect(() => {
        setData(null);
        setFilter('all');
        setShowAll(false);
        return load(false);
    }, [load]);

    if (data && !data.configured) return null;
    const section = (summary, content) => <GDSection id="achievements" title="Achievements" summary={summary}>{content}</GDSection>;
    if (error) return section('Couldn\'t load', <div className="gd-note gd-error">{error}</div>);
    if (!data) return section('Looking up…', <div className="gd-note">Looking this game up on RetroAchievements...</div>);
    if (!data.matched) {
        return section('Not recognised', (
            <div className="gd-row">
                <span className="gd-note">RetroAchievements doesn't recognise this ROM file, so it has no achievements to show.</span>
                <button className="gd-btn small" disabled={loading} onClick={() => load(true)}>{loading ? 'Checking...' : 'Check again'}</button>
            </div>
        ));
    }
    if (!data.total) {
        return section('None yet', <div className="gd-note">RetroAchievements knows this game (<a href={data.url} target="_blank" rel="noopener noreferrer">{data.title}</a>) but has no achievements for it yet.</div>);
    }

    const list = data.achievements.filter(a => filter === 'all' || (filter === 'earned' ? a.earned : !a.earned));
    const shown = showAll ? list : list.slice(0, PREVIEW_COUNT);
    const TYPE_LABELS = { progression: 'Progression', win_condition: 'Beats the game', missable: 'Missable' };
    // RetroAchievements gives times in UTC
    const earnedDate = (text) => new Date(text.replace(' ', 'T') + 'Z');
    const summary = data.user ? `${data.earned} of ${data.total} · ${Math.round(data.completion)}%` : `${data.total} to earn`;

    return section(summary, (
        <>
            <div className="gd-row" style={{alignItems: 'baseline'}}>
                {data.user ? (
                    <>
                        <span className="gd-big">{Math.round(data.completion)}%</span>
                        <span>
                            <b>{data.earned}</b> of {data.total} earned · {data.points_earned} of {data.points} points
                            {data.earned_hardcore > 0 && ` · ${data.earned_hardcore} in hardcore`}
                        </span>
                    </>
                ) : (
                    <span>{data.total} achievements · {data.points} points</span>
                )}
                <span style={{flex: 1}} />
                <a href={data.url} target="_blank" rel="noopener noreferrer" className="gd-small">{data.title} on RetroAchievements ↗</a>
                <button className="gd-btn small" disabled={loading} onClick={() => load(true)} title="Fetch the latest from RetroAchievements">{loading ? 'Refreshing...' : 'Refresh'}</button>
            </div>
            {data.user ? (
                <div className="gd-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(data.completion)} aria-label="Achievements earned">
                    <div style={{width: `${data.completion}%`, background: data.earned === data.total ? 'var(--success)' : 'var(--accent-orange)'}} />
                </div>
            ) : <div className="gd-note">Add your RetroAchievements user name in Tools › Settings to show which ones have been earned.</div>}
            {data.user && (
                <div className="gd-row gd-small" style={{margin: '10px 0'}}>
                    <span className="gd-note">Earned by {(data.people || []).length > 1 ? (
                        <select value={who || data.people[0]} onChange={e => setWho(e.target.value)} aria-label="Whose achievements">
                            {data.people.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                    ) : data.user}</span>
                    {[['all', `All ${data.total}`], ['earned', `Earned ${data.earned}`], ['locked', `Not yet ${data.total - data.earned}`]].map(([key, label]) => (
                        <button key={key} className={`gd-btn small${filter === key ? ' primary' : ''}`} onClick={() => { setFilter(key); setShowAll(false); }}>{label}</button>
                    ))}
                </div>
            )}
            {!list.length && <div className="gd-note">{filter === 'earned' ? 'None earned yet.' : 'Every achievement is earned.'}</div>}
            <div className="gd-cheevos">
                {shown.map(a => (
                    <div key={a.id} className={`gd-cheevo${a.earned ? ' earned' : ''}${a.earned || !data.user ? '' : ' locked'}`}>
                        <img src={a.earned || !data.user ? a.badge : a.badge_locked} alt="" loading="lazy" width="44" height="44" onError={e => { e.target.style.visibility = 'hidden'; }} />
                        <div style={{flex: 1, minWidth: 0}}>
                            <div className="gd-cheevo-title">
                                {a.earned && <span className="gd-ok" aria-label="Earned">✓ </span>}
                                {a.title} <span className="gd-note">({a.points})</span>
                            </div>
                            <div className="gd-note">{a.description}</div>
                            <div className={`gd-tiny${a.earned ? ' gd-ok' : ' gd-note'}`}>
                                {a.earned && <span title={earnedDate(a.earned).toLocaleString()}>Earned {gdAgo(earnedDate(a.earned).getTime())}{a.hardcore ? ' · hardcore' : ''}</span>}
                                {a.earned && TYPE_LABELS[a.type] && ' · '}
                                {TYPE_LABELS[a.type]}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
            {list.length > PREVIEW_COUNT && (
                <button className="gd-btn small" style={{marginTop: 8}} onClick={() => setShowAll(v => !v)}>
                    {showAll ? 'Show fewer' : `Show all ${list.length}`}
                </button>
            )}
        </>
    ));
}

// Saves and save states found for the game, by person
function GDSaves({ system, game }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [expanded, setExpanded] = React.useState({});
    const PREVIEW_COUNT = 5;

    React.useEffect(() => {
        let cancelled = false;
        setData(null);
        setError(null);
        setExpanded({});
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/saves?${new URLSearchParams({ rom: game.path })}`)
            .then(r => r.json())
            .then(d => { if (!cancelled) d.success ? setData(d) : setError(d.error || 'Could not load saves'); })
            .catch(err => { if (!cancelled) setError(err.message); });
        return () => { cancelled = true; };
    }, [system, game.path]);

    const section = (summary, content) => <GDSection id="saves" title="Saves" summary={summary}>{content}</GDSection>;
    if (error) return section('Couldn\'t load', <div className="gd-note gd-error">{error}</div>);
    if (!data) return section('Looking…', <div className="gd-note">Looking for saves...</div>);
    if (!Object.values(data.available || {}).some(Boolean)) {
        return section('Not set up', <div className="gd-note">The saves folders aren't mounted. Add them to docker-compose.yml (see the README).</div>);
    }

    // Each person in the configured order, then the shared in-game saves,
    // then older states that sit outside anyone's folder (collapsed)
    const groupOf = (s) => s.profile !== 'shared' ? s.profile : s.root === 'saves' ? 'shared-saves' : 'shared-states';
    const GROUP_LABELS = { 'shared-saves': 'In-game saves (shared)', 'shared-states': "Old save states, not in a person's folder" };
    const groups = [...data.profiles, 'shared-saves', 'shared-states']
        .map(profile => ({ profile, items: data.saves.filter(s => groupOf(s) === profile) }))
        .filter(g => g.items.length);
    if (!groups.length) return section('None', <div className="gd-note">No saves or save states for this game.</div>);

    const shot = (s) => `${GD_API}/api/save-screenshot/${s.root}/${gdEncode(s.screenshot)}`;
    const row = (s) => (
        <div key={`${s.root}/${s.path}`} className="gd-save">
            {s.screenshot
                ? <a className="gd-save-shot" href={shot(s)} target="_blank" rel="noopener noreferrer" title="Open the screenshot"><img src={shot(s)} alt="" loading="lazy" /></a>
                : <span className="gd-save-shot" aria-hidden="true">{s.kind === 'save' ? '💾' : '⏸'}</span>}
            <div style={{flex: 1, minWidth: 0}}>
                <div className="gd-cheevo-title">
                    {s.label}
                    {s.empty && <span className="gd-badge" title="The file is there but nothing was ever saved in it: the game starts with no save">Empty</span>}
                    {s.conflict && <span className="gd-badge" title="Syncthing kept two versions of this file">Sync conflict</span>}
                </div>
                <div className="gd-note gd-clip" title={`${s.root}/${s.path}`}>{s.root}/{s.path}</div>
            </div>
            <div className="gd-small" style={{textAlign: 'right', flexShrink: 0}}>
                <div title={new Date(s.modified).toLocaleString()}>{gdAgo(new Date(s.modified).getTime())}</div>
                <div className="gd-note">{gdBytes(s.size)}</div>
            </div>
        </div>
    );
    const newestOverall = Math.max(...data.saves.map(s => new Date(s.modified).getTime()));

    return section(`${data.saves.length} file${data.saves.length === 1 ? '' : 's'} · latest ${gdAgo(newestOverall)}`, (
        <>
            <div className="gd-row gd-small">
                <span className="gd-note" style={{flex: 1, minWidth: 200}}>
                    Found by file name in the saves and savestates folders.
                    {data.saves.some(s => s.conflict) && ' Resolve sync conflicts in Tools › Saves.'}
                </span>
                <a className="gd-btn small" href={`${GD_API}/api/systems/${encodeURIComponent(system)}/saves/download?${new URLSearchParams({ rom: game.path })}`}>Download all (zip)</a>
            </div>
            {groups.map(({ profile, items }) => {
                const open = expanded[profile] ?? profile !== 'shared-states';
                const showAll = expanded[`${profile}:all`];
                const shown = showAll ? items : items.slice(0, PREVIEW_COUNT);
                return (
                    <div key={profile} style={{marginTop: 10}}>
                        <button className="gd-group-head" onClick={() => setExpanded(prev => ({ ...prev, [profile]: !open }))} aria-expanded={open}>
                            <span className="gd-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
                            {GROUP_LABELS[profile] || profile[0].toUpperCase() + profile.slice(1)}
                            <span className="gd-note">{items.length} file{items.length > 1 ? 's' : ''} · latest {gdAgo(new Date(items[0].modified).getTime())}</span>
                        </button>
                        {open && (
                            <div className="gd-saves">
                                {shown.map(row)}
                                {items.length > PREVIEW_COUNT && (
                                    <button className="gd-btn small" style={{alignSelf: 'flex-start'}} onClick={() => setExpanded(prev => ({ ...prev, [`${profile}:all`]: !showAll }))}>
                                        {showAll ? 'Show fewer' : `Show all ${items.length}`}
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </>
    ));
}

// The game's manual (a PDF), read in place over the page
function GDManual({ name, url, onClose }) {
    React.useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [onClose]);
    return ReactDOM.createPortal(
        <div className="gd-manual" role="dialog" aria-modal="true" aria-label={`${name} manual`}>
            <div className="gd-manual-bar">
                <b>{name}: manual</b>
                <a className="gd-btn small" href={url} target="_blank" rel="noopener noreferrer">Open in a new tab ↗</a>
                <button className="gd-btn small primary" onClick={onClose} autoFocus>Close</button>
            </div>
            <iframe src={url} title={`${name} manual`} />
        </div>,
        document.body
    );
}

// The ROM file: what the ROM check (Tools > ROM check) found, and its checksums.
// Folded like the others; rarely needed, so nothing is fetched until it's opened.
const GD_ROM_STATUS = {
    verified: ['Verified', 'var(--success, #3ccf91)', 'Listed in a ROM database as a known good dump'],
    known: ['Recognised', 'var(--accent-blue)', 'Recognised, but not listed as a verified dump'],
    hack: ['Hack', 'var(--accent-pink)', 'A ROM hack RetroAchievements lists'],
    unknown: ['Not recognised', 'var(--accent-orange)', 'No database knows this file: a hack, a patched or trimmed ROM, or a bad dump'],
    skipped: ['Not checked', 'var(--text-secondary)', 'A folder, a disc list, or a file too large to hash'],
};
const GD_ROM_SOURCES = { NoIntros: 'No-Intro', NoIntro: 'No-Intro', MAMEArcade: 'MAME', MAMEMess: 'MAME' };
function GDRomFile({ system, game }) {
    const [info, setInfo] = React.useState(null);
    const [copied, setCopied] = React.useState(null);
    // The game's files one by one, for a game the ROM check has no checksums
    // for (a disc game is a .cue and its tracks, which it doesn't hash)
    const [files, setFiles] = React.useState(null);
    const [hashing, setHashing] = React.useState(false);
    const loadFiles = React.useCallback((workOut) => {
        if (workOut) setHashing(true);
        return fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/rom-files?${new URLSearchParams({ rom: game.path, ...(workOut ? { hash: '1' } : {}) })}`).then(r => r.json())
            .then(d => { if (d.success) setFiles(d.files); }).catch(() => {}).finally(() => { if (workOut) setHashing(false); });
    }, [system, game.path]);
    React.useEffect(() => {
        let cancelled = false;
        setInfo(null);
        setFiles(null);
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/rom-info?${new URLSearchParams({ rom: game.path })}`).then(r => r.json())
            .then(d => { if (cancelled) return; const got = d.success ? d : { checked: false }; setInfo(got); if (!got.sha1) loadFiles(false); })
            .catch(() => { if (!cancelled) { setInfo({ checked: false }); loadFiles(false); } });
        return () => { cancelled = true; };
    }, [system, game.path]);
    const copy = (label, value) => {
        const done = () => { setCopied(label); setTimeout(() => setCopied(c => (c === label ? null : c)), 1500); };
        try { navigator.clipboard.writeText(value).then(done, () => {}); } catch (e) {}
    };
    const file = String(game.path).replace(/^(\.\/)+/, '');
    if (!info) return <div className="gd-note">Looking...</div>;
    const status = info.checked ? (GD_ROM_STATUS[info.status] || GD_ROM_STATUS.unknown) : null;
    const sources = (info.sources || []).map(s => GD_ROM_SOURCES[s] || s).join(', ');
    const sums = [['SHA-1', info.sha1], ['MD5', info.md5], ['CRC32', info.crc32]].filter(s => s[1]);
    return (
        <div className="gd-romfile">
            <dl className="gd-facts">
                <dt>File</dt><dd className="gd-mono">{file}</dd>
                {info.size > 0 && <><dt>Size</dt><dd>{gdBytes(info.size)}</dd></>}
                {status && <><dt>ROM check</dt><dd>
                    <span title={status[2]} style={{color: status[1]}}>{status[0]}</span>
                    {sources && <span className="gd-note"> · listed by {sources}</span>}
                    {info.known_name && <span className="gd-note"> as {info.known_name}</span>}
                    {info.reason && <span className="gd-note"> · {info.reason}</span>}
                </dd></>}
                {sums.map(([label, value]) => (
                    <React.Fragment key={label}>
                        <dt>{label}</dt>
                        <dd className="gd-mono">{value} <button className="gd-linkbutton" onClick={() => copy(label, value)}>{copied === label ? 'Copied' : 'Copy'}</button></dd>
                    </React.Fragment>
                ))}
            </dl>
            {!sums.length && files && files.length > 0 && (
                <div className="gd-romfiles">
                    {files.map(f => (
                        <div key={f.name} className="gd-romfiles-file">
                            <div><span className="gd-mono">{f.name}</span> <span className="gd-note">{gdBytes(f.size)}</span></div>
                            {f.sha1 && (
                                <dl className="gd-facts">
                                    {[['SHA-1', f.sha1], ['MD5', f.md5], ['CRC32', f.crc32]].map(([label, value]) => (
                                        <React.Fragment key={label}>
                                            <dt>{label}</dt>
                                            <dd className="gd-mono">{value} <button className="gd-linkbutton" onClick={() => copy(`${f.name}:${label}`, value)}>{copied === `${f.name}:${label}` ? 'Copied' : 'Copy'}</button></dd>
                                        </React.Fragment>
                                    ))}
                                </dl>
                            )}
                        </div>
                    ))}
                    {files.some(f => !f.sha1) && (
                        <div className="gd-row" style={{marginTop: 8}}>
                            <button className="gd-btn small" disabled={hashing} onClick={() => loadFiles(true)}>{hashing ? 'Working them out...' : 'Work out the checksums'}</button>
                            <span className="gd-note">{hashing ? 'Each file is read whole: a disc takes a while.' : `${gdBytes(files.filter(f => !f.sha1).reduce((n, f) => n + f.size, 0))} to read. They're kept once worked out.`}</span>
                        </div>
                    )}
                </div>
            )}
            {!sums.length && files && !files.length && <div className="gd-note" style={{marginTop: 6}}>No checksums: this game is a folder, not a file.</div>}
        </div>
    );
}

// --- Series: the other games in this one's series, and which of them you have ---
// (backend/series_index.py; the lists come from IGDB)
const gdCover = (imageId) => imageId ? `https://images.igdb.com/igdb/image/upload/t_cover_small/${imageId}.jpg` : null;
const gdPut = (url, body) => fetch(`${GD_API}${url}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
// A library game's page, on whichever of the Library and the Console you're on
const gdGameUrl = (have) => `${window.location.pathname.startsWith('/console') ? '/console' : '/'}?${new URLSearchParams({ system: have.system, game: have.path })}`;

// A series' games in release order. The ones you have are solid and link to
// your copy; the rest are faint, each with Want and Not interested.
//   view     the series, as /api/series/game gives it
//   reload   fetch it again (after a mark changes)
//   here     { system, path } of the game this is shown for, which is outlined
function GDSeriesGames({ view, reload, here, notify }) {
    const [show, setShow] = React.useState('all');   // all | missing | want
    const [showHidden, setShowHidden] = React.useState(false);
    const act = async (url, body) => {
        try {
            const d = await gdPut(url, body);
            if (!d.success && notify) notify(d.error || 'That didn\'t work', 'error');
        } catch (e) { if (notify) notify(e.message, 'error'); }
        reload();
    };
    const mark = (game, value) => act('/api/series/mark', { id: game.id, mark: game.mark === value ? null : value });
    const isHidden = (g) => g.mark === 'skip' || g.platform_skipped;
    const missing = view.games.filter(g => !g.have.length);
    const hidden = missing.filter(isHidden);
    const wanted = missing.filter(g => g.mark === 'want');
    const shown = view.games.filter(g => (show === 'all' || !g.have.length) && (show !== 'want' || g.mark === 'want') && (showHidden || !isHidden(g)));
    // Platforms among the games you're missing, to hide one in a go (arcade, mobile...)
    const platforms = {};
    missing.filter(g => !g.platform_skipped).forEach(g => g.platforms.forEach(p => { platforms[p] = (platforms[p] || 0) + 1; }));
    const isHere = (g) => here && g.have.some(h => h.system === here.system && h.path === String(here.path).replace(/^(\.\/)+/, ''));
    const year = (g) => g.date ? new Date(g.date * 1000).getUTCFullYear() : null;
    return (
        <div className="gd-series">
            <div className="gd-row gd-small">
                {[['all', `All ${view.total}`], ['missing', `Missing ${view.total - view.have}`], ['want', `Want ${wanted.length}`]].map(([key, label]) => (
                    <button key={key} className={`gd-btn small${show === key ? ' primary' : ''}`} onClick={() => setShow(key)}>{label}</button>
                ))}
                {Object.keys(platforms).length > 1 && (
                    <select value="" aria-label="Hide a platform's games in this series" onChange={e => { if (e.target.value) act('/api/series/platform', { series: view.key, platform: e.target.value, skip: true }); }}>
                        <option value="">Hide a platform…</option>
                        {Object.entries(platforms).sort((a, b) => b[1] - a[1]).map(([p, n]) => <option key={p} value={p}>{p} ({n})</option>)}
                    </select>
                )}
                {view.skipped_platforms.map(p => (
                    <button key={p} className="gd-chip on" title="Show this platform's games again" onClick={() => act('/api/series/platform', { series: view.key, platform: p, skip: false })}>{p} hidden ×</button>
                ))}
                {hidden.length > 0 && (
                    <label className="gd-note" style={{display: 'inline-flex', gap: 5, alignItems: 'center', cursor: 'pointer'}}>
                        <input type="checkbox" checked={showHidden} onChange={e => setShowHidden(e.target.checked)} /> Show the {hidden.length} not wanted
                    </label>
                )}
            </div>
            {!shown.length && <div className="gd-note">{show === 'want' ? 'Nothing on the want list from this series yet.' : 'Nothing to show.'}</div>}
            <div className="gd-series-grid">
                {shown.map(g => {
                    const have = g.have[0];
                    return (
                        <div key={g.id} className={`gd-series-game${have ? ' have' : ''}${isHidden(g) ? ' hidden' : ''}${g.mark === 'want' ? ' want' : ''}${isHere(g) ? ' here' : ''}`}>
                            {gdCover(g.cover) ? <img src={gdCover(g.cover)} alt="" loading="lazy" onError={e => { e.target.style.visibility = 'hidden'; }} /> : <span className="gd-series-nocover" aria-hidden="true">🎮</span>}
                            <div className="gd-series-text">
                                {have
                                    ? <a className="gd-series-name" href={gdGameUrl(have)} title={g.have.length > 1 ? `You have ${g.have.length} copies` : 'Open your copy'}>{g.name}</a>
                                    : <span className="gd-series-name">{g.name}</span>}
                                <span className="gd-note">{[year(g), g.type, g.platforms.slice(0, 4).join(' / ') + (g.platforms.length > 4 ? ' …' : '')].filter(Boolean).join(' · ')}</span>
                                {have ? <span className="gd-tiny gd-ok">{isHere(g) ? 'This game' : `In your library${g.have.length > 1 ? ` ×${g.have.length}` : ''}`}</span> : (
                                    <span className="gd-series-marks">
                                        {g.platform_skipped ? <span className="gd-tiny gd-note">Platform hidden</span> : <>
                                            <button className={`gd-chip${g.mark === 'want' ? ' on gd-fav' : ''}`} aria-pressed={g.mark === 'want'} onClick={() => mark(g, 'want')}>{g.mark === 'want' ? '★ Wanted' : '☆ Want'}</button>
                                            <button className={`gd-chip${g.mark === 'skip' ? ' on' : ''}`} aria-pressed={g.mark === 'skip'} onClick={() => mark(g, 'skip')}
                                                title={g.mark === 'skip' ? 'Put it back in the list' : 'Not interested: hide it and leave it out of the count'}>{g.mark === 'skip' ? 'Restore' : '✕'}</button>
                                        </>}
                                    </span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// Search IGDB for the game a library game is, and pick it (onDone runs after)
function GDSeriesPicker({ system, game, onDone, notify }) {
    const [query, setQuery] = React.useState(gdTitle(game.name));
    const [candidates, setCandidates] = React.useState(null);
    const search = React.useCallback(async (text) => {
        setCandidates(null);
        try {
            const d = await (await fetch(`${GD_API}/api/series/candidates?${new URLSearchParams({ system, rom: game.path, ...(text ? { q: text } : {}) })}`)).json();
            setCandidates(d.success ? d.candidates : []);
        } catch (e) { setCandidates([]); }
    }, [system, game.path]);
    React.useEffect(() => { search(''); }, [search]);
    const choose = async (id) => {
        const d = await gdPut('/api/series/match', { system, rom_path: game.path, id }).catch(e => ({ success: false, error: e.message }));
        if (!d.success && notify) notify(d.error || 'That didn\'t work', 'error');
        if (onDone) onDone();
    };
    return (
        <div className="gd-series-candidates">
            <div className="gd-row">
                <input type="search" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') search(query); }} aria-label="Search IGDB" />
                <button className="gd-btn small" onClick={() => search(query)}>Search</button>
            </div>
            {!candidates && <div className="gd-note">Searching IGDB...</div>}
            {candidates && !candidates.length && <div className="gd-note">Nothing found. Try a shorter name.</div>}
            {(candidates || []).map(c => (
                <button key={c.id} className="gd-series-candidate" onClick={() => choose(c.id)}>
                    <b>{c.name}</b> <span className="gd-note">{[c.year, c.series || 'no series'].filter(Boolean).join(' · ')}</span>
                </button>
            ))}
        </div>
    );
}

// The Series row of the panel. Nothing without IGDB keys (Tools > Settings).
function GDSeries({ system, game, notify }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [fixing, setFixing] = React.useState(false);
    const [query, setQuery] = React.useState('');
    const [candidates, setCandidates] = React.useState(null);
    const load = React.useCallback(() => {
        let cancelled = false;
        fetch(`${GD_API}/api/series/game?${new URLSearchParams({ system, rom: game.path })}`).then(r => r.json())
            .then(d => { if (!cancelled) d.success ? (setData(d), setError(null)) : setError(d.error || 'Could not load the series'); })
            .catch(e => { if (!cancelled) setError(e.message); });
        return () => { cancelled = true; };
    }, [system, game.path]);
    React.useEffect(() => { setData(null); setError(null); setFixing(false); setCandidates(null); return load(); }, [load]);

    if (error && !data) return <GDSection id="series" title="Series" summary="Couldn't load"><div className="gd-note gd-error">{error}</div></GDSection>;
    if (!data || !data.configured) return null;

    const search = async (text) => {
        setCandidates(null);
        try {
            const d = await (await fetch(`${GD_API}/api/series/candidates?${new URLSearchParams({ system, rom: game.path, ...(text ? { q: text } : {}) })}`)).json();
            setCandidates(d.success ? d.candidates : []);
        } catch (e) { setCandidates([]); }
    };
    const choose = async (id) => {
        const d = await gdPut('/api/series/match', { system, rom_path: game.path, id }).catch(e => ({ success: false, error: e.message }));
        if (!d.success && notify) notify(d.error || 'That didn\'t work', 'error');
        setFixing(false);
        setData(null);
        load();
    };
    const series = data.series;
    const matched = data.match && data.match.id;
    const fix = (
        <div className="gd-series-fix">
            <span className="gd-note">
                {matched ? <>Matched to <b>{data.match.name}</b> on IGDB{data.match.how === 'loose' ? ' (a near match)' : data.match.how === 'manual' ? ' (chosen by you)' : ''}.</> : "IGDB didn't have a game by this name."}
                {' '}<button className="gd-linkbutton" onClick={() => { setFixing(f => !f); if (!fixing) { setQuery(gdTitle(game.name)); search(''); } }}>{fixing ? 'Cancel' : matched ? 'Wrong game?' : 'Find it'}</button>
            </span>
            {fixing && (
                <div className="gd-series-candidates">
                    <div className="gd-row">
                        <input type="search" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') search(query); }} aria-label="Search IGDB" />
                        <button className="gd-btn small" onClick={() => search(query)}>Search</button>
                        {data.match && data.match.how === 'manual' && <button className="gd-btn small" onClick={() => choose(null)}>Match it automatically again</button>}
                    </div>
                    {!candidates && <div className="gd-note">Searching IGDB...</div>}
                    {candidates && !candidates.length && <div className="gd-note">Nothing found.</div>}
                    {(candidates || []).map(c => (
                        <button key={c.id} className="gd-series-candidate" onClick={() => choose(c.id)}>
                            <b>{c.name}</b> <span className="gd-note">{[c.year, c.series || 'no series'].filter(Boolean).join(' · ')}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
    if (!series) return <GDSection id="series" title="Series" summary={matched ? 'Not in one' : 'Not found'}>{fix}</GDSection>;
    return (
        <GDSection id="series" title={series.kind === 'franchise' ? `${series.name} games` : `${series.name} series`} summary={`${series.have} of ${series.total}`}>
            <GDSeriesGames view={series} reload={load} here={{ system, path: game.path }} notify={notify} />
            {fix}
        </GDSection>
    );
}

// The panel. Give it the game itself (`game`, as the Library has it), or
// `system` and `path` and it fetches the game, showing `seed` (whatever the
// page already knows: name, desc, pictures...) until that arrives.
//   system       the system's folder name
//   systemLabel  its full name, shown under the title
//   actions      extra buttons for the top right (className "gd-btn")
//   notify       (message, 'error' | 'success') for things that go wrong
// An admin can change the game here (src/common/game-details-edit.jsx): ✏ makes
// the text editable in place and becomes Save, 🗑 removes the game, and the
// Media section takes new files.
//   onSaved      (rom path, the fields that changed) after a save or an upload,
//                for the page to refresh what it holds
//   onDeleted    (rom path) after the game is removed
//   editState    a ref kept at {dirty, save}, for a page that asks before
//                leaving unsaved edits
//   Scraper      the Library's scrape popup; without it Scrape opens the game
//                in the Library
function GameDetails({ system, systemLabel, game, path, seed, actions, notify, onChanged, onSaved, onDeleted, editState, Scraper }) {
    gdUsePhone();   // (in the phone app: redrawn when the connection or the phone's games change)
    const [pinning, setPinning] = React.useState(false);
    // In the phone app: the "more" menu beside Play
    const [moreOpen, setMoreOpen] = React.useState(false);
    const moreRef = React.useRef(null);
    React.useEffect(() => {
        if (!moreOpen) return undefined;
        const away = (e) => { if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false); };
        const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); setMoreOpen(false); } };
        document.addEventListener('pointerdown', away);
        document.addEventListener('keydown', esc, true);
        return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc, true); };
    }, [moreOpen]);
    const [fetched, setFetched] = React.useState(null);
    const [reload, setReload] = React.useState(0);
    // What was just saved or added here, shown until the page's own copy has it
    const [override, setOverride] = React.useState(null);
    // The fields being edited; null when not editing
    const [draft, setDraft] = React.useState(null);
    const [saving, setSaving] = React.useState(false);
    const [deleting, setDeleting] = React.useState(false);
    const [scraping, setScraping] = React.useState(false);
    const [picturePref, setPicturePref] = useGdPicture();
    const [manualOpen, setManualOpen] = React.useState(false);
    // Without the page's own way of saying what happened, it's said in the panel
    const [problem, setProblem] = React.useState(null);
    React.useEffect(() => {
        if (!problem) return;
        const timer = setTimeout(() => setProblem(null), 6000);
        return () => clearTimeout(timer);
    }, [problem]);
    const report = notify || ((message, kind) => setProblem({ message, kind }));
    const wanted = game ? null : `${system}/${path}`;
    React.useEffect(() => {
        if (!wanted) return;
        let cancelled = false;
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/games/${gdEncode(path)}`).then(r => r.json())
            .then(d => { if (!cancelled && d.success) setFetched({ key: wanted, game: d.game }); })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [wanted, reload]);

    const key = `${system}/${game ? game.path : path}`;
    const base = game || (fetched && fetched.key === wanted ? fetched.game : null);
    const full = base && override && override.key === key ? { ...base, ...override.fields } : base;
    const shown = full || seed;
    // Another game: nothing of the last one's editing carries over
    React.useEffect(() => { setDraft(null); setOverride(null); setDeleting(false); setScraping(false); }, [key]);
    // The page's copy is fresh again
    React.useEffect(() => { setOverride(null); }, [game, fetched]);
    const keep = (fields) => setOverride(o => ({ key, fields: { ...(o && o.key === key ? o.fields : {}), ...fields } }));

    const dirty = !!(draft && full && GD_EDIT_FIELDS.some(f => !gdSame(draft[f], full[f])));
    const setField = (field, value) => setDraft(d => ({ ...d, [field]: value }));
    const startEdit = () => { if (full && !draft) setDraft(Object.fromEntries(GD_EDIT_FIELDS.map(f => [f, full[f]]))); };
    const save = async () => {
        if (!draft || !full) return true;
        if (!String(draft.name || '').trim()) { report('The game needs a name', 'error'); return false; }
        setSaving(true);
        const result = await gdSaveGame(system, { ...full, ...draft });
        setSaving(false);
        if (!result.ok) { report(result.error, 'error'); return false; }
        const fields = { ...Object.fromEntries(GD_EDIT_FIELDS.map(f => [f, result.game[f]])), has_metadata: true };
        keep(fields);
        setDraft(null);
        setReload(n => n + 1);
        report('Game saved', 'success');
        if (onSaved) await onSaved(full.path, fields);
        return true;
    };
    // A file added in the Media section, or a PC game's launch file changed: already saved
    const changed = (fields, newPath) => {
        keep(fields);
        setReload(n => n + 1);
        if (onSaved) onSaved(newPath || full.path, fields);
    };
    // What a scrape found goes into the fields, for you to save; media it downloaded is already there
    const applyScrape = (merged) => {
        const media = Object.fromEntries(GD_MEDIA.map(m => m[0]).filter(f => typeof merged[f] === 'string' && merged[f] !== full[f]).map(f => [f, merged[f]]));
        if (Object.keys(media).length) keep(media);
        const filled = gdAutoFill({ ...full, ...media, ...Object.fromEntries(GD_EDIT_FIELDS.map(f => [f, merged[f]])) }).game;
        setDraft(Object.fromEntries(GD_EDIT_FIELDS.map(f => [f, filled[f]])));
        report('Filled in from the scrape. Save to write it.', 'success');
    };
    // The page can ask before leaving unsaved edits, and save them
    React.useEffect(() => {
        gdUnsaved.dirty = dirty;
        if (editState) editState.current = { dirty, save };
        return () => { gdUnsaved.dirty = false; if (editState) editState.current = { dirty: false }; };
    });
    // E in the game list edits the open game
    const startEditRef = React.useRef(startEdit);
    startEditRef.current = startEdit;
    React.useEffect(() => {
        const edit = () => { if (!gdIsPlayer()) startEditRef.current(); };
        window.addEventListener('retromanager:edit-game', edit);
        return () => window.removeEventListener('retromanager:edit-game', edit);
    }, []);
    // Scrape, pressed on another page, opened the game here
    React.useEffect(() => {
        const want = window.gdScrapeOnOpen;
        if (Scraper && full && want && want.system === system && gdEncode(want.path) === gdEncode(full.path)) {
            window.gdScrapeOnOpen = null;
            setScraping(true);
        }
    }, [key, !!full]);
    if (!shown) return <div className="gd"><div className="gd-note">Loading...</div></div>;

    const field = gdPictureField(shown, picturePref);
    const stars = typeof shown.rating === 'number' ? Math.min(Math.max(shown.rating, 0), 1) * 5 : null;
    const facts = [['Developer', shown.developer], ['Publisher', shown.publisher], ['Released', gdReleased(shown)], ['Genre', shown.genre], ['Players', shown.players]].filter(f => f[1]);
    const romPath = full ? full.path : path;
    // The page's picture versions (as the Bookcase has them), so a preloaded picture is the one shown
    const versions = (seed && seed.v) || {};

    return (
        <div className="gd">
            <div className="gd-inner">
                <div className="gd-head">
                    {/* The game's logo beside its name */}
                    {!draft && shown.wheel && (
                        <img className="gd-head-logo" src={gdThumb(shown.wheel, 160, versions.wheel)} alt="" draggable={false} onError={e => { e.target.style.display = 'none'; }} />
                    )}
                    <div className="gd-heading">
                        {draft
                            ? <input className="gd-input gd-title-input" type="text" value={draft.name || ''} onChange={e => setField('name', e.target.value)} aria-label="Name" autoFocus />
                            : <h2 className="gd-title">{gdTitle(shown.name || shown.title)}</h2>}
                        <div className="gd-sub">
                            {systemLabel || system}
                            {full && full.has_metadata === false && <span className="gd-badge">Missing metadata</span>}
                        </div>
                    </div>
                    <div className={`gd-actions${gdPhone ? ' gd-actions-app' : ''}`}>
                        {!draft && gdCanPlay(shown, system) && romPath && <a className="gd-btn primary" href={gdPlayUrl(system, romPath)} onClick={gdPlayClick(system, romPath)} title={!gdPhone ? "Play this game in the browser" : gdNeedsEmulator(system) ? "Nothing on this phone plays this yet: press to see what's needed" : gdHere(system, romPath) ? "Play this game on the phone" : "Fetch this game to the phone, then play it"}>{gdNeedsEmulator(system) ? '⚠ Needs an emulator' : gdPhone && !gdHere(system, romPath) ? '⬇ Fetch and play' : '▶ Play'}</a>}
                        {!draft && gdPhone && romPath && shown.phone_playable && !gdCanPlay(shown, system) && <span className="gd-badge" title="RetroManager can't be reached, and this game isn't on the phone">Not on this phone</span>}
                        {/* In the phone app: fetches the game to the phone without starting it */}
                        {!draft && gdPhone && gdPhone.fetch && romPath && shown.phone_playable && !gdHere(system, romPath) && !gdPhoneState().offline && (
                            <button className="gd-btn" title="Fetch this game to the phone, to play later (with no connection, if need be)"
                                onClick={() => gdPhone.fetch(system, romPath, gdTitle(shown.name || shown.title))}>⬇ Fetch</button>
                        )}
                        {pinning && <GdPinPicture game={shown} onClose={() => setPinning(false)}
                            onPick={(picture) => { setPinning(false); gdPhone.pin(system, romPath, gdTitle(shown.name || shown.title), picture); }} />}
                        {/* In the phone app: Edit beside Play, and the rest in one menu at the right */}
                        {gdPhone && !draft && full && (
                            <button className="gd-btn admin-only gd-edit-button" onClick={startEdit} title="Edit this game’s details" aria-label="Edit details">{gdIcon('pencil')}Edit</button>
                        )}
                        {gdPhone && !draft && (
                            <div className="gd-menu-wrap" ref={moreRef}>
                                <button className="gd-btn gd-more-button" onClick={() => setMoreOpen(o => !o)} aria-haspopup="menu" aria-expanded={moreOpen} aria-label="More for this game" title="More for this game">⋯</button>
                                {moreOpen && (
                                    <div className="gd-more" role="menu" onClick={() => setMoreOpen(false)}>
                                        {gdPhone.pin && romPath && shown.phone_playable && (
                                            <button role="menuitem" onClick={() => {
                                                // With more than one picture to make the icon from, which is asked
                                                const pictures = gdPinPictures(shown);
                                                if (pictures.length > 1) setPinning(true);
                                                else gdPhone.pin(system, romPath, gdTitle(shown.name || shown.title), pictures.length ? pictures[0][2] : '');
                                            }}>{gdIcon('home')}Add to home screen</button>
                                        )}
                                        {gdPhone.chooseEmulator && romPath && shown.phone_playable && (
                                            <button role="menuitem" onClick={() => gdPhone.chooseEmulator(system, romPath, gdTitle(shown.name || shown.title))}>{gdIcon('sliders')}Choose emulator</button>
                                        )}
                                        {shown.manuals && <button role="menuitem" onClick={() => setManualOpen(true)}>{gdIcon('book')}Manual</button>}
                                        {gdPhone.removeLocal && romPath && gdHere(system, romPath) && (
                                            <button role="menuitem" onClick={() => gdPhone.removeLocal(system, romPath, gdTitle(shown.name || shown.title))}>{gdIcon('phone')}Remove from phone</button>
                                        )}
                                        {/* The library's own, for an admin, apart from the phone's */}
                                        {full && <hr className="admin-only" />}
                                        {full && <button role="menuitem" className="admin-only danger" onClick={() => setDeleting(true)}>{gdIcon('bin')}Delete from library</button>}
                                    </div>
                                )}
                            </div>
                        )}
                        {!gdPhone && !draft && shown.manuals && <button className="gd-btn" onClick={() => setManualOpen(true)}>📖 Manual</button>}
                        {!draft && actions}
                        {/* Edit and delete, which become save and cancel while editing */}
                        {full && (draft ? <>
                            <button className="gd-btn primary" onClick={save} disabled={saving} title={dirty ? 'Write your changes to gamelist.xml' : 'Nothing has changed yet'}>{saving ? 'Saving…' : 'Save'}</button>
                            <button className="gd-btn" onClick={() => setDraft(null)} disabled={saving} title="Leave the game as it was">Cancel</button>
                        </> : !gdPhone && <>
                            <button className="gd-btn gd-icon admin-only" onClick={startEdit} title="Edit this game’s details (E)" aria-label="Edit">✏</button>
                            <button className="gd-btn gd-icon admin-only" onClick={() => setDeleting(true)} title="Remove this game" aria-label="Delete">🗑</button>
                        </>)}
                        {full && (Scraper
                            ? <button className="gd-btn admin-only" onClick={() => setScraping(true)} title="Look this game up and fill in its details">Scrape</button>
                            : !draft && !gdPhone && <a className="gd-btn admin-only" href={`/?${new URLSearchParams({ system, game: full.path, scrape: '1' })}`} title="Look this game up, in the Library">Scrape</a>)}
                    </div>
                </div>
                <div className="gd-body">
                    <div className="gd-art">
                        {field
                            ? <a href={gdMedia(shown[field])} target="_blank" rel="noopener noreferrer" title="Open the full picture"><img key={shown[field]} className="gd-picture" src={gdThumb(shown[field], 480, versions[field])} alt="" draggable={false} /></a>
                            : <div className="gd-no-picture" aria-hidden="true">🎮</div>}
                        {field === 'mix' && shown.mix_generated && <span className="gd-badge" title="This Mix was made by RetroManager from the game’s other media, not scraped">generated</span>}
                        {/* The Mix picture already has the logo in it */}
                        {/* (in the phone app the logo is beside the game's name instead) */}
                        <select className="gd-picture-pick" value={picturePref} onChange={e => { setPicturePref(e.target.value); e.target.blur(); }}
                            aria-label="Picture shown for every game" title="Which picture this panel shows, for every game. A game without it shows another one it has.">
                            {GD_PICTURES.map(([key, label]) => <option key={key} value={key}>Picture: {label}</option>)}
                        </select>
                    </div>
                    <div className="gd-info">
                        {draft && <GDFactsEdit draft={draft} set={setField} />}
                        {draft && <GDRatingEdit value={typeof draft.rating === 'number' ? draft.rating : (draft.rating ? parseFloat(draft.rating) : null)} onChange={v => setField('rating', v)} />}
                        {!draft && facts.length > 0 && (
                            <dl className="gd-facts">
                                {facts.map(([label, value]) => <React.Fragment key={label}><dt>{label}</dt><dd>{value}</dd></React.Fragment>)}
                            </dl>
                        )}
                        {!draft && stars !== null && (
                            <div className="gd-stars" role="img" aria-label={`Rated ${Math.round(stars * 10) / 10} out of 5`}>
                                {[1, 2, 3, 4, 5].map(n => <span key={n}>★<span style={{width: `${Math.min(Math.max(stars - (n - 1), 0), 1) * 100}%`}}>★</span></span>)}
                            </div>
                        )}
                        {full
                            ? <GDStatus system={system} game={full} notify={report} onChanged={onChanged} />
                            // Still fetching the game: the same row, held in place so nothing jumps when it arrives
                            : <div className="gd-status gd-pending" aria-hidden="true">{['☆ Favourite', '⏵ Playing', '🕓 Backlog', '✔ Finished', '📁 Collections ▾'].map(label => <span key={label} className="gd-chip">{label}</span>)}</div>}
                        {problem && <div className={`gd-note ${problem.kind === 'error' ? 'gd-error' : 'gd-ok'}`} role={problem.kind === 'error' ? 'alert' : 'status'}>{problem.message}</div>}
                        {draft
                            ? <textarea className="gd-input gd-desc-input" value={draft.desc || ''} onChange={e => setField('desc', e.target.value)} aria-label="Description" placeholder="Description" />
                            : <p className={`gd-desc${shown.desc ? '' : ' gd-note'}`}>{shown.desc || 'No description yet.'}</p>}
                    </div>
                </div>
                {deleting && full && <GDDelete system={system} game={full} notify={report} onClose={() => setDeleting(false)}
                    onDeleted={() => { setDeleting(false); if (onDeleted) onDeleted(full.path); }} />}
                {Scraper && full && <Scraper isOpen={scraping} onClose={() => setScraping(false)} gameData={draft ? { ...full, ...draft } : full} systemName={system} onApplyMetadata={applyScrape} />}
                {manualOpen && shown.manuals && <GDManual name={gdTitle(shown.name || shown.title)} url={gdMedia(shown.manuals)} onClose={() => setManualOpen(false)} />}
                {!full && (
                    <div className="gd-sections gd-pending" aria-hidden="true">
                        {['Achievements', 'Saves', 'Series'].map(title => (
                            <section key={title} className="gd-section"><div className="gd-section-head"><span className="gd-caret">▸</span><span className="gd-section-title">{title}</span><span className="gd-section-summary">Loading…</span></div></section>
                        ))}
                    </div>
                )}
                {full && (
                    <div className="gd-sections">
                        <GDMedia system={system} game={full} notify={report} onUploaded={fields => changed(fields)} />
                        <GDAchievements system={system} game={full} />
                        <GDSaves system={system} game={full} />
                        <GDSeries system={system} game={full} notify={report} />
                        <GDGamelist system={system} game={full} draft={draft} set={setField} notify={report} onMoved={newPath => changed({}, newPath)} />
                        {full.rom_exists !== false && <GDSection id="romfile" title="ROM file" summary="Checksums"><GDRomFile system={system} game={full} /></GDSection>}
                    </div>
                )}
            </div>
        </div>
    );
}

// In the phone app: the pictures a game's home screen icon can be made from
// ([field, label, media path]), the box first, and the popup that asks which.
const GD_PIN_PICTURES = [['box2d', '2D box'], ['mix', 'Mix'], ['wheel', 'Logo'], ['box3d', '3D box'], ['images', 'Image'], ['screenshot', 'Screenshot'],
    ['screenshottitle', 'Title screen'], ['marquee', 'Marquee'], ['posters', 'Poster'], ['fanart', 'Fan art']];
const gdPinPictures = (game) => GD_PIN_PICTURES.filter(([field]) => game && typeof game[field] === 'string' && game[field]).map(([field, label]) => [field, label, game[field]]);
function GdPinPicture({ game, onPick, onClose }) {
    React.useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
        document.addEventListener('keydown', onKey, true);
        return () => document.removeEventListener('keydown', onKey, true);
    }, [onClose]);
    return (
        <div className="gd-pin" role="dialog" aria-modal="true" aria-label="Picture for the home screen icon" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <div className="gd-pin-box">
                <h3>Which picture for the icon?</h3>
                <div className="gd-pin-pictures">
                    {gdPinPictures(game).map(([field, label, path]) => (
                        <button key={field} onClick={() => onPick(path)}>
                            <img src={gdThumb(path, 320)} alt="" />
                            <span>{label}</span>
                        </button>
                    ))}
                </div>
                <button className="gd-btn" onClick={onClose}>Cancel</button>
            </div>
        </div>
    );
}

// The panel in a popup (Bookcase, Timeline). Closes on Escape, or a press and
// release on the backdrop.
let gdBackdropPress = null;
function GameDetailsPopup({ open, onClose, label, children }) {
    React.useEffect(() => {
        if (!open) return;
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open, onClose]);
    if (!open) return null;
    // Not without asking, when the panel has edits that aren't saved
    const close = () => { if (!gdUnsaved.dirty || window.confirm('Close without saving your changes?')) onClose(); };
    return (
        <div className="gd-backdrop" onMouseDown={e => { gdBackdropPress = e.target; }}
            onClick={e => { const pressedHere = gdBackdropPress === e.currentTarget; gdBackdropPress = null; if (pressedHere && e.target === e.currentTarget) close(); }}>
            <div className="gd-popup" role="dialog" aria-modal="true" aria-label={label}>{children}</div>
        </div>
    );
}
