// Tools: play history.
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
