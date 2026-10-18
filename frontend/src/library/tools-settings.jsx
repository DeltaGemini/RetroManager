// Tools: settings.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// What's been played, by whom, from save and save-state times
// Tools > Settings: accounts, keys and scraping options (kept on the server in
// DATA_PATH/settings.json). Saved passwords and keys never come back to the
// browser: a secret field is empty, and says whether one is saved.
function SettingsPanel({ onClose, showNotification }) {
    const [groups, setGroups] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [edits, setEdits] = React.useState({});   // key -> new value ('' clears a saved one)
    const [saving, setSaving] = React.useState(false);
    useEffect(() => {
        fetch(`${API_BASE}/api/settings`).then(r => r.json())
            .then(d => d.success ? setGroups(d.groups) : setError(d.error || 'Could not load settings'))
            .catch(e => setError(e.message));
    }, []);

    // Backups of RetroManager's own data (made every night; see backend/maintenance.py)
    const [backups, setBackups] = React.useState(null);
    const [backingUp, setBackingUp] = React.useState(false);
    useEffect(() => {
        fetch(`${API_BASE}/api/data-backups`).then(r => r.json()).then(d => { if (d.success) setBackups(d); }).catch(() => {});
    }, []);
    const backUpNow = async () => {
        setBackingUp(true);
        try {
            const d = await (await fetch(`${API_BASE}/api/data-backups`, { method: 'POST' })).json();
            if (d.success) setBackups(prev => ({ ...(prev || {}), backups: d.backups }));
            else setError(d.error || 'Could not make a backup');
        } catch (e) { setError(e.message); }
        setBackingUp(false);
    };
    const edit = (key, value) => setEdits(prev => ({ ...prev, [key]: value }));
    const undo = (key) => setEdits(prev => { const next = { ...prev }; delete next[key]; return next; });
    const changes = Object.keys(edits).length;
    const save = async () => {
        setSaving(true);
        setError(null);
        try {
            const d = await RM.sendJson('/api/settings', 'PUT', { values: edits });
            if (!d.success) { setError(d.error || 'Could not save settings'); return; }
            setGroups(d.groups);
            setEdits({});
            if (showNotification) showNotification(d.changed.length ? 'Settings saved' : 'Nothing changed', 'success');
        } catch (e) {
            setError(e.message);
        } finally {
            setSaving(false);
        }
    };

    const inputStyle = { width: '100%', padding: 8, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13 };
    const field = (f) => {
        const edited = f.key in edits;
        const clearing = edited && edits[f.key] === '' && f.set;
        let status = null;
        if (clearing) status = <span style={{color: 'var(--accent-pink)'}}>Will be removed when you save</span>;
        else if (f.secret && edited) status = <span style={{color: 'var(--accent-orange)'}}>New value, not saved yet</span>;
        else if (f.secret) status = f.set ? <span style={{color: 'var(--success)'}}>Saved{f.source === 'environment' ? ` (from ${f.env} in docker-compose.yml)` : ''}</span> : 'Not set';
        else if (f.set && f.source === 'environment') status = `From ${f.env} in docker-compose.yml`;
        return (
            <div key={f.key} style={{display: 'grid', gridTemplateColumns: 'minmax(140px, 220px) 1fr', gap: 12, alignItems: 'start', marginBottom: 10}}>
                <label htmlFor={`setting-${f.key}`} style={{fontSize: 13, paddingTop: 8}}>{f.label}</label>
                <div>
                    <div style={{display: 'flex', gap: 6}}>
                        {f.choices ? (
                            <select id={`setting-${f.key}`} value={edited ? edits[f.key] : f.value} onChange={e => e.target.value === f.value ? undo(f.key) : edit(f.key, e.target.value)} style={inputStyle}>
                                {f.choices.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                            </select>
                        ) : (
                            <input id={`setting-${f.key}`} type={f.secret ? 'password' : 'text'} autoComplete={f.secret ? 'new-password' : 'off'} spellCheck={false}
                                value={edited ? edits[f.key] : (f.secret ? '' : f.value)}
                                placeholder={f.secret ? (f.set && !clearing ? 'Saved: leave empty to keep it' : '') : ''}
                                onChange={e => (!f.secret && e.target.value === f.value) || (f.secret && e.target.value === '') ? undo(f.key) : edit(f.key, e.target.value)}
                                style={inputStyle} />
                        )}
                        {f.secret && f.set && !edited && (
                            <button className="btn btn-secondary btn-small" onClick={() => edit(f.key, '')} title="Remove the saved value">Remove</button>
                        )}
                        {edited && <button className="btn btn-secondary btn-small" onClick={() => undo(f.key)}>Undo</button>}
                    </div>
                    {status && <div style={{fontSize: 11, color: 'var(--text-secondary)', marginTop: 3}}>{status}</div>}
                </div>
            </div>
        );
    };

    return (
        <Modal open={true} onClose={saving ? () => {} : onClose}>
            <h2 style={{marginBottom: 4}}>Settings</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 640}}>
                Accounts and keys for the scraping sources. They're kept on the server and take effect as soon as you save;
                saved passwords and keys are never shown again.
            </div>
            {error && <div role="alert" style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {!groups && !error && <div style={{color: 'var(--text-secondary)'}}>Loading...</div>}
            {groups && (
                <>
                    <div style={{maxHeight: '60vh', overflowY: 'auto', paddingRight: 6}}>
                        {groups.map(group => (
                            <fieldset key={group.title} style={{border: 'none', borderTop: '1px solid var(--border-color)', padding: '12px 0 4px', margin: 0}}>
                                <legend style={{fontSize: 14, fontWeight: 700, color: 'var(--accent-pink)', paddingRight: 8}}>{group.title}</legend>
                                {group.help && <div style={{fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10}}>{group.help}</div>}
                                {group.fields.map(field)}
                            </fieldset>
                        ))}
                        {backups && (
                            <div style={{borderTop: '1px solid var(--border-color)', padding: '12px 0 4px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', fontSize: 13}}>
                                <span style={{flex: 1, minWidth: 220}}>
                                    <b>Data backups:</b> {backups.backups.length
                                        ? `${backups.backups.length} kept, the latest made ${timeAgo(new Date(backups.backups[0].made).getTime())}`
                                        : 'none yet'}
                                    <span style={{display: 'block', fontSize: 11, color: 'var(--text-secondary)'}}>In {backups.folder}. They hold the same passwords and keys as the settings.</span>
                                </span>
                                <button className="btn btn-secondary btn-small" onClick={backUpNow} disabled={backingUp}>{backingUp ? 'Backing up...' : 'Back up now'}</button>
                            </div>
                        )}
                    </div>
                    <div style={{display: 'flex', justifyContent: 'flex-end', gap: 8, alignItems: 'center', marginTop: 12}}>
                        {changes > 0 && <span style={{fontSize: 12, color: 'var(--text-secondary)', marginRight: 'auto'}}>{changes} unsaved change{changes === 1 ? '' : 's'}</span>}
                        <button className="btn btn-secondary" onClick={onClose} disabled={saving}>Close</button>
                        <button className="btn btn-primary" onClick={save} disabled={saving || !changes}>{saving ? 'Saving...' : 'Save'}</button>
                    </div>
                </>
            )}
        </Modal>
    );
}
