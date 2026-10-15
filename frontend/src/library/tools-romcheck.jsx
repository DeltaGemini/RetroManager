// Tools: ROM check, and what it knows about one game's file.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const ROM_STATUS = {
    verified: { label: 'Verified', color: 'var(--success)', help: 'Listed in a ROM database as a known good dump' },
    known: { label: 'Recognised', color: 'var(--accent-blue)', help: 'Recognised, but not listed as a verified dump' },
    hack: { label: 'Hack', color: 'var(--accent-pink)', help: 'A ROM hack RetroAchievements lists' },
    unknown: { label: 'Not recognised', color: 'var(--accent-orange)', help: 'No database knows this file: a hack, a patched or trimmed ROM, or a bad dump' },
    skipped: { label: 'Not checked', color: 'var(--text-secondary)', help: 'A folder, a disc list, or a file too large to hash' },
};
const ROM_SOURCE_NAMES = { NoIntros: 'No-Intro', NoIntro: 'No-Intro', MAMEArcade: 'MAME', MAMEMess: 'MAME' };
const romSources = (sources) => (sources || []).map(s => ROM_SOURCE_NAMES[s] || s).join(', ');

// Tools > ROM check: hash every ROM in the background, then show what's verified,
// duplicated, mislabelled or unknown
function RomCheckPanel({ onClose }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [tab, setTab] = React.useState('summary');
    const refresh = React.useCallback(async () => {
        try {
            const d = await (await fetch(`${API_BASE}/api/rom-index`)).json();
            d.success ? setData(d) : setError(d.error || 'Could not load the ROM check');
            return d;
        } catch (e) { setError(e.message); return null; }
    }, []);
    useEffect(() => {
        let timer, stopped = false;
        const tick = async () => {
            const d = await refresh();
            if (!stopped) timer = setTimeout(tick, d && d.running ? 3000 : 30000);
        };
        tick();
        return () => { stopped = true; clearTimeout(timer); };
    }, [refresh]);
    const start = async (recheck) => { await postJson('/api/rom-index/start', { recheck }); refresh(); RM.tasksChanged(); };
    // Fixes: which mislabelled files are ticked, which copy of each duplicate to keep, and what the last fix did
    const [ticked, setTicked] = React.useState({});
    const [keep, setKeep] = React.useState({});
    const [working, setWorking] = React.useState(false);
    const [outcome, setOutcome] = React.useState(null);
    const romKey = (g) => `${g.system}/${g.rom_path}`;
    const renameTicked = async () => {
        const items = (data?.report?.mislabelled || []).filter(g => ticked[romKey(g)]);
        if (!items.length) return;
        setWorking(true);
        try {
            const d = await postJson('/api/rom-index/rename', { items: items.map(g => ({ system: g.system, rom_path: g.rom_path })) });
            const problems = (d.results || []).filter(r => r.error || (r.errors || []).length).map(r => `${r.rom_path}: ${r.error || r.errors.join('; ')}`);
            setOutcome({ text: `Renamed ${d.renamed || 0} file${d.renamed === 1 ? '' : 's'}.`, problems });
            setTicked({});
            announceGameChange();
        } catch (e) { setOutcome({ text: 'Renaming failed.', problems: [e.message] }); }
        setWorking(false);
        refresh();
    };
    const moveCopies = async (group) => {
        const kept = keep[romKey(group[0])] || romKey(group[0]);
        setWorking(true);
        try {
            const d = await postJson('/api/rom-index/duplicates/resolve', {
                keep: group.find(g => romKey(g) === kept), remove: group.filter(g => romKey(g) !== kept) });
            setOutcome({ text: d.success ? `Moved ${d.moved.length} cop${d.moved.length === 1 ? 'y' : 'ies'} to ${d.moved_to}.` : (d.error || 'Nothing was moved.'), problems: d.errors || [] });
            announceGameChange();
        } catch (e) { setOutcome({ text: 'Moving failed.', problems: [e.message] }); }
        setWorking(false);
        refresh();
    };
    const stop = async () => { await postJson('/api/rom-index/stop', {}); refresh(); RM.tasksChanged(); };

    const report = data?.report;
    const gameRow = (g, extra) => (
        <a key={`${g.system}/${g.rom_path}`} href={gameLink(g.system, g.rom_path)}
            style={{display: 'flex', gap: 10, alignItems: 'baseline', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, textDecoration: 'none', color: 'inherit'}}>
            <div style={{flex: 1, minWidth: 0}}>
                <div style={{fontWeight: 600}}>{g.name}</div>
                <div style={{color: 'var(--text-secondary)', fontSize: 12, wordBreak: 'break-word'}}>{g.full_name} · {g.rom_path}</div>
            </div>
            {extra && <div style={{fontSize: 12, textAlign: 'right', maxWidth: '50%'}}>{extra}</div>}
        </a>
    );
    const TABS = report ? [
        ['summary', 'Summary'],
        ['duplicates', `Duplicates (${report.duplicates.length})`],
        ['mislabelled', `Name doesn't match (${report.mislabelled.length})`],
        ['unknown', `Not recognised (${report.unknown.length})`],
        ['hacks', `Hacks (${report.hacks.length})`],
    ] : [];
    const list = (rows, empty, extra) => (
        <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
            {!rows.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>{empty}</div>}
            {rows.map(g => gameRow(g, extra && extra(g)))}
        </div>
    );

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>ROM check</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 660}}>
                Works out each ROM's checksum and looks it up in the ROM databases (No-Intro, Redump, TOSEC) and on RetroAchievements.
                It runs in the background, and only looks again at files that are new or changed. Nothing in the library is changed.
            </div>
            {error && <div role="alert" style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {!data && !error && <div style={{color: 'var(--text-secondary)'}}>Loading...</div>}
            {data && (
                <>
                    <div style={{display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                        {data.running ? (
                            <>
                                <div style={{flex: 1, minWidth: 220}}>
                                    <div style={{fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6}}>
                                        Checking {Math.min(data.done + 1, data.total)} of {data.total}{data.current && <>: <b style={{color: 'var(--text-primary)'}}>{data.current.name}</b> ({data.current.system_name})</>}
                                    </div>
                                    <div style={{height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden'}}>
                                        <div style={{height: '100%', width: `${data.total ? (data.done / data.total) * 100 : 0}%`, background: 'var(--accent-orange)', transition: 'width 0.3s'}} />
                                    </div>
                                </div>
                                <button className="btn btn-secondary" onClick={stop} disabled={data.stopping}>{data.stopping ? 'Stopping...' : 'Stop'}</button>
                            </>
                        ) : (
                            <>
                                <button className="btn btn-primary" onClick={() => start(false)}>{report && report.checked ? 'Check new and changed files' : 'Check the library'}</button>
                                {report && report.checked > 0 && <button className="btn btn-secondary" onClick={() => start(true)}>Check everything again</button>}
                                <span style={{fontSize: 12, color: 'var(--text-secondary)'}}>
                                    {report && report.checked ? `${report.checked} files checked` : 'Nothing checked yet'}
                                    {data.finished && ` · last run ${timeAgo(new Date(data.finished).getTime())}`}
                                    {data.stopped_reason && data.stopped_reason !== 'Stopped' && <span style={{color: 'var(--accent-pink)'}}> · stopped: {data.stopped_reason}</span>}
                                </span>
                            </>
                        )}
                    </div>
                    {report && report.checked > 0 && (
                        <>
                            <div role="tablist" style={{display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12}}>
                                {TABS.map(([key, label]) => (
                                    <button key={key} role="tab" aria-selected={tab === key} className={`btn btn-small ${tab === key ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab(key)}>{label}</button>
                                ))}
                            </div>
                            {outcome && (
                                <div role="status" style={{marginBottom: 10, padding: '8px 10px', borderRadius: 4, fontSize: 13, background: 'var(--bg-tertiary)', border: `1px solid ${outcome.problems.length ? 'var(--accent-pink)' : 'var(--success)'}`}}>
                                    {outcome.text}
                                    {outcome.problems.map((p, i) => <div key={i} style={{color: 'var(--accent-pink)', fontSize: 12}}>{p}</div>)}
                                </div>
                            )}
                            <div style={{maxHeight: '52vh', overflowY: 'auto'}}>
                                {tab === 'summary' && (
                                    <>
                                        <div style={{display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12, fontSize: 13}}>
                                            {Object.keys(ROM_STATUS).map(key => (
                                                <span key={key} title={ROM_STATUS[key].help}><b style={{color: ROM_STATUS[key].color}}>{report.counts[key] || 0}</b> {ROM_STATUS[key].label.toLowerCase()}</span>
                                            ))}
                                        </div>
                                        <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 13}}>
                                            <thead>
                                                <tr style={{textAlign: 'right', color: 'var(--text-secondary)'}}>
                                                    <th style={{textAlign: 'left', padding: '4px 6px', fontWeight: 400}}>System</th>
                                                    {Object.keys(ROM_STATUS).map(key => <th key={key} style={{padding: '4px 6px', fontWeight: 400}}>{ROM_STATUS[key].label}</th>)}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {report.by_system.map(s => (
                                                    <tr key={s.system} style={{textAlign: 'right', borderTop: '1px solid var(--border-color)'}}>
                                                        <td style={{textAlign: 'left', padding: '4px 6px'}}>{s.full_name}</td>
                                                        {Object.keys(ROM_STATUS).map(key => <td key={key} style={{padding: '4px 6px', color: s[key] ? 'inherit' : 'var(--text-secondary)'}}>{s[key] || 0}</td>)}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </>
                                )}
                                {tab === 'duplicates' && (
                                    <>
                                        {!report.duplicates.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No two files have the same contents.</div>}
                                        {report.duplicates.length > 0 && <div style={{fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10}}>Choose the copy to keep in each set. The others are moved out of the library (to the duplicates folder in RetroManager's data folder, nothing is deleted), their gamelist entries are removed, and the kept copy takes over their play status and collections.</div>}
                                        {report.duplicates.map((group, i) => {
                                            const kept = keep[romKey(group[0])] || romKey(group[0]);
                                            return (
                                                <div key={i} style={{marginBottom: 12, padding: 8, background: 'var(--bg-tertiary)', borderRadius: 4}}>
                                                    {group.map(g => (
                                                        <label key={romKey(g)} style={{display: 'flex', gap: 10, alignItems: 'baseline', padding: '4px 0', fontSize: 13, cursor: 'pointer'}}>
                                                            <input type="radio" name={`keep-${i}`} checked={kept === romKey(g)} onChange={() => setKeep(prev => ({ ...prev, [romKey(group[0])]: romKey(g) }))} />
                                                            <span style={{flex: 1, minWidth: 0}}>
                                                                <b>{g.name}</b> <span style={{color: 'var(--text-secondary)', fontSize: 12, wordBreak: 'break-word'}}>· {g.full_name} · {g.rom_path}</span>
                                                            </span>
                                                            <span style={{fontSize: 11, color: kept === romKey(g) ? 'var(--success)' : 'var(--text-secondary)'}}>{kept === romKey(g) ? 'keep' : 'move aside'}</span>
                                                        </label>
                                                    ))}
                                                    <button className="btn btn-secondary btn-small" style={{marginTop: 6}} disabled={working} onClick={() => moveCopies(group)}>
                                                        Move the other {group.length === 2 ? 'copy' : `${group.length - 1} copies`} aside
                                                    </button>
                                                </div>
                                            );
                                        })}
                                    </>
                                )}
                                {tab === 'mislabelled' && (
                                    <>
                                        {!report.mislabelled.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>Every recognised file is named like the game inside it.</div>}
                                        {report.mislabelled.length > 0 && (
                                            <div style={{display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10}}>
                                                <span style={{flex: 1, minWidth: 220, fontSize: 12, color: 'var(--text-secondary)'}}>Tick the ones that really are misnamed (a different edition or translation of the same game is fine as it is). Renaming gives the file the database's name, and renames its media, saves and save states to match.</span>
                                                <button className="btn btn-primary btn-small" disabled={working || !Object.values(ticked).some(Boolean)} onClick={renameTicked}>
                                                    {working ? 'Working...' : `Rename ${Object.values(ticked).filter(Boolean).length || ''} to match`}
                                                </button>
                                            </div>
                                        )}
                                        <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
                                            {report.mislabelled.map(g => (
                                                <div key={romKey(g)} style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 8px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13}}>
                                                    <input type="checkbox" aria-label={`Rename ${g.rom_path}`} checked={!!ticked[romKey(g)]} onChange={() => setTicked(prev => ({ ...prev, [romKey(g)]: !prev[romKey(g)] }))} />
                                                    <a href={gameLink(g.system, g.rom_path)} style={{flex: 1, minWidth: 0, color: 'inherit', textDecoration: 'none'}}>
                                                        <div style={{fontWeight: 600}}>{g.name}</div>
                                                        <div style={{color: 'var(--text-secondary)', fontSize: 12, wordBreak: 'break-word'}}>{g.full_name} · {g.rom_path}</div>
                                                    </a>
                                                    <div style={{fontSize: 12, textAlign: 'right', maxWidth: '45%'}}>contains<br /><b>{g.known_name}</b></div>
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                )}
                                {tab === 'unknown' && list(report.unknown, 'Every file checked is in a database.')}
                                {tab === 'hacks' && list(report.hacks, 'No ROM hacks recognised. (This needs a RetroAchievements key in Settings.)', g => g.known_name)}
                            </div>
                        </>
                    )}
                </>
            )}
        </Modal>
    );
}
