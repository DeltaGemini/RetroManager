// Tools: the Media viewer, one kind of media for every game of every system, with
// how many games each system is missing of each kind, and Mix pictures made here.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// The shape each kind of picture is shown in
const VIEWER_ASPECT = { box2d: '3 / 4', box3d: '3 / 4', boxside: '1 / 3', support: '1 / 1' };
const VIEWER_KIND_KEY = 'rm-media-viewer-kind';
const VIEWER_SIZE_KEY = 'rm-media-viewer-size';
// Kinds that aren't pictures: shown as a tile saying the game has one
const VIEWER_FILES = { manuals: '📄 Manual', videos: '🎬 Video' };

// `options` (from Fill the gaps, or coming back from it): {system, kind, show} to open on
function MediaViewerPanel({ options, onClose }) {
    const [kind, setKind] = React.useState(() => {
        if (options && options.kind) return options.kind;
        try { return localStorage.getItem(VIEWER_KIND_KEY) || 'box2d'; } catch (e) { return 'box2d'; }
    });
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [system, setSystem] = React.useState((options && options.system) || '');
    const [show, setShow] = React.useState((options && options.show) || 'all'); // all | has | missing
    const [search, setSearch] = React.useState('');
    const [picked, setPicked] = React.useState({}); // key -> true
    const [reload, setReload] = React.useState(0);
    // Tile width in pixels, from the size slider (spines are drawn a third as wide)
    const [size, setSize] = React.useState(() => {
        const fallback = window.innerWidth < 600 ? 130 : 180; // two to a row on a phone
        try { return Number(localStorage.getItem(VIEWER_SIZE_KEY)) || fallback; } catch (e) { return fallback; }
    });
    useEffect(() => { try { localStorage.setItem(VIEWER_SIZE_KEY, String(size)); } catch (e) {} }, [size]);
    const [broken, setBroken] = React.useState({}); // pictures that wouldn't load -> true
    const lastClicked = useRef(null);
    // Asked before picked games are let go: {kind} when changing kind, {} for Clear
    const [asking, setAsking] = React.useState(null);
    // How many games each system is missing of each kind (fetched when first wanted: it scans every system)
    const [overview, setOverview] = React.useState(null);
    const [overviewOpen, setOverviewOpen] = React.useState(false);
    const [mixGames, setMixGames] = React.useState(null); // what Generate Mix is making: {games} or {generated, systems?}
    useEffect(() => {
        if (!(overviewOpen || kind === 'mix') || (overview && overview.reload === reload)) return;
        fetch(`${API_BASE}/api/missing-media`).then(r => r.json())
            .then(d => d.success && setOverview({ ...d, reload }))
            .catch(() => {});
    }, [overviewOpen, kind, reload]);
    // A count in the table: that system's games missing that kind
    const jump = (systemName, folder) => {
        setOverviewOpen(false);
        setSystem(systemName);
        setShow('missing');
        if (folder !== kind) { if (chosen.length) setAsking({ kind: folder }); else setKind(folder); }
    };

    useEffect(() => {
        try { localStorage.setItem(VIEWER_KIND_KEY, kind); } catch (e) {}
        setData(null);
        setError(null);
        setBroken({});
        fetch(`${API_BASE}/api/media-viewer?folder=${encodeURIComponent(kind)}`).then(r => r.json())
            .then(d => d.success ? setData(d) : setError(d.error))
            .catch(e => setError(e.message));
    }, [kind, reload]);

    const keyOf = (g) => `${g.system}|${g.path}`;
    const all = data ? data.games : [];
    const systems = React.useMemo(() => {
        const seen = new Map();
        all.forEach(g => seen.set(g.system, g.system_name));
        return [...seen].sort((a, b) => a[1].localeCompare(b[1]));
    }, [data]);
    const words = search.trim().toLowerCase();
    const games = all.filter(g => (!system || g.system === system)
        && (show === 'all' || (show === 'has') === !!g.picture)
        && (!words || (g.name || g.path).toLowerCase().includes(words)));
    const inSystem = all.filter(g => !system || g.system === system);
    const having = inSystem.filter(g => g.picture).length;
    const chosen = all.filter(g => picked[keyOf(g)]);
    // (the 3D boxes or spines RetroManager made, shown: they can be made again)
    const madeHere = inSystem.filter(g => (g.made || []).includes(kind));

    // A click picks a game; with Shift, every game from the last one clicked
    const toggle = (g, index, shift) => {
        const key = keyOf(g);
        const on = !picked[key];
        if (shift && lastClicked.current !== null) {
            const [from, to] = [Math.min(lastClicked.current, index), Math.max(lastClicked.current, index)];
            setPicked(prev => ({ ...prev, ...Object.fromEntries(games.slice(from, to + 1).map(x => [keyOf(x), on])) }));
        } else {
            setPicked(prev => ({ ...prev, [key]: on }));
        }
        lastClicked.current = index;
    };
    const allShownPicked = games.length > 0 && games.every(g => picked[keyOf(g)]);

    // Fill the gaps, with every source's version beside what each game has
    const fillable = typeof FILL_MEDIA !== 'undefined' && FILL_MEDIA.includes(kind);
    const openFill = (fillOptions) => window.dispatchEvent(new CustomEvent('retromanager:open-tool', {
        detail: { tool: 'fill', options: { ...fillOptions, from: 'viewer', viewer: { system, kind, show } } } }));

    if (mixGames) {
        return <MixGeneratePanel selection={mixGames} onBack={() => setMixGames(null)} onClose={onClose}
            onDone={() => { setPicked({}); setReload(n => n + 1); }} />;
    }

    const field = {padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13};
    const label = mediaSourceLabel(kind);
    const generated = overview ? overview.systems.filter(s => !system || s.system === system).reduce((n, s) => n + (s.mix_generated || 0), 0) : 0;
    return (
        <Modal open={true} onClose={onClose}>
          <div style={{width: 'min(1700px, calc(100vw - 80px))', maxWidth: '100%'}}>
            <h2 style={{marginBottom: 4}}>Media viewer</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12}}>
                One kind of media for every game. Click games to pick them (Shift-click for a run of them), then fill them from every source.{' '}
                <button onClick={() => setOverviewOpen(o => !o)} style={{background: 'none', border: 'none', padding: 0, color: 'var(--accent-orange)', cursor: 'pointer', fontSize: 13, textDecoration: 'underline'}}>
                    {overviewOpen ? 'Hide' : 'What each system is missing'}
                </button>
            </div>
            {overviewOpen && (
                <div style={{overflowX: 'auto', marginBottom: 14, maxHeight: '45vh', overflowY: 'auto'}}>
                    {!overview ? <div style={{color: 'var(--text-secondary)', fontSize: 13}}>Checking every system...</div> : (
                        <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 13}}>
                            <thead>
                                <tr style={{borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)'}}>
                                    <th style={{textAlign: 'left', padding: '6px'}}>System</th>
                                    <th style={{padding: '6px', fontWeight: 500}}>Games</th>
                                    {overview.folders.map(f => <th key={f} style={{padding: '6px', fontWeight: 500}}>{mediaSourceLabel(f)}</th>)}
                                </tr>
                            </thead>
                            <tbody>
                                {overview.systems.map(s => (
                                    <tr key={s.system} style={{borderBottom: '1px solid var(--border-color)'}}>
                                        <td style={{padding: '6px', whiteSpace: 'nowrap'}}>{s.full_name}</td>
                                        <td style={{padding: '6px', textAlign: 'center', color: 'var(--text-secondary)'}}>{s.total}</td>
                                        {overview.folders.map(f => {
                                            const n = s.missing[f];
                                            return (
                                                <td key={f} style={{padding: 2, textAlign: 'center'}}>
                                                    {n ? <span style={{display: 'inline-flex', alignItems: 'center', gap: 2}}>
                                                            <button onClick={() => jump(s.system, f)} title={`${s.full_name}'s games without a ${mediaSourceLabel(f)}`}
                                                                style={{background: 'none', border: 'none', cursor: 'pointer', padding: '4px 6px', fontWeight: 600, fontSize: 13,
                                                                        color: n === s.total ? 'var(--accent-pink)' : 'var(--accent-orange)'}}>{n}</button>
                                                            {typeof FILL_MEDIA !== 'undefined' && FILL_MEDIA.includes(f) && (
                                                                <button onClick={() => openFill({ system: s.system, kinds: [f], show: 'gaps' })} title={`Fill ${s.full_name}'s missing ${mediaSourceLabel(f)}, from every source`}
                                                                    style={{background: 'none', border: '1px solid var(--border-color)', borderRadius: 4, cursor: 'pointer', padding: '0 5px', fontSize: 10, color: 'var(--text-secondary)'}}>Fill</button>
                                                            )}
                                                        </span>
                                                       : <span style={{color: 'var(--success)'}}>✓</span>}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                    {overview && <div style={{fontSize: 12, color: 'var(--text-secondary)', marginTop: 6}}>Numbers are games missing that media. Click one to see them.</div>}
                </div>
            )}
            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10}}>
                <select value={kind} onChange={e => { if (chosen.length) setAsking({ kind: e.target.value }); else setKind(e.target.value); }} style={field} aria-label="Kind of picture">
                    {(data?.folders || ['box2d', 'box3d', 'boxside', 'support', 'screenshot', 'screenshottitle', 'wheel', 'fanart', 'mix', 'manuals', 'videos'])
                        .map(f => <option key={f} value={f}>{mediaSourceLabel(f)}</option>)}
                </select>
                <select value={system} onChange={e => setSystem(e.target.value)} style={field} aria-label="System">
                    <option value="">All systems</option>
                    {systems.map(([name, full]) => <option key={name} value={name}>{full}</option>)}
                </select>
                <select value={show} onChange={e => setShow(e.target.value)} style={field} aria-label="Which games">
                    <option value="all">All games</option>
                    <option value="has">With a {label}</option>
                    <option value="missing">Without a {label}</option>
                </select>
                <input type="search" placeholder="Find a game..." value={search} onChange={e => setSearch(e.target.value)}
                    style={{...field, flex: '1 1 160px', minWidth: 0}} />
            </div>
            <div style={{display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12, fontSize: 13}}>
                {data && <span style={{color: 'var(--text-secondary)'}}>{having} of {inSystem.length} have a {label} · {games.length} shown</span>}
                <label style={{display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto'}} title="Picture size">
                    <span aria-hidden="true" style={{fontSize: 11}}>🖼</span>
                    <input type="range" min={90} max={420} step={10} value={size} onChange={e => setSize(Number(e.target.value))}
                        aria-label="Picture size" style={{width: 110}} />
                    <span aria-hidden="true" style={{fontSize: 17}}>🖼</span>
                </label>
                <label style={{display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer'}}>
                    <input type="checkbox" checked={allShownPicked} disabled={!games.length}
                        onChange={e => setPicked(prev => ({ ...prev, ...Object.fromEntries(games.map(g => [keyOf(g), e.target.checked])) }))} />
                    Pick all shown
                </label>
                {chosen.length > 0 && <button className="btn btn-secondary btn-small" onClick={() => setAsking({})}>Clear ({chosen.length})</button>}
                {['box3d', 'boxside'].includes(kind) && madeHere.length > 0 && (
                    <button className="btn btn-secondary btn-small"
                        onClick={() => openFill({ games: madeHere.map(g => ({ system: g.system, path: g.path })), kinds: [kind], replace: true, start: true, remake: true })}
                        title={`Make the ${label.toLowerCase()} pictures RetroManager made again, from each game's cover as it is now. Fill the gaps shows each beside the one there; nothing is replaced until you apply.`}>
                        Make again {madeHere.length} made
                    </button>
                )}
                {kind === 'mix' && generated > 0 && (
                    <button className="btn btn-secondary btn-small" onClick={() => setMixGames({ generated: true, ...(system ? { systems: [system] } : {}) })}
                        title="Make the Mix pictures RetroManager generated again, with the template as it is now. You review them before anything is replaced.">
                        Regenerate {generated} generated
                    </button>
                )}
                {kind === 'mix' && (
                    <button className="btn btn-secondary btn-small" disabled={!chosen.length}
                        title="Make a Mix from each picked game's own screenshot, box and logo. You review them before anything is saved."
                        onClick={() => setMixGames({ games: chosen.map(g => ({ system: g.system, rom_path: g.path })) })}>
                        Generate Mix{chosen.length ? ` (${chosen.length})` : ''}
                    </button>
                )}
                {fillable && (
                    <button className="btn btn-primary btn-small" disabled={!chosen.length}
                        title={`Every source's ${label} for the picked games, beside what each has, to choose from (Fill the gaps)`}
                        onClick={() => openFill({ games: chosen.map(g => ({ system: g.system, path: g.path })), kinds: [kind], replace: true, start: true })}>
                        Fill {chosen.length || ''} picked
                    </button>
                )}
            </div>
            {asking && ReactDOM.createPortal(
                <div onClick={e => { e.stopPropagation(); setAsking(null); }}
                    style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16}}>
                    <div role="alertdialog" aria-label="Picked games" onClick={e => e.stopPropagation()}
                        style={{background: 'var(--bg-modal)', borderRadius: 8, padding: 20, maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 14}}>
                        <div style={{fontSize: 15}}>
                            {asking.kind
                                ? <>You have <b>{chosen.length}</b> game{chosen.length === 1 ? '' : 's'} picked. Keep {chosen.length === 1 ? 'it' : 'them'} picked for {mediaSourceLabel(asking.kind)}?</>
                                : <>Clear the <b>{chosen.length}</b> picked game{chosen.length === 1 ? '' : 's'}?</>}
                        </div>
                        <div style={{display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap'}}>
                            <button className="btn btn-secondary btn-small" onClick={() => setAsking(null)}>Cancel</button>
                            <button className={`btn btn-small ${asking.kind ? 'btn-secondary' : 'btn-primary'}`}
                                onClick={() => { setPicked({}); if (asking.kind) setKind(asking.kind); setAsking(null); }}>Clear them</button>
                            {asking.kind && <button className="btn btn-primary btn-small" onClick={() => { setKind(asking.kind); setAsking(null); }}>Keep them</button>}
                        </div>
                    </div>
                </div>,
                document.body
            )}
            {error ? <div style={{color: 'var(--accent-pink)'}}>{error}</div>
             : !data ? <div style={{color: 'var(--text-secondary)'}}>Gathering every game's {label}...</div>
             : games.length === 0 ? <div style={{color: 'var(--text-secondary)', padding: '20px 0'}}>No games here.</div>
             : (
                <div style={{display: 'grid', gridTemplateColumns: `repeat(auto-fill, minmax(min(${kind === 'boxside' ? Math.round(size / 3) : size}px, 100%), 1fr))`, gap: 10, maxHeight: '68vh', overflowY: 'auto', padding: 2}}>
                    {games.map((g, i) => {
                        const on = !!picked[keyOf(g)];
                        const title = splitGameName(g.name || g.path).title;
                        return (
                            <div key={keyOf(g)} role="checkbox" aria-checked={on} tabIndex={0}
                                onClick={e => toggle(g, i, e.shiftKey)}
                                onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(g, i, e.shiftKey); } }}
                                title={`${g.name} · ${g.system_name}${g.picture ? '' : ` · no ${label}`}`}
                                style={{background: 'var(--bg-tertiary)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative', cursor: 'pointer',
                                        outline: on ? '3px solid var(--accent-pink)' : 'none', outlineOffset: -1}}>
                                <input type="checkbox" checked={on} readOnly tabIndex={-1} aria-hidden="true"
                                    style={{position: 'absolute', top: 6, left: 6, width: 18, height: 18, zIndex: 1, pointerEvents: 'none'}} />
                                <a href={gameLink(g.system, g.path)} onClick={e => e.stopPropagation()} title="Open the game"
                                    style={{position: 'absolute', top: 4, right: 4, zIndex: 1, fontSize: 12, padding: '2px 6px', borderRadius: 4, background: 'rgba(0,0,0,0.55)', color: 'white', textDecoration: 'none'}}>↗</a>
                                <div style={{aspectRatio: VIEWER_ASPECT[kind] || '4 / 3', background: 'var(--bg-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                                    {g.picture && VIEWER_FILES[kind]
                                        ? <span style={{fontSize: 15, fontWeight: 600}}>{VIEWER_FILES[kind]}</span>
                                        : g.picture && !broken[g.picture]
                                        // (`r` changes after a scrape, so pictures downloaded again are fetched anew)
                                        ? <img src={`${thumbUrl(size > 230 && kind !== 'boxside' ? 480 : 320, g.picture)}?r=${reload}${kind === 'boxside' ? '&spine=1' : ''}`} alt="" loading="lazy"
                                               onError={() => setBroken(prev => ({ ...prev, [g.picture]: true }))}
                                               style={{width: '100%', height: '100%', objectFit: 'contain'}} />
                                        : <span style={{padding: 8, textAlign: 'center', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', overflowWrap: 'anywhere'}}>{title}</span>}
                                </div>
                                <div style={{padding: '6px 8px', fontSize: 12}}>
                                    <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{title}</div>
                                    <div style={{color: 'var(--text-secondary)', fontSize: 11, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{g.system_name}</div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
          </div>
        </Modal>
    );
}
