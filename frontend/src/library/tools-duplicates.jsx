// Tools: duplicates, every game in the library more than once (by name, and by identical files).
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const DUPLICATE_REASONS = {
    name: { label: 'Same name', help: 'The same title apart from region and version tags, or the same gamelist name' },
    contents: { label: 'Identical files', help: 'The files have exactly the same contents (found by the ROM check)' },
};

function DuplicatesPanel({ initialSystem, onClose, onChanged, showNotification }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [system, setSystem] = React.useState(initialSystem || '');
    const [keeps, setKeeps] = React.useState({}); // group id -> kept copy's key
    const [ticked, setTicked] = React.useState({}); // group id -> true
    const [working, setWorking] = React.useState(false);
    const [reload, setReload] = React.useState(0);

    useEffect(() => {
        setError(null);
        fetch(`${API_BASE}/api/duplicates`).then(r => r.json())
            .then(d => d.success ? setData(d) : setError(d.error))
            .catch(e => setError(e.message));
    }, [reload]);

    const copyKey = (c) => `${c.system}/${c.path}`.toLowerCase();
    const keepOf = (g) => keeps[g.id] || g.keep;
    const all = data ? data.groups : [];
    const systems = React.useMemo(() => {
        const seen = new Map();
        all.forEach(g => g.copies.forEach(c => seen.set(c.system, g.system === c.system ? g.full_name : c.system)));
        return [...seen].sort((a, b) => a[1].localeCompare(b[1]));
    }, [data]);
    const groups = all.filter(g => !system || g.copies.some(c => c.system === system));
    const chosen = groups.filter(g => ticked[g.id]);

    // Each group is moved by the check that found it: by name, with its details and
    // media folded into the kept copy; identical files, by the ROM check
    const moveAside = async () => {
        const extra = chosen.reduce((n, g) => n + g.copies.length - 1, 0);
        if (!chosen.length || !window.confirm(`Move ${extra} extra cop${extra === 1 ? 'y' : 'ies'} out of the library?\n\nThey go to the duplicates folder in RetroManager's data folder (nothing is deleted; Tools › Storage can delete them later). The kept copies take over their play status and collections.`)) return;
        setWorking(true);
        let moved = 0;
        const problems = [];
        const byName = {};
        for (const g of chosen) {
            const kept = g.copies.find(c => copyKey(c) === keepOf(g));
            const others = g.copies.filter(c => c !== kept);
            if (g.reasons.includes('name')) {
                (byName[g.system] = byName[g.system] || []).push({ keep: kept.path, remove: others.map(c => c.path) });
                continue;
            }
            try {
                const d = await postJson('/api/rom-index/duplicates/resolve', {
                    keep: { system: kept.system, rom_path: kept.path }, remove: others.map(c => ({ system: c.system, rom_path: c.path })) });
                moved += (d.moved || []).length;
                problems.push(...(d.errors || []), ...(d.success ? [] : [d.error || 'Nothing was moved']));
            } catch (e) { problems.push(e.message); }
        }
        for (const [name, list] of Object.entries(byName)) {
            try {
                const d = await postJson(`/api/systems/${encodeURIComponent(name)}/duplicates/resolve`, { groups: list });
                if (d.success) moved += list.reduce((n, g) => n + g.remove.length, 0);
                else problems.push(d.error || `${name}: nothing was moved`);
                problems.push(...(d.errors || []));
            } catch (e) { problems.push(e.message); }
        }
        setWorking(false);
        setTicked({});
        showNotification(problems.length ? `Moved ${moved}. ${problems.slice(0, 2).join('; ')}` : `Moved ${moved} extra cop${moved === 1 ? 'y' : 'ies'} aside`, problems.length ? 'error' : 'success');
        if (typeof announceGameChange === 'function') announceGameChange();
        onChanged && onChanged();
        setReload(n => n + 1);
    };

    const field = {padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13};
    let body;
    if (error) body = <div style={{color: 'var(--accent-pink)'}}>{error}</div>;
    else if (!data) body = <div style={{color: 'var(--text-secondary)'}}>Checking every system...</div>;
    else body = (
        <>
            <div style={{display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12, fontSize: 13}}>
                <select value={system} onChange={e => setSystem(e.target.value)} style={field} aria-label="System">
                    <option value="">All systems</option>
                    {systems.map(([name, full]) => <option key={name} value={name}>{full}</option>)}
                </select>
                <span style={{color: 'var(--text-secondary)'}}>{groups.length} game{groups.length === 1 ? '' : 's'} with more than one copy</span>
                {groups.length > 0 && (
                    <label style={{display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto', cursor: 'pointer'}}>
                        <input type="checkbox" checked={groups.every(g => ticked[g.id])}
                            onChange={e => setTicked(prev => ({ ...prev, ...Object.fromEntries(groups.map(g => [g.id, e.target.checked])) }))} /> Tick all
                    </label>
                )}
                <button className="btn btn-primary btn-small" disabled={!chosen.length || working} style={groups.length ? {} : {marginLeft: 'auto'}} onClick={moveAside}>
                    {working ? 'Moving…' : `Move extra copies aside${chosen.length ? ` (${chosen.length})` : ''}`}
                </button>
            </div>
            {!data.rom_check_ran && (
                <div style={{fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10}}>
                    Identical files under different names are found by the ROM check, which hasn't checked your games yet (Tools › ROM check).
                </div>
            )}
            {groups.length === 0 ? <div style={{color: 'var(--text-secondary)', padding: '16px 0'}}>No duplicates.</div> : (
                <div style={{display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '62vh', overflowY: 'auto'}}>
                    {groups.map(g => (
                        <div key={g.id} style={{display: 'flex', gap: 10, alignItems: 'flex-start', padding: 10, background: 'var(--bg-tertiary)', borderRadius: 6, fontSize: 13}}>
                            <input type="checkbox" style={{marginTop: 3}} checked={!!ticked[g.id]} aria-label={`Move extra copies of ${g.name}`}
                                onChange={e => setTicked(prev => ({ ...prev, [g.id]: e.target.checked }))} />
                            <div style={{flex: 1, minWidth: 0}}>
                                <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4}}>
                                    <b>{g.name}</b>
                                    <span style={{color: 'var(--text-secondary)', fontSize: 12}}>{g.full_name}</span>
                                    {g.reasons.map(r => (
                                        <span key={r} title={DUPLICATE_REASONS[r].help}
                                            style={{fontSize: 11, padding: '1px 6px', borderRadius: 3, border: `1px solid ${r === 'contents' ? 'var(--success)' : 'var(--accent-orange)'}`,
                                                    color: r === 'contents' ? 'var(--success)' : 'var(--accent-orange)'}}>{DUPLICATE_REASONS[r].label}</span>
                                    ))}
                                </div>
                                {g.copies.map(c => {
                                    const kept = keepOf(g) === copyKey(c);
                                    const pick = () => setKeeps(prev => ({ ...prev, [g.id]: copyKey(c) }));
                                    return (
                                        <div key={copyKey(c)} role="radio" aria-checked={kept} tabIndex={0} onClick={pick}
                                            onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); pick(); } }}
                                            style={{display: 'flex', gap: 8, alignItems: 'baseline', padding: '2px 0', cursor: 'pointer', opacity: kept ? 1 : 0.75}}>
                                            <span style={{color: kept ? 'var(--success)' : 'var(--text-secondary)', width: 48, flexShrink: 0, fontSize: 11}}>{kept ? '● Keep' : '○ Move'}</span>
                                            <span style={{flex: 1, minWidth: 0, wordBreak: 'break-word'}}>
                                                {!g.system && <span style={{color: 'var(--text-secondary)'}}>{c.system}/</span>}{c.path}
                                                <span style={{color: 'var(--text-secondary)', fontSize: 11, marginLeft: 6}}>
                                                    {[c.size != null ? formatBytes(c.size) : null, c.name ? 'in gamelist' : 'no entry',
                                                      c.media != null ? (c.media ? `${c.media} media` : 'no media') : null,
                                                      c.playcount ? `played ${c.playcount}×` : null].filter(Boolean).join(' · ')}
                                                </span>
                                            </span>
                                            <a href={gameLink(c.system, c.path)} onClick={e => e.stopPropagation()} title="Open the game" style={{fontSize: 12, color: 'var(--text-secondary)'}}>↗</a>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Duplicates</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 760}}>
                Games in your library more than once: the same game under another region or revision, or exactly the same file twice.
                Pick the copy to keep in each (a suggestion is picked: the one with an entry, more media, more plays and a USA, Europe or World tag),
                tick the games to tidy, and move the extra copies aside. Their details and any media the kept copy lacks carry over.
            </div>
            {body}
        </Modal>
    );
}
