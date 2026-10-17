// Tools: the background scrape (every system, on the server, nothing applied) and Library health.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Library health: every system's Scan results in one table
const HEALTH_COLUMNS = [
    { key: 'truncated_names', label: 'Cut-off names', safe: true, help: 'Names missing their first letter or two' },
    { key: 'multi_disc', label: 'Multi-disc', help: 'Discs of one game that could be one .m3u entry' },
    { key: 'saves_in_roms', label: 'Saves in ROM folders', help: 'Save files that belong in the saves/savestates folders' },
    { key: 'game_folders', label: 'PS3 folders', help: 'PS3 game folders not yet named .ps3' },
    { key: 'duplicates', label: 'Duplicates', help: 'The same game more than once' },
    { key: 'empty_roms', label: 'Empty files', help: 'ROM files with nothing in them (0 bytes): a download or copy that failed' },
    { key: 'name_style', label: 'Name style', help: 'Names not in house style (Star Wars: Rogue Leader - Rogue Squadron II)' },
    { key: 'media_links', label: 'Unlinked media', safe: true, help: 'Media exists but the gamelist doesn’t use it' },
    { key: 'disc_tracks', label: 'Disc track entries', safe: true, help: 'Gamelist entries for a disc’s track files' },
    { key: 'relink', label: 'Wrong file name', help: 'Entries pointing at a nearly identical ROM name' },
    { key: 'new_roms', label: 'ROMs without entry', help: 'ROMs with no gamelist entry' },
    { key: 'orphaned_metadata', label: 'Entries without ROM', help: 'Gamelist entries whose ROM is gone' },
    { key: 'orphaned_media', label: 'Unused media', help: 'Media files nothing uses' },
];

// Link that opens a game in the library (used from Tools panels)
const gameLink = (system, romPath) => `/?${new URLSearchParams({ system, game: `./${String(romPath).replace(/^\.\//, '')}` })}`;

// The background scrape (backend/fill_queue.py): Fill the gaps' look-up, every source in your
// order, run on the server over the systems chosen. Nothing is applied: what it finds waits
// here, system by system, to check and apply in Fill the gaps (opened on its Choose step
// with those games looked up already).
function BackgroundScrapePanel({ onClose }) {
    const [status, setStatus] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [systemsList, setSystemsList] = React.useState([]);
    const [only, setOnly] = React.useState(null); // null: every system; else [names]
    // What to fill and the sources' order: Fill the gaps' own, as remembered in this browser
    const [kinds, setKinds] = React.useState(() => {
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(FILL_ON_KEY)); } catch (e) {}
        return Object.fromEntries([...FILL_MEDIA, ...Object.keys(FILL_FIELDS)].map(k => [k, saved ? !!saved[k] : !['box3d', 'boxside', 'fanart', 'screenshottitle', 'manuals', 'videos', 'players', 'rating'].includes(k)]));
    });
    const [recheck, setRecheck] = React.useState(false);
    const order = (() => {
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(FILL_ORDER_KEY)); } catch (e) {}
        const known = (saved || []).filter(s => SCRAPE_SOURCES.some(x => x.id === s.id));
        return [...known, ...SCRAPE_SOURCES.filter(x => !known.some(s => s.id === x.id)).map(x => ({ id: x.id, on: true }))].filter(s => s.on).map(s => s.id);
    })();

    const refresh = React.useCallback(async () => {
        try {
            const d = await (await fetch(`${API_BASE}/api/fill/background`)).json();
            if (d.success) setStatus(d);
            return d;
        } catch (e) { return null; }
    }, []);
    useEffect(() => {
        let timer, live = true;
        const tick = async () => { const d = await refresh(); if (live) timer = setTimeout(tick, d && d.running ? 2000 : 15000); };
        tick();
        fetch(`${API_BASE}/api/systems`).then(r => r.json()).then(d => setSystemsList((Array.isArray(d) ? d : d.systems || []).filter(x => x.rom_count > 0))).catch(() => {});
        return () => { live = false; clearTimeout(timer); };
    }, [refresh]);

    const start = async () => {
        setError(null);
        const d = await postJson('/api/fill/background/start', { systems: only, kinds: Object.keys(kinds).filter(k => kinds[k]), sources: order, recheck });
        if (!d.success) setError(d.error || "It couldn't start");
        refresh();
        RM.tasksChanged();
    };
    const stop = async () => { await postJson('/api/fill/background/stop', {}); refresh(); RM.tasksChanged(); };
    const review = (games) => window.dispatchEvent(new CustomEvent('retromanager:open-tool', { detail: { tool: 'fill', options: {
        games: games.map(g => ({ system: g.system, path: g.rom })), prepared: true, start: true, from: 'background',
        kinds: [...new Set(games.flatMap(g => g.offered))] } } }));
    const leave = async (games) => {
        if (!window.confirm(`Leave what was found for ${games.length} game${games.length === 1 ? '' : 's'}? They aren't changed; they're just no longer listed (a later run finds them again).`)) return;
        await postJson('/api/fill/found/forget', { games: games.map(g => ({ system: g.system, rom: g.rom })) });
        refresh();
    };

    const s = status || {};
    const found = (s.systems || []).map(x => ({ ...x, games: x.games.map(g => ({ ...g, system: x.system })) }));
    const everyFound = found.flatMap(x => x.games);
    const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
    const field = { padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13 };
    const checks = (list) => (
        <div className="fill-checks">{list.map(k => (
            <label key={k}><input type="checkbox" checked={!!kinds[k]} disabled={s.running} onChange={e => setKinds(prev => ({ ...prev, [k]: e.target.checked }))} /> {fillLabel(k)}</label>))}</div>
    );
    return (
        <Modal open={true} onClose={onClose}>
            <div className="fill">
                <h2 style={{marginBottom: 4}}>Background scrape</h2>
                <p className="fill-lede">Looks each system's games up on every source, in the order set in Fill the gaps, on the server: close this and carry on (the strip under the header shows how far it's got). <b>Nothing is changed.</b> What it finds waits here, to check and apply in Fill the gaps.</p>

                {s.running ? (
                    <div className="fill-box">
                        <div className="fill-progress"><div style={{width: `${pct}%`}} /><span>{s.done} of {s.total} looked up{s.current ? ` · ${s.current.name} (${s.current.system_name})` : ''}</span>
                            <button className="btn btn-secondary btn-small" disabled={s.stopping} onClick={stop}>{s.stopping ? 'Stopping…' : 'Stop'}</button></div>
                        <p className="fill-note">{s.found_now} game{s.found_now === 1 ? '' : 's'} with something found so far.</p>
                    </div>
                ) : (
                    <div className="fill-cols">
                        <div className="fill-box"><h3>Systems</h3>
                            <div className="fill-radios" style={{marginBottom: 8}}>
                                <label><input type="radio" name="bg-systems" checked={!only} onChange={() => setOnly(null)} /> Every system</label>
                                <label><input type="radio" name="bg-systems" checked={!!only} onChange={() => setOnly([])} /> These</label>
                            </div>
                            {only && <div className="fill-checks" style={{maxHeight: 220, overflow: 'auto'}}>{systemsList.map(x => (
                                <label key={x.name}><input type="checkbox" checked={only.includes(x.name)} onChange={e => setOnly(prev => e.target.checked ? [...prev, x.name] : prev.filter(n => n !== x.name))} /> {x.full_name || x.name}</label>))}</div>}
                        </div>
                        <div className="fill-box"><h3>Fill</h3>
                            <h4 className="fill-subhead">Images</h4>{checks(FILL_PICTURES)}
                            <h4 className="fill-subhead">Manuals and videos</h4>{checks(FILL_FILES)}
                            <h4 className="fill-subhead">Text</h4>{checks(Object.keys(FILL_FIELDS))}
                            <p className="fill-note">Games missing any of these are looked up.</p>
                        </div>
                        <div className="fill-box"><h3>Sources</h3>
                            <p className="fill-note" style={{marginTop: 0}}>{order.map(id => scrapeSource(id).label).join(', ') || 'none'}: the order and choices in Fill the gaps (a source that isn't set up is passed over).</p>
                            <label style={{display: 'flex', gap: 6, fontSize: 13}}><input type="checkbox" checked={recheck} onChange={e => setRecheck(e.target.checked)} />
                                Look again at games looked up in the last 30 days</label>
                            {error && <p className="fill-error" style={{fontSize: 13}}>{error}</p>}
                            <button className="btn btn-primary" style={{marginTop: 10}} disabled={(only && !only.length) || !Object.values(kinds).some(Boolean) || !order.length} onClick={start}>Start</button>
                            {s.finished && <p className="fill-note">Last run finished {new Date(s.finished).toLocaleString()}: {s.done} of {s.total} looked up{s.skipped_recent ? `, ${s.skipped_recent} skipped (looked up recently)` : ''}{s.stopped_reason ? ` · ${s.stopped_reason === 'Stopped' ? 'stopped by you' : `stopped: ${s.stopped_reason}`}` : ''}.</p>}
                        </div>
                    </div>
                )}

                <div className="fill-box" style={{marginTop: 14}}>
                    <div className="fill-bar"><h3 className="grow" style={{margin: 0}}>Found, to check</h3>
                        {everyFound.length > 0 && <button className="btn btn-primary btn-small" onClick={() => review(everyFound)}>Review all {everyFound.length}</button>}</div>
                    {!found.length ? <p className="muted" style={{fontSize: 13, margin: '6px 0 0'}}>{s.running ? 'Nothing yet.' : 'Nothing waiting. Start a run above.'}</p> : (
                        <table className="fill-table"><tbody>{found.map(x => {
                            const kindsOffered = [...new Set(x.games.flatMap(g => g.offered))];
                            return (
                                <tr key={x.system}>
                                    <td><b>{x.system_name}</b><div className="muted" style={{fontSize: 12}}>{x.games.length} game{x.games.length === 1 ? '' : 's'}</div></td>
                                    <td><div className="fill-chips">{kindsOffered.map(k => <span key={k} className={`fill-chip ${FILL_FIELDS[k] ? 'text' : 'pic'}`}>{fillLabel(k)}</span>)}</div></td>
                                    <td style={{whiteSpace: 'nowrap', textAlign: 'right'}}>
                                        <button className="btn btn-primary btn-small" onClick={() => review(x.games)}>Review</button>{' '}
                                        <button className="btn btn-secondary btn-small" onClick={() => leave(x.games)} title="Take them off this list without changing anything">Leave</button>
                                    </td>
                                </tr>
                            );
                        })}</tbody></table>
                    )}
                </div>
            </div>
        </Modal>
    );
}

const thumbUrl = (height, mediaPath) => `${API_BASE}/api/thumb/${height}/${String(mediaPath).split('/').map(encodeURIComponent).join('/')}`;
