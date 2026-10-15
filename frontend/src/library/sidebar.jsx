// The systems sidebar: search, filters and sorting.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Who made each system, what kind it is and its console generation (common/systems.js)
const { makerOf, typeOf, generationGroup } = RM.systems;
const SYSTEM_SORTS = {
    name: (a, b) => (a.full_name || a.name).localeCompare(b.full_name || b.name),
    roms: (a, b) => b.rom_count - a.rom_count,
    missing: (a, b) => (b.missing_metadata_count || 0) - (a.missing_metadata_count || 0) || b.rom_count - a.rom_count,
    maker: (a, b) => makerOf(a.name).localeCompare(makerOf(b.name)) || (a.full_name || a.name).localeCompare(b.full_name || b.name),
    generation: (a, b) => generationGroup(a.name).rank - generationGroup(b.name).rank || (a.full_name || a.name).localeCompare(b.full_name || b.name),
};

function Sidebar({ systems, selectedSystem, onSystemSelect, onOpenGame, onResizeStart }) {
    const remembered = (key, fallback) => { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } };
    const [sortMode, setSortModeState] = React.useState(() => SYSTEM_SORTS[remembered('retromanager.systemSort', '')] ? remembered('retromanager.systemSort', '') : 'roms');
    const setSortMode = (m) => { setSortModeState(m); try { localStorage.setItem('retromanager.systemSort', m); } catch (e) {} };
    const [query, setQuery] = React.useState('');
    const [filtersOpen, setFiltersOpen] = React.useState(false);
    const [makers, setMakers] = React.useState([]);
    const [types, setTypes] = React.useState([]);
    const [needsWork, setNeedsWork] = React.useState(false);
    const [showEmpty, setShowEmpty] = React.useState(false);
    // Every game in the library, fetched the first time you search
    const [library, setLibrary] = React.useState(null);
    const [gameLimit, setGameLimit] = React.useState(25);

    useEffect(() => {
        if (!query.trim() || library) return;
        setLibrary('loading');
        fetch(`${API_BASE}/api/shelf`).then(r => r.json())
            .then(d => setLibrary(d.success ? d.shelves.flatMap(s => s.games.map(g => ({ ...g, system: s.system, full_name: s.full_name }))) : []))
            .catch(() => setLibrary([]));
    }, [query]);
    useEffect(() => { setGameLimit(25); }, [query]);

    const q = plainText(query.trim());
    const toggleIn = (setter) => (value) => setter(list => list.includes(value) ? list.filter(v => v !== value) : [...list, value]);
    const sortedSystems = React.useMemo(() => systems
        .filter(s => showEmpty || s.rom_count > 0)
        .filter(s => !needsWork || s.missing_metadata_count > 0)
        .filter(s => !makers.length || makers.includes(makerOf(s.name)))
        .filter(s => !types.length || types.includes(typeOf(s.name)))
        .filter(s => !q || plainText(s.full_name || s.name).includes(q) || plainText(s.name).includes(q))
        .sort(SYSTEM_SORTS[sortMode] || SYSTEM_SORTS.name),
    [systems, sortMode, q, makers, types, needsWork, showEmpty]);
    const gameHits = React.useMemo(() => {
        if (!q || !Array.isArray(library)) return [];
        return library.filter(g => (!makers.length || makers.includes(makerOf(g.system))) && (!types.length || types.includes(typeOf(g.system)))
            && [g.name, g.developer, g.genre].some(v => plainText(v).includes(q)))
            // Names starting with the search first, then names containing it, then developer/genre matches
            .map(g => { const n = plainText(splitGameName(g.name).title); return [n.startsWith(q) ? 0 : n.includes(q) ? 1 : 2, g]; })
            .sort((a, b) => a[0] - b[0] || (a[1].name || '').localeCompare(b[1].name || ''))
            .map(([, g]) => g);
    }, [library, q, makers, types]);

    const filterCount = makers.length + types.length + (needsWork ? 1 : 0) + (showEmpty ? 1 : 0);
    const makerCounts = countBy(systems.filter(s => showEmpty || s.rom_count > 0), s => [makerOf(s.name)]);
    const typeCounts = countBy(systems.filter(s => showEmpty || s.rom_count > 0), s => [typeOf(s.name)]);
    let lastGroup = null;

    // Helper to get system image, fallback to auto-allgames.jpg if missing
    // Folders whose artwork file has a different name
    const getSystemImg = RM.systems.imageOf;

    return (
        <div className="sidebar">
            <div className="sidebar-header">
                <div className="sidebar-header-title">
                    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8,marginBottom:0}}>
                        <h2 style={{marginBottom:0}}>Systems</h2>
                        <select className="sidebar-sort" value={sortMode} onChange={e => setSortMode(e.target.value)} aria-label="Sort systems">
                            <option value="name">Sort: Name</option>
                            <option value="roms">Sort: Most games</option>
                            <option value="missing">Sort: Most missing metadata</option>
                            <option value="maker">Sort: Maker</option>
                            <option value="generation">Sort: Generation</option>
                        </select>
                    </div>
                </div>
                <div style={{display:'flex',gap:8,marginBottom:8}}>
                    <input type="search" className="filter-input" style={{flex:1,minWidth:0}} placeholder="Search systems and games"
                        value={query} onChange={e => setQuery(e.target.value)} aria-label="Search systems and games" />
                    <button className={`btn btn-secondary btn-small filters-button${filtersOpen ? ' open' : ''}`} aria-expanded={filtersOpen} onClick={() => setFiltersOpen(o => !o)}>
                        Filters{filterCount > 0 && <span className="filters-count">{filterCount}</span>}
                    </button>
                </div>
                {filtersOpen && (
                    <div className="filter-panel" style={{maxHeight:'none'}}>
                        <div className="facet">
                            <div className="facet-title">Maker</div>
                            <div className="facet-chips">
                                {makerCounts.map(([m, n]) => (
                                    <button key={m} className="fchip" aria-pressed={makers.includes(m)} onClick={() => toggleIn(setMakers)(m)}>{m}<span className="n">{n}</span></button>
                                ))}
                            </div>
                        </div>
                        <div className="facet">
                            <div className="facet-title">Type</div>
                            <div className="facet-chips">
                                {typeCounts.map(([t, n]) => (
                                    <button key={t} className="fchip" aria-pressed={types.includes(t)} onClick={() => toggleIn(setTypes)(t)}>{t}s<span className="n">{n}</span></button>
                                ))}
                            </div>
                        </div>
                        <div className="facet-chips">
                            <button className="fchip" aria-pressed={needsWork} onClick={() => setNeedsWork(v => !v)}>Missing metadata</button>
                            <button className="fchip" aria-pressed={showEmpty} onClick={() => setShowEmpty(v => !v)}>Show empty systems</button>
                            {filterCount > 0 && <button className="link-button" onClick={() => { setMakers([]); setTypes([]); setNeedsWork(false); setShowEmpty(false); }}>Clear</button>}
                        </div>
                    </div>
                )}
            </div>
            {q && sortedSystems.length > 0 && <div className="sidebar-group">Systems ({sortedSystems.length})</div>}
            {sortedSystems.map(system => {
                const group = sortMode === 'maker' ? makerOf(system.name) : sortMode === 'generation' ? generationGroup(system.name).label : null;
                const heading = group && group !== lastGroup ? (lastGroup = group) : null;
                return (
                <React.Fragment key={system.name}>
                {heading && <div className="sidebar-group">{heading}</div>}
                <div
                    className={`system-item${system.rom_count === 0 ? ' disabled' : ''}${selectedSystem?.name === system.name ? ' active' : ''}`}
                    onClick={() => onSystemSelect(system)}
                    style={{display:'flex',alignItems:'stretch',gap:0,padding:0,height:'72px',minHeight:'48px'}}
                >
                    <div style={{width:'72px',height:'100%',flexShrink:0,display:'flex',alignItems:'stretch',justifyContent:'flex-start',background:'var(--bg-modal)',borderRadius:'4px 0 0 4px',overflow:'hidden',borderRight:'1px solid var(--border-color)'}}>
                        <img
                            src={getSystemImg(system.name)}
                            alt={system.name}
                            style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}}
                            onError={e => {
                                if (!e.target.dataset.fallback) {
                                    e.target.src = 'imgs/auto-allgames.jpg';
                                    e.target.dataset.fallback = '1';
                                } else {
                                    e.target.style.display = 'none';
                                }
                            }}
                        />
                    </div>
                    <div style={{flex:1,minWidth:0,display:'flex',flexDirection:'column',justifyContent:'center',padding:'12px'}}>
                        <div className="system-name">{system.full_name || system.name}</div>
                        <div className="system-stats">
                            <span>ROMs: {system.rom_count}</span>
                            {system.missing_metadata_count > 0 && (
                                <span style={{color: 'var(--accent-pink)'}}>Missing: {system.missing_metadata_count}</span>
                            )}
                        </div>
                    </div>
                </div>
                </React.Fragment>
                );
            })}
            {!q && sortedSystems.length === 0 && systems.length > 0 && <div style={{color: 'var(--text-secondary)', fontSize: '13px', padding: '4px 0 8px'}}>No systems match.</div>}
            {systems.length === 0 && <div style={{color: 'var(--text-secondary)', fontSize: '14px'}}>No systems found</div>}
            {q && (
                <>
                    <div className="sidebar-group">Games in every system {Array.isArray(library) ? `(${gameHits.length})` : ''}</div>
                    {library === 'loading' && <div style={{color:'var(--text-secondary)',fontSize:13}}>Searching...</div>}
                    {Array.isArray(library) && gameHits.length === 0 && <div style={{color:'var(--text-secondary)',fontSize:13}}>No games match.</div>}
                    {gameHits.slice(0, gameLimit).map(g => (
                        <button key={`${g.system}|${g.path}`} className="search-hit" onClick={() => onOpenGame(g.system, g.path)}>
                            <span className="search-hit-art">
                                {g.box2d ? <img src={`${API_BASE}/api/thumb/160/${g.box2d.split('/').map(encodeURIComponent).join('/')}`} alt="" loading="lazy" /> : '🎮'}
                            </span>
                            <span style={{minWidth:0,flex:1}}>
                                <span className="search-hit-name">{splitGameName(g.name).title}</span>
                                <span className="search-hit-meta">{[g.full_name, g.year].filter(Boolean).join(' · ')}</span>
                            </span>
                        </button>
                    ))}
                    {gameHits.length > gameLimit && (
                        <button className="link-button" style={{margin:'6px 0'}} onClick={() => setGameLimit(l => l + 50)}>Show {Math.min(50, gameHits.length - gameLimit)} more</button>
                    )}
                </>
            )}
        </div>
    );
}
