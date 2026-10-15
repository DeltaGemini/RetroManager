// Tools: library scrape and missing media.
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

// Progress of the background library scrape, polled while it runs
function useScrapeQueue() {
    const [status, setStatus] = React.useState(null);
    const refresh = React.useCallback(async () => {
        try {
            const d = await (await fetch(`${API_BASE}/api/scrape-queue`)).json();
            if (d.success) setStatus(d);
            return d;
        } catch (e) { return null; }
    }, []);
    useEffect(() => {
        let timer;
        const tick = async () => {
            const d = await refresh();
            timer = setTimeout(tick, d && d.running ? 3000 : 60000);
        };
        tick();
        return () => clearTimeout(timer);
    }, [refresh]);
    return [status, refresh];
}

// Scrape every system in the background: confident matches are applied,
// the rest are listed for review
function LibraryScrapePanel({ status, refresh, onClose, onChanged }) {
    const [includeMedia, setIncludeMedia] = React.useState(false);
    const [media, setMedia] = React.useState(() => Object.fromEntries(BULK_MEDIA.map(m => [m.key, true])));
    const [recheck, setRecheck] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [open, setOpen] = React.useState({ review: true });
    const wasRunning = useRef(false);

    useEffect(() => {
        if (wasRunning.current && status && !status.running) onChanged && onChanged();
        wasRunning.current = !!status?.running;
    }, [status?.running]);

    const start = async () => {
        setError(null);
        const d = await postJson('/api/scrape-queue/start', {
            include_media: includeMedia, recheck,
            media: BULK_MEDIA.filter(m => media[m.key]).map(m => m.key),
        });
        if (!d.success) setError(d.error || 'Could not start');
        refresh();
        RM.tasksChanged();
    };
    const stop = async () => { await postJson('/api/scrape-queue/stop', {}); refresh(); RM.tasksChanged(); };

    const s = status || {};
    const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
    const hasResults = (s.applied || []).length || (s.review || []).length || (s.failed || []).length;

    const list = (key, title, items, render) => items.length > 0 && (
        <div style={{marginTop: 12}}>
            <button onClick={() => setOpen(o => ({ ...o, [key]: !o[key] }))}
                style={{background: 'none', border: 'none', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '4px 0'}}>
                <span style={{color: 'var(--text-secondary)', marginRight: 6}}>{open[key] ? '▾' : '▸'}</span>{title} ({items.length})
            </button>
            {open[key] && (
                <div style={{display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4, maxHeight: 320, overflowY: 'auto'}}>
                    {items.map((item, i) => (
                        <div key={i} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>
                            <div style={{flex: 1, minWidth: 0}}>
                                <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{item.name}</div>
                                <div style={{color: 'var(--text-secondary)', fontSize: 12}}>{item.system_name} · {render(item)}</div>
                            </div>
                            <a className="btn btn-secondary btn-small" href={gameLink(item.system, item.rom_path)} style={{textDecoration: 'none', flexShrink: 0}}>Open</a>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Library scrape</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16, maxWidth: 640}}>
                Scrapes every system from ScreenScraper in the background; you can close this and keep using the app.
                Confident matches fill empty fields and add media a game doesn't have yet. Uncertain ones are listed for you to check.
                Each gamelist is backed up before its first change.
            </div>

            {s.running ? (
                <div>
                    <div style={{height: 8, background: 'var(--bg-tertiary)', borderRadius: 4, overflow: 'hidden', marginBottom: 8}}>
                        <div style={{height: '100%', width: `${pct}%`, background: 'var(--accent-pink)', transition: 'width .3s'}} />
                    </div>
                    <div style={{fontSize: 13, marginBottom: 12}}>
                        {s.done} of {s.total} · {(s.applied || []).length} filled · {(s.review || []).length} to review
                        {s.current && <div style={{color: 'var(--text-secondary)', marginTop: 4}}>Now: {s.current.name} ({s.current.system_name})</div>}
                    </div>
                    <button className="btn btn-secondary" onClick={stop} disabled={s.stopping}>{s.stopping ? 'Stopping after this game...' : 'Stop'}</button>
                </div>
            ) : (
                <div>
                    <label style={{display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, marginBottom: 8}}>
                        <input type="checkbox" checked disabled /> Games missing metadata
                    </label>
                    <label style={{display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, marginBottom: 8}}>
                        <input type="checkbox" checked={includeMedia} onChange={e => setIncludeMedia(e.target.checked)} /> Also games that have metadata but are missing media
                    </label>
                    <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px 14px', margin: '4px 0 12px 24px', fontSize: 13}}>
                        {BULK_MEDIA.map(m => (
                            <label key={m.key} style={{display: 'flex', gap: 6, alignItems: 'center'}}>
                                <input type="checkbox" checked={!!media[m.key]} onChange={e => setMedia(prev => ({ ...prev, [m.key]: e.target.checked }))} /> {m.label}
                            </label>
                        ))}
                    </div>
                    <label style={{display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, marginBottom: 16, color: 'var(--text-secondary)'}}>
                        <input type="checkbox" checked={recheck} onChange={e => setRecheck(e.target.checked)} /> Recheck games already checked in the last 30 days
                    </label>
                    <button className="btn btn-primary" onClick={start}>Start library scrape</button>
                    {error && <div style={{color: 'var(--accent-pink)', marginTop: 8}}>{error}</div>}
                    {s.finished && (
                        <div style={{marginTop: 16, fontSize: 13, color: s.stopped_reason && s.stopped_reason !== 'Stopped' ? 'var(--accent-pink)' : 'var(--text-secondary)'}}>
                            Last run finished {new Date(s.finished).toLocaleString()}: {s.done} of {s.total} checked
                            {s.skipped_recent ? `, ${s.skipped_recent} skipped (checked recently)` : ''}
                            {s.stopped_reason ? `. ${s.stopped_reason === 'Stopped' ? 'Stopped by you' : `Stopped: ${s.stopped_reason}`}.` : '.'}
                        </div>
                    )}
                </div>
            )}

            {hasResults ? (
                <div style={{marginTop: 8}}>
                    {list('review', 'Needs a look', s.review || [], item => item.match
                        ? <>best guess <b>{item.match.nom}</b>{item.match.year ? ` (${item.match.year})` : ''} · <span style={{color: CONFIDENCE[item.confidence]?.color}}>{CONFIDENCE[item.confidence]?.label}</span></>
                        : 'no match found')}
                    {list('applied', 'Filled', s.applied || [], item => [
                        item.filled?.length ? `${item.filled.length} field${item.filled.length > 1 ? 's' : ''}` : null,
                        item.downloaded?.length ? item.downloaded.map(mediaSourceLabel).join(', ') : null,
                    ].filter(Boolean).join(' · ') || 'nothing new')}
                    {list('failed', 'Failed', s.failed || [], item => item.error)}
                </div>
            ) : null}
        </Modal>
    );
}

const thumbUrl = (height, mediaPath) => `${API_BASE}/api/thumb/${height}/${String(mediaPath).split('/').map(encodeURIComponent).join('/')}`;

// Which games lack which media: per-system counts, then a grid for one system
function MissingMediaPanel({ onClose, onScrape }) {
    const [overview, setOverview] = React.useState(null);
    const [folders, setFolders] = React.useState([]);
    const [system, setSystem] = React.useState(null);
    const [detail, setDetail] = React.useState(null);
    const [filter, setFilter] = React.useState('box2d');
    const [error, setError] = React.useState(null);
    // Games ticked to have a Mix generated (the Mix filter), and what's being generated:
    // {games: [...]} for the ticked ones, {generated: true, systems?} to make generated ones again
    const [picked, setPicked] = React.useState({});
    const [mixGames, setMixGames] = React.useState(null);
    const [reload, setReload] = React.useState(0);

    useEffect(() => {
        fetch(`${API_BASE}/api/missing-media`).then(r => r.json())
            .then(d => { if (d.success) { setOverview(d.systems); setFolders(d.folders); } else setError(d.error); })
            .catch(e => setError(e.message));
    }, [reload]);
    useEffect(() => {
        if (!system) return;
        setDetail(null);
        setPicked({});
        fetch(`${API_BASE}/api/missing-media?system=${encodeURIComponent(system)}`).then(r => r.json())
            .then(d => d.success ? setDetail(d.systems[0]) : setError(d.error))
            .catch(e => setError(e.message));
    }, [system, reload]);

    const scrapeable = new Set(BULK_MEDIA.map(m => m.key));
    const startScrape = async (media) => {
        const d = await postJson('/api/scrape-queue/start', { systems: [system], include_media: true, media });
        if (d.success) { RM.tasksChanged(); onScrape && onScrape(); } else setError(d.error || 'Could not start the scrape');
    };

    const countCell = (n, total) => (
        <span style={{color: !n ? 'var(--success)' : n === total ? 'var(--accent-pink)' : 'var(--accent-orange)', fontWeight: n ? 600 : 400}}>
            {n ? n : '✓'}
        </span>
    );

    if (mixGames) {
        return <MixGeneratePanel selection={mixGames} onBack={() => setMixGames(null)} onClose={onClose} onDone={() => setReload(n => n + 1)} />;
    }

    let body;
    if (error) body = <div style={{color: 'var(--accent-pink)'}}>{error}</div>;
    else if (!overview) body = <div style={{color: 'var(--text-secondary)'}}>Checking every system...</div>;
    else if (!system) body = (
        <div style={{overflowX: 'auto'}}>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 13}}>
                <thead>
                    <tr style={{borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)'}}>
                        <th style={{textAlign: 'left', padding: '8px 6px'}}>System</th>
                        <th style={{padding: '8px 6px', fontWeight: 500}}>Games</th>
                        {folders.map(f => <th key={f} style={{padding: '8px 6px', fontWeight: 500}}>{mediaSourceLabel(f)}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {overview.map(s => (
                        <tr key={s.system} onClick={() => setSystem(s.system)} style={{borderBottom: '1px solid var(--border-color)', cursor: 'pointer'}}
                            title={`Show ${s.full_name}'s games`}>
                            <td style={{padding: '8px 6px', whiteSpace: 'nowrap'}}>{s.full_name}</td>
                            <td style={{padding: '8px 6px', textAlign: 'center', color: 'var(--text-secondary)'}}>{s.total}</td>
                            {folders.map(f => <td key={f} style={{padding: '8px 6px', textAlign: 'center'}}>{countCell(s.missing[f], s.total)}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
            <div style={{fontSize: 12, color: 'var(--text-secondary)', marginTop: 8}}>Numbers are games missing that media. Click a system to see them.</div>
            {(() => {
                const made = overview.reduce((sum, s) => sum + (s.mix_generated || 0), 0);
                return made > 0 && (
                    <div style={{fontSize: 13, marginTop: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap'}}>
                        <span>{made} Mix picture{made === 1 ? ' was' : 's were'} generated by RetroManager.</span>
                        <button className="btn btn-secondary btn-small" onClick={() => setMixGames({ generated: true })}
                            title="Make them again, with the template as it is now. You review them before anything is replaced.">Regenerate {made === 1 ? 'it' : 'them all'}</button>
                    </div>
                );
            })()}
        </div>
    );
    else {
        const games = detail ? detail.games.filter(g => filter === 'any' ? folders.some(f => !g.media[f]) : !g.media[filter]) : [];
        // A Mix can be made here, from the game's other media, as well as scraped
        const picking = filter === 'mix';
        const chosen = picking ? games.filter(g => picked[g.path]) : [];
        body = (
            <>
                <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                    <button className="btn btn-secondary btn-small" onClick={() => setSystem(null)}>‹ All systems</button>
                    <b>{detail?.full_name || system}</b>
                    <span style={{color: 'var(--text-secondary)', fontSize: 13}}>games missing</span>
                    <select value={filter} onChange={e => setFilter(e.target.value)}>
                        <option value="any">any media</option>
                        {folders.map(f => <option key={f} value={f}>{mediaSourceLabel(f)}{detail ? ` (${detail.missing[f]})` : ''}</option>)}
                    </select>
                    {picking && detail && detail.mix_generated > 0 && (
                        <button className="btn btn-secondary btn-small" style={{marginLeft: 'auto'}} onClick={() => setMixGames({ generated: true, systems: [system] })}
                            title="Make this system's generated Mix pictures again, with the template as it is now. You review them before anything is replaced.">
                            Regenerate {detail.mix_generated} generated
                        </button>
                    )}
                    {picking && games.length > 0 && (
                        <>
                            <label style={{marginLeft: detail && detail.mix_generated > 0 ? 0 : 'auto', fontSize: 13}}>
                                <input type="checkbox" checked={chosen.length === games.length}
                                    onChange={e => setPicked(e.target.checked ? Object.fromEntries(games.map(g => [g.path, true])) : {})} /> Select all
                            </label>
                            <button className="btn btn-primary btn-small" disabled={!chosen.length} title="Make a Mix from each game’s own screenshot, box and logo. You review them before anything is saved."
                                onClick={() => setMixGames({ games: chosen.map(g => ({ system, rom_path: g.path })) })}>
                                Generate Mix{chosen.length ? ` (${chosen.length})` : ''}
                            </button>
                        </>
                    )}
                    {detail && (filter === 'any' || scrapeable.has(filter)) && games.length > 0 && (
                        <button className={`btn btn-small ${picking ? 'btn-secondary' : 'btn-primary'}`} style={picking ? {} : {marginLeft: 'auto'}}
                            onClick={() => startScrape(filter === 'any' ? [...scrapeable] : [filter])}>
                            Scrape {filter === 'any' ? 'missing media' : mediaSourceLabel(filter)} for these
                        </button>
                    )}
                </div>
                {!detail ? <div style={{color: 'var(--text-secondary)'}}>Loading...</div> : games.length === 0 ? (
                    <div style={{color: 'var(--text-secondary)', padding: '20px 0'}}>Every game has it.</div>
                ) : (
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, maxHeight: '60vh', overflowY: 'auto'}}>
                        {games.map(g => {
                            const art = g.media.box2d || g.media.screenshot || g.media.wheel;
                            const lacking = folders.filter(f => !g.media[f]);
                            return (
                                <a key={g.path} href={gameLink(system, g.path)} title={`Missing: ${lacking.map(mediaSourceLabel).join(', ')}`}
                                    style={{textDecoration: 'none', color: 'inherit', background: 'var(--bg-tertiary)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative'}}>
                                    {picking && (
                                        <input type="checkbox" checked={!!picked[g.path]} aria-label={`Generate a Mix for ${g.name}`}
                                            style={{position: 'absolute', top: 6, left: 6, width: 18, height: 18, zIndex: 1}}
                                            onClick={e => e.stopPropagation()}
                                            onChange={e => setPicked(prev => ({ ...prev, [g.path]: e.target.checked }))} />
                                    )}
                                    <div style={{aspectRatio: '3 / 4', background: 'var(--bg-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                                        {art ? <img src={thumbUrl(320, art)} alt="" loading="lazy" style={{width: '100%', height: '100%', objectFit: 'contain'}} />
                                             : <span style={{fontSize: 28, opacity: 0.4}}>🎮</span>}
                                    </div>
                                    <div style={{padding: '6px 8px', fontSize: 12}}>
                                        <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{g.name}</div>
                                        <div style={{color: 'var(--text-secondary)', fontSize: 11, marginTop: 2}}>{lacking.length} missing</div>
                                    </div>
                                </a>
                            );
                        })}
                    </div>
                )}
            </>
        );
    }

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Missing media</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16}}>Media found by file name in each system's media folders.</div>
            {body}
        </Modal>
    );
}
