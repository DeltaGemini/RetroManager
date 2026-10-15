// Tools: collections (rename, delete, see and remove their games), and adding
// many of a system's games to a collection at once.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const sendJson = async (url, method, body) => {
    const res = await fetch(`${API_BASE}${url}`, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    return res.json();
};

// Tools > Collections
function CollectionsPanel({ onClose }) {
    const [collections, setCollections] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [openId, setOpenId] = React.useState(null);
    const [renaming, setRenaming] = React.useState(null);   // {id, name}
    const [deleting, setDeleting] = React.useState(null);   // id awaiting a second click
    const [newName, setNewName] = React.useState('');

    const load = React.useCallback(() => fetch(`${API_BASE}/api/collections`).then(r => r.json())
        .then(d => d.success ? setCollections(d.collections) : setError(d.error || 'Could not load collections'))
        .catch(e => setError(e.message)), []);
    useEffect(() => { load(); }, [load]);

    const run = async (request) => {
        setError(null);
        try {
            const d = await request;
            if (!d.success) { setError(d.error || "That didn't work"); return false; }
            await load();
            announceGameChange();
            return true;
        } catch (e) { setError(e.message); return false; }
    };
    const create = async () => { if (newName.trim() && await run(sendJson('/api/collections', 'POST', { name: newName.trim() }))) setNewName(''); };
    const rename = async () => { if (await run(sendJson(`/api/collections/${renaming.id}`, 'PUT', { name: renaming.name }))) setRenaming(null); };
    const remove = async (id) => { if (await run(sendJson(`/api/collections/${id}`, 'DELETE'))) setDeleting(null); };
    const takeOut = (id, g) => run(sendJson(`/api/collections/${id}/games`, 'PUT', { games: [{ system: g.system, rom_path: g.rom_path }], member: false }));

    const inputStyle = { padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13 };
    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Collections</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 640}}>
                Your own lists of games. Add a game from its page (📁 Collections), or many at once with <b>Bulk › Add to a collection</b> above a system's game list.
                Each one is a Bookcase shelf, a Timeline filter and an EmulationStation custom collection.
            </div>
            {error && <div role="alert" style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {!collections && !error && <div style={{color: 'var(--text-secondary)'}}>Loading...</div>}
            {collections && (
                <>
                    <div style={{display: 'flex', gap: 6, marginBottom: 12}}>
                        <input type="text" value={newName} placeholder="New collection..." maxLength={60} onChange={e => setNewName(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') create(); }} style={{...inputStyle, flex: 1}} />
                        <button className="btn btn-primary btn-small" onClick={create} disabled={!newName.trim()}>Create</button>
                    </div>
                    {!collections.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No collections yet.</div>}
                    <div style={{maxHeight: '56vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6}}>
                        {collections.map(c => {
                            const open = openId === c.id;
                            return (
                                <div key={c.id} style={{background: 'var(--bg-tertiary)', borderRadius: 4}}>
                                    <div style={{display: 'flex', gap: 8, alignItems: 'center', padding: '8px 10px'}}>
                                        {renaming && renaming.id === c.id ? (
                                            <>
                                                <input type="text" autoFocus value={renaming.name} maxLength={60} onChange={e => setRenaming({ id: c.id, name: e.target.value })}
                                                    onKeyDown={e => { if (e.key === 'Enter') rename(); if (e.key === 'Escape') setRenaming(null); }} style={{...inputStyle, flex: 1}} />
                                                <button className="btn btn-primary btn-small" onClick={rename} disabled={!renaming.name.trim()}>Save</button>
                                                <button className="btn btn-secondary btn-small" onClick={() => setRenaming(null)}>Cancel</button>
                                            </>
                                        ) : (
                                            <>
                                                <button onClick={() => setOpenId(open ? null : c.id)} aria-expanded={open}
                                                    style={{flex: 1, minWidth: 0, textAlign: 'left', background: 'none', border: 'none', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: 0}}>
                                                    <span style={{color: 'var(--text-secondary)', display: 'inline-block', width: 14}}>{open ? '▾' : '▸'}</span>
                                                    {c.name} <span style={{color: 'var(--text-secondary)', fontWeight: 400, fontSize: 12}}>{c.games.length} game{c.games.length === 1 ? '' : 's'}</span>
                                                </button>
                                                <button className="btn btn-secondary btn-small" onClick={() => { setRenaming({ id: c.id, name: c.name }); setDeleting(null); }}>Rename</button>
                                                {deleting === c.id ? (
                                                    <>
                                                        <button className="btn btn-primary btn-small" onClick={() => remove(c.id)}>Delete "{c.name}"</button>
                                                        <button className="btn btn-secondary btn-small" onClick={() => setDeleting(null)}>Keep</button>
                                                    </>
                                                ) : (
                                                    <button className="btn btn-secondary btn-small" onClick={() => setDeleting(c.id)} title="Deletes the collection, not its games">Delete</button>
                                                )}
                                            </>
                                        )}
                                    </div>
                                    {open && (
                                        <div style={{padding: '0 10px 10px', display: 'flex', flexDirection: 'column', gap: 4}}>
                                            {!c.games.length && <div style={{color: 'var(--text-secondary)', fontSize: 12}}>Empty. Add games from their pages, or with Bulk above a game list.</div>}
                                            {c.games.map(g => (
                                                <div key={`${g.system}/${g.rom_path}`} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '4px 8px', background: 'var(--bg-secondary)', borderRadius: 4, fontSize: 13}}>
                                                    <a href={gameLink(g.system, g.rom_path)} style={{flex: 1, minWidth: 0, color: 'inherit', textDecoration: 'none'}}>
                                                        <span style={{fontWeight: 600}}>{g.name}</span>
                                                        <span style={{color: 'var(--text-secondary)', fontSize: 12}}> · {g.full_name}</span>
                                                        {g.missing && <span className="status-badge status-missing" style={{marginLeft: 8}} title="No ROM file with this name any more">File gone</span>}
                                                    </a>
                                                    <button className="btn btn-secondary btn-small" onClick={() => takeOut(c.id, g)}>Remove</button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </>
            )}
        </Modal>
    );
}

// "Bulk > Add to a collection" above a system's game list: tick games, pick a collection, add them all
function BulkCollectPanel({ system, games, onClose }) {
    const [collections, setCollections] = React.useState(null);
    const [target, setTarget] = React.useState('');
    const [newName, setNewName] = React.useState('');
    const [picked, setPicked] = React.useState({});
    const [find, setFind] = React.useState('');
    const [message, setMessage] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    useEffect(() => {
        fetch(`${API_BASE}/api/library-state`).then(r => r.json()).then(d => {
            if (!d.success) return;
            setCollections(d.collections);
            setTarget(t => t || (d.collections[0] ? d.collections[0].id : 'new'));
        }).catch(() => {});
    }, []);

    const listed = games.filter(g => g.rom_exists && splitGameName(g.name).title.toLowerCase().includes(find.trim().toLowerCase()));
    const chosen = games.filter(g => picked[g.path]);
    const inTarget = (g) => (g.collections || []).includes(target);
    const add = async () => {
        setBusy(true);
        setMessage(null);
        try {
            let id = target;
            if (target === 'new') {
                const made = await sendJson('/api/collections', 'POST', { name: newName.trim() });
                if (!made.success) { setMessage({ error: true, text: made.error }); return; }
                id = made.collection.id;
                setCollections(prev => [...(prev || []), made.collection]);
                setTarget(id);
                setNewName('');
            }
            const d = await sendJson(`/api/collections/${id}/games`, 'PUT', { games: chosen.map(g => ({ system: system.name, rom_path: g.path })), member: true });
            if (!d.success) { setMessage({ error: true, text: d.error }); return; }
            chosen.forEach(g => { g.collections = [...new Set([...(g.collections || []), id])]; });
            announceGameChange();
            setMessage({ text: `Added ${d.changed} game${d.changed === 1 ? '' : 's'}${chosen.length - d.changed ? ` (${chosen.length - d.changed} were already in it)` : ''}.` });
            setPicked({});
        } catch (e) {
            setMessage({ error: true, text: e.message });
        } finally {
            setBusy(false);
        }
    };
    const selectStyle = { padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13 };

    return (
        <Modal open={true} onClose={busy ? () => {} : onClose}>
            <h2 style={{marginBottom: 4}}>Add to a collection: {system.full_name || system.name}</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12}}>Tick the games, choose the collection, then Add.</div>
            <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10}}>
                <select value={target} onChange={e => setTarget(e.target.value)} aria-label="Collection" style={selectStyle}>
                    {(collections || []).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    <option value="new">New collection...</option>
                </select>
                {target === 'new' && <input type="text" autoFocus value={newName} placeholder="Its name" maxLength={60} onChange={e => setNewName(e.target.value)} style={{...selectStyle, flex: 1, minWidth: 140}} />}
                <input type="search" value={find} placeholder="Find a game" onChange={e => setFind(e.target.value)} style={{...selectStyle, flex: 1, minWidth: 140}} />
            </div>
            <div style={{display: 'flex', gap: 10, alignItems: 'center', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6}}>
                <button className="link-button" onClick={() => setPicked(Object.fromEntries(listed.filter(g => !inTarget(g)).map(g => [g.path, true])))}>Tick all shown</button>
                <button className="link-button" onClick={() => setPicked({})}>Untick all</button>
                <span>{chosen.length} ticked</span>
            </div>
            <div style={{maxHeight: '46vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12}}>
                {listed.map(g => {
                    const n = splitGameName(g.name);
                    return (
                        <label key={g.path} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, cursor: inTarget(g) ? 'default' : 'pointer', opacity: inTarget(g) ? 0.55 : 1}}>
                            <input type="checkbox" disabled={inTarget(g)} checked={inTarget(g) || !!picked[g.path]} onChange={() => setPicked(prev => ({ ...prev, [g.path]: !prev[g.path] }))} />
                            <span style={{flex: 1}}>{n.title} <span style={{color: 'var(--text-secondary)', fontSize: 11}}>{n.tags}</span></span>
                            {inTarget(g) && <span style={{fontSize: 11, color: 'var(--text-secondary)'}}>already in it</span>}
                        </label>
                    );
                })}
                {!listed.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No games match.</div>}
            </div>
            <div style={{display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'flex-end'}}>
                {message && <span role="status" style={{marginRight: 'auto', fontSize: 13, color: message.error ? 'var(--accent-pink)' : 'var(--success)'}}>{message.text}</span>}
                <button className="btn btn-secondary" onClick={onClose} disabled={busy}>Close</button>
                <button className="btn btn-primary" onClick={add} disabled={busy || !chosen.length || (target === 'new' && !newName.trim())}>{busy ? 'Adding...' : `Add ${chosen.length || ''}`.trim()}</button>
            </div>
        </Modal>
    );
}
