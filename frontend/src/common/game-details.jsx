// The Game Details panel every page shows for a game: the Library (beside the
// game list and on the Home screen) and, in a popup, the Bookcase and the
// Timeline. Styled by common/game-details.css.
// Loaded before each page's own scripts, which share one global scope with it,
// so everything here is named gd.../GD... except the two components pages use:
// GameDetails and GameDetailsPopup. Its rows are in the files loaded after it:
// game-details-sections.jsx (status, achievements, saves), game-details-series.jsx,
// game-details-edit.jsx (editing) and game-details-rom.jsx (the ROM file).

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

// The game's manual (a PDF), read in place over the page
// A game's picture over the page, as large as fits the screen; a tap, Escape or Back-in-the-app closes it
function GDPicture({ name, url, onClose }) {
    React.useEffect(() => {
        const key = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
        // (Back, a phone's above all, closes it rather than leaving the page)
        let backed = false;
        const back = () => { backed = true; onClose(); };
        window.history.pushState({ gdPicture: true }, '');
        window.addEventListener('popstate', back);
        window.addEventListener('keydown', key, true);
        return () => {
            window.removeEventListener('keydown', key, true);
            window.removeEventListener('popstate', back);
            if (!backed && window.history.state && window.history.state.gdPicture) window.history.back();
        };
    }, []);
    return ReactDOM.createPortal(
        <div className="gd-picture-view" role="dialog" aria-label={`${name}: picture`} onClick={onClose}>
            <img src={url} alt={name} />
            <a className="gd-picture-full" href={url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>Full size ↗</a>
        </div>,
        document.body
    );
}

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
//   onScrape     the Library's Fill the gaps for this game; without it Scrape opens the game
//                in the Library, in Fill the gaps
function GameDetails({ system, systemLabel, game, path, seed, actions, notify, onChanged, onSaved, onDeleted, editState, onScrape }) {
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
    const [picturePref, setPicturePref] = useGdPicture();
    const [manualOpen, setManualOpen] = React.useState(false);
    const [pictureOpen, setPictureOpen] = React.useState(false);
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
    React.useEffect(() => { setDraft(null); setOverride(null); setDeleting(false); }, [key]);
    // The page's copy is fresh again
    React.useEffect(() => { setOverride(null); }, [game, fetched]);
    const keep = (fields) => setOverride(o => ({ key, fields: { ...(o && o.key === key ? o.fields : {}), ...fields } }));

    // (and the ROM's version, which RetroManager keeps itself: backend/rom_versions.py)
    const versioned = !!(full && full.rom_exists !== false);
    const dirty = !!(draft && full && (GD_EDIT_FIELDS.some(f => !gdSame(draft[f], full[f])) || (versioned && !gdSame(draft.rom_version, full.rom_version))));
    const setField = (field, value) => setDraft(d => ({ ...d, [field]: value }));
    const startEdit = () => { if (full && !draft) setDraft({ ...Object.fromEntries(GD_EDIT_FIELDS.map(f => [f, full[f]])), ...(versioned ? { rom_version: full.rom_version || '' } : {}) }); };
    const save = async () => {
        if (!draft || !full) return true;
        if (!String(draft.name || '').trim()) { report('The game needs a name', 'error'); return false; }
        setSaving(true);
        const result = await gdSaveGame(system, { ...full, ...draft });
        if (result.ok && versioned && !gdSame(draft.rom_version, full.rom_version)) {
            try {
                const d = await gdPut(`/api/systems/${encodeURIComponent(system)}/rom-version`, { rom: String(full.path).replace(/^(\.\/)+/, ''), version: draft.rom_version });
                if (!d.success) throw new Error(d.error);
            } catch (e) { report(`Saved, but not the version: ${e.message}`, 'error'); }
        }
        setSaving(false);
        if (!result.ok) { report(result.error, 'error'); return false; }
        const fields = { ...Object.fromEntries(GD_EDIT_FIELDS.map(f => [f, result.game[f]])), ...(versioned ? { rom_version: (draft.rom_version || '').trim() } : {}), has_metadata: true };
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
    if (!shown) return <div className="gd"><div className="gd-note">Loading...</div></div>;

    const field = gdPictureField(shown, picturePref);
    const stars = typeof shown.rating === 'number' ? Math.min(Math.max(shown.rating, 0), 1) * 5 : null;
    const facts = [['Developer', shown.developer], ['Publisher', shown.publisher], ['Released', gdReleased(shown)], ['Genre', shown.genre], ['Players', shown.players], ['Version', shown.rom_version]].filter(f => f[1]);
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
                            <button className="gd-btn admin-only gd-edit-button" onClick={startEdit} title="Edit this game’s details (E)">{gdIcon('pencil')}Edit</button>
                            <button className="gd-btn gd-icon gd-delete-button admin-only" onClick={() => setDeleting(true)} title="Remove this game" aria-label="Delete">{gdIcon('bin')}</button>
                        </>)}
                        {full && !draft && (onScrape
                            ? <button className="gd-btn admin-only" onClick={() => onScrape(full)}
                                title="Every source's pictures and details for this game, beside what it has, to choose from">Scrape</button>
                            : !gdPhone && <a className="gd-btn admin-only" href={`/?${new URLSearchParams({ system, game: full.path, scrape: '1' })}`} title="Look this game up, in the Library's Fill the gaps">Scrape</a>)}
                    </div>
                </div>
                <div className="gd-body">
                    <div className="gd-art">
                        {field
                            ? <a href={gdMedia(shown[field])} target="_blank" rel="noopener noreferrer" title="See the picture larger"
                                // (shown over the page, fitted to the screen: opened as a page of its own, the phone app showed it at full size)
                                onClick={e => { if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return; e.preventDefault(); setPictureOpen(true); }}>
                                <img key={shown[field]} className="gd-picture" src={gdThumb(shown[field], 480, versions[field])} alt="" draggable={false} /></a>
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
                {pictureOpen && field && <GDPicture name={gdTitle(shown.name || shown.title)} url={gdMedia(shown[field])} onClose={() => setPictureOpen(false)} />}
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
                        {full.rom_exists !== false && <GDSection id="romfile" title="ROM file" summary="Version, checksums, replace"><GDRomFile system={system} game={full} notify={report} onMoved={newPath => changed({}, newPath)} onVersion={version => keep({ rom_version: version })} /></GDSection>}
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
