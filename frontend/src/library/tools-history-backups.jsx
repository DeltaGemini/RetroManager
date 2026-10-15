// Tools: play history and gamelist backups.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function PlayHistoryPanel({ onClose }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [person, setPerson] = React.useState('all');
    const [limit, setLimit] = React.useState(30);
    useEffect(() => {
        fetch(`${API_BASE}/api/play-history`).then(r => r.json())
            .then(d => d.success ? setData(d) : setError(d.error)).catch(e => setError(e.message));
    }, []);

    const lastFor = (g) => person === 'all' ? g.last : (g.profiles[person] || 0);
    const games = (data?.games || []).filter(g => lastFor(g) > 0).sort((a, b) => lastFor(b) - lastFor(a));
    const mostPlayed = (data?.games || []).filter(g => g.playcount > 0).sort((a, b) => b.playcount - a.playcount).slice(0, 10);
    const monthAgo = Date.now() / 1000 - 30 * 86400;
    const bySystem = {};
    games.forEach(g => {
        const s = bySystem[g.full_name] || (bySystem[g.full_name] = { ever: 0, month: 0 });
        s.ever++;
        if (lastFor(g) >= monthAgo) s.month++;
    });
    const people = data ? ['all', ...data.people, 'shared'] : [];
    const personLabel = (p) => p === 'all' ? 'Everyone' : p === 'shared' ? 'Shared saves' : capitalize(p);

    const row = (g, extra) => (
        <a key={`${g.system}/${g.rom_path}`} href={gameLink(g.system, g.rom_path)}
            style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, textDecoration: 'none', color: 'inherit'}}>
            <div style={{width: 36, height: 48, flexShrink: 0, borderRadius: 3, overflow: 'hidden', background: 'var(--bg-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                {g.box2d ? <img src={thumbUrl(160, g.box2d)} alt="" loading="lazy" style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : <span style={{opacity: 0.4}}>🎮</span>}
            </div>
            <div style={{flex: 1, minWidth: 0}}>
                <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{g.name}</div>
                <div style={{color: 'var(--text-secondary)', fontSize: 12}}>{g.full_name}</div>
            </div>
            <div style={{textAlign: 'right', fontSize: 12, flexShrink: 0}}>{extra}</div>
        </a>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Play history</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 640}}>
                When each game's saves and save states were last written, and by whom.
                {data && !data.games.some(g => g.playcount) && ' EmulationStation isn’t recording play counts in the gamelists, so saves are the only record.'}
            </div>
            {error && <div style={{color: 'var(--accent-pink)'}}>{error}</div>}
            {!data && !error && <div style={{color: 'var(--text-secondary)'}}>Reading saves...</div>}
            {data && (
                <>
                    <div role="tablist" style={{display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14}}>
                        {people.map(p => (
                            <button key={p} role="tab" aria-selected={person === p} className={`btn btn-small ${person === p ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => { setPerson(p); setLimit(30); }}>{personLabel(p)}</button>
                        ))}
                    </div>
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20}}>
                        <div>
                            <h3 style={{fontSize: 14, marginBottom: 8}}>Recently played <span style={{color: 'var(--text-secondary)', fontWeight: 400}}>({games.length})</span></h3>
                            <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
                                {games.length === 0 && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No saves yet.</div>}
                                {games.slice(0, limit).map(g => row(g, (
                                    <>
                                        <div title={new Date(lastFor(g) * 1000).toLocaleString()}>{timeAgo(lastFor(g) * 1000)}</div>
                                        {person === 'all' && g.last_by && <div style={{color: 'var(--text-secondary)'}}>{personLabel(g.last_by)}</div>}
                                    </>
                                )))}
                                {games.length > limit && (
                                    <button className="btn btn-secondary btn-small" style={{alignSelf: 'flex-start'}} onClick={() => setLimit(l => l + 50)}>Show more</button>
                                )}
                            </div>
                        </div>
                        <div>
                            <h3 style={{fontSize: 14, marginBottom: 8}}>By system</h3>
                            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 20}}>
                                <thead>
                                    <tr style={{color: 'var(--text-secondary)', borderBottom: '1px solid var(--border-color)'}}>
                                        <th style={{textAlign: 'left', padding: '6px 4px', fontWeight: 500}}>System</th>
                                        <th style={{padding: '6px 4px', fontWeight: 500}}>Last 30 days</th>
                                        <th style={{padding: '6px 4px', fontWeight: 500}}>Ever</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {Object.entries(bySystem).sort((a, b) => b[1].month - a[1].month || b[1].ever - a[1].ever).map(([name, s]) => (
                                        <tr key={name} style={{borderBottom: '1px solid var(--border-color)'}}>
                                            <td style={{padding: '6px 4px'}}>{name}</td>
                                            <td style={{padding: '6px 4px', textAlign: 'center'}}>{s.month || '·'}</td>
                                            <td style={{padding: '6px 4px', textAlign: 'center'}}>{s.ever}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {mostPlayed.length > 0 && (
                                <>
                                    <h3 style={{fontSize: 14, marginBottom: 8}}>Most played (EmulationStation count)</h3>
                                    <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
                                        {mostPlayed.map(g => row(g, <div>{g.playcount}×</div>))}
                                    </div>
                                </>
                            )}
                            {data.unmatched > 0 && (
                                <div style={{color: 'var(--text-secondary)', fontSize: 12}}>{data.unmatched} save files didn't match a game in the library.</div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </Modal>
    );
}

// Every saved copy of a system's gamelist: what restoring it would change
function BackupsPanel({ systems, initialSystem, onClose, onChanged, showNotification }) {
    const [system, setSystem] = React.useState(initialSystem || systems.find(s => s.rom_count)?.name || '');
    const [list, setList] = React.useState(null);
    const [picked, setPicked] = React.useState(null);
    const [diff, setDiff] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [expanded, setExpanded] = React.useState({});
    const base = `${API_BASE}/api/systems/${encodeURIComponent(system)}/gamelist-backups`;

    const load = () => {
        setList(null);
        return fetch(base).then(r => r.json()).then(d => setList(d.success ? d : { backups: [], error: d.error }));
    };
    useEffect(() => { if (system) { setPicked(null); load(); } }, [system]);
    useEffect(() => {
        setDiff(null);
        setExpanded({});
        if (!picked) return;
        fetch(`${base}/${encodeURIComponent(picked)}/diff`).then(r => r.json()).then(setDiff);
    }, [picked]);

    const restore = async () => {
        if (!window.confirm(`Replace ${system}'s gamelist.xml with ${picked}? The current one is backed up first.`)) return;
        setBusy(true);
        const d = await postJson(`/api/systems/${encodeURIComponent(system)}/gamelist-backups/${encodeURIComponent(picked)}/restore`, {});
        setBusy(false);
        if (d.success) {
            showNotification(`Restored ${picked}. The previous gamelist is saved as ${d.backup}.`, 'success');
            setPicked(null);
            load();
            onChanged && onChanged();
        } else showNotification(d.error || 'Restore failed', 'error');
    };
    const remove = async (name) => {
        if (!window.confirm(`Delete ${name}? This can't be undone.`)) return;
        const d = await (await fetch(`${base}/${encodeURIComponent(name)}`, { method: 'DELETE' })).json();
        if (d.success) { if (picked === name) setPicked(null); load(); } else showNotification(d.error || 'Delete failed', 'error');
    };
    const dated = (list?.backups || []).filter(b => b.kind === 'Backup');
    const prune = async () => {
        if (!window.confirm(`Delete ${dated.length - 10} older dated backups, keeping the newest 10?`)) return;
        const d = await postJson(`/api/systems/${encodeURIComponent(system)}/gamelist-backups/prune`, { keep: 10 });
        if (d.success) { showNotification(`Deleted ${d.removed.length} old backups`, 'success'); load(); }
    };

    const clip = (text, key) => {
        if (!text) return <i style={{color: 'var(--text-secondary)'}}>empty</i>;
        if (text.length <= 140 || expanded[key]) return text;
        return <>{text.slice(0, 140)}… <button onClick={() => setExpanded(e => ({ ...e, [key]: true }))} style={{background: 'none', border: 'none', color: 'var(--accent-blue)', cursor: 'pointer', padding: 0}}>more</button></>;
    };
    const group = (title, items, render, color) => items.length > 0 && (
        <div style={{marginBottom: 14}}>
            <h4 style={{fontSize: 13, margin: '0 0 6px', color}}>{title} ({items.length})</h4>
            <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>{items.map(render)}</div>
        </div>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Gamelist backups</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14}}>
                Every fix makes a dated copy of gamelist.xml first. Pick one to see what restoring it would change.
            </div>
            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                <select value={system} onChange={e => setSystem(e.target.value)}>
                    {systems.filter(s => s.rom_count).map(s => <option key={s.name} value={s.name}>{s.full_name || s.name}</option>)}
                </select>
                {list && <span style={{fontSize: 13, color: 'var(--text-secondary)'}}>{list.backups.length} copies · current gamelist has {list.current_entries} entries</span>}
                {dated.length > 10 && <button className="btn btn-secondary btn-small" style={{marginLeft: 'auto'}} onClick={prune}>Keep newest 10 backups</button>}
            </div>
            <div style={{display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) minmax(0, 2fr)', gap: 16}} className="backups-grid">
                <div style={{display: 'flex', flexDirection: 'column', gap: 4, maxHeight: '60vh', overflowY: 'auto'}}>
                    {!list && <div style={{color: 'var(--text-secondary)'}}>Loading...</div>}
                    {list && list.backups.length === 0 && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No copies for this system.</div>}
                    {(list?.backups || []).map(b => (
                        <button key={b.name} onClick={() => setPicked(b.name)}
                            style={{textAlign: 'left', padding: '8px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)',
                                    background: picked === b.name ? 'var(--bg-secondary)' : 'var(--bg-tertiary)',
                                    border: `1px solid ${picked === b.name ? 'var(--accent-pink)' : 'transparent'}`}}>
                            <div>{new Date(b.modified).toLocaleString()}</div>
                            <div style={{color: 'var(--text-secondary)', fontSize: 11}}>
                                {b.kind} · {b.entries ?? '?'} entries{b.kind !== 'Backup' ? ` · ${b.name}` : ''}
                            </div>
                        </button>
                    ))}
                </div>
                <div style={{minWidth: 0, maxHeight: '60vh', overflowY: 'auto'}}>
                    {!picked ? <div style={{color: 'var(--text-secondary)', fontSize: 13}}>Pick a copy on the left.</div> : !diff ? (
                        <div style={{color: 'var(--text-secondary)'}}>Comparing...</div>
                    ) : !diff.success ? <div style={{color: 'var(--accent-pink)'}}>{diff.error}</div> : (
                        <>
                            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                                <span style={{fontSize: 13, flex: 1}}>
                                    {diff.added.length + diff.removed.length + diff.changed.length === 0
                                        ? 'Identical to the current gamelist.'
                                        : 'Restoring this copy would:'}
                                </span>
                                <button className="btn btn-primary btn-small" disabled={busy} onClick={restore}>Restore this copy</button>
                                <button className="btn btn-secondary btn-small" onClick={() => remove(picked)}>Delete</button>
                            </div>
                            {group('Bring back entries', diff.added, e => (
                                <div key={e.path} style={{padding: '4px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>{e.name || e.path}</div>
                            ), 'var(--success)')}
                            {group('Remove entries', diff.removed, e => (
                                <div key={e.path} style={{padding: '4px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>{e.name || e.path}</div>
                            ), 'var(--accent-pink)')}
                            {group('Change entries', diff.changed, c => (
                                <div key={c.path} style={{padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>
                                    <div style={{fontWeight: 600, marginBottom: 4}}>{c.name || c.path}</div>
                                    {c.fields.map(f => (
                                        <div key={f.field} style={{display: 'grid', gridTemplateColumns: '90px 1fr', gap: 8, fontSize: 12, marginBottom: 2}}>
                                            <span style={{color: 'var(--text-secondary)'}}>{f.field}</span>
                                            <span style={{wordBreak: 'break-word'}}>
                                                <span style={{textDecoration: 'line-through', color: 'var(--text-secondary)'}}>{clip(f.now, `${c.path}:${f.field}:now`)}</span>
                                                {' → '}{clip(f.then, `${c.path}:${f.field}:then`)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            ), 'var(--accent-orange)')}
                        </>
                    )}
                </div>
            </div>
        </Modal>
    );
}
