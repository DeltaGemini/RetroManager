// Tools: storage, what RetroManager has set aside and the caches it keeps, and deleting them.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const STORAGE_AGES = [[7, 'a week'], [30, 'a month'], [90, '3 months'], [180, '6 months'], [365, 'a year']];
const storageQuery = (params) => new URLSearchParams(params).toString();

// What putting a gamelist copy back would change, or a text file's changed lines
function StorageDiff({ area, item, rel }) {
    const [diff, setDiff] = React.useState(null);
    useEffect(() => {
        fetch(`${API_BASE}/api/storage/diff?${storageQuery({ area, item, rel })}`).then(r => r.json()).then(setDiff)
            .catch(e => setDiff({ success: false, error: e.message }));
    }, [area, item, rel]);
    if (!diff) return <div style={{color: 'var(--text-secondary)', fontSize: 12}}>Comparing…</div>;
    if (!diff.success) return <div style={{color: 'var(--accent-pink)', fontSize: 12}}>{diff.error}</div>;
    const box = {maxHeight: 280, overflowY: 'auto', background: 'var(--bg-secondary)', borderRadius: 4, padding: 8, fontSize: 12};
    if (diff.gamelist) {
        const { added, removed, changed } = diff.gamelist;
        if (!added.length && !removed.length && !changed.length) return <div style={{fontSize: 12, color: 'var(--success)'}}>Its entries are the same as the gamelist's now.</div>;
        return (
            <div style={box}>
                <div style={{marginBottom: 6}}>Putting this copy back would bring back <b>{added.length}</b> game{added.length === 1 ? '' : 's'}, remove <b>{removed.length}</b> and change <b>{changed.length}</b>.</div>
                {added.slice(0, 50).map(g => <div key={`a${g.path}`} style={{color: 'var(--success)'}}>+ {g.name || g.path}</div>)}
                {removed.slice(0, 50).map(g => <div key={`r${g.path}`} style={{color: 'var(--accent-pink)'}}>− {g.name || g.path}</div>)}
                {changed.slice(0, 100).map(g => (
                    <div key={`c${g.path}`} style={{marginTop: 4}}>
                        <b>{g.name || g.path}</b>
                        {g.fields.map(f => (
                            <div key={f.field} style={{paddingLeft: 10, wordBreak: 'break-word'}}>
                                <span style={{color: 'var(--text-secondary)'}}>{f.field}:</span>{' '}
                                <span style={{color: 'var(--accent-pink)', textDecoration: 'line-through'}}>{String(f.now).slice(0, 160) || '(empty)'}</span>{' → '}
                                <span style={{color: 'var(--success)'}}>{String(f.then).slice(0, 160) || '(empty)'}</span>
                            </div>
                        ))}
                    </div>
                ))}
            </div>
        );
    }
    if (!diff.lines.length) return <div style={{fontSize: 12, color: 'var(--success)'}}>The same as the library's now.</div>;
    return (
        <pre style={{...box, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontFamily: 'monospace'}}>
            {diff.lines.map((line, i) => (
                <div key={i} style={{color: line.startsWith('+') ? 'var(--success)' : line.startsWith('-') ? 'var(--accent-pink)' : line.startsWith('@') ? 'var(--accent-orange)' : 'inherit'}}>{line}</div>
            ))}
            {diff.more > 0 && <div style={{color: 'var(--text-secondary)'}}>… and {diff.more} more lines</div>}
        </pre>
    );
}

// One item's files beside the library's own versions of them
function StorageCompare({ area, item, onClose, onDelete, onRestored }) {
    const [data, setData] = React.useState(null);
    const [open, setOpen] = React.useState({}); // rel -> showing what's different
    useEffect(() => {
        fetch(`${API_BASE}/api/storage/compare?${storageQuery({ area: area.id, item: item.id })}`).then(r => r.json()).then(setData)
            .catch(e => setData({ success: false, error: e.message }));
    }, [area.id, item.id]);
    useEffect(() => {
        const key = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
        window.addEventListener('keydown', key, true);
        return () => window.removeEventListener('keydown', key, true);
    }, []);
    const fileUrl = (rel, side) => `${API_BASE}/api/storage/file?${storageQuery({ area: area.id, item: item.id, rel, side })}`;
    const describe = (f) => f ? `${formatBytes(f.size)} · ${new Date(f.date).toLocaleString()}` : '';
    const side = (f, which) => {
        const info = which === 'aside' ? f.aside : f.now;
        return (
            <div style={{flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4}}>
                <div style={{fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600}}>{which === 'aside' ? 'Set aside' : 'In the library now'}</div>
                {f.kind === 'picture' && info ? (
                    <a href={fileUrl(f.rel, which)} target="_blank" rel="noopener"
                        style={{height: 'clamp(120px, 24vh, 260px)', background: 'var(--bg-secondary)', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden'}}>
                        <img src={fileUrl(f.rel, which)} alt="" loading="lazy" style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain'}} />
                    </a>
                ) : (
                    <div style={{padding: 8, background: 'var(--bg-secondary)', borderRadius: 4, fontSize: 12, minHeight: 34, wordBreak: 'break-word'}}>
                        {info ? <>{which === 'now' && info.name !== f.name ? <div>{info.name}</div> : null}<a href={fileUrl(f.rel, which)} target="_blank" rel="noopener">Open</a></>
                              : <span style={{color: 'var(--text-secondary)'}}>Not in the library now</span>}
                    </div>
                )}
                <div style={{fontSize: 11, color: 'var(--text-secondary)'}}>{describe(info)}</div>
            </div>
        );
    };
    const [system, name] = item.id.split('/');
    const restore = async () => {
        if (!window.confirm(`Put this copy back as ${system}'s gamelist.xml? The gamelist now is backed up first.`)) return;
        const d = await postJson(`/api/systems/${encodeURIComponent(system)}/gamelist-backups/${encodeURIComponent(name)}/restore`, {});
        onRestored(d);
    };
    return ReactDOM.createPortal(
        <div onClick={e => { e.stopPropagation(); onClose(); }}
            style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12}}>
            <div role="dialog" aria-label={`Compare ${item.name}`} onClick={e => e.stopPropagation()}
                style={{background: 'var(--bg-modal)', borderRadius: 8, padding: 16, width: 'min(1100px, 100%)', maxHeight: '100%', display: 'flex', flexDirection: 'column', gap: 12}}>
                <div style={{display: 'flex', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap'}}>
                    <div style={{flex: 1, minWidth: 200}}>
                        <div style={{fontWeight: 700, fontSize: 16, wordBreak: 'break-word'}}>{item.name}</div>
                        <div style={{fontSize: 12, color: 'var(--text-secondary)'}}>{area.name} · {item.date ? new Date(item.date).toLocaleString() : ''} · {formatBytes(item.size)}</div>
                    </div>
                    {data?.restorable && <button className="btn btn-primary btn-small" onClick={restore}>Put this copy back</button>}
                    <button className="btn btn-secondary btn-small" onClick={onDelete}>Delete it</button>
                    <button className="btn btn-secondary btn-small" onClick={onClose}>Close</button>
                </div>
                <div style={{overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10}}>
                    {!data ? <div style={{color: 'var(--text-secondary)'}}>Comparing…</div>
                     : !data.success ? <div style={{color: 'var(--accent-pink)'}}>{data.error}</div>
                     : data.files.map(f => (
                        <div key={f.rel || f.name} style={{padding: 10, background: 'var(--bg-tertiary)', borderRadius: 6}}>
                            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8, fontSize: 13}}>
                                <b style={{wordBreak: 'break-word'}}>{f.rel || f.name}</b>
                                {f.now && (f.same === true ? <span style={{fontSize: 11, color: 'var(--success)'}}>the same as now</span>
                                    : f.same === false ? <span style={{fontSize: 11, color: 'var(--accent-orange)'}}>different from now</span> : null)}
                            </div>
                            <div style={{display: 'flex', gap: 10}}>{side(f, 'aside')}{side(f, 'now')}</div>
                            {f.now && f.same !== true && ['gamelist', 'text'].includes(f.kind) && (
                                <div style={{marginTop: 8}}>
                                    {open[f.rel] ? <StorageDiff area={area.id} item={item.id} rel={f.rel} />
                                        : <button className="btn btn-secondary btn-small" onClick={() => setOpen(prev => ({ ...prev, [f.rel]: true }))}>Show what's different</button>}
                                </div>
                            )}
                        </div>
                    ))}
                    {data?.success && data.total > data.files.length && <div style={{fontSize: 12, color: 'var(--text-secondary)'}}>The first {data.files.length} of {data.total} files.</div>}
                </div>
            </div>
        </div>,
        document.body
    );
}

function StoragePanel({ initialSystem, onClose, showNotification }) {
    const [report, setReport] = React.useState(null);
    const [error, setError] = React.useState(null);
    // From a system's settings: its gamelist backups, open
    const [open, setOpen] = React.useState(() => (initialSystem ? { 'gamelist-backups': true } : {}));
    const [onlySystem, setOnlySystem] = React.useState(initialSystem || null);
    const [ticked, setTicked] = React.useState({}); // area id -> {item id: true}
    const [age, setAge] = React.useState({}); // area id -> days
    const [busy, setBusy] = React.useState(null);
    const [reload, setReload] = React.useState(0);
    const [comparing, setComparing] = React.useState(null); // {area, item}

    useEffect(() => {
        setError(null);
        fetch(`${API_BASE}/api/storage`).then(r => r.json())
            .then(d => d.success ? setReport(d) : setError(d.error))
            .catch(e => setError(e.message));
    }, [reload]);

    const daysOf = (area) => age[area.id] || 90;
    const olderThan = (area) => {
        const cutoff = Date.now() - daysOf(area) * 86400000;
        return area.items.filter(i => i.date && new Date(i.date).getTime() < cutoff);
    };
    const sum = (items) => items.reduce((n, i) => n + i.size, 0);

    const remove = async (area, body, what, items) => {
        const files = items.reduce((n, i) => n + i.files, 0);
        if (!window.confirm(`Delete ${what} from “${area.name}” for good?\n\n${files} file${files === 1 ? '' : 's'}, ${formatBytes(sum(items))}. This can't be undone.`)) return;
        setBusy(area.id);
        try {
            const d = await postJson('/api/storage/delete', { area: area.id, ...body });
            if (d.deleted && d.deleted.length) showNotification(`Deleted ${d.files} file${d.files === 1 ? '' : 's'}, freeing ${formatBytes(d.freed)}`, 'success');
            if (d.errors && d.errors.length) showNotification(`Couldn't delete some: ${d.errors.slice(0, 2).join('; ')}`, 'error');
            if (!d.success && d.error) showNotification(d.error, 'error');
        } catch (e) {
            showNotification(e.message, 'error');
        }
        setTicked(prev => ({ ...prev, [area.id]: {} }));
        setBusy(null);
        setReload(n => n + 1);
    };

    const field = {padding: 5, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13};
    let body;
    if (error) body = <div style={{color: 'var(--accent-pink)'}}>{error}</div>;
    else if (!report) body = <div style={{color: 'var(--text-secondary)'}}>Measuring...</div>;
    else body = (
        <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
            {report.areas.map(area => {
                const picked = area.items.filter(i => (ticked[area.id] || {})[i.id]);
                const old = olderThan(area);
                const isOpen = !!open[area.id];
                const empty = !area.items.length;
                return (
                    <div key={area.id} style={{background: 'var(--bg-tertiary)', borderRadius: 6, padding: 12, opacity: empty ? 0.6 : 1}}>
                        <div style={{display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap'}}>
                            <button onClick={() => setOpen(o => ({ ...o, [area.id]: !o[area.id] }))} disabled={empty}
                                style={{background: 'none', border: 'none', padding: 0, color: 'var(--text-primary)', cursor: empty ? 'default' : 'pointer', fontSize: 15, fontWeight: 600, textAlign: 'left'}}>
                                {!empty && <span style={{color: 'var(--text-secondary)', marginRight: 6}}>{isOpen ? '▾' : '▸'}</span>}{area.name}
                            </button>
                            <span style={{marginLeft: 'auto', fontWeight: 600, whiteSpace: 'nowrap'}}>{empty ? 'Empty' : formatBytes(area.size)}</span>
                        </div>
                        <div style={{fontSize: 12, color: 'var(--text-secondary)', margin: '4px 0 0'}}>
                            {area.help}{!empty && ` ${area.files} file${area.files === 1 ? '' : 's'} in ${area.items.length} item${area.items.length === 1 ? '' : 's'}.`}
                        </div>
                        {!empty && (
                            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 10, fontSize: 13}}>
                                {area.cache ? (
                                    <button className="btn btn-secondary btn-small" disabled={busy === area.id}
                                        onClick={() => remove(area, { all: true }, 'everything', area.items)}>Empty it ({formatBytes(area.size)})</button>
                                ) : (
                                    <>
                                        <span>Older than</span>
                                        <select value={daysOf(area)} onChange={e => setAge(prev => ({ ...prev, [area.id]: Number(e.target.value) }))} style={field} aria-label={`Age for ${area.name}`}>
                                            {STORAGE_AGES.map(([days, label]) => <option key={days} value={days}>{label}</option>)}
                                        </select>
                                        <button className="btn btn-secondary btn-small" disabled={!old.length || busy === area.id}
                                            onClick={() => remove(area, { older_than_days: daysOf(area) }, `everything older than ${STORAGE_AGES.find(a => a[0] === daysOf(area))[1]}`, old)}>
                                            Delete {old.length ? `${old.length} (${formatBytes(sum(old))})` : 'none'}
                                        </button>
                                        <button className="btn btn-secondary btn-small" disabled={busy === area.id}
                                            onClick={() => remove(area, { all: true }, 'everything', area.items)}>Delete all</button>
                                        {picked.length > 0 && (
                                            <button className="btn btn-primary btn-small" disabled={busy === area.id}
                                                onClick={() => remove(area, { items: picked.map(i => i.id) }, `${picked.length} ticked item${picked.length === 1 ? '' : 's'}`, picked)}>
                                                Delete ticked ({formatBytes(sum(picked))})
                                            </button>
                                        )}
                                    </>
                                )}
                                {busy === area.id && <span style={{color: 'var(--text-secondary)'}}>Deleting…</span>}
                            </div>
                        )}
                        {isOpen && !empty && area.id === 'gamelist-backups' && onlySystem && (
                            <div style={{fontSize: 12, marginTop: 8}}>
                                Showing {onlySystem}'s only.{' '}
                                <button onClick={() => setOnlySystem(null)} style={{background: 'none', border: 'none', padding: 0, color: 'var(--accent-orange)', cursor: 'pointer', fontSize: 12, textDecoration: 'underline'}}>Show every system's</button>
                            </div>
                        )}
                        {isOpen && !empty && (
                            <div style={{display: 'flex', flexDirection: 'column', gap: 2, marginTop: 10, maxHeight: 300, overflowY: 'auto'}}>
                                {area.items.filter(item => !(area.id === 'gamelist-backups' && onlySystem) || item.id.startsWith(`${onlySystem}/`)).map(item => (
                                    <label key={item.id} style={{display: 'flex', gap: 8, alignItems: 'center', padding: '4px 6px', background: 'var(--bg-secondary)', borderRadius: 4, fontSize: 12, cursor: area.cache ? 'default' : 'pointer'}}>
                                        {!area.cache && <input type="checkbox" checked={!!(ticked[area.id] || {})[item.id]}
                                            onChange={e => setTicked(prev => ({ ...prev, [area.id]: { ...(prev[area.id] || {}), [item.id]: e.target.checked } }))} />}
                                        <span style={{flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}} title={item.name}>{item.name}</span>
                                        <span style={{color: 'var(--text-secondary)', whiteSpace: 'nowrap'}}>{item.date ? new Date(item.date).toLocaleDateString() : ''}</span>
                                        <span style={{color: 'var(--text-secondary)', whiteSpace: 'nowrap', minWidth: 64, textAlign: 'right'}}>{formatBytes(item.size)}</span>
                                        {!area.cache && (
                                            <button className="btn btn-secondary btn-small" style={{padding: '2px 8px'}} title="Compare with what's in the library now"
                                                onClick={e => { e.preventDefault(); setComparing({ area, item }); }}>Compare</button>
                                        )}
                                    </label>
                                ))}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Storage</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 720}}>
                RetroManager sets things aside rather than deleting them. Here's what it's keeping{report ? `: ${formatBytes(report.total)} in all` : ''}.
                Deleting here is for good. Open an area to see what's in it, compare an item with what's in the library now, and tick items to delete just those.
            </div>
            {body}
            {comparing && (
                <StorageCompare area={comparing.area} item={comparing.item} onClose={() => setComparing(null)}
                    onDelete={() => { const { area, item } = comparing; setComparing(null); remove(area, { items: [item.id] }, `“${item.name}”`, [item]); }}
                    onRestored={d => {
                        setComparing(null);
                        showNotification(d.success ? 'Put back. The gamelist it replaced was backed up first.' : (d.error || "Couldn't put it back"), d.success ? 'success' : 'error');
                        setReload(n => n + 1);
                    }} />
            )}
        </Modal>
    );
}
