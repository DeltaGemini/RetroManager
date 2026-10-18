// A game's ROM file section (src/common/game-details.jsx draws it): the file, what the ROM
// check made of it and its checksums; its version, as noted; and putting an updated ROM, or a
// patched one, in its place or beside it. Loaded after game-details.jsx on every page that
// shows the panel, sharing one global scope with it, so everything here is named gd.../GD... too.

// The ROM file: what the ROM check (Tools > ROM check) found, and its checksums.
// Folded like the others; rarely needed, so nothing is fetched until it's opened.
const GD_ROM_STATUS = {
    verified: ['Verified', 'var(--success, #3ccf91)', 'Listed in a ROM database as a known good dump'],
    known: ['Recognised', 'var(--accent-blue)', 'Recognised, but not listed as a verified dump'],
    hack: ['Hack', 'var(--accent-pink)', 'A ROM hack RetroAchievements lists'],
    unknown: ['Not recognised', 'var(--accent-orange)', 'No database knows this file: a hack, a patched or trimmed ROM, or a bad dump'],
    skipped: ['Not checked', 'var(--text-secondary)', 'A folder, a disc list, or a file too large to hash'],
};
const GD_ROM_SOURCES = { NoIntros: 'No-Intro', NoIntro: 'No-Intro', MAMEArcade: 'MAME', MAMEMess: 'MAME' };
// What RetroAchievements made of a replaced or patched ROM (the server's {before, now}: the game it
// knew the old file as, and knows the new one as), said in a sentence; '' when it wasn't asked
const gdAchievementsSaid = (ra) => {
    if (!ra) return '';
    const { before, now } = ra;
    const game = (g) => `${g.title}${g.achievements ? ` (${g.achievements} achievements)` : ''}`;
    if (before && now && before.id === now.id) return `RetroAchievements still recognises it: ${game(now)}.`;
    if (before && now) return `RetroAchievements now knows it as ${game(now)}, not ${before.title}.`;
    if (before) return `RetroAchievements doesn't recognise the new file, so it won't earn ${before.title}'s achievements (a patched or updated ROM often isn't one it lists).`;
    if (now) return `RetroAchievements recognises it: ${game(now)}.`;
    return "RetroAchievements doesn't recognise it (nor did it the file before).";
};

// The ROM's version, as noted (backend/rom_versions.py), and an updated ROM put in its place: it
// takes the old one's name, so saves, states and pictures still go with it; the old file is kept
// (Tools > Storage)
function GDRomVersion({ system, game, notify, onReplaced }) {
    const [record, setRecord] = React.useState(null);
    const [editing, setEditing] = React.useState(null); // the version being typed
    const [replacing, setReplacing] = React.useState(null); // {file, version, progress, busy, error}
    // A patch being applied (IPS, UPS, BPS): {file, as: new | replace, name, version, busy, error}
    const [patching, setPatching] = React.useState(null);
    // What RetroAchievements made of the file just put in (gdAchievementsSaid), shown until the game changes
    const [raSaid, setRaSaid] = React.useState('');
    React.useEffect(() => { setRaSaid(''); }, [system, game.path]);
    const patch = async () => {
        const { file } = patching;
        setPatching(p => ({ ...p, busy: true, error: null }));
        try {
            const upload = await RMUpload.send(file, { key: `patch|${file.name}|${file.size}|${file.lastModified}`, giveUpAfter: 6 });
            const d = await RM.sendJson(`/api/systems/${encodeURIComponent(system)}/patch-rom`, 'POST',
                { rom, upload, as: patching.as, name: patching.name, version: patching.version });
            if (!d.success) throw new Error(d.error);
            setPatching(null);
            if (patching.as === 'new') {
                notify && notify(`Patched: ${d.rom.split('/').pop()} added as a new game (${(d.notes || []).join('; ')}). ${gdAchievementsSaid(d.achievements)}`.trim(), 'success');
                onReplaced && onReplaced(`./${d.rom}`, d.version || '');
            } else {
                setRecord(d);
                setRaSaid(gdAchievementsSaid(d.achievements));
                notify && notify(`Patched in place (${(d.notes || []).join('; ')}). The ROM it had is kept in Tools › Storage. ${gdAchievementsSaid(d.achievements)}`.trim(), 'success');
                onReplaced && onReplaced(null, d.version || '');
            }
        } catch (e) { setPatching(p => ({ ...p, busy: false, error: e.message })); }
    };
    const rom = String(game.path).replace(/^(\.\/)+/, '');
    React.useEffect(() => {
        setRecord(null); setEditing(null); setReplacing(null);
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/rom-version?${new URLSearchParams({ rom })}`).then(r => r.json())
            .then(d => setRecord(d.success ? d : {})).catch(() => setRecord({}));
    }, [system, rom, game.rom_version]);
    const saveVersion = async () => {
        try {
            const d = await gdPut(`/api/systems/${encodeURIComponent(system)}/rom-version`, { rom, version: editing });
            if (!d.success) throw new Error(d.error);
            setRecord(d); setEditing(null);
            onReplaced && onReplaced(null, d.version || '');
        } catch (e) { notify && notify(`The version wasn't saved: ${e.message}`, 'error'); }
    };
    const replace = async () => {
        const { file, version } = replacing;
        setReplacing(r => ({ ...r, busy: true, error: null, progress: 0 }));
        try {
            // (common/upload.js, as on the Add games page)
            const upload = await RMUpload.send(file, { key: `replace|${file.name}|${file.size}|${file.lastModified}`, giveUpAfter: 6,
                onProgress: (got, size) => setReplacing(r => ({ ...r, error: null, progress: size ? got / size : 1 })),
                onRetry: (wait) => setReplacing(r => ({ ...r, error: `Connection lost, trying again in ${wait}s` })) });
            setReplacing(r => ({ ...r, progress: 1, placing: true }));
            const d = await RM.sendJson(`/api/systems/${encodeURIComponent(system)}/replace-rom`, 'POST', { rom, upload, version });
            if (!d.success) throw new Error(d.error);
            setRecord(d); setReplacing(null);
            setRaSaid(gdAchievementsSaid(d.achievements));
            notify && notify(`Replaced with ${file.name}${d.rom !== rom ? `, now ${d.rom.split('/').pop()}` : ''}. The old file is kept in Tools › Storage. ${gdAchievementsSaid(d.achievements)}`.trim(), 'success');
            onReplaced && onReplaced(d.rom !== rom ? `./${d.rom}` : null, d.version || '');
        } catch (e) { setReplacing(r => ({ ...r, busy: false, placing: false, error: e.message })); }
    };
    if (!record) return null;
    const ext = rom.includes('.') ? rom.slice(rom.lastIndexOf('.')) : '';
    const newExt = replacing?.file && replacing.file.name.includes('.') ? replacing.file.name.slice(replacing.file.name.lastIndexOf('.')).toLowerCase() : ext.toLowerCase();
    const keptName = newExt === ext.toLowerCase() ? rom.split('/').pop() : rom.split('/').pop().replace(/\.[^.]+$/, newExt);
    return (
        <>
            <dl className="gd-facts">
                <dt>Version</dt>
                <dd>{editing !== null ? (
                    <span className="gd-row">
                        <input className="gd-input" style={{width: 160}} value={editing} autoFocus maxLength={60} placeholder="1.1, v2, 2024-06-01…" aria-label="Version"
                            onChange={e => setEditing(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') saveVersion(); if (e.key === 'Escape') setEditing(null); }} />
                        <button className="gd-btn small" onClick={saveVersion}>Save</button>
                        <button className="gd-linkbutton" onClick={() => setEditing(null)}>Cancel</button>
                    </span>
                ) : (
                    <>{record.version || <span className="gd-note">not noted</span>}{' '}
                        <button className="gd-linkbutton admin-only" onClick={() => setEditing(record.version || '')}>{record.version ? 'Change' : 'Note it'}</button></>
                )}</dd>
                {raSaid && <><dt>Achievements</dt><dd className="gd-note">{raSaid}</dd></>}
                {record.patched_from && <><dt>Made from</dt><dd className="gd-note">{record.patched_from.rom}, patched with {record.patched_from.patch}</dd></>}
                {(record.history || []).length > 0 && <><dt>Before</dt><dd className="gd-note">
                    {record.history.map((h, i) => <div key={i}>{h.version || 'no version noted'}, {h.then_patched_with ? `patched with ${h.then_patched_with}` : 'replaced'} {new Date(h.at * 1000).toLocaleDateString()} (kept in Tools › Storage)</div>)}
                </dd></>}
            </dl>
            {/* (not a disc and its tracks: those are several files) */}
            {!['.cue', '.m3u', '.gdi', '.ccd', '.toc', '.mds'].includes(ext.toLowerCase()) && <div className="admin-only" style={{marginTop: 8}}>
                {!replacing && !patching ? (
                    <div className="gd-row">
                        <button className="gd-btn small" onClick={() => setReplacing({ file: null, version: record.version || '' })}>Replace with an updated ROM…</button>
                        {!['.zip', '.7z'].includes(ext.toLowerCase()) && <button className="gd-btn small" onClick={() => setPatching({ file: null, as: 'new', name: '', version: '' })}
                            title="Apply an IPS, UPS or BPS patch (a ROM hack, a translation) to this ROM">Apply a patch…</button>}
                    </div>
                ) : patching ? (
                    <div className="gd-replace">
                        <label className="gd-row"><span>Patch</span>
                            <input type="file" accept=".ips,.ups,.bps" disabled={patching.busy} onChange={e => {
                                const file = e.target.files[0] || null;
                                setPatching(p => ({ ...p, file, name: p.name || (file ? file.name.replace(/\.[^.]+$/, '') : '') }));
                            }} /></label>
                        <div className="gd-row" role="radiogroup" aria-label="Where the patched ROM goes">
                            <label><input type="radio" name="gd-patch-as" checked={patching.as === 'new'} disabled={patching.busy} onChange={() => setPatching(p => ({ ...p, as: 'new' }))} /> As a new game beside this one</label>
                            <label><input type="radio" name="gd-patch-as" checked={patching.as === 'replace'} disabled={patching.busy} onChange={() => setPatching(p => ({ ...p, as: 'replace', version: p.version || record.version || '' }))} /> In place of this ROM</label>
                        </div>
                        {patching.as === 'new' && <label className="gd-row"><span>Its name</span>
                            <input className="gd-input" style={{flex: '1 1 160px', minWidth: 0}} value={patching.name} disabled={patching.busy} placeholder="Pokémon Emerald Crest"
                                onChange={e => setPatching(p => ({ ...p, name: e.target.value }))} /></label>}
                        <label className="gd-row"><span>Its version</span>
                            <input className="gd-input" style={{width: 160}} value={patching.version} maxLength={60} disabled={patching.busy} placeholder="1.0, v2…"
                                onChange={e => setPatching(p => ({ ...p, version: e.target.value }))} /></label>
                        <div className="gd-note">{patching.as === 'new'
                            ? 'This game stays as it is; the patched ROM is added beside it, to fill in like any game.'
                            : 'The patched ROM takes this one’s name, so its saves and pictures keep working; the ROM it has now is kept in Tools › Storage.'}
                            {' '}UPS and BPS patches are checked against the ROM they're for; IPS patches can't be.</div>
                        {patching.busy && <div className="gd-note">Patching…</div>}
                        {patching.error && <div className="gd-note" style={{color: 'var(--accent-pink)'}}>{patching.error}</div>}
                        <div className="gd-row">
                            <button className="gd-btn small" disabled={!patching.file || patching.busy || (patching.as === 'new' && !patching.name.trim())} onClick={patch}>Apply the patch</button>
                            <button className="gd-linkbutton" disabled={patching.busy} onClick={() => setPatching(null)}>Cancel</button>
                        </div>
                    </div>
                ) : (
                    <div className="gd-replace">
                        <label className="gd-row"><span>New file</span>
                            <input type="file" disabled={replacing.busy} onChange={e => setReplacing(r => ({ ...r, file: e.target.files[0] || null }))} /></label>
                        <label className="gd-row"><span>Its version</span>
                            <input className="gd-input" style={{width: 160}} value={replacing.version} maxLength={60} disabled={replacing.busy} placeholder="1.1, v2…"
                                onChange={e => setReplacing(r => ({ ...r, version: e.target.value }))} /></label>
                        {replacing.file && <div className="gd-note">It's saved as <span className="gd-mono">{keptName}</span>, so the saves, save states and pictures named after the game keep working. The file it has now is kept in Tools › Storage.</div>}
                        {replacing.busy && <div className="gd-note">{replacing.placing ? 'Putting it in place…' : `Uploading ${Math.floor((replacing.progress || 0) * 100)}%…`}</div>}
                        {replacing.error && <div className="gd-note" style={{color: 'var(--accent-pink)'}}>{replacing.error}</div>}
                        <div className="gd-row">
                            <button className="gd-btn small" disabled={!replacing.file || replacing.busy} onClick={replace}>Replace the ROM</button>
                            <button className="gd-linkbutton" disabled={replacing.busy} onClick={() => setReplacing(null)}>Cancel</button>
                        </div>
                    </div>
                )}
            </div>}
        </>
    );
}

function GDRomFile({ system, game, notify, onMoved, onVersion }) {
    const [info, setInfo] = React.useState(null);
    const [reload, setReload] = React.useState(0);
    const [copied, setCopied] = React.useState(null);
    // The game's files one by one, for a game the ROM check has no checksums
    // for (a disc game is a .cue and its tracks, which it doesn't hash)
    const [files, setFiles] = React.useState(null);
    const [hashing, setHashing] = React.useState(false);
    const loadFiles = React.useCallback((workOut) => {
        if (workOut) setHashing(true);
        return fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/rom-files?${new URLSearchParams({ rom: game.path, ...(workOut ? { hash: '1' } : {}) })}`).then(r => r.json())
            .then(d => { if (d.success) setFiles(d.files); }).catch(() => {}).finally(() => { if (workOut) setHashing(false); });
    }, [system, game.path]);
    React.useEffect(() => {
        let cancelled = false;
        setInfo(null);
        setFiles(null);
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/rom-info?${new URLSearchParams({ rom: game.path })}`).then(r => r.json())
            .then(d => { if (cancelled) return; const got = d.success ? d : { checked: false }; setInfo(got); if (!got.sha1) loadFiles(false); })
            .catch(() => { if (!cancelled) { setInfo({ checked: false }); loadFiles(false); } });
        return () => { cancelled = true; };
    }, [system, game.path, reload]);
    const copy = (label, value) => {
        const done = () => { setCopied(label); setTimeout(() => setCopied(c => (c === label ? null : c)), 1500); };
        try { navigator.clipboard.writeText(value).then(done, () => {}); } catch (e) {}
    };
    const file = String(game.path).replace(/^(\.\/)+/, '');
    if (!info) return <div className="gd-note">Looking...</div>;
    const status = info.checked ? (GD_ROM_STATUS[info.status] || GD_ROM_STATUS.unknown) : null;
    const sources = (info.sources || []).map(s => GD_ROM_SOURCES[s] || s).join(', ');
    const sums = [['SHA-1', info.sha1], ['MD5', info.md5], ['CRC32', info.crc32]].filter(s => s[1]);
    return (
        <div className="gd-romfile">
            <dl className="gd-facts">
                <dt>File</dt><dd className="gd-mono">{file}</dd>
                {info.size > 0 && <><dt>Size</dt><dd>{RM.bytes(info.size)}</dd></>}
                {status && <><dt>ROM check</dt><dd>
                    <span title={status[2]} style={{color: status[1]}}>{status[0]}</span>
                    {sources && <span className="gd-note"> · listed by {sources}</span>}
                    {info.known_name && <span className="gd-note"> as {info.known_name}</span>}
                    {info.reason && <span className="gd-note"> · {info.reason}</span>}
                </dd></>}
                {sums.map(([label, value]) => (
                    <React.Fragment key={label}>
                        <dt>{label}</dt>
                        <dd className="gd-mono">{value} <button className="gd-linkbutton" onClick={() => copy(label, value)}>{copied === label ? 'Copied' : 'Copy'}</button></dd>
                    </React.Fragment>
                ))}
            </dl>
            {!sums.length && files && files.length > 0 && (
                <div className="gd-romfiles">
                    {files.map(f => (
                        <div key={f.name} className="gd-romfiles-file">
                            <div><span className="gd-mono">{f.name}</span> <span className="gd-note">{RM.bytes(f.size)}</span></div>
                            {f.sha1 && (
                                <dl className="gd-facts">
                                    {[['SHA-1', f.sha1], ['MD5', f.md5], ['CRC32', f.crc32]].map(([label, value]) => (
                                        <React.Fragment key={label}>
                                            <dt>{label}</dt>
                                            <dd className="gd-mono">{value} <button className="gd-linkbutton" onClick={() => copy(`${f.name}:${label}`, value)}>{copied === `${f.name}:${label}` ? 'Copied' : 'Copy'}</button></dd>
                                        </React.Fragment>
                                    ))}
                                </dl>
                            )}
                        </div>
                    ))}
                    {files.some(f => !f.sha1) && (
                        <div className="gd-row" style={{marginTop: 8}}>
                            <button className="gd-btn small" disabled={hashing} onClick={() => loadFiles(true)}>{hashing ? 'Working them out...' : 'Work out the checksums'}</button>
                            <span className="gd-note">{hashing ? 'Each file is read whole: a disc takes a while.' : `${RM.bytes(files.filter(f => !f.sha1).reduce((n, f) => n + f.size, 0))} to read. They're kept once worked out.`}</span>
                        </div>
                    )}
                </div>
            )}
            {!sums.length && files && !files.length && <div className="gd-note" style={{marginTop: 6}}>No checksums: this game is a folder, not a file.</div>}
            {!(files && !files.length && !sums.length) && (
                <div style={{marginTop: 10}}>
                    <GDRomVersion system={system} game={game} notify={notify}
                        onReplaced={(newPath, version) => (newPath ? onMoved && onMoved(newPath) : (setReload(n => n + 1), version !== undefined && onVersion && onVersion(version)))} />
                </div>
            )}
        </div>
    );
}
