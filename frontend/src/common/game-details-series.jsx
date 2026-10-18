// The Series row of the panel: the other games in this one's series. Part of the Game Details panel (src/common/game-details.jsx), loaded after it on every page
// that shows the panel; they share one global scope, so this uses its gd... helpers.

// --- Series: the other games in this one's series, and which of them you have ---
// (backend/series_index.py; the lists come from IGDB)
const gdCover = (imageId) => imageId ? `https://images.igdb.com/igdb/image/upload/t_cover_small/${imageId}.jpg` : null;
const gdPut = (url, body) => RM.sendJson(url, 'PUT', body);
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
