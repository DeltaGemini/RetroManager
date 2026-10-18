// The rows of the panel about you and the game: favourite, play status and
// collections; RetroAchievements; saves and save states. Part of the Game Details panel (src/common/game-details.jsx), loaded after it on every page
// that shows the panel; they share one global scope, so this uses its gd... helpers.

const GD_STATUSES = [['playing', 'Playing', '⏵'], ['backlog', 'Backlog', '🕓'], ['finished', 'Finished', '✔']];

// Favourite, play status and collections
function GDStatus({ system, game, notify, onChanged }) {
    const [status, setStatus] = React.useState(game.play_status || null);
    const [favorite, setFavorite] = React.useState(!!game.favorite);
    const [member, setMember] = React.useState(game.collections || []);
    const [collections, setCollections] = React.useState(null);
    const [newName, setNewName] = React.useState('');
    const [menuOpen, setMenuOpen] = React.useState(false);
    const [find, setFind] = React.useState('');
    const menuRef = React.useRef(null);
    React.useEffect(() => {
        if (!menuOpen) return;
        const close = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
        const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); setMenuOpen(false); } };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', esc, true);
        return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc, true); };
    }, [menuOpen]);
    React.useEffect(() => {
        setStatus(game.play_status || null);
        setFavorite(!!game.favorite);
        setMember(game.collections || []);
        setMenuOpen(false);
        setFind('');
        setNewName('');
    }, [system, game.path]);
    // Fetched at first, and again each time the checklist opens (the Collections tool may have changed them)
    React.useEffect(() => {
        fetch(`${GD_API}/api/library-state`).then(r => r.json()).then(d => {
            if (!d.success) return;
            setCollections(d.collections);
            // ...and which of them hold this game now (another page may have changed that)
            const key = `${system}/${String(game.path).replace(/^(\.\/)+/, '')}`;
            setMember(d.collections.filter(c => (c.games || []).includes(key)).map(c => c.id));
        }).catch(() => {});
    }, [menuOpen]);

    const who = { system, rom_path: game.path };
    const send = async (url, body, method = 'PUT') => {
        try {
            const res = await fetch(`${GD_API}${url}`, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            const d = await res.json();
            if (!d.success && notify) notify(d.error || 'That didn\'t work', 'error');
            return d;
        } catch (e) {
            if (notify) notify(e.message, 'error');
            return { success: false };
        }
    };
    // The game object is the page's own, so lists drawn from it follow
    const changed = (patch) => {
        Object.assign(game, patch);
        if (onChanged) onChanged(patch);
        window.dispatchEvent(new Event('retromanager:game-changed'));
    };
    const pickStatus = async (key) => {
        const next = status === key ? null : key;
        const d = await send('/api/play-status', { ...who, status: next });
        if (d.success) { setStatus(next); changed({ play_status: next }); }
    };
    const toggleFavorite = async () => {
        const d = await send('/api/favorite', { ...who, favorite: !favorite });
        if (d.success) { setFavorite(d.favorite); changed({ favorite: d.favorite, has_metadata: true }); }
    };
    // (one change at a time: a second click before the first is answered would be sent from the old state)
    const [toggling, setToggling] = React.useState(null);
    const toggleCollection = async (id) => {
        if (toggling) return;
        setToggling(id);
        const d = await send(`/api/collections/${id}/games`, { ...who, member: !member.includes(id) });
        setToggling(null);
        if (d.success) {
            setMember(d.collections);
            const key = `${system}/${String(game.path).replace(/^(\.\/)+/, '')}`;
            setCollections(prev => (prev || []).map(c => c.id !== id ? c : { ...c, games: d.collections.includes(id) ? [...new Set([...c.games, key])] : c.games.filter(g => g !== key) }));
            changed({ collections: d.collections });
        }
    };
    const createCollection = async () => {
        const name = newName.trim();
        if (!name) return;
        const d = await send('/api/collections', { name }, 'POST');
        if (!d.success) return;
        setCollections(prev => [...(prev || []), d.collection]);
        setNewName('');
        toggleCollection(d.collection.id);
    };

    return (
        <div className="gd-status">
            <button className={`gd-chip${favorite ? ' on gd-fav' : ''}`} onClick={toggleFavorite} aria-pressed={favorite}
                title={favorite ? 'Remove from favourites' : 'Add to favourites (EmulationStation shows these too)'}>{favorite ? '★' : '☆'} Favourite</button>
            <span role="group" aria-label="Play status" className="gd-chip-group">
                {GD_STATUSES.map(([key, label, icon]) => (
                    <button key={key} className={`gd-chip${status === key ? ' on' : ''}`} onClick={() => pickStatus(key)} aria-pressed={status === key}>{icon} {label}</button>
                ))}
            </span>
            <span ref={menuRef} className="gd-menu-wrap admin-only">
                <button className={`gd-chip${member.length ? ' on' : ''}`} onClick={() => setMenuOpen(o => !o)} aria-haspopup="dialog" aria-expanded={menuOpen}
                    title="Choose which collections this game is in">
                    📁 {member.length === 0 ? 'Collections' : member.length === 1 ? ((collections || []).find(c => c.id === member[0]) || {}).name || '1 collection' : `${member.length} collections`} ▾
                </button>
                {menuOpen && (
                    <div role="dialog" aria-label="Collections" className="gd-menu">
                        {(collections || []).length > 6 && (
                            <input type="search" autoFocus value={find} placeholder="Find a collection" onChange={e => setFind(e.target.value)} />
                        )}
                        <div className="gd-menu-list">
                            {collections && !collections.length && <div className="gd-note">No collections yet. Name one below to start it with this game.</div>}
                            {(collections || []).filter(c => c.name.toLowerCase().includes(find.trim().toLowerCase())).map(c => (
                                <label key={c.id}>
                                    <input type="checkbox" checked={member.includes(c.id)} disabled={!!toggling} onChange={() => toggleCollection(c.id)} />
                                    <span className="gd-menu-name">{c.name}</span>
                                    <span className="gd-note">{c.games.length}</span>
                                </label>
                            ))}
                        </div>
                        <div className="gd-menu-new">
                            <input type="text" value={newName} placeholder="New collection..." maxLength={60} onChange={e => setNewName(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') createCollection(); }} />
                            <button className="gd-btn small" onClick={createCollection} disabled={!newName.trim()}>Add</button>
                        </div>
                    </div>
                )}
            </span>
        </div>
    );
}

// The game's RetroAchievements: completion, then every achievement with the
// earned ones in colour. Not shown at all without a RetroAchievements API key (Tools > Settings).
function GDAchievements({ system, game }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [loading, setLoading] = React.useState(false);
    // Whose progress to show (a name from Settings; '' is the main user), remembered in this browser
    const [who, setWhoState] = React.useState(() => { try { return localStorage.getItem('retromanager.achievements.who') || ''; } catch (e) { return ''; } });
    const setWho = (name) => { setWhoState(name); try { localStorage.setItem('retromanager.achievements.who', name); } catch (e) {} };
    const [filter, setFilter] = React.useState('all'); // all | earned | locked
    const [showAll, setShowAll] = React.useState(false);
    const PREVIEW_COUNT = 12;

    const load = React.useCallback((refresh) => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        const params = new URLSearchParams({ rom: game.path, ...(who ? { who } : {}), ...(refresh ? { refresh: '1' } : {}) });
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/achievements?${params}`)
            .then(r => r.json())
            .then(d => { if (!cancelled) d.success ? setData(d) : setError(d.error || 'Could not load achievements'); })
            .catch(err => { if (!cancelled) setError(err.message); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [system, game.path, who]);

    React.useEffect(() => {
        setData(null);
        setFilter('all');
        setShowAll(false);
        return load(false);
    }, [load]);

    if (data && !data.configured) return null;
    const section = (summary, content) => <GDSection id="achievements" title="Achievements" summary={summary}>{content}</GDSection>;
    if (error) return section('Couldn\'t load', <div className="gd-note gd-error">{error}</div>);
    if (!data) return section('Looking up…', <div className="gd-note">Looking this game up on RetroAchievements...</div>);
    if (!data.matched) {
        return section('Not recognised', (
            <div className="gd-row">
                <span className="gd-note">RetroAchievements doesn't recognise this ROM file, so it has no achievements to show.</span>
                <button className="gd-btn small" disabled={loading} onClick={() => load(true)}>{loading ? 'Checking...' : 'Check again'}</button>
            </div>
        ));
    }
    if (!data.total) {
        return section('None yet', <div className="gd-note">RetroAchievements knows this game (<a href={data.url} target="_blank" rel="noopener noreferrer">{data.title}</a>) but has no achievements for it yet.</div>);
    }

    const list = data.achievements.filter(a => filter === 'all' || (filter === 'earned' ? a.earned : !a.earned));
    const shown = showAll ? list : list.slice(0, PREVIEW_COUNT);
    const TYPE_LABELS = { progression: 'Progression', win_condition: 'Beats the game', missable: 'Missable' };
    // RetroAchievements gives times in UTC
    const earnedDate = (text) => new Date(text.replace(' ', 'T') + 'Z');
    const summary = data.user ? `${data.earned} of ${data.total} · ${Math.round(data.completion)}%` : `${data.total} to earn`;

    return section(summary, (
        <>
            <div className="gd-row" style={{alignItems: 'baseline'}}>
                {data.user ? (
                    <>
                        <span className="gd-big">{Math.round(data.completion)}%</span>
                        <span>
                            <b>{data.earned}</b> of {data.total} earned · {data.points_earned} of {data.points} points
                            {data.earned_hardcore > 0 && ` · ${data.earned_hardcore} in hardcore`}
                        </span>
                    </>
                ) : (
                    <span>{data.total} achievements · {data.points} points</span>
                )}
                <span style={{flex: 1}} />
                <a href={data.url} target="_blank" rel="noopener noreferrer" className="gd-small">{data.title} on RetroAchievements ↗</a>
                <button className="gd-btn small" disabled={loading} onClick={() => load(true)} title="Fetch the latest from RetroAchievements">{loading ? 'Refreshing...' : 'Refresh'}</button>
            </div>
            {data.user ? (
                <div className="gd-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(data.completion)} aria-label="Achievements earned">
                    <div style={{width: `${data.completion}%`, background: data.earned === data.total ? 'var(--success)' : 'var(--accent-orange)'}} />
                </div>
            ) : <div className="gd-note">Add your RetroAchievements user name in Tools › Settings to show which ones have been earned.</div>}
            {data.user && (
                <div className="gd-row gd-small" style={{margin: '10px 0'}}>
                    <span className="gd-note">Earned by {(data.people || []).length > 1 ? (
                        <select value={who || data.people[0]} onChange={e => setWho(e.target.value)} aria-label="Whose achievements">
                            {data.people.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                    ) : data.user}</span>
                    {[['all', `All ${data.total}`], ['earned', `Earned ${data.earned}`], ['locked', `Not yet ${data.total - data.earned}`]].map(([key, label]) => (
                        <button key={key} className={`gd-btn small${filter === key ? ' primary' : ''}`} onClick={() => { setFilter(key); setShowAll(false); }}>{label}</button>
                    ))}
                </div>
            )}
            {!list.length && <div className="gd-note">{filter === 'earned' ? 'None earned yet.' : 'Every achievement is earned.'}</div>}
            <div className="gd-cheevos">
                {shown.map(a => (
                    <div key={a.id} className={`gd-cheevo${a.earned ? ' earned' : ''}${a.earned || !data.user ? '' : ' locked'}`}>
                        <img src={a.earned || !data.user ? a.badge : a.badge_locked} alt="" loading="lazy" width="44" height="44" onError={e => { e.target.style.visibility = 'hidden'; }} />
                        <div style={{flex: 1, minWidth: 0}}>
                            <div className="gd-cheevo-title">
                                {a.earned && <span className="gd-ok" aria-label="Earned">✓ </span>}
                                {a.title} <span className="gd-note">({a.points})</span>
                            </div>
                            <div className="gd-note">{a.description}</div>
                            <div className={`gd-tiny${a.earned ? ' gd-ok' : ' gd-note'}`}>
                                {a.earned && <span title={earnedDate(a.earned).toLocaleString()}>Earned {gdAgo(earnedDate(a.earned).getTime())}{a.hardcore ? ' · hardcore' : ''}</span>}
                                {a.earned && TYPE_LABELS[a.type] && ' · '}
                                {TYPE_LABELS[a.type]}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
            {list.length > PREVIEW_COUNT && (
                <button className="gd-btn small" style={{marginTop: 8}} onClick={() => setShowAll(v => !v)}>
                    {showAll ? 'Show fewer' : `Show all ${list.length}`}
                </button>
            )}
        </>
    ));
}

// Saves and save states found for the game, by person
function GDSaves({ system, game }) {
    const [data, setData] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [expanded, setExpanded] = React.useState({});
    const PREVIEW_COUNT = 5;

    React.useEffect(() => {
        let cancelled = false;
        setData(null);
        setError(null);
        setExpanded({});
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/saves?${new URLSearchParams({ rom: game.path })}`)
            .then(r => r.json())
            .then(d => { if (!cancelled) d.success ? setData(d) : setError(d.error || 'Could not load saves'); })
            .catch(err => { if (!cancelled) setError(err.message); });
        return () => { cancelled = true; };
    }, [system, game.path]);

    const section = (summary, content) => <GDSection id="saves" title="Saves" summary={summary}>{content}</GDSection>;
    if (error) return section('Couldn\'t load', <div className="gd-note gd-error">{error}</div>);
    if (!data) return section('Looking…', <div className="gd-note">Looking for saves...</div>);
    if (!Object.values(data.available || {}).some(Boolean)) {
        return section('Not set up', <div className="gd-note">The saves folders aren't mounted. Add them to docker-compose.yml (see the README).</div>);
    }

    // Each person in the configured order, then the shared in-game saves,
    // then older states that sit outside anyone's folder (collapsed)
    const groupOf = (s) => s.profile !== 'shared' ? s.profile : s.root === 'saves' ? 'shared-saves' : 'shared-states';
    const GROUP_LABELS = { 'shared-saves': 'In-game saves (shared)', 'shared-states': "Old save states, not in a person's folder" };
    const groups = [...data.profiles, 'shared-saves', 'shared-states']
        .map(profile => ({ profile, items: data.saves.filter(s => groupOf(s) === profile) }))
        .filter(g => g.items.length);
    if (!groups.length) return section('None', <div className="gd-note">No saves or save states for this game.</div>);

    const shot = (s) => `${GD_API}/api/save-screenshot/${s.root}/${gdEncode(s.screenshot)}`;
    const row = (s) => (
        <div key={`${s.root}/${s.path}`} className="gd-save">
            {s.screenshot
                ? <a className="gd-save-shot" href={shot(s)} target="_blank" rel="noopener noreferrer" title="Open the screenshot"><img src={shot(s)} alt="" loading="lazy" /></a>
                : <span className="gd-save-shot" aria-hidden="true">{s.kind === 'save' ? '💾' : '⏸'}</span>}
            <div style={{flex: 1, minWidth: 0}}>
                <div className="gd-cheevo-title">
                    {s.label}
                    {s.empty && <span className="gd-badge" title="The file is there but nothing was ever saved in it: the game starts with no save">Empty</span>}
                    {s.conflict && <span className="gd-badge" title="Syncthing kept two versions of this file">Sync conflict</span>}
                </div>
                <div className="gd-note gd-clip" title={`${s.root}/${s.path}`}>{s.root}/{s.path}</div>
            </div>
            <div className="gd-small" style={{textAlign: 'right', flexShrink: 0}}>
                <div title={new Date(s.modified).toLocaleString()}>{gdAgo(new Date(s.modified).getTime())}</div>
                <div className="gd-note">{RM.bytes(s.size)}</div>
            </div>
        </div>
    );
    const newestOverall = Math.max(...data.saves.map(s => new Date(s.modified).getTime()));

    return section(`${data.saves.length} file${data.saves.length === 1 ? '' : 's'} · latest ${gdAgo(newestOverall)}`, (
        <>
            <div className="gd-row gd-small">
                <span className="gd-note" style={{flex: 1, minWidth: 200}}>
                    Found by file name in the saves and savestates folders.
                    {data.saves.some(s => s.conflict) && ' Resolve sync conflicts in Tools › Saves.'}
                </span>
                <a className="gd-btn small" href={`${GD_API}/api/systems/${encodeURIComponent(system)}/saves/download?${new URLSearchParams({ rom: game.path })}`}>Download all (zip)</a>
            </div>
            {groups.map(({ profile, items }) => {
                const open = expanded[profile] ?? profile !== 'shared-states';
                const showAll = expanded[`${profile}:all`];
                const shown = showAll ? items : items.slice(0, PREVIEW_COUNT);
                return (
                    <div key={profile} style={{marginTop: 10}}>
                        <button className="gd-group-head" onClick={() => setExpanded(prev => ({ ...prev, [profile]: !open }))} aria-expanded={open}>
                            <span className="gd-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
                            {GROUP_LABELS[profile] || profile[0].toUpperCase() + profile.slice(1)}
                            <span className="gd-note">{items.length} file{items.length > 1 ? 's' : ''} · latest {gdAgo(new Date(items[0].modified).getTime())}</span>
                        </button>
                        {open && (
                            <div className="gd-saves">
                                {shown.map(row)}
                                {items.length > PREVIEW_COUNT && (
                                    <button className="gd-btn small" style={{alignSelf: 'flex-start'}} onClick={() => setExpanded(prev => ({ ...prev, [`${profile}:all`]: !showAll }))}>
                                        {showAll ? 'Show fewer' : `Show all ${items.length}`}
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </>
    ));
}
