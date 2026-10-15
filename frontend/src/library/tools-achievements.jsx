// Tools: achievement overview.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Tools > Achievement overview: every game with RetroAchievements progress,
// ranked by how much of it is earned
const AWARD_LABELS = { mastered: 'Mastered', completed: 'Completed', 'beaten-hardcore': 'Beaten (hardcore)', 'beaten-softcore': 'Beaten' };
const ACHIEVEMENT_SORTS = {
    completion: { label: 'Most complete', compare: (a, b) => b.completion - a.completion || b.earned - a.earned },
    closest: { label: 'Closest to finishing', compare: (a, b) => (a.total - a.earned) - (b.total - b.earned) || b.completion - a.completion },
    earned: { label: 'Most earned', compare: (a, b) => b.earned - a.earned || b.completion - a.completion },
    recent: { label: 'Earned most recently', compare: (a, b) => (b.last_earned || '').localeCompare(a.last_earned || '') },
};
function AchievementOverviewPanel({ onClose }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [loading, setLoading] = React.useState(false);
    const [sortKey, setSortKey] = React.useState('completion');
    const [libraryOnly, setLibraryOnly] = React.useState(false);
    // Whose achievements (a name from Settings; '' is the main user), and which list is showing
    const [who, setWho] = React.useState('');
    const [tab, setTab] = React.useState('games');   // games | unlocks
    const [unlocks, setUnlocks] = React.useState(null);
    const load = (refresh) => {
        setLoading(true);
        setError(null);
        const query = new URLSearchParams({ ...(who ? { who } : {}), ...(refresh ? { refresh: '1' } : {}) });
        fetch(`${API_BASE}/api/achievements/overview?${query}`).then(r => r.json())
            .then(d => d.success ? setData(d) : setError(d.error || 'Could not load achievements'))
            .catch(e => setError(e.message))
            .finally(() => setLoading(false));
        fetch(`${API_BASE}/api/achievements/unlocks?${query}`).then(r => r.json())
            .then(d => { if (d.success) setUnlocks(d); }).catch(() => {});
    };
    useEffect(() => { load(false); }, [who]);

    const games = (data?.games || []).filter(g => !libraryOnly || g.library).slice().sort(ACHIEVEMENT_SORTS[sortKey].compare);
    const earned = games.reduce((n, g) => n + g.earned, 0);
    const total = games.reduce((n, g) => n + g.total, 0);
    const finished = games.filter(g => g.total > 0 && g.earned === g.total).length;
    // RetroAchievements gives times in UTC
    const earnedDate = (text) => new Date(text.replace(' ', 'T').replace(/([+-]\d\d:\d\d|Z)?$/, m => m || 'Z'));

    const row = (g, rank) => {
        const done = g.total > 0 && g.earned === g.total;
        const content = (
            <>
                <div style={{width: 24, textAlign: 'right', color: 'var(--text-secondary)', fontSize: 12, flexShrink: 0}}>{rank}</div>
                <img src={g.icon || ''} alt="" loading="lazy" width="40" height="40" style={{flexShrink: 0, borderRadius: 4, background: 'var(--bg-secondary)'}}
                    onError={e => { e.target.style.visibility = 'hidden'; }} />
                <div style={{flex: 1, minWidth: 0}}>
                    <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                        {g.library ? g.library.name : g.title}
                        {g.is_hack && <span style={{marginLeft: 8, fontSize: 11, padding: '1px 6px', borderRadius: 3, border: '1px solid var(--accent-pink)', color: 'var(--accent-pink)', fontWeight: 400}}>Hack</span>}
                        {AWARD_LABELS[g.award] && <span style={{marginLeft: 8, fontSize: 11, padding: '1px 6px', borderRadius: 3, border: '1px solid var(--success)', color: 'var(--success)', fontWeight: 400}}>{AWARD_LABELS[g.award]}</span>}
                    </div>
                    <div style={{color: 'var(--text-secondary)', fontSize: 12}}>
                        {g.library ? g.library.full_name : `${g.console} · not in the library`}
                        {g.last_earned && <span title={earnedDate(g.last_earned).toLocaleString()}> · last earned {timeAgo(earnedDate(g.last_earned).getTime())}</span>}
                    </div>
                    <div style={{height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden', marginTop: 5}}>
                        <div style={{height: '100%', width: `${g.completion}%`, background: done ? 'var(--success)' : 'var(--accent-orange)'}} />
                    </div>
                </div>
                <div style={{textAlign: 'right', flexShrink: 0, width: 92}}>
                    <div style={{fontSize: 18, fontWeight: 700, color: done ? 'var(--success)' : 'inherit'}}>{Math.round(g.completion)}%</div>
                    <div style={{color: 'var(--text-secondary)', fontSize: 12}}>{g.earned} of {g.total}{g.earned_hardcore > 0 ? ` · ${g.earned_hardcore} HC` : ''}</div>
                </div>
            </>
        );
        const style = {display: 'flex', gap: 10, alignItems: 'center', padding: '8px 10px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, textDecoration: 'none', color: 'inherit'};
        // A game in the library opens its page; any other opens on RetroAchievements
        return g.library
            ? <a key={g.game_id} href={gameLink(g.library.system, g.library.rom_path)} style={style} title="Open this game">{content}</a>
            : <a key={g.game_id} href={g.url} target="_blank" rel="noopener noreferrer" style={style} title="Open on RetroAchievements">{content}</a>;
    };

    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Achievement overview</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 640}}>
                Every game {data?.user || 'you'} {data?.user ? 'has' : 'have'} earned a RetroAchievements achievement in, ranked by how much of it is done.
            </div>
            {error && <div style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {!data && !error && <div style={{color: 'var(--text-secondary)'}}>Asking RetroAchievements...</div>}
            {data && !data.configured && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>Add your RetroAchievements API key and user name in Tools › Settings to use this.</div>}
            {data && data.configured && (
                <>
                    <div style={{display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'baseline', marginBottom: 12}}>
                        <div><span style={{fontSize: 22, fontWeight: 700}}>{total ? Math.round(100 * earned / total) : 0}%</span> <span style={{fontSize: 13, color: 'var(--text-secondary)'}}>overall</span></div>
                        <div style={{fontSize: 13}}><b>{earned}</b> of {total} achievements</div>
                        <div style={{fontSize: 13}}><b>{games.length}</b> game{games.length === 1 ? '' : 's'}{finished > 0 && ` · ${finished} finished`}</div>
                    </div>
                    <div role="tablist" style={{display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12}}>
                        <button role="tab" aria-selected={tab === 'games'} className={`btn btn-small ${tab === 'games' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('games')}>Games</button>
                        <button role="tab" aria-selected={tab === 'unlocks'} className={`btn btn-small ${tab === 'unlocks' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('unlocks')}>Recent unlocks{unlocks ? ` (${unlocks.count})` : ''}</button>
                        {(data.people || []).length > 1 && (
                            <select value={who || data.people[0]} onChange={e => setWho(e.target.value)} aria-label="Whose achievements"
                                style={{marginLeft: 'auto', padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13}}>
                                {data.people.map(p => <option key={p} value={p}>{p}</option>)}
                            </select>
                        )}
                    </div>
                    {tab === 'unlocks' && (
                        <div style={{display: 'flex', flexDirection: 'column', gap: 4, maxHeight: '58vh', overflowY: 'auto'}}>
                            {!unlocks && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>Asking RetroAchievements...</div>}
                            {unlocks && !unlocks.unlocks.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No achievements earned yet.</div>}
                            {unlocks && unlocks.unlocks.map((u, i) => (
                                <a key={i} href={`https://retroachievements.org/game/${u.game_id}`} target="_blank" rel="noopener noreferrer"
                                    style={{display: 'flex', gap: 10, alignItems: 'center', padding: '6px 10px', background: 'var(--bg-tertiary)', borderRadius: 4, fontSize: 13, textDecoration: 'none', color: 'inherit'}}>
                                    <img src={u.badge || ''} alt="" loading="lazy" width="40" height="40" style={{flexShrink: 0, borderRadius: 4, background: 'var(--bg-secondary)'}} onError={e => { e.target.style.visibility = 'hidden'; }} />
                                    <div style={{flex: 1, minWidth: 0}}>
                                        <div style={{fontWeight: 600}}>{u.title} <span style={{color: 'var(--text-secondary)', fontWeight: 400}}>({u.points})</span></div>
                                        <div style={{color: 'var(--text-secondary)', fontSize: 12}}>{u.description}</div>
                                        <div style={{fontSize: 12}}>{u.game_title} <span style={{color: 'var(--text-secondary)'}}>· {u.console}</span></div>
                                    </div>
                                    <div style={{textAlign: 'right', flexShrink: 0, fontSize: 12, color: 'var(--text-secondary)'}} title={earnedDate(u.date).toLocaleString()}>
                                        {timeAgo(earnedDate(u.date).getTime())}{u.hardcore && <div style={{color: 'var(--success)'}}>hardcore</div>}
                                    </div>
                                </a>
                            ))}
                            {unlocks && unlocks.count > unlocks.unlocks.length && <div style={{color: 'var(--text-secondary)', fontSize: 12, padding: 4}}>The latest {unlocks.unlocks.length} of {unlocks.count}.</div>}
                        </div>
                    )}
                    {tab === 'games' && <>
                    <div style={{display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12, fontSize: 13}}>
                        <select value={sortKey} onChange={e => setSortKey(e.target.value)} aria-label="Rank by"
                            style={{padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)'}}>
                            {Object.entries(ACHIEVEMENT_SORTS).map(([key, sort]) => <option key={key} value={key}>{sort.label}</option>)}
                        </select>
                        <label style={{display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer'}}>
                            <input type="checkbox" checked={libraryOnly} onChange={e => setLibraryOnly(e.target.checked)} /> Only games in the library
                        </label>
                        <span style={{flex: 1}} />
                        <button className="btn btn-secondary btn-small" disabled={loading} onClick={() => load(true)}>{loading ? 'Refreshing...' : 'Refresh'}</button>
                    </div>
                    {!games.length && <div style={{color: 'var(--text-secondary)', fontSize: 13}}>No achievements earned yet.</div>}
                    <div style={{display: 'flex', flexDirection: 'column', gap: 4, maxHeight: '58vh', overflowY: 'auto'}}>
                        {games.map((g, i) => row(g, i + 1))}
                    </div>
                    </>}
                </>
            )}
        </Modal>
    );
}
