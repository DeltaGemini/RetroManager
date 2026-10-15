// The game list the Library and the Console page share: each game as a row
// with its logo over its screenshot, with search, filters and sorting.
// Styled by common/app.css. Loaded after the shared Game Details panel and
// before each page's own scripts, which share one global scope with it.

// "Super Mario World (USA) (Rev 1)" -> title "Super Mario World", tags "(USA) (Rev 1)"
const splitGameName = (name) => {
    const full = (name || '').trim();
    const tags = full.match(/[\(\[][^\)\]]*[\)\]]/g) || [];
    const title = full.replace(/\s*[\(\[][^\)\]]*[\)\]]/g, '').replace(/\s+/g, ' ').trim();
    return { title: title || full, tags: title ? tags.join(' ') : '' };
};

const byTitle = (a, b) => splitGameName(a.name).title.localeCompare(splitGameName(b.name).title, undefined, { sensitivity: 'base', numeric: true });
const GAME_SORTS = {
    name: byTitle,
    // Undated / unrated games go last
    date: (a, b) => (a.releasedate || '99999999').localeCompare(b.releasedate || '99999999') || byTitle(a, b),
    newest: (a, b) => (b.releasedate || '').localeCompare(a.releasedate || '') || byTitle(a, b),
    rating: (a, b) => (b.rating ?? -1) - (a.rating ?? -1) || byTitle(a, b),
    developer: (a, b) => (a.developer || '￿').localeCompare(b.developer || '￿') || byTitle(a, b),
    series: (a, b) => (a._series || '￿').localeCompare(b._series || '￿') || (a.releasedate || '9').localeCompare(b.releasedate || '9'),
    file: (a, b) => (a.path || '').localeCompare(b.path || '', undefined, { sensitivity: 'base', numeric: true }),
};
const SORT_LABELS = { name: 'Name', date: 'Oldest first', newest: 'Newest first', rating: 'Rating', developer: 'Developer', series: 'Series', file: 'File name' };

// ------------------------------------------------------------------
// Game filters: facets worked out from the games themselves
// ------------------------------------------------------------------
const plainText = (t) => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// "Star Wars: Rogue Leader" -> "Star Wars"; "Castlevania II: …" -> "Castlevania";
// "Pokémon Snap" joins Pokémon. A series needs two games. (Same rules as the Timeline.)
function assignSeries(games) {
    const labels = {};
    const prefix = (name) => {
        const i = name.indexOf(': ');
        return i < 1 ? null : name.slice(0, i).replace(/\s+(\d+|[IVX]+)$/, '').trim() || null;
    };
    const key = {};
    games.forEach(g => {
        const p = prefix(splitGameName(g.name).title);
        if (!p) return;
        const k = plainText(p);
        (labels[k] = labels[k] || {})[p] = (labels[k][p] || 0) + 1;
        key[g.path] = k;
    });
    const keys = Object.keys(labels).sort((a, b) => b.length - a.length);
    games.forEach(g => {
        if (key[g.path]) return;
        const t = plainText(splitGameName(g.name).title);
        const k = keys.find(k => t === k || t.startsWith(k + ' '));
        if (k) key[g.path] = k;
    });
    const counts = {};
    Object.values(key).forEach(k => { counts[k] = (counts[k] || 0) + 1; });
    const result = {};
    games.forEach(g => {
        const k = key[g.path];
        result[g.path] = k && counts[k] >= 2 ? Object.entries(labels[k]).sort((a, b) => b[1] - a[1])[0][0] : null;
    });
    return result;
}

// Main genre of each listed one: "Platform / Run & Jump, Action" -> Platform, Action.
// Older scrapes use hyphens: "Driving-Racing TPV" -> Driving
const genresOf = (g) => [...new Set((g.genre || '').split(',').map(s => s.split(' / ')[0].split(/-(?=[A-Z])/)[0].trim()).filter(Boolean))];
const yearOf = (g) => /^\d{4}/.test(g.releasedate || '') ? Number(g.releasedate.slice(0, 4)) : null;
const maxPlayers = (g) => { const n = String(g.players || '').match(/\d+/g); return n ? Math.max(...n.map(Number)) : null; };
const REGION_TAGS = [
    ['USA', /^(usa|us|u|ntsc-u)$/i], ['Europe', /^(europe|eu|e|pal|uk|australia)$/i],
    ['Japan', /^(japan|jp|j|ntsc-j)$/i], ['World', /^(world|w|ue|ju|uj)$/i],
];
// Regions from the file name's tags: "(USA, Europe)" -> USA, Europe
const regionsOf = (g) => {
    const file = (g.path || '').split('/').pop();
    const found = new Set();
    (file.match(/\(([^)]*)\)/g) || []).forEach(tag => tag.slice(1, -1).split(',').forEach(part => {
        const hit = REGION_TAGS.find(([, re]) => re.test(part.trim()));
        if (hit) found.add(hit[0]);
    }));
    return found.size ? [...found] : ['No region tag'];
};
const FILTER_MEDIA = [
    ['box2d', 'Box 2D'], ['box3d', 'Box 3D'], ['boxside', 'Spine'], ['support', 'Cart / disc'], ['screenshot', 'Screenshot'],
    ['screenshottitle', 'Title screen'], ['wheel', 'Wheel'], ['fanart', 'Fanart'], ['videos', 'Video'], ['manuals', 'Manual'],
];
const STATUS_FACETS = [
    ['missing', 'Missing metadata', g => !g.has_metadata],
    ['rom-missing', 'ROM missing', g => !g.rom_exists],
    ['no-image', 'No image in gamelist', g => g.has_metadata && !g.image],
    ['no-desc', 'No description', g => !g.desc],
    ['favorite', 'Favourites', g => !!g.favorite],
    ['playing', 'Playing', g => g.play_status === 'playing'],
    ['backlog', 'Backlog', g => g.play_status === 'backlog'],
    ['finished', 'Finished', g => g.play_status === 'finished'],
];
const PLAYER_FACETS = [['1', 'One player'], ['2', '2+'], ['3', '3+'], ['4', '4+']];
const RATING_FACETS = [['0', 'Any'], ['0.4', '2★+'], ['0.6', '3★+'], ['0.8', '4★+']];
const EMPTY_FILTERS = { status: [], collections: [], series: [], genre: [], decade: [], region: [], missing: [], players: '', rating: '0', developer: '', publisher: '' };
// Filters that only make sense within one system, cleared when you switch
const SYSTEM_SPECIFIC_FILTERS = ['series', 'genre', 'developer', 'publisher'];

function gameMatches(g, f) {
    const any = (list, test) => !list.length || list.some(test);
    return any(f.status, k => STATUS_FACETS.find(s => s[0] === k)[2](g))
        && any(f.collections, id => (g.collections || []).includes(id))
        && any(f.series, s => g._series === s)
        && any(f.genre, s => genresOf(g).includes(s))
        && any(f.decade, d => { const y = yearOf(g); return d === 'unknown' ? y === null : y !== null && Math.floor(y / 10) * 10 === Number(d); })
        && any(f.region, r => regionsOf(g).includes(r))
        && any(f.missing, m => !g[m])
        && (!f.players || (f.players === '1' ? maxPlayers(g) === 1 : (maxPlayers(g) || 0) >= Number(f.players)))
        && (f.rating === '0' || (g.rating ?? -1) >= Number(f.rating))
        && (!f.developer || (g.developer || '') === f.developer)
        && (!f.publisher || (g.publisher || '') === f.publisher);
}

const countBy = (games, valuesOf) => {
    const counts = {};
    games.forEach(g => valuesOf(g).forEach(v => { if (v !== null && v !== undefined && v !== '') counts[v] = (counts[v] || 0) + 1; }));
    return Object.entries(counts).sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
};

// The filter panel under the game list's search box
function GameFilterPanel({ games, filters, setFilters, collections }) {
    const [more, setMore] = React.useState({});
    const toggle = (facet, value) => setFilters(f => ({ ...f, [facet]: f[facet].includes(value) ? f[facet].filter(v => v !== value) : [...f[facet], value] }));
    const set = (facet, value) => setFilters(f => ({ ...f, [facet]: value }));
    const chips = (facet, entries, limit = 12) => {
        const shown = more[facet] ? entries : entries.slice(0, limit);
        const picked = entries.filter(([v]) => filters[facet].includes(String(v)) && !shown.some(([s]) => s === v));
        return (
            <div className="facet-chips">
                {[...shown, ...picked].map(([value, count, label]) => (
                    <button key={value} className="fchip" aria-pressed={filters[facet].includes(String(value))} onClick={() => toggle(facet, String(value))}>
                        {label || value}<span className="n">{count}</span>
                    </button>
                ))}
                {entries.length > limit && (
                    <button className="fchip more" onClick={() => setMore(m => ({ ...m, [facet]: !m[facet] }))}>
                        {more[facet] ? 'Fewer' : `+${entries.length - limit} more`}
                    </button>
                )}
            </div>
        );
    };
    const series = countBy(games, g => [g._series]);
    const genres = countBy(games, genresOf);
    const decades = countBy(games, g => { const y = yearOf(g); return [y === null ? 'unknown' : Math.floor(y / 10) * 10]; })
        .sort((a, b) => a[0] === 'unknown' ? 1 : b[0] === 'unknown' ? -1 : Number(a[0]) - Number(b[0]))
        .map(([d, n]) => [d, n, d === 'unknown' ? 'No date' : `${d}s`]);
    const regions = countBy(games, regionsOf);
    const developers = countBy(games, g => [g.developer]);
    const publishers = countBy(games, g => [g.publisher]);
    const facet = (title, body) => body && (
        <div className="facet"><div className="facet-title">{title}</div>{body}</div>
    );
    return (
        <div className="filter-panel">
            {facet('Show only', chips('status', STATUS_FACETS.map(([k, label, test]) => [k, games.filter(test).length, label]).filter(e => e[1]), 99))}
            {(collections || []).some(c => games.some(g => (g.collections || []).includes(c.id))) && facet('Collection',
                chips('collections', (collections || []).map(c => [c.id, games.filter(g => (g.collections || []).includes(c.id)).length, c.name]).filter(e => e[1]), 99))}
            {series.length > 0 && facet('Series', chips('series', series))}
            {genres.length > 0 && facet('Genre', chips('genre', genres))}
            {facet('Decade', chips('decade', decades, 99))}
            {facet('Region', chips('region', regions, 99))}
            {facet('Missing media', chips('missing', FILTER_MEDIA.map(([k, label]) => [k, games.filter(g => !g[k]).length, label]).filter(e => e[1]), 99))}
            <div className="facet-row">
                <div className="facet">
                    <div className="facet-title">Players</div>
                    <div className="facet-chips">
                        <button className="fchip" aria-pressed={!filters.players} onClick={() => set('players', '')}>Any</button>
                        {PLAYER_FACETS.map(([v, label]) => (
                            <button key={v} className="fchip" aria-pressed={filters.players === v} onClick={() => set('players', filters.players === v ? '' : v)}>{label}</button>
                        ))}
                    </div>
                </div>
                <div className="facet">
                    <div className="facet-title">Rating</div>
                    <div className="facet-chips">
                        {RATING_FACETS.map(([v, label]) => (
                            <button key={v} className="fchip" aria-pressed={filters.rating === v} onClick={() => set('rating', v)}>{label}</button>
                        ))}
                    </div>
                </div>
            </div>
            <div className="facet-row">
                {developers.length > 0 && (
                    <label className="facet">
                        <span className="facet-title">Developer</span>
                        <select value={filters.developer} onChange={e => set('developer', e.target.value)}>
                            <option value="">Any</option>
                            {developers.map(([d, n]) => <option key={d} value={d}>{d} ({n})</option>)}
                        </select>
                    </label>
                )}
                {publishers.length > 0 && (
                    <label className="facet">
                        <span className="facet-title">Publisher</span>
                        <select value={filters.publisher} onChange={e => set('publisher', e.target.value)}>
                            <option value="">Any</option>
                            {publishers.map(([d, n]) => <option key={d} value={d}>{d} ({n})</option>)}
                        </select>
                    </label>
                )}
            </div>
        </div>
    );
}

// Chips for the filters in use, each removable
function activeFilterChips(filters, setFilters, collections) {
    const out = [];
    const drop = (facet, value) => setFilters(f => ({ ...f, [facet]: Array.isArray(f[facet]) ? f[facet].filter(v => v !== value) : EMPTY_FILTERS[facet] }));
    filters.status.forEach(v => out.push([`status:${v}`, STATUS_FACETS.find(s => s[0] === v)[1], () => drop('status', v)]));
    filters.collections.forEach(v => out.push([`collection:${v}`, `📁 ${((collections || []).find(c => c.id === v) || {}).name || 'Collection'}`, () => drop('collections', v)]));
    filters.series.forEach(v => out.push([`series:${v}`, `Series: ${v}`, () => drop('series', v)]));
    filters.genre.forEach(v => out.push([`genre:${v}`, v, () => drop('genre', v)]));
    filters.decade.forEach(v => out.push([`decade:${v}`, v === 'unknown' ? 'No date' : `${v}s`, () => drop('decade', v)]));
    filters.region.forEach(v => out.push([`region:${v}`, v, () => drop('region', v)]));
    filters.missing.forEach(v => out.push([`missing:${v}`, `No ${FILTER_MEDIA.find(m => m[0] === v)[1].toLowerCase()}`, () => drop('missing', v)]));
    if (filters.players) out.push(['players', `${PLAYER_FACETS.find(p => p[0] === filters.players)[1]} players`.replace('One player players', 'One player'), () => drop('players')]);
    if (filters.rating !== '0') out.push(['rating', RATING_FACETS.find(r => r[0] === filters.rating)[1], () => drop('rating')]);
    if (filters.developer) out.push(['developer', `Dev: ${filters.developer}`, () => drop('developer')]);
    if (filters.publisher) out.push(['publisher', `Pub: ${filters.publisher}`, () => drop('publisher')]);
    return out;
}

const isTypingTarget = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable);

const GAME_STATUS_ICONS = { playing: '▶', backlog: '🕓', finished: '✔' };
// A game in a list drawn from several systems (Favourites, a collection) names its own: game._system
const gamePlayUrl = (system, game) => gdPlayUrl(game._system || system.name, game.path);
const gameListKey = (game) => (game ? `${game._system || ''}/${game.path}` : null);

// The list itself.
//   games, system, loading   what to show
//   selectedGame, onGameSelect(game, { auto })   the chosen game
//   actions     buttons for the right of the heading (the Library's Scan, Bulk, Add...)
//   autoSelect  choose the first game when none is chosen
//   onEdit(game)  what E (and Enter, for a game the browser can't play) does
//   children    the page's own popups
// Keys: up/down or W/S (Page Up/Down, Home, End) move, Enter plays, E edits,
// "/" jumps to the search box and Esc leaves it.
function SharedGameList({ games, selectedGame, onGameSelect, loading, system, actions, autoSelect, onEdit, children }) {
    const [gameFilter, setGameFilter] = React.useState('');
    // Redraw when a game's star, play status or collections change on its page
    const [, redraw] = React.useState(0);
    // The collections, for the Collection filter (fetched again whenever one changes)
    const [collections, setCollections] = React.useState([]);
    const loadCollections = React.useCallback(() => {
        fetch(`${GD_API}/api/library-state`).then(r => r.json()).then(d => { if (d.success) setCollections(d.collections); }).catch(() => {});
    }, []);
    React.useEffect(() => { loadCollections(); }, [loadCollections]);
    React.useEffect(() => {
        const onChange = () => { redraw(n => n + 1); loadCollections(); };
        window.addEventListener('retromanager:game-changed', onChange);
        return () => window.removeEventListener('retromanager:game-changed', onChange);
    }, []);
    // Which of this system's games have achievements, and how many are earned
    // (known once Tools > ROM check has looked at the files)
    const [achievementBadges, setAchievementBadges] = React.useState({});
    React.useEffect(() => {
        setAchievementBadges({});
        if (!system || !system.name) return;
        let cancelled = false;
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system.name)}/achievement-badges`).then(r => r.json())
            .then(d => { if (!cancelled && d.success) setAchievementBadges(d.badges || {}); }).catch(() => {});
        return () => { cancelled = true; };
    }, [system?.name]);
    // In the phone app: which games are on the phone, whether the server's there,
    // and a button that leaves only the phone's games in the list
    const phone = gdUsePhone();
    const [phoneOnly, setPhoneOnly] = React.useState(false);
    const hereOf = (game) => gdHere(game._system || (system && system.name), game.path);
    const selectedKey = gameListKey(selectedGame);
    const [filters, setFilters] = React.useState(EMPTY_FILTERS);
    const [filtersOpen, setFiltersOpen] = React.useState(false);
    // Sort is remembered in this browser
    const [sortKey, setSortKeyState] = React.useState(() => {
        try { return GAME_SORTS[localStorage.getItem('retromanager.gameSort')] ? localStorage.getItem('retromanager.gameSort') : 'name'; } catch (e) { return 'name'; }
    });
    const setSortKey = (k) => { setSortKeyState(k); try { localStorage.setItem('retromanager.gameSort', k); } catch (e) {} };
    const filterInputRef = React.useRef(null);
    const listRef = React.useRef(null);

    // Each game's series, worked out once per list
    const seriesGames = React.useMemo(() => {
        const series = assignSeries(games);
        return games.map(g => ({ ...g, _series: series[g.path] }));
    }, [games]);

    // Search text (accents ignored), filters and sort
    const filteredGames = React.useMemo(() => {
        const query = plainText(gameFilter.trim());
        const matchesText = (game) => !query ||
            ['name', 'path', 'desc', 'genre', 'developer', 'publisher', '_series'].some(f => plainText(game[f]).includes(query));
        const list = seriesGames.filter(g => gameMatches(g, filters) && matchesText(g) && (!phoneOnly || hereOf(g))).sort(GAME_SORTS[sortKey] || GAME_SORTS.name);
        // Back to the original objects, so selection still matches
        const byKey = Object.fromEntries(games.map(g => [gameListKey(g), g]));
        return list.map(g => Object.assign(byKey[gameListKey(g)], { _series: g._series }));
    }, [games, seriesGames, gameFilter, filters, sortKey, phoneOnly, phone.roms]);
    const activeChips = activeFilterChips(filters, setFilters, collections);
    // In the phone app: the listed games the phone could play but hasn't got
    const toFetch = gdPhone ? filteredGames.filter(g => g.phone_playable && g.rom_exists !== false && !hereOf(g)) : [];

    React.useEffect(() => {
        if (autoSelect && !loading && filteredGames.length && !filteredGames.some(g => gameListKey(g) === selectedKey)) onGameSelect(filteredGames[0], { auto: true });
    }, [autoSelect, loading, filteredGames, selectedKey]);

    React.useEffect(() => {
        // Something drawn over the list (a popup, a tool's panel) has the keyboard instead
        const covered = () => {
            const el = listRef.current;
            const box = el && el.getBoundingClientRect();
            if (!box || !box.width || !box.height) return true;
            const top = document.elementFromPoint(box.left + box.width / 2, box.top + Math.min(box.height / 2, 160));
            return !top || !el.contains(top);
        };
        const onKey = (e) => {
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            const focus = document.activeElement;
            const inSearch = focus === filterInputRef.current;
            const typing = isTypingTarget(focus);
            if (e.key === '/' && !typing) {
                if (covered()) return;
                e.preventDefault();
                filterInputRef.current && filterInputRef.current.focus();
                return;
            }
            if (e.key === 'Escape' && inSearch) { filterInputRef.current.blur(); return; }
            const key = e.key.toLowerCase();
            const current = filteredGames.findIndex(g => gameListKey(g) === selectedKey);
            const step = { arrowdown: 1, arrowup: -1, s: 1, w: -1, pagedown: 10, pageup: -10, home: -Infinity, end: Infinity }[key];
            if (step !== undefined) {
                // The arrows also work from the search box; the letters would type into it
                if (typing && !(inSearch && key.startsWith('arrow'))) return;
                if (!filteredGames.length || covered()) return;
                e.preventDefault();
                const next = current === -1 ? 0 : Math.min(Math.max(current + step, 0), filteredGames.length - 1);
                if (next !== current) onGameSelect(filteredGames[next], { keys: true });
                return;
            }
            const game = filteredGames[current];
            if (!game || typing || covered()) return;
            // Enter on a button or link is that button's own
            if (key === 'enter' && !['BUTTON', 'A', 'SUMMARY'].includes(focus && focus.tagName)) {
                e.preventDefault();
                if (gdCanPlay(game, system.name)) gdPlay(game._system || system.name, game.path);
                else if (gdPhone) return;
                else if (onEdit) onEdit(game);
            } else if (key === 'e' && gdPhone) {
                // In the phone app (a controller's X): the game's page
                e.preventDefault();
                onGameSelect(game);
            } else if (key === 'e' && onEdit) {
                e.preventDefault();
                onEdit(game);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [filteredGames, selectedGame, onGameSelect, onEdit, system]);

    // A new system starts with an empty search, and drops the filters that
    // only apply to one system (series, genre, developer, publisher)
    React.useEffect(() => {
        setGameFilter('');
        setFilters(f => ({ ...f, ...Object.fromEntries(SYSTEM_SPECIFIC_FILTERS.map(k => [k, EMPTY_FILTERS[k]])) }));
    }, [system?.name, system?.key]);

    // Keep the selected game visible when moving with the keyboard
    React.useEffect(() => {
        if (!selectedGame || !listRef.current) return;
        const el = listRef.current.querySelector(`[data-key="${CSS.escape(selectedKey)}"]`);
        if (el) el.scrollIntoView({ block: 'nearest' });
    }, [selectedGame]);

    // Card background: the in-game screenshot, or the title screen if there's none
    const backgroundOf = (game) => {
        const path = game.screenshot || game.screenshottitle;
        return typeof path === 'string' ? path : null;
    };
    const thumbnailOf = (game) => game[game.thumbnail_type || 'wheel'] || null;
    return (
        <div className="game-list" ref={listRef}>
            <div className="game-list-header">
                <div className="game-list-header-title">
                    <h2>Games ({games.length})</h2>
                    {actions && <div className="game-list-actions" style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap',justifyContent:'flex-end'}}>{actions}</div>}
                </div>
                {system && (
                    <>
                        <div className={`game-list-toolbar${gdPhone ? ' phone' : ''}`}>
                            <input
                                ref={filterInputRef}
                                type="search"
                                className="filter-input"
                                placeholder="Search games  ( / )"
                                value={gameFilter}
                                onChange={e => setGameFilter(e.target.value)}
                            />
                            <button className={`btn btn-secondary btn-small filters-button${filtersOpen ? ' open' : ''}`} aria-expanded={filtersOpen}
                                onClick={() => setFiltersOpen(o => !o)} title="Filter by status, series, genre, decade, region...">
                                Filters{activeChips.length > 0 && <span className="filters-count">{activeChips.length}</span>}
                            </button>
                            {gdPhone && (
                                <button className={`btn btn-secondary btn-small filters-button${phoneOnly ? ' open' : ''}`} aria-pressed={phoneOnly}
                                    onClick={() => setPhoneOnly(on => !on)} title="Only the games that are on this phone">📱 On this phone</button>
                            )}
                            {/* Every game in the list as it's filtered that the phone hasn't got (the app asks first) */}
                            {gdPhone && gdPhone.fetchAll && !phone.offline && toFetch.length > 0 && (
                                <button className="btn btn-secondary btn-small filters-button" title="Fetch the games shown here that aren't on this phone yet"
                                    onClick={() => gdPhone.fetchAll(JSON.stringify(toFetch.map(g => [g._system || system.name, g.path])))}>⬇ Fetch {toFetch.length === 1 ? 'the 1 not here' : `the ${toFetch.length} not here`}</button>
                            )}
                            <select value={sortKey} onChange={e => { setSortKey(e.target.value); e.target.blur(); }} title="Sort by">
                                {Object.entries(SORT_LABELS).map(([k, label]) => <option key={k} value={k}>Sort: {label}</option>)}
                            </select>
                        </div>
                        {filtersOpen && <GameFilterPanel games={seriesGames} filters={filters} setFilters={setFilters} collections={collections} />}
                        {activeChips.length > 0 && (
                            <div className="active-filters">
                                {activeChips.map(([key, label, remove]) => (
                                    <button key={key} className="fchip on" onClick={remove} aria-label={`Remove filter ${label}`}>{label} <span aria-hidden="true">×</span></button>
                                ))}
                                <button className="link-button" onClick={() => setFilters(EMPTY_FILTERS)}>Clear all</button>
                            </div>
                        )}
                        {filteredGames.length !== games.length && (
                            <div className="game-list-count">Showing {filteredGames.length} of {games.length}</div>
                        )}
                    </>
                )}
            </div>
            {children}
            {!system ? (
                <div className="empty-state">
                    <div className="empty-icon">🕹️</div>
                    <p>Pick a system on the left to see its games</p>
                </div>
            ) : loading ? (
                <div className="loading"><div className="spinner"></div></div>
            ) : filteredGames.length === 0 ? (
                <div style={{color: 'var(--text-secondary)', fontSize: '14px', textAlign: 'center', padding: '40px 0'}}>
                    {games.length ? 'No games match the search or filter.' : 'No games found for this system.'}
                </div>
            ) : (
                <>
                {filteredGames.map(game => {
                    const background = backgroundOf(game);
                    const thumbnail = thumbnailOf(game);
                    const name = splitGameName(game.name);
                    const badge = achievementBadges[String(game.path).replace(/^(\.\/)+/, '')];
                    return (
                    <div key={gameListKey(game)} data-key={gameListKey(game)} className={`game-item${gameListKey(game) === selectedKey ? ' active' : ''}${background ? ' has-bg' : ''}${gdPhone && phone.offline && !hereOf(game) ? ' not-here' : ''}`}>
                        {background && (
                            <img className="game-bg" src={gdMedia(background)} alt="" loading="lazy" decoding="async"
                                onError={e => { e.target.style.display = 'none'; }} />
                        )}
                        <div className="game-scrim" />
                        <div className="game-card-content" onClick={() => onGameSelect(game)} style={{flex:1, display:'flex', minWidth: 0}}>
                            <div className="game-thumbnail">
                                {thumbnail ? (
                                    <img src={gdMedia(thumbnail)} alt={game.name} loading="lazy" onError={e => { e.target.style.display = 'none'; }} />
                                ) : (
                                    <div className="game-thumbnail-placeholder">🎮</div>
                                )}
                            </div>
                            <div className="game-info">
                                <div className="game-name" title={game.name}>
                                    {name.title}
                                    {name.tags && <div className="game-tags">{name.tags}</div>}
                                </div>
                                {/* The year, and the system where the list mixes them, on a line of their own */}
                                {/* (a search across systems has the year as `year`) */}
                                {((game.releasedate && game.releasedate.length >= 4) || game.year || game._system_label) && (
                                    <div className="game-sub">{[game.releasedate && game.releasedate.length >= 4 ? game.releasedate.slice(0, 4) : game.year, game._system_label].filter(Boolean).join(' · ')}</div>
                                )}
                                <div className="game-status">
                                    {game.favorite && <span className="achievement-badge" title="Favourite" style={{color: 'var(--accent-orange)'}}>★</span>}
                                    {gdPhone && hereOf(game) && <span className="achievement-badge" title="On this phone">📱</span>}
                                    {game.play_status && <span className="achievement-badge" title={game.play_status}>{GAME_STATUS_ICONS[game.play_status]} {game.play_status}</span>}
                                    {badge && (
                                        <span className="achievement-badge" title={badge.earned ? `${badge.earned} of ${badge.total} achievements earned` : `${badge.total} achievements`}>
                                            🏆 {badge.earned ? `${Math.round(badge.completion)}%` : badge.total}
                                            {badge.earned > 0 && <span className="achievement-bar"><span style={{width: `${badge.completion}%`, background: badge.earned === badge.total ? 'var(--success)' : 'var(--accent-orange)'}} /></span>}
                                        </span>
                                    )}
                                    {!game.has_metadata && <span className="status-badge status-missing">Missing Metadata</span>}
                                    {!game.rom_exists && <span className="status-badge status-missing">ROM Missing</span>}
                                </div>
                            </div>
                        </div>
                        {gdCanPlay(game, system.name) && (
                            <a className={`game-play${gdPlayMark(game, system.name) !== '▶' ? ' fetch' : ''}`} href={gamePlayUrl(system, game)} onClick={gdPlayClick(game._system || system.name, game.path)}
                                title={!gdPhone ? `Play ${name.title} in the browser` : hereOf(game) ? `Play ${name.title} in RetroArch` : `Fetch ${name.title} to the phone and play it`} aria-label={`Play ${name.title}`}>{gdPlayMark(game, system.name)}</a>
                        )}
                    </div>
                    );
                })}
                </>
            )}
        </div>
    );
}
