// Tools: library health, and each system's Scan panel.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function HealthPanel({ onClose, onReview, onChanged, showNotification }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [fixing, setFixing] = React.useState(null); // progress text while fixing

    const load = async () => {
        setError(null);
        try {
            const res = await fetch(`${API_BASE}/api/library-scan`);
            const d = await res.json();
            if (d.success) setData(d.systems); else setError(d.error || 'Scan failed');
        } catch (err) {
            setError(err.message);
        }
    };
    useEffect(() => { load(); }, []);

    const issueCount = (s) => HEALTH_COLUMNS.reduce((n, c) => n + (s.counts[c.key] || 0), 0);
    const withIssues = (data || []).filter(s => issueCount(s) > 0 || s.error);
    const clean = (data || []).filter(s => issueCount(s) === 0 && !s.error);
    const totals = Object.fromEntries(HEALTH_COLUMNS.map(c => [c.key, (data || []).reduce((n, s) => n + (s.counts[c.key] || 0), 0)]));
    const safeTotal = totals.truncated_names + totals.media_links + totals.disc_tracks;

    // Only the fixes that can't lose anything: linking existing media and
    // folding disc track entries into their disc. Each makes a gamelist backup.
    const fixSafeEverywhere = async () => {
        const jobs = [];
        (data || []).forEach(s => {
            if (s.counts.truncated_names) jobs.push({ system: s, url: 'names/fix', label: 'fixing names' });
            if (s.counts.disc_tracks) jobs.push({ system: s, url: 'disc-tracks/merge', label: 'merging disc tracks' });
            if (s.counts.media_links) jobs.push({ system: s, url: 'link-media', label: 'linking media' });
        });
        let changed = 0, failed = 0;
        for (let i = 0; i < jobs.length; i++) {
            const job = jobs[i];
            setFixing(`${i + 1} of ${jobs.length}: ${job.system.full_name || job.system.system}, ${job.label}`);
            try {
                const d = await RM.sendJson(`/api/systems/${encodeURIComponent(job.system.system)}/${job.url}`, 'POST', {});
                if (d.success) changed += d.changed || 0; else failed++;
            } catch (err) {
                failed++;
            }
        }
        setFixing(null);
        showNotification(`Fixed ${changed} item${changed === 1 ? '' : 's'}${failed ? `, ${failed} failed` : ''}. Gamelists were backed up first.`, failed ? 'error' : 'success');
        onChanged();
        load();
    };

    const cell = (n, col) => (
        <td key={col.key} style={{textAlign: 'center', padding: '8px 6px', color: n ? (col.safe ? 'var(--accent-orange)' : 'var(--text-primary)') : 'var(--text-secondary)', fontWeight: n ? 600 : 400}}>
            {n || '·'}
        </td>
    );

    return (
        <Modal open={true} onClose={fixing ? null : onClose}>
            <h2 style={{marginBottom: 4}}>Library health</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16}}>
                Every system's Scan in one place. <b style={{color: 'var(--accent-orange)'}}>Orange</b> issues are safe to fix everywhere at once; the others are best reviewed per system.
            </div>
            {error && <div style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {!data && !error && <div style={{color: 'var(--text-secondary)'}}>Scanning every system...</div>}
            {data && (
                <>
                    <div style={{display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                        <button className="btn btn-primary" disabled={!safeTotal || !!fixing} onClick={fixSafeEverywhere}>
                            {fixing ? 'Fixing...' : `Fix safe issues everywhere (${safeTotal})`}
                        </button>
                        <span style={{fontSize: 12, color: 'var(--text-secondary)'}}>
                            {fixing || `Fixes ${totals.truncated_names} cut-off names, links ${totals.media_links} unlinked media and merges ${totals.disc_tracks} disc track entries. Files aren't touched.`}
                        </span>
                    </div>
                    {withIssues.length === 0 ? (
                        <div style={{padding: '20px 0', color: 'var(--text-secondary)'}}>Nothing to fix in any system.</div>
                    ) : (
                        <div style={{overflowX: 'auto'}}>
                            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 13}}>
                                <thead>
                                    <tr style={{borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)'}}>
                                        <th style={{textAlign: 'left', padding: '8px 6px'}}>System</th>
                                        {HEALTH_COLUMNS.map(c => <th key={c.key} title={c.help} style={{padding: '8px 6px', fontWeight: 500}}>{c.label}</th>)}
                                        <th />
                                    </tr>
                                </thead>
                                <tbody>
                                    {withIssues.map(s => (
                                        <tr key={s.system} style={{borderBottom: '1px solid var(--border-color)'}}>
                                            <td style={{padding: '8px 6px'}}>{s.full_name || s.system}{s.error && <span style={{color: 'var(--accent-pink)'}}> (scan failed)</span>}</td>
                                            {HEALTH_COLUMNS.map(c => cell(s.counts[c.key] || 0, c))}
                                            <td style={{padding: '4px 6px', textAlign: 'right'}}>
                                                <button className="btn btn-secondary btn-small" disabled={!!fixing} onClick={() => onReview(s.system)}>Review</button>
                                            </td>
                                        </tr>
                                    ))}
                                    <tr style={{color: 'var(--text-secondary)'}}>
                                        <td style={{padding: '8px 6px', fontWeight: 600}}>Total</td>
                                        {HEALTH_COLUMNS.map(c => <td key={c.key} style={{textAlign: 'center', padding: '8px 6px', fontWeight: 600}}>{totals[c.key] || '·'}</td>)}
                                        <td />
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    )}
                    {clean.length > 0 && (
                        <div style={{marginTop: 12, fontSize: 12, color: 'var(--text-secondary)'}}>
                            Nothing to fix in {clean.length} system{clean.length === 1 ? '' : 's'}: {clean.map(s => s.full_name || s.system).join(', ')}.
                        </div>
                    )}
                </>
            )}
        </Modal>
    );
}

// Asks what to do with unsaved edits before switching game or system
function UnsavedChangesModal({ gameName, onSave, onDiscard, onCancel, saving }) {
    return (
        <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.7)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1100}} {...backdropClose(onCancel)}>
            <div style={{background:'var(--bg-modal)',padding:24,borderRadius:8,maxWidth:440,width:'90%',boxShadow:'0 8px 32px rgba(0,0,0,0.4)'}} onClick={e => e.stopPropagation()}>
                <h2 style={{marginBottom:12,fontSize:18}}>Unsaved changes</h2>
                <p style={{color:'var(--text-secondary)',marginBottom:20,lineHeight:1.5}}>
                    <b style={{color:'var(--text-primary)'}}>{gameName}</b> has changes that haven't been saved to gamelist.xml.
                </p>
                <div style={{display:'flex',gap:8,justifyContent:'flex-end',flexWrap:'wrap'}}>
                    <button className="btn btn-secondary" onClick={onCancel} disabled={saving}>Keep editing</button>
                    <button className="btn btn-secondary" onClick={onDiscard} disabled={saving}>Discard</button>
                    <button className="btn btn-primary" onClick={onSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
                </div>
            </div>
        </div>
    );
}

// Scan results for one system, with an action for each kind of problem
function ScanPanel({ result, system, onClose, onChanged, showNotification }) {
    const sections = [
        {
            key: 'multi_disc',
            title: 'Multi-disc games without a playlist',
            help: "These discs belong to one game. Creating an .m3u playlist makes them one entry in EmulationStation (swap discs from the emulator's menu). The disc entries' details and disc 1's media move to the playlist entry. Disc files aren't moved.",
            items: result.multi_disc || [],
            id: item => item.m3u,
            defaultChecked: () => true,
            render: item => (
                <>
                    <div>{item.name}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:11}}>{item.m3u} ← {item.discs.map(d => d.split('/').pop()).join(' + ')}</div>
                </>
            ),
            action: 'Create .m3u',
            run: items => ({ url: 'multi-disc/create', body: { m3us: items.map(i => i.m3u) } }),
        },
        {
            key: 'game_folders',
            title: 'PS3 game folders not named .ps3',
            help: 'A PS3 disc game is a folder (PS3_GAME, PS3_DISC.SFB), not one file. Renamed to "<game>.ps3" the folder is one game here, and in Batocera and ES-DE (RPCS3 opens the folder directly). Nothing inside it changes, and a gamelist entry pointing inside it (often named "Eboot") becomes the game\'s entry. Until then its files are ignored. Wait until a game has finished copying before renaming it.',
            items: result.game_folders || [],
            id: item => item.path,
            defaultChecked: item => item.complete && !item.copying,
            render: item => (
                <>
                    <div>{item.path}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:11}}>
                        → {item.to.split('/').pop()}
                        {item.copying ? <span style={{color:'var(--accent-orange)'}}> · still being copied: scan again when it has finished</span>
                            : !item.complete && <span style={{color:'var(--accent-orange)'}}> · looks unfinished: no PARAM.SFO or EBOOT.BIN</span>}
                    </div>
                </>
            ),
            action: 'Rename to .ps3',
            run: items => ({ url: 'game-folders/rename', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'saves_in_roms',
            title: 'Saves inside the ROM folder',
            help: 'Saves and save states belong only in the top-level saves and savestates folders (an emulator saving next to the ROM means its save folder setting is missing). Moving puts them in save-backups/in-rom-folders/ on the NAS, where nothing syncs them; copy one into saves/ or savestates/ if you still need it.',
            items: result.saves_in_roms || [],
            id: item => item,
            defaultChecked: () => true,
            render: item => <div>{item}</div>,
            action: 'Move out of roms',
            run: items => ({ url: 'saves-in-roms/move', body: { paths: items } }),
        },
        {
            key: 'truncated_names',
            title: 'Names missing their first letters',
            help: "These names are the ROM's file name with the first letter or two cut off (a Skraper glitch). Fixing puts the missing letters back; nothing else changes.",
            items: result.truncated_names || [],
            id: item => item.path,
            defaultChecked: () => true,
            render: item => (
                <>
                    <div style={{textDecoration:'line-through',color:'var(--text-secondary)'}}>{item.name}</div>
                    <div>→ {item.fixed}</div>
                </>
            ),
            action: 'Fix names',
            run: items => ({ url: 'names/fix', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'name_style',
            title: 'Names not in house style',
            help: 'Series and subtitle split by a colon ("Star Wars: Rogue Leader - Rogue Squadron II"), "Legend of Zelda, The" moved to "The Legend of Zelda", region/language tags removed, Title Case, Pokémon with its é. Untick any you want to keep as they are.',
            items: result.name_style || [],
            id: item => item.path,
            defaultChecked: () => true,
            render: item => (
                <>
                    <div style={{textDecoration:'line-through',color:'var(--text-secondary)'}}>{item.name}</div>
                    <div>→ {item.styled}</div>
                </>
            ),
            action: 'Rename',
            run: items => ({ url: 'names/style', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'disc_tracks',
            title: 'Disc track files listed as games',
            help: "These gamelist entries are for a disc's track files (named in its .cue), not separate games. Merging copies any details only the track entry has onto the disc's entry, then removes the track entry. No files are touched.",
            items: result.disc_tracks || [],
            id: item => item.path,
            defaultChecked: () => true,
            render: item => (
                <>
                    <div>{item.path}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:11}}>part of {item.disc}</div>
                </>
            ),
            action: 'Merge into disc',
            run: items => ({ url: 'disc-tracks/merge', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'relink',
            title: 'Entries pointing at a wrong file name',
            help: 'These gamelist entries have no ROM, but a ROM with a nearly identical name has no entry. Relinking points the entry (and its metadata) at the real file, and renames media saved under the wrong name.',
            items: result.relink,
            id: item => item.from,
            defaultChecked: item => item.score >= 0.9,
            render: item => (
                <>
                    <div style={{textDecoration:'line-through',color:'var(--text-secondary)'}}>{item.from}</div>
                    <div>→ {item.to} <span style={{color: item.score >= 0.97 ? 'var(--success)' : 'var(--accent-orange)',fontSize:11,marginLeft:6}}>{Math.round(item.score * 100)}% match</span></div>
                </>
            ),
            action: 'Relink',
            run: items => ({ url: 'relink', body: { pairs: items.map(i => ({ from: i.from, to: i.to })) } }),
        },
        {
            key: 'media_links',
            title: 'Media not linked in the gamelist',
            help: "EmulationStation only shows the <image>, <thumbnail> and <video> set in gamelist.xml. These are empty or point at a missing file, but matching media exists.",
            items: result.media_links,
            id: item => item.path,
            defaultChecked: () => true,
            render: item => (
                <>
                    <div>{item.name || item.path}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:11}}>
                        {Object.entries(item.fields).map(([f, p]) => `${f} ← ${p.split('/').slice(-2, -1)[0]}`).join(' · ')}
                    </div>
                </>
            ),
            action: 'Link media',
            run: items => ({ url: 'link-media', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'empty_roms',
            title: 'Empty ROM files',
            help: 'These files have nothing in them (0 bytes), so they can\'t be played: a download or copy that failed. Moving puts them in the duplicates folder in RetroManager\'s data folder and removes their gamelist entries; get the game again to replace it.',
            items: result.empty_roms || [],
            id: item => item.path,
            defaultChecked: () => true,
            render: item => (
                <>
                    <div>{item.name || item.path}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:11}}>{item.path}</div>
                </>
            ),
            action: 'Move out of the library',
            run: items => ({ url: 'empty-roms/move', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'new_roms',
            title: 'ROMs without a gamelist entry',
            help: 'Creates a basic entry named after the file and links any matching media. Scrape afterwards to fill in the details.',
            items: result.new_roms,
            id: item => item,
            defaultChecked: () => true,
            render: item => <div>{item}</div>,
            action: 'Create entries',
            run: items => ({ url: 'entries/create', body: { rom_paths: items } }),
        },
        {
            key: 'orphaned_metadata',
            title: 'Gamelist entries with no ROM',
            help: 'No matching ROM was found. Removing deletes only the gamelist entry; no files are touched.',
            items: result.orphaned_metadata,
            id: item => item.path,
            defaultChecked: () => false,
            render: item => (
                <>
                    <div>{item.name || item.path}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:11}}>{item.path}</div>
                </>
            ),
            action: 'Remove from gamelist',
            run: items => ({ url: 'entries/remove', body: { paths: items.map(i => i.path) } }),
        },
        {
            key: 'orphaned_media',
            title: 'Media files nothing uses',
            help: `No ROM matches these and no gamelist entry refers to them. Moving puts them in ${result.media_system}/_orphaned/ so you can restore them by hand.`,
            items: result.orphaned_media,
            id: item => item,
            defaultChecked: () => false,
            render: item => <div>{item.split('/').slice(1).join('/')}</div>,
            action: 'Move to _orphaned',
            run: items => ({ url: 'orphaned-media/move', body: { files: items } }),
        },
    ];

    const initialSelection = () => {
        const selection = {};
        sections.forEach(s => s.items.forEach(item => { selection[`${s.key}:${s.id(item)}`] = s.defaultChecked(item); }));
        return selection;
    };
    const [selected, setSelected] = React.useState(initialSelection);
    const [busy, setBusy] = React.useState(null);
    React.useEffect(() => { setSelected(initialSelection()); }, [result]);

    const toggle = (key) => setSelected(prev => ({ ...prev, [key]: !prev[key] }));
    const setAll = (section, value) => setSelected(prev => {
        const next = { ...prev };
        section.items.forEach(item => { next[`${section.key}:${section.id(item)}`] = value; });
        return next;
    });

    const runAction = async (section) => {
        const items = section.items.filter(item => selected[`${section.key}:${section.id(item)}`]);
        if (!items.length) return;
        const { url, body } = section.run(items);
        setBusy(section.key);
        try {
            const res = await fetch(`${API_BASE}/api/systems/${encodeURIComponent(system.name)}/${url}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!data.success) {
                showNotification(data.error || `${section.action} failed`, 'error');
            } else {
                const backup = data.backup ? ` (backup: ${data.backup})` : '';
                const problems = data.errors && data.errors.length ? `, ${data.errors.length} failed` : '';
                const media = data.renamed_media ? `, ${data.renamed_media} media files renamed` : '';
                showNotification(`${section.action}: ${data.changed} done${media}${problems}${backup}`, problems ? 'error' : 'success');
            }
        } catch (err) {
            showNotification(`${section.action} failed: ${err.message}`, 'error');
        } finally {
            setBusy(null);
            onChanged();
        }
    };

    const total = sections.reduce((n, s) => n + s.items.length, 0);

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom:4}}>Scan: {system.full_name || system.name}</h2>
            <div style={{color:'var(--text-secondary)',fontSize:13,marginBottom:20}}>
                {total === 0 && !(result.duplicates || []).length ? 'Everything matches. Nothing to fix.' : 'Changes to gamelist.xml make a dated backup first (restore it from the settings button).'}
            </div>
            {(result.duplicates || []).length > 0 && (
                <div style={{display:'flex',gap:10,alignItems:'center',flexWrap:'wrap',padding:12,marginBottom:16,background:'var(--bg-tertiary)',borderRadius:6,fontSize:13}}>
                    <span><b>{result.duplicates.length}</b> game{result.duplicates.length === 1 ? '' : 's'} here may be in the library more than once.</span>
                    <button className="btn btn-secondary btn-small" onClick={() => window.dispatchEvent(new CustomEvent('retromanager:open-tool', { detail: { tool: 'duplicates', system: system.name } }))}>
                        Open Duplicates
                    </button>
                </div>
            )}
            {sections.filter(s => s.items.length > 0).map(section => {
                const count = section.items.filter(item => selected[`${section.key}:${section.id(item)}`]).length;
                return (
                    <div key={section.key} style={{marginBottom:20,background:'var(--bg-secondary)',border:'1px solid var(--border-color)',borderRadius:6,padding:14}}>
                        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,flexWrap:'wrap',marginBottom:6}}>
                            <h3 style={{fontSize:15,margin:0}}>{section.title} <span style={{color:'var(--accent-orange)'}}>({section.items.length})</span></h3>
                            <div style={{display:'flex',gap:6}}>
                                <button className="btn btn-secondary btn-small" onClick={() => setAll(section, true)}>All</button>
                                <button className="btn btn-secondary btn-small" onClick={() => setAll(section, false)}>None</button>
                                <button className="btn btn-primary btn-small" disabled={!count || busy} onClick={() => runAction(section)}>
                                    {busy === section.key ? 'Working...' : `${section.action} (${count})`}
                                </button>
                            </div>
                        </div>
                        <div style={{color:'var(--text-secondary)',fontSize:12,marginBottom:10,lineHeight:1.4}}>{section.help}</div>
                        <div style={{maxHeight:240,overflowY:'auto',display:'flex',flexDirection:'column',gap:4}}>
                            {section.items.map(item => {
                                const key = `${section.key}:${section.id(item)}`;
                                return (
                                    <label key={key} style={{display:'flex',gap:10,alignItems:'flex-start',padding:'6px 8px',background:'var(--bg-tertiary)',borderRadius:4,fontSize:13,cursor:'pointer',wordBreak:'break-word'}}>
                                        <input type="checkbox" checked={!!selected[key]} onChange={() => toggle(key)} style={{marginTop:3}} />
                                        <div style={{flex:1}}>{section.render(item)}</div>
                                    </label>
                                );
                            })}
                        </div>
                    </div>
                );
            })}
        </Modal>
    );
}
