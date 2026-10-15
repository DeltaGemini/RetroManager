// Tools: missing in series.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Tools > Missing in series: every series the library has games from, how
// much of each you have, and your want list. The lists are IGDB's; matching
// the library to it runs in the background (backend/series_index.py).
function SeriesPanel({ onClose, showNotification }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [tab, setTab] = React.useState('series');   // series | want
    const [open, setOpen] = React.useState(null);     // the series unfolded: its key
    const [view, setView] = React.useState(null);
    const [find, setFind] = React.useState('');
    const [finding, setFinding] = React.useState(null);   // the unmatched game being looked up: "system/path"
    const load = React.useCallback(() => {
        fetch(`${API_BASE}/api/series/overview`).then(r => r.json())
            .then(d => d.success ? setData(d) : setError(d.error || 'Could not load the series'))
            .catch(e => setError(e.message));
    }, []);
    useEffect(() => { load(); }, [load]);
    // While the matching runs, follow it
    const running = !!(data && data.progress && data.progress.running);
    useEffect(() => {
        if (!running) return;
        const timer = setInterval(load, 3000);
        return () => clearInterval(timer);
    }, [running, load]);
    const loadView = React.useCallback((key) => {
        fetch(`${API_BASE}/api/series/list?${new URLSearchParams({ key })}`).then(r => r.json())
            .then(d => { if (d.success) setView(d.series); }).catch(() => {});
    }, []);
    const toggle = (key) => {
        setView(null);
        setOpen(o => (o === key ? null : key));
        if (open !== key) loadView(key);
    };
    const run = async (redo) => {
        try {
            const d = await (await fetch(`${API_BASE}/api/series/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ redo }) })).json();
            if (!d.success && showNotification) showNotification(d.error || 'Could not start', 'error');
        } catch (e) { if (showNotification) showNotification(e.message, 'error'); }
        load();
        RM.tasksChanged();
    };
    const unwant = async (game) => {
        await fetch(`${API_BASE}/api/series/mark`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: game.id, mark: null }) }).catch(() => {});
        load();
    };

    const progress = data && data.progress;
    const series = ((data && data.series) || []).filter(s => !find.trim() || (s.name || '').toLowerCase().includes(find.trim().toLowerCase()));
    const year = (g) => g.date ? new Date(g.date * 1000).getUTCFullYear() : null;
    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Missing in series</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12, maxWidth: 700}}>
                What you have of each series your games belong to, on every platform. The lists are IGDB's: originals, remakes and remasters, without ports, bundles or DLC.
            </div>
            {error && <div role="alert" style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {data && !data.configured && <div style={{color: 'var(--text-secondary)'}}>{data.error}</div>}
            {data && data.configured && (
                <div className="gd" style={{containerType: 'normal'}}>
                    <div className="gd-row gd-small">
                        <span style={{flex: 1, minWidth: 220}}>
                            {running
                                ? <><b>{progress.step}</b>: {progress.done} of {progress.total}</>
                                : <>{data.matched} games matched to IGDB{data.unmatched > 0 && `, ${data.unmatched} not found`}{data.waiting > 0 && ` · ${data.waiting} series still to fetch`}</>}
                            {progress && progress.error && <span className="gd-error"> · Stopped: {progress.error}</span>}
                        </span>
                        <button className="gd-btn small admin-only" disabled={running} onClick={() => run(false)} title="Look up the games that haven't been, and fetch their series">{running ? 'Working...' : data.matched + data.unmatched ? 'Match new games' : 'Match the library'}</button>
                        {!running && data.matched + data.unmatched > 0 && <button className="gd-btn small admin-only" onClick={() => run(true)} title="Look every game up again (a few minutes)">Match everything again</button>}
                    </div>
                    {running && (
                        <div className="gd-bar"><div style={{width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%`, background: 'var(--accent-orange)'}} /></div>
                    )}
                    <div className="gd-row gd-small" style={{marginTop: 10}}>
                        {[['series', `Series ${data.series.length}`], ['want', `Want list ${data.wanted.length}`], ['unmatched', `Not found ${(data.unmatched_games || []).length}`]].map(([key, label]) => (
                            <button key={key} className={`gd-btn small${tab === key ? ' primary' : ''}`} onClick={() => setTab(key)}>{label}</button>
                        ))}
                        {tab === 'series' && data.series.length > 8 && (
                            <input type="search" value={find} placeholder="Find a series" onChange={e => setFind(e.target.value)}
                                style={{flex: 1, minWidth: 140, padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 12}} />
                        )}
                    </div>
                    <div style={{maxHeight: '56vh', overflowY: 'auto', paddingRight: 6}}>
                        {tab === 'series' && !data.series.length && (
                            <div className="gd-note" style={{padding: '16px 0'}}>{running ? 'Series appear here as they are fetched.' : 'Nothing yet. Press Match the library: it takes a few minutes the first time.'}</div>
                        )}
                        {tab === 'series' && series.map(s => (
                            <section key={s.key} className="gd-section">
                                <button className="gd-section-head" onClick={() => toggle(s.key)} aria-expanded={open === s.key}>
                                    <span className="gd-caret" aria-hidden="true">{open === s.key ? '▾' : '▸'}</span>
                                    <span className="gd-section-title">{s.name}{s.kind === 'franchise' && <span className="gd-note"> · franchise</span>}</span>
                                    <span className="gd-section-summary">
                                        {s.have} of {s.total}
                                        <span className="achievement-bar" style={{marginLeft: 8, width: 70}}><span style={{display: 'block', height: '100%', width: `${s.total ? (s.have / s.total) * 100 : 0}%`, background: s.have >= s.total ? 'var(--success)' : 'var(--accent-orange)'}} /></span>
                                    </span>
                                </button>
                                {open === s.key && (
                                    <div className="gd-section-body">
                                        {view && view.key === s.key
                                            ? <GDSeriesGames view={view} reload={() => { loadView(s.key); load(); }} notify={showNotification} />
                                            : <div className="gd-note">Loading...</div>}
                                    </div>
                                )}
                            </section>
                        ))}
                        {tab === 'unmatched' && (
                            <>
                                <div className="gd-note" style={{padding: '10px 0 6px'}}>
                                    Games IGDB had nothing for under their name: hacks, translations, homebrew, and names it spells differently. <b>Find it</b> searches IGDB so you can pick the right game; one that really isn't there can be left.
                                </div>
                                {!(data.unmatched_games || []).length && <div className="gd-note">Every game was found.</div>}
                                {(data.unmatched_games || []).map(g => {
                                    const key = `${g.system}/${g.path}`;
                                    return (
                                        <section key={key} className="gd-section">
                                            <div className="gd-section-head" style={{cursor: 'default'}}>
                                                <span className="gd-section-title">{g.name}</span>
                                                <span className="gd-note">{g.system}</span>
                                                <span className="gd-section-summary">
                                                    <button className="gd-btn small admin-only" onClick={() => setFinding(f => (f === key ? null : key))}>{finding === key ? 'Cancel' : 'Find it'}</button>
                                                </span>
                                            </div>
                                            {finding === key && (
                                                <div className="gd-section-body">
                                                    <GDSeriesPicker system={g.system} game={g} notify={showNotification} onDone={() => { setFinding(null); load(); }} />
                                                </div>
                                            )}
                                        </section>
                                    );
                                })}
                            </>
                        )}
                        {tab === 'want' && !data.wanted.length && <div className="gd-note" style={{padding: '16px 0'}}>Nothing yet. Press ☆ Want on a game you don't have, here or in a game's Series section.</div>}
                        {tab === 'want' && (
                            <div className="gd-series-grid" style={{marginTop: 8}}>
                                {data.wanted.map(g => (
                                    <div key={g.id} className="gd-series-game want">
                                        {gdCover(g.cover) ? <img src={gdCover(g.cover)} alt="" loading="lazy" /> : <span className="gd-series-nocover" aria-hidden="true">🎮</span>}
                                        <div className="gd-series-text">
                                            <a className="gd-series-name" href={`https://www.igdb.com/search?type=1&q=${encodeURIComponent(g.name)}`} target="_blank" rel="noopener noreferrer" title="Look it up on IGDB">{g.name}</a>
                                            <span className="gd-note">{[year(g), g.type, g.platforms.slice(0, 4).join(' / ')].filter(Boolean).join(' · ')}</span>
                                            <span className="gd-tiny gd-note">{g.series}</span>
                                            <span className="gd-series-marks"><button className="gd-chip" onClick={() => unwant(g)}>Remove</button></span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </Modal>
    );
}
