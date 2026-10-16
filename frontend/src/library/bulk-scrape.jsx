// Bulk scrape: match many games, review, then apply.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Media bulk scraping can download (videos are left out: large and slow)
const BULK_MEDIA = [
    { key: 'box2d', label: 'Box 2D' },
    { key: 'screenshot', label: 'Screenshot' },
    { key: 'screenshottitle', label: 'Title screen' },
    { key: 'wheel', label: 'Wheel' },
    { key: 'mix', label: 'Mix' },
    { key: 'box3d', label: 'Box 3D' },
    { key: 'boxside', label: 'Spine' },
    { key: 'support', label: 'Cart / disc' },
    { key: 'fanart', label: 'Fanart' },
    { key: 'manuals', label: 'Manual' },
];

const BULK_PRESETS = [
    { key: 'missing', label: 'Missing metadata', test: g => !g.has_metadata },
    { key: 'no-desc', label: 'No description', test: g => !g.desc },
    { key: 'no-image', label: 'No image in gamelist', test: g => !g.image },
    { key: 'all', label: 'All games', test: () => true },
];

const CONFIDENCE = {
    exact: { label: 'Exact', color: 'var(--success)', help: 'This exact ROM file was recognised, by its name or its checksum' },
    likely: { label: 'Likely', color: 'var(--accent-orange)', help: "The game's name closely matches the ROM" },
    unsure: { label: 'Unsure', color: 'var(--accent-pink)', help: 'The names differ: check before applying' },
    none: { label: 'No match', color: 'var(--text-secondary)', help: 'Nothing found. Try searching another name' },
};

const postJson = async (url, body) => {
    const res = await fetch(`${API_BASE}${url}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return res.json();
};

// A match's picture large, beside the one the game has now: stepped through
// game by game, each ticked or not from here too
function MatchCompare({ items, index, setIndex, ticked, onTick, onClose }) {
    const item = items[index];
    useEffect(() => {
        const key = (e) => {
            if (e.key === 'Escape') { e.stopPropagation(); onClose(); }
            else if (e.key === 'ArrowLeft' && index > 0) setIndex(index - 1);
            else if (e.key === 'ArrowRight' && index < items.length - 1) setIndex(index + 1);
        };
        window.addEventListener('keydown', key, true);
        return () => window.removeEventListener('keydown', key, true);
    }, [index, items.length]);
    if (!item) return null;
    const label = mediaSourceLabel(item.kind);
    // On a phone the two are one above the other, so each is shorter
    const tall = window.innerWidth < 600 ? '33vh' : '58vh';
    const pane = (heading, src, empty) => (
        <div style={{flex: '1 1 260px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6}}>
            <div style={{fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{heading}</div>
            <div style={{flex: 1, minHeight: 120, background: 'var(--bg-tertiary)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden'}}>
                {src ? (VIEWER_FILES[item.kind] ? <a href={src} target="_blank" rel="noopener" style={{fontSize: 15}}>Open the {label.toLowerCase()}</a>
                        : <img key={src} src={src} alt={heading} style={{maxWidth: '100%', maxHeight: tall, objectFit: 'contain'}} />)
                     : <span style={{color: 'var(--text-secondary)', fontSize: 13, padding: 16, textAlign: 'center'}}>{empty}</span>}
            </div>
        </div>
    );
    return ReactDOM.createPortal(
        <div onClick={e => { e.stopPropagation(); onClose(); }}
            style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12}}>
            <div onClick={e => e.stopPropagation()} role="dialog" aria-label={`Compare pictures for ${item.title}`}
                style={{background: 'var(--bg-modal)', borderRadius: 8, padding: 16, width: 'min(1100px, 100%)', maxHeight: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12}}>
                <div style={{display: 'flex', gap: 10, alignItems: 'flex-start'}}>
                    <div style={{flex: 1, minWidth: 0}}>
                        <div style={{fontWeight: 700, fontSize: 16}}>{item.title}</div>
                        <div style={{fontSize: 12, color: 'var(--text-secondary)'}}>{[item.system, label, `${index + 1} of ${items.length}`].filter(Boolean).join(' · ')}</div>
                    </div>
                    <button className="btn btn-secondary btn-small" onClick={onClose}>Close</button>
                </div>
                <div style={{display: 'flex', gap: 12, flexWrap: 'wrap'}}>
                    {pane('Now', item.current ? localMediaUrl(item.current) : null, `No ${label} yet`)}
                    {pane(`ScreenScraper: ${item.matchName || 'no match'}`, item.found,
                          item.matchName ? `ScreenScraper has no ${label} for it` : 'No match chosen')}
                </div>
                <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
                    <button className="btn btn-secondary" style={{whiteSpace: 'nowrap'}} disabled={index === 0} onClick={() => setIndex(index - 1)}>‹ Prev</button>
                    <label style={{display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, cursor: item.canTick ? 'pointer' : 'default', margin: '0 auto', textAlign: 'center'}}>
                        <input type="checkbox" style={{width: 20, height: 20}} disabled={!item.canTick} checked={!!ticked[item.key] && item.canTick} onChange={() => onTick(item.key)} />
                        Apply this one
                    </label>
                    <button className="btn btn-primary" style={{whiteSpace: 'nowrap'}} disabled={index === items.length - 1} onClick={() => setIndex(index + 1)}>Next ›</button>
                </div>
            </div>
        </div>,
        document.body
    );
}

// Match many games to ScreenScraper, review the matches, then fill their blanks.
// Games are one system's (`system`), or, from the Media viewer, games of any
// systems already chosen (`chosen`: each with its own `system`, and a `key`).
function BulkScrapePanel({ system, games, chosen, onClose, onDone, initialMedia, initialReplace = false }) {
    games = chosen || games;
    const [stage, setStage] = React.useState(() => chosen ? 'matching' : 'select'); // select | matching | review | applying | done
    const [preset, setPreset] = React.useState(() => chosen ? 'all' : games.some(g => !g.has_metadata) ? 'missing' : 'no-desc');
    const [picked, setPicked] = React.useState({});
    const [media, setMedia] = React.useState(() => Object.fromEntries(BULK_MEDIA.map(m => [m.key, initialMedia ? initialMedia.includes(m.key) : true])));
    // Also download the chosen media where a game has it already (for pictures that are the wrong ones)
    const [replace, setReplace] = React.useState(initialReplace);
    const [matches, setMatches] = React.useState({}); // rom path -> {confidence, alternatives, chosen, error}
    const [ticked, setTicked] = React.useState({});
    const [progress, setProgress] = React.useState(null);
    const [message, setMessage] = React.useState(null);
    const [results, setResults] = React.useState({}); // rom path -> apply result
    const [reviewFilter, setReviewFilter] = React.useState('all');
    const [searchText, setSearchText] = React.useState({});
    const [searching, setSearching] = React.useState({});
    const [comparing, setComparing] = React.useState(null); // index into the review list, in the comparison popup
    const cancelRef = React.useRef(false);

    const presetGames = React.useMemo(() => {
        const p = BULK_PRESETS.find(x => x.key === preset) || BULK_PRESETS[0];
        return games.filter(p.test);
    }, [games, preset]);
    useEffect(() => {
        setPicked(Object.fromEntries(presetGames.map(g => [keyOf(g), true])));
    }, [presetGames]);

    // Games are known by their ROM path, or by `key` when they're from several systems
    const keyOf = (g) => g.key || g.path;
    const selectedGames = presetGames.filter(g => picked[keyOf(g)]);
    const gameByPath = React.useMemo(() => Object.fromEntries(games.map(g => [keyOf(g), g])), [games]);
    const title = (key) => splitGameName(gameByPath[key]?.name || key).title;
    const systemOf = (key) => gameByPath[key]?.system || system.name;
    const romOf = (key) => gameByPath[key]?.path || key;

    const findMatches = async (list = selectedGames) => {
        cancelRef.current = false;
        setMessage(null);
        setStage('matching');
        const found = {};
        const autoTick = {};
        for (let i = 0; i < list.length; i++) {
            if (cancelRef.current) break;
            const g = list[i];
            const key = keyOf(g);
            setProgress({ done: i, total: list.length, current: title(key) });
            try {
                const d = await postJson('/api/bulk-scrape/match', { system_name: systemOf(key), rom_path: g.path });
                if (!d.success) {
                    found[key] = { confidence: 'none', alternatives: [], error: d.error };
                    if (d.fatal) {
                        setMessage({ type: 'error', text: `Stopped: ${d.error}` });
                        break;
                    }
                } else {
                    found[key] = { confidence: d.confidence, alternatives: d.alternatives, chosen: d.match_id };
                    autoTick[key] = d.confidence === 'exact' || d.confidence === 'likely';
                }
            } catch (err) {
                found[key] = { confidence: 'none', alternatives: [], error: err.message };
            }
            setMatches({ ...found });
        }
        setTicked(autoTick);
        setProgress(null);
        setStage('review');
    };

    // Games picked in the Media viewer are already chosen, as is what to download: straight to matching
    useEffect(() => { if (chosen) findMatches(games); }, []);

    const researchOne = async (path) => {
        const query = (searchText[path] || '').trim();
        if (!query) return;
        setSearching(prev => ({ ...prev, [path]: true }));
        try {
            const d = await postJson('/api/bulk-scrape/match', { system_name: systemOf(path), rom_path: romOf(path), query });
            if (d.success) {
                setMatches(prev => ({ ...prev, [path]: { confidence: d.confidence, alternatives: d.alternatives, chosen: d.match_id } }));
                // You searched for it yourself, so the top result is ticked
                setTicked(prev => ({ ...prev, [path]: !!d.match_id }));
            } else {
                setMatches(prev => ({ ...prev, [path]: { ...prev[path], error: d.error } }));
            }
        } finally {
            setSearching(prev => ({ ...prev, [path]: false }));
        }
    };

    const applyAll = async () => {
        const paths = Object.keys(matches).filter(p => ticked[p] && matches[p].chosen);
        if (!paths.length) return;
        cancelRef.current = false;
        setMessage(null);
        setStage('applying');
        // One backup of the gamelist before anything is written
        for (const name of new Set(paths.map(systemOf))) {
            try { await postJson('/api/backup_gamelist', { system: name }); } catch (e) {}
        }
        const mediaList = Object.keys(media).filter(k => media[k]);
        const done = {};
        for (let i = 0; i < paths.length; i++) {
            if (cancelRef.current) break;
            const path = paths[i];
            setProgress({ done: i, total: paths.length, current: title(path) });
            try {
                const d = await postJson('/api/bulk-scrape/apply', { system_name: systemOf(path), rom_path: romOf(path), game_id: matches[path].chosen, media: mediaList, replace });
                done[path] = d;
                if (!d.success && d.fatal) {
                    setMessage({ type: 'error', text: `Stopped: ${d.error}` });
                    setResults({ ...done });
                    break;
                }
            } catch (err) {
                done[path] = { success: false, error: err.message };
            }
            setResults({ ...done });
        }
        setProgress(null);
        setStage('done');
        onDone();
    };

    const progressBar = progress && (
        <div style={{marginBottom: 16}}>
            <div style={{fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6}}>
                {stage === 'matching' ? 'Finding' : 'Applying'} {progress.done + 1} of {progress.total}: <b style={{color: 'var(--text-primary)'}}>{progress.current}</b>
            </div>
            <div style={{height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden'}}>
                <div style={{height: '100%', width: `${(progress.done / progress.total) * 100}%`, background: 'var(--accent-orange)', transition: 'width 0.3s'}} />
            </div>
            <button className="btn btn-secondary btn-small" style={{marginTop: 10}} onClick={() => { cancelRef.current = true; }}>
                Stop after this game
            </button>
        </div>
    );

    const badge = (confidence) => {
        const c = CONFIDENCE[confidence] || CONFIDENCE.none;
        return <span title={c.help} style={{fontSize: 11, padding: '1px 6px', borderRadius: 3, border: `1px solid ${c.color}`, color: c.color, whiteSpace: 'nowrap'}}>{c.label}</span>;
    };

    const counts = Object.values(matches).reduce((acc, m) => ({ ...acc, [m.confidence]: (acc[m.confidence] || 0) + 1 }), {});
    const tickedCount = Object.keys(matches).filter(p => ticked[p] && matches[p].chosen).length;
    const reviewPaths = Object.keys(matches).filter(p =>
        reviewFilter === 'all' || (reviewFilter === 'attention' ? ['unsure', 'none'].includes(matches[p].confidence) : ticked[p]));

    // The kind of picture to compare: the one ticked to download, the first of several, else the box
    const tickedKinds = BULK_MEDIA.filter(m => media[m.key]).map(m => m.key);
    const previewKind = tickedKinds.length === 1 ? tickedKinds[0] : (tickedKinds.find(k => k !== 'manuals') || BULK_MEDIA[0].key);
    const compareItems = reviewPaths.map(path => {
        const m = matches[path];
        const g = gameByPath[path] || {};
        const best = (m.alternatives || []).find(a => String(a.id) === String(m.chosen));
        return { key: path, title: title(path), system: chosen ? g.system_name : null, kind: previewKind,
                 current: chosen ? g.picture : g[previewKind], found: best?.media?.[previewKind] || null,
                 matchName: best?.nom, canTick: !!m.chosen };
    });

    let body;
    if (stage === 'select') {
        body = (
            <>
                {!chosen && <div style={{display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12}}>
                    {BULK_PRESETS.map(p => (
                        <button key={p.key} className={`btn btn-small ${preset === p.key ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setPreset(p.key)}>
                            {p.label} ({games.filter(p.test).length})
                        </button>
                    ))}
                </div>}
                <div style={{maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 16}}>
                    {presetGames.length === 0 && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No games in this group.</div>}
                    {presetGames.map(g => {
                        const n = splitGameName(g.name);
                        return (
                            <label key={keyOf(g)} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, cursor: 'pointer'}}>
                                <input type="checkbox" checked={!!picked[keyOf(g)]} onChange={() => setPicked(prev => ({ ...prev, [keyOf(g)]: !prev[keyOf(g)] }))} />
                                <span style={{flex: 1}}>{n.title} <span style={{color: 'var(--text-secondary)', fontSize: 11}}>{n.tags}{chosen && g.system_name ? ` · ${g.system_name}` : ''}</span></span>
                                {!g.has_metadata && <span className="status-badge status-missing">No entry</span>}
                            </label>
                        );
                    })}
                </div>
                <div style={{fontSize: 13, fontWeight: 600, marginBottom: 6}}>Media to download ({replace ? 'replacing what the game has' : 'only where the game has none yet'})</div>
                <div style={{display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16, fontSize: 13}}>
                    {BULK_MEDIA.map(m => (
                        <label key={m.key} style={{display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer'}}>
                            <input type="checkbox" checked={!!media[m.key]} onChange={() => setMedia(prev => ({ ...prev, [m.key]: !prev[m.key] }))} />
                            {m.label}
                        </label>
                    ))}
                </div>
                <label style={{display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer', fontSize: 13, marginBottom: 16}}>
                    <input type="checkbox" style={{marginTop: 3}} checked={replace} onChange={() => setReplace(r => !r)} />
                    <span>Replace the media these games already have
                        <span style={{display: 'block', fontSize: 12, color: 'var(--text-secondary)'}}>For pictures that are the wrong ones: each ticked type is downloaded again for every game you apply, where the match has one. The old files are kept in the data folder under replaced-media. It uses more of the ScreenScraper quota.</span>
                    </span>
                </label>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap'}}>
                    <span style={{fontSize: 12, color: 'var(--text-secondary)'}}>Nothing is written until you review the matches and click Apply.</span>
                    <button className="btn btn-primary" disabled={!selectedGames.length} onClick={() => findMatches()}>Find matches ({selectedGames.length})</button>
                </div>
            </>
        );
    } else if (stage === 'matching') {
        body = (
            <>
                {progressBar}
                <div style={{fontSize: 13, color: 'var(--text-secondary)'}}>
                    {Object.keys(CONFIDENCE).map(k => counts[k] ? `${counts[k]} ${CONFIDENCE[k].label.toLowerCase()}` : null).filter(Boolean).join(' · ') || 'Starting...'}
                </div>
            </>
        );
    } else if (stage === 'review') {
        body = (
            <>
                <div style={{display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12, fontSize: 13}}>
                    {Object.keys(CONFIDENCE).map(k => counts[k] ? <span key={k}>{badge(k)} {counts[k]}</span> : null)}
                    <select value={reviewFilter} onChange={e => setReviewFilter(e.target.value)} style={{marginLeft: 'auto', padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)'}}>
                        <option value="all">Show all</option>
                        <option value="attention">Needs attention</option>
                        <option value="ticked">Ticked only</option>
                    </select>
                </div>
                <div style={chosen
                        ? {maxHeight: '64vh', overflowY: 'auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(380px, 100%), 1fr))', gap: 10, marginBottom: 16, padding: 2}
                        : {maxHeight: '52vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16}}>
                    {reviewPaths.map((path, i) => {
                        const m = matches[path];
                        const best = m.alternatives.find(a => String(a.id) === String(m.chosen));
                        const tick = <input type="checkbox" style={{marginTop: 4, width: chosen ? 18 : undefined, height: chosen ? 18 : undefined}} disabled={!m.chosen}
                            checked={!!ticked[path] && !!m.chosen} aria-label={`Apply ${title(path)}`}
                            onChange={() => setTicked(prev => ({ ...prev, [path]: !prev[path] }))} />;
                        const where = <div style={{color: 'var(--text-secondary)', fontSize: 11, wordBreak: 'break-word'}}>{chosen ? `${gameByPath[path]?.system_name || systemOf(path)} · ` : ''}{romOf(path)}</div>;
                        // Which ScreenScraper game it is: the results, and a search for another name
                        const searchOpen = ['unsure', 'none'].includes(m.confidence) || searchText[path] !== undefined;
                        const controls = (
                            <>
                                {m.alternatives.length > 0 && (
                                    <select value={m.chosen || ''} onChange={e => setMatches(prev => ({ ...prev, [path]: { ...prev[path], chosen: e.target.value } }))}
                                        aria-label={`ScreenScraper game for ${title(path)}`}
                                        style={{width: '100%', padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 12}}>
                                        {m.alternatives.map(a => (
                                            <option key={a.id} value={a.id}>
                                                {a.nom}{a.year ? ` · ${a.year}` : ''} · {a.systemenom}{a.is_hack ? ' · hack' : ''} ({Math.round(a.score * 100)}%)
                                            </option>
                                        ))}
                                    </select>
                                )}
                                {m.error && <div style={{color: 'var(--accent-pink)', fontSize: 12, marginTop: 4}}>{m.error}</div>}
                                {searchOpen ? (
                                    <div style={{display: 'flex', gap: 6, marginTop: 6}}>
                                        <input type="text" placeholder="Search another name..." value={searchText[path] || ''}
                                            onChange={e => setSearchText(prev => ({ ...prev, [path]: e.target.value }))}
                                            onKeyDown={e => { if (e.key === 'Enter') researchOne(path); }}
                                            style={{flex: 1, minWidth: 0, padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 12}} />
                                        <button className="btn btn-secondary btn-small" disabled={searching[path]} onClick={() => researchOne(path)}>{searching[path] ? '...' : 'Search'}</button>
                                    </div>
                                ) : chosen && (
                                    <button onClick={() => setSearchText(prev => ({ ...prev, [path]: '' }))}
                                        style={{background: 'none', border: 'none', padding: '4px 0 0', color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer', textDecoration: 'underline'}}>
                                        Wrong game? Search another name
                                    </button>
                                )}
                            </>
                        );
                        if (chosen) {
                            // From the Media viewer: the picture it has beside the one it would get, large enough to judge
                            const c = compareItems[i];
                            const pane = (heading, src, empty) => (
                                <button onClick={() => setComparing(i)} title="See it larger"
                                    style={{flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, background: 'none', border: 'none', padding: 0, cursor: 'zoom-in', color: 'inherit', textAlign: 'left'}}>
                                    <span style={{fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%'}}>{heading}</span>
                                    <span style={{width: '100%', height: 'clamp(130px, 26vh, 300px)', background: 'var(--bg-secondary)', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden'}}>
                                        {src ? (VIEWER_FILES[previewKind] ? <span style={{fontSize: 14, fontWeight: 600}}>{VIEWER_FILES[previewKind]}</span>
                                                : <img src={src} alt="" loading="lazy" style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain'}} />)
                                             : <span style={{color: 'var(--text-secondary)', fontSize: 12, padding: 8, textAlign: 'center'}}>{empty}</span>}
                                    </span>
                                </button>
                            );
                            return (
                                <div key={path} style={{display: 'flex', flexDirection: 'column', gap: 8, padding: 10, background: 'var(--bg-tertiary)', borderRadius: 6, fontSize: 13,
                                                        outline: ticked[path] && m.chosen ? '2px solid var(--accent-orange)' : 'none', outlineOffset: -2}}>
                                    <div style={{display: 'flex', gap: 10, alignItems: 'flex-start'}}>
                                        {tick}
                                        <div style={{flex: 1, minWidth: 0}}>
                                            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'}}><b>{title(path)}</b> {badge(m.confidence)}</div>
                                            {where}
                                        </div>
                                    </div>
                                    <div style={{display: 'flex', gap: 10}}>
                                        {pane('Now', c.current ? localMediaUrl(c.current) : null, `No ${mediaSourceLabel(previewKind)} yet`)}
                                        {pane('ScreenScraper', c.found, best ? `It has no ${mediaSourceLabel(previewKind)} for this game` : 'No match')}
                                    </div>
                                    <div>{controls}</div>
                                </div>
                            );
                        }
                        return (
                            <div key={path} style={{display: 'flex', gap: 10, alignItems: 'flex-start', padding: 8, background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>
                                {tick}
                                <button onClick={() => setComparing(i)} title="Compare with the picture it has now, larger"
                                    style={{width: 64, height: 64, flexShrink: 0, borderRadius: 3, overflow: 'hidden', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: 0, cursor: 'zoom-in', position: 'relative'}}>
                                    {(best?.media?.[previewKind] || best?.image) && <img src={best.media?.[previewKind] || best.image} alt="" loading="lazy" style={{width: '100%', height: '100%', objectFit: 'contain'}} />}
                                    <span aria-hidden="true" style={{position: 'absolute', right: 2, bottom: 2, fontSize: 11, background: 'rgba(0,0,0,0.6)', color: 'white', borderRadius: 3, padding: '0 3px'}}>⤢</span>
                                </button>
                                <div style={{flex: 1, minWidth: 0}}>
                                    <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'}}>
                                        <b>{title(path)}</b> {badge(m.confidence)}
                                    </div>
                                    <div style={{marginBottom: 4}}>{where}</div>
                                    {controls}
                                </div>
                            </div>
                        );
                    })}
                </div>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap'}}>
                    <span style={{fontSize: 12, color: 'var(--text-secondary)'}}>Fills only empty fields and downloads {replace ? 'the ticked media again, keeping the old files' : 'only missing media'}. The gamelist is backed up first.</span>
                    <button className="btn btn-primary" disabled={!tickedCount} onClick={applyAll}>Apply {tickedCount} game{tickedCount === 1 ? '' : 's'}</button>
                </div>
            </>
        );
    } else {
        const entries = Object.entries(results);
        const ok = entries.filter(([, r]) => r.success);
        const totalMedia = ok.reduce((n, [, r]) => n + (r.downloaded || []).length, 0);
        body = (
            <>
                {progressBar}
                {stage === 'done' && (
                    <div style={{fontSize: 14, marginBottom: 12}}>
                        Updated <b>{ok.length}</b> game{ok.length === 1 ? '' : 's'} and downloaded <b>{totalMedia}</b> media file{totalMedia === 1 ? '' : 's'}.
                        {entries.length - ok.length > 0 && <span style={{color: 'var(--accent-pink)'}}> {entries.length - ok.length} failed.</span>}
                    </div>
                )}
                <div style={{maxHeight: '52vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4}}>
                    {entries.map(([path, r]) => (
                        <div key={path} style={{padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>
                            <b>{title(path)}</b>{' '}
                            {r.success ? (
                                <span style={{color: 'var(--text-secondary)'}}>
                                    {r.filled.length ? `filled ${r.filled.join(', ')}` : 'nothing to fill'}
                                    {r.downloaded.length ? ` · downloaded ${r.downloaded.join(', ')}` : ''}{(r.replaced || []).length ? ` (replaced ${r.replaced.join(', ')})` : ''}
                                </span>
                            ) : <span style={{color: 'var(--accent-pink)'}}>{r.error}</span>}
                            {r.errors && r.errors.length > 0 && <div style={{color: 'var(--accent-pink)', fontSize: 12}}>{r.errors.join(' · ')}</div>}
                        </div>
                    ))}
                </div>
            </>
        );
    }

    const compare = comparing !== null && stage === 'review' && (
        <MatchCompare items={compareItems} index={comparing} setIndex={setComparing} ticked={ticked}
            onTick={key => setTicked(prev => ({ ...prev, [key]: !prev[key] }))} onClose={() => setComparing(null)} />
    );
    const busy = stage === 'matching' || stage === 'applying';
    return (
        <Modal open={true} onClose={busy ? () => {} : onClose}>
          <div style={chosen ? {width: 'min(1500px, calc(100vw - 80px))', maxWidth: '100%'} : undefined}>
            <h2 style={{marginBottom: 4}}>Bulk scrape: {chosen ? `${games.length} game${games.length === 1 ? '' : 's'}` : system.full_name || system.name}</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16}}>
                {stage === 'select' && 'Choose games. Each is looked up on ScreenScraper by its ROM file name, then by checksum, then by title.'}
                {(stage === 'matching' || stage === 'review') && (chosen
                    ? `Exact and Likely matches are ticked. Compare each game's ${mediaSourceLabel(previewKind)} with ScreenScraper's (tap one to see it larger), untick any to leave as they are, and pick another result if it's the wrong game.`
                    : 'Exact and Likely matches are ticked. Check the Unsure ones, pick another result, or search a different name.')}
                {(stage === 'applying' || stage === 'done') && 'Filling empty fields and downloading missing media.'}
            </div>
            {message && (
                <div role="alert" style={{marginBottom: 12, padding: '10px 12px', borderRadius: 4, fontSize: 13, background: 'rgba(255,107,157,0.12)', border: '1px solid var(--accent-pink)'}}>{message.text}</div>
            )}
            {body}
            {compare}
          </div>
        </Modal>
    );
}
