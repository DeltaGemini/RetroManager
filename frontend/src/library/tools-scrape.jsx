// Tools: the background scrape (every system, on the server).
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

// Progress of the background scrape, polled while it runs
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
            <h2 style={{marginBottom: 4}}>Background scrape</h2>
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
                    <button className="btn btn-primary" onClick={start}>Start the background scrape</button>
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
