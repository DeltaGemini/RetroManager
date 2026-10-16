// Tools: saves (sync conflicts, too many save states, and backups).
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const saveShotUrl = (root, rel) => `${API_BASE}/api/save-screenshot/${root}/${rel.split('/').map(encodeURIComponent).join('/')}`;
// "sync-conflict-20260101-120000-ABC1234" -> the device id Syncthing appended
const conflictDevice = (path) => (path.match(/sync-conflict-\d{8}-\d{6}-([A-Z0-9]+)/) || [])[1];

// Syncthing conflicts and zipped save backups
function SavesToolPanel({ systems, onClose, showNotification }) {
    const [conflicts, setConflicts] = React.useState(null);
    const [writable, setWritable] = React.useState(true);
    const [backups, setBackups] = React.useState(null);
    const [scope, setScope] = React.useState('');
    const [includeStates, setIncludeStates] = React.useState(true);
    const [busy, setBusy] = React.useState(null);
    const [error, setError] = React.useState(null);
    // Too many save states: what keeping each person's newest few of each game would move
    const [keepStates, setKeepStates] = React.useState(10);
    const [thinPlan, setThinPlan] = React.useState(null);
    const [thinning, setThinning] = React.useState(false);
    const [renumber, setRenumber] = React.useState(true);
    const lookThin = () => fetch(`${API_BASE}/api/save-states/thin?keep=${keepStates}`).then(r => r.json())
        .then(d => { if (d.success) setThinPlan(d); else setError(d.error); }).catch(e => setError(e.message));
    const thin = async () => {
        if (!thinPlan || !window.confirm(`Move ${thinPlan.files} older save state${thinPlan.files === 1 ? '' : 's'} (${formatBytes(thinPlan.bytes)}) to save-backups/thinned-states/? Each person keeps the ${thinPlan.keep} newest of each game, and every auto state.`)) return;
        setThinning(true);
        const d = await postJson('/api/save-states/thin', { keep: thinPlan.keep, renumber });
        setThinning(false);
        if (d.success) showNotification(`${d.moved} save state${d.moved === 1 ? '' : 's'} moved to save-backups/${d.backup}${d.renumbered ? `, ${d.renumbered} renumbered` : ''}${d.problems && d.problems.length ? ` (${d.problems.length} couldn't be)` : ''}.`, d.problems && d.problems.length ? 'error' : 'success');
        else showNotification(d.error || 'Could not move them', 'error');
        lookThin();
    };

    const loadConflicts = () => fetch(`${API_BASE}/api/save-conflicts`).then(r => r.json())
        .then(d => { if (d.success) { setConflicts(d.conflicts); setWritable(d.writable); } else setError(d.error); })
        .catch(e => setError(e.message));
    const loadBackups = () => fetch(`${API_BASE}/api/save-backups`).then(r => r.json())
        .then(d => { if (d.success) setBackups(d); return d; }).catch(e => setError(e.message));
    useEffect(() => { loadConflicts(); loadBackups(); }, []);
    // Poll while a backup is being zipped
    useEffect(() => {
        if (!backups?.job?.running) return;
        const t = setTimeout(loadBackups, 1500);
        return () => clearTimeout(t);
    }, [backups]);

    const keep = async (group, version) => {
        setBusy(group.id);
        const d = await postJson('/api/save-conflicts/resolve', { id: group.id, keep: version.path });
        setBusy(null);
        if (d.success) {
            showNotification(`Kept ${version.path === group.path ? 'the original' : 'that version'}; ${d.moved.length} file${d.moved.length === 1 ? '' : 's'} moved to save-backups/${d.backup}.`, 'success');
            loadConflicts();
        } else showNotification(d.error || 'Could not resolve', 'error');
    };
    const startBackup = async () => {
        const d = await postJson('/api/save-backups', { system: scope || null, include_states: includeStates });
        if (!d.success) showNotification(d.error || 'Could not start the backup', 'error');
        loadBackups();
    };
    const removeBackup = async (name) => {
        if (!window.confirm(`Delete ${name}? This can't be undone.`)) return;
        const d = await (await fetch(`${API_BASE}/api/save-backups/${encodeURIComponent(name)}`, { method: 'DELETE' })).json();
        if (!d.success) showNotification(d.error || 'Could not delete', 'error');
        loadBackups();
    };

    const job = backups?.job;
    const section = (title, children) => (
        <div style={{marginBottom: 20, background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 6, padding: 14}}>
            <h3 style={{fontSize: 15, margin: '0 0 8px'}}>{title}</h3>
            {children}
        </div>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 16}}>Saves</h2>
            {error && <div style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}

            {section(<>Sync conflicts {conflicts && <span style={{color: 'var(--accent-orange)'}}>({conflicts.length})</span>}</>, (
                <>
                    <div style={{color: 'var(--text-secondary)', fontSize: 12, marginBottom: 10, lineHeight: 1.4}}>
                        Syncthing keeps both versions when a save changes on two devices at once. Pick the one to keep:
                        it gets the normal name so the emulator loads it, and the others move to <code>save-backups/conflicts/</code>.
                    </div>
                    {!writable && <div style={{color: 'var(--accent-pink)', fontSize: 13, marginBottom: 10}}>The saves folders are mounted read-only, so conflicts can't be resolved. Remove <code>:ro</code> from them in docker-compose.yml.</div>}
                    {!conflicts ? <div style={{color: 'var(--text-secondary)'}}>Looking...</div> : conflicts.length === 0 ? (
                        <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No conflicts.</div>
                    ) : conflicts.map(group => (
                        <div key={group.id} style={{marginBottom: 12}}>
                            <div style={{fontWeight: 600, fontSize: 14}}>
                                {group.game?.name || group.base}
                                <span style={{color: 'var(--text-secondary)', fontWeight: 400, fontSize: 12, marginLeft: 8}}>
                                    {[group.game?.full_name || group.folder, group.profile !== 'shared' ? capitalize(group.profile) : null, group.path].filter(Boolean).join(' · ')}
                                </span>
                            </div>
                            <div style={{display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6}}>
                                {group.versions.map((v, i) => (
                                    <div key={v.path} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>
                                        {v.screenshot && <img src={saveShotUrl(v.root, v.screenshot)} alt="" style={{width: 56, height: 42, objectFit: 'cover', borderRadius: 3}} />}
                                        <div style={{flex: 1, minWidth: 0}}>
                                            <div>
                                                {v.path === group.path ? 'Current file' : `Copy from device ${conflictDevice(v.path) || '?'}`}
                                                {i === 0 && <span style={{color: 'var(--success)', fontSize: 11, marginLeft: 8}}>newest</span>}
                                            </div>
                                            <div style={{color: 'var(--text-secondary)', fontSize: 12}}>
                                                {new Date(v.modified).toLocaleString()} · {formatBytes(v.size)}
                                            </div>
                                        </div>
                                        <button className="btn btn-secondary btn-small" disabled={!writable || busy === group.id} onClick={() => keep(group, v)}>Keep this</button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </>
            ))}

            {section('Too many save states', (
                <>
                    <div style={{color: 'var(--text-secondary)', fontSize: 12, marginBottom: 10}}>
                        Keeps each person's newest save states of each game, and every auto state (RetroArch loads that one by itself). The rest move to <code>save-backups/thinned-states/</code> on the NAS, with their screenshots, under the paths they had: nothing is deleted. Devices that sync the save states folder (Syncthing) lose them too.
                    </div>
                    <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10}}>
                        <label style={{display: 'flex', gap: 6, alignItems: 'center', fontSize: 13}}>
                            Keep the newest <input type="number" min="1" max="999" value={keepStates} style={{width: 64}}
                                onChange={e => { setKeepStates(Math.max(1, parseInt(e.target.value, 10) || 1)); setThinPlan(null); }} /> of each game
                        </label>
                        <label style={{display: 'flex', gap: 6, alignItems: 'center', fontSize: 13}} title="Each game's remaining states become slots 1, 2, 3..., oldest first, so the newest has the highest number and RetroArch's next slot follows it. Auto states keep their name.">
                            <input type="checkbox" checked={renumber} onChange={e => setRenumber(e.target.checked)} /> then number what's left 1, 2, 3…
                        </label>
                        <button className="btn btn-secondary btn-small" onClick={lookThin}>Show what would move</button>
                        {thinPlan && thinPlan.files > 0 && (
                            <button className="btn btn-primary btn-small" disabled={thinning || !writable} onClick={thin}>
                                {thinning ? 'Moving…' : `Move ${thinPlan.files} older state${thinPlan.files === 1 ? '' : 's'} (${formatBytes(thinPlan.bytes)})`}
                            </button>
                        )}
                    </div>
                    {thinPlan && !thinPlan.files && <div style={{fontSize: 13}}>Nobody has more than {thinPlan.keep} save states of any game.</div>}
                    {thinPlan && thinPlan.groups.map(g => (
                        <div key={`${g.root}/${g.profile}/${g.folder}/${g.game}`} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '5px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, marginBottom: 3}}>
                            <div style={{flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}} title={g.game}>
                                {g.game}<span style={{color: 'var(--text-secondary)'}}> · {g.folder || 'loose'} · {g.profile === 'shared' ? 'everyone' : g.profile}</span>
                            </div>
                            <div style={{color: 'var(--text-secondary)', whiteSpace: 'nowrap'}}>{g.total} → {g.total - g.move.length} · {formatBytes(g.move.reduce((n, r) => n + r.size, 0))}</div>
                        </div>
                    ))}
                </>
            ))}

            {section('Backups', (
                <>
                    <div style={{color: 'var(--text-secondary)', fontSize: 12, marginBottom: 10}}>
                        Zips every person's saves (and, if ticked, save states) into <code>save-backups/zips/</code> on the NAS.
                        One game's saves can be downloaded from its Saves section.
                    </div>
                    {backups && !backups.folder_ok && <div style={{color: 'var(--accent-pink)', fontSize: 13, marginBottom: 10}}>The save-backups folder isn't mounted or isn't writable (see docker-compose.yml).</div>}
                    <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                        <select value={scope} onChange={e => setScope(e.target.value)}>
                            <option value="">Everything</option>
                            {systems.filter(s => s.rom_count).map(s => <option key={s.name} value={s.name}>{s.full_name || s.name}</option>)}
                        </select>
                        <label style={{display: 'flex', gap: 6, alignItems: 'center', fontSize: 13}}>
                            <input type="checkbox" checked={includeStates} onChange={e => setIncludeStates(e.target.checked)} /> Include save states
                        </label>
                        <button className="btn btn-primary btn-small" disabled={job?.running || (backups && !backups.folder_ok)} onClick={startBackup}>
                            {job?.running ? `Zipping ${job.done}/${job.total || '…'}` : 'Create backup'}
                        </button>
                    </div>
                    {job?.error && <div style={{color: 'var(--accent-pink)', fontSize: 13, marginBottom: 8}}>Last backup failed: {job.error}</div>}
                    {(backups?.backups || []).map(b => (
                        <div key={b.name} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, marginBottom: 4}}>
                            <div style={{flex: 1, minWidth: 0}}>
                                <div style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{b.name}</div>
                                <div style={{color: 'var(--text-secondary)', fontSize: 12}}>{new Date(b.modified).toLocaleString()} · {formatBytes(b.size)}</div>
                            </div>
                            <a className="btn btn-secondary btn-small" href={`${API_BASE}/api/save-backups/${encodeURIComponent(b.name)}`} style={{textDecoration: 'none'}}>Download</a>
                            <button className="btn btn-secondary btn-small" onClick={() => removeBackup(b.name)} aria-label={`Delete ${b.name}`}>Delete</button>
                        </div>
                    ))}
                </>
            ))}
        </Modal>
    );
}
