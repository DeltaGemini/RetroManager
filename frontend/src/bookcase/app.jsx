// The page itself: loads the library, filters and draws the shelves.
// Part of the Bookcase page (shelf.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function ShelfApp() {
    const [shelves, setShelves] = useState(null);
    const [error, setError] = useState(null);
    const [search, setSearch] = useState('');
    const [sortKey, setSortKey] = useState('name');
    const [showAll, setShowAll] = useState(false);
    const [options, setOptions] = useBookcaseOptions();
    useEffect(() => {
        const root = document.documentElement;
        if (FINISHES.some(([key]) => key === options.finish) && options.finish !== 'mahogany') root.dataset.bookcase = options.finish;
        else delete root.dataset.bookcase;
    }, [options.finish]);
    // '' = every system; remembered in this browser
    const [systemFilter, setSystemFilter] = useState(() => {
        try { return localStorage.getItem('retromanager.shelf.system') || ''; } catch (e) { return ''; }
    });
    // What each shelf holds (a SHELF_MODES key); remembered in this browser
    const [shelfMode, setShelfMode] = useState(() => {
        try {
            const saved = localStorage.getItem('retromanager.shelf.shelves');
            if (SHELF_MODES.some(m => m.key === saved)) return saved;
            // The earlier "Shelves: Generation" order
            return localStorage.getItem('retromanager.shelf.order') === 'generation' ? 'console-generation' : 'console';
        } catch (e) { return 'console'; }
    });
    const pickShelfMode = (value) => {
        setShelfMode(value);
        try { localStorage.setItem('retromanager.shelf.shelves', value); } catch (e) {}
    };
    const pickSystem = (value) => {
        setSystemFilter(value);
        try { localStorage.setItem('retromanager.shelf.system', value); } catch (e) {}
    };
    const [hovered, setHovered] = useState(null);   // {key, shelf, el, game}: the box facing you
    // Play statuses and collections (set on a game's page in the Library)
    const [libraryState, setLibraryState] = useState({ status: {}, collections: [] });
    useEffect(() => {
        fetch(`${API_BASE}/api/library-state`).then(r => r.json()).then(d => { if (d.success) setLibraryState(d); }).catch(() => {});
    }, []);
    const [outKey, setOutKey] = useState(null);     // "system|path" of the box off the shelf
    const [returningKey, setReturningKey] = useState(null);
    const [openEntry, setOpenEntry] = useState(null);
    const [pulling, setPulling] = useState(false);
    const spineRefs = useRef({}); // "shelf id|index" -> element

    useEffect(() => {
        fetch(`${API_BASE}/api/shelf`).then(r => r.json())
            .then(d => d.success
                // By system name, so Nintendo 3DS sits with the other Nintendo systems
                ? setShelves(d.shelves.slice().sort((a, b) => a.full_name.localeCompare(b.full_name, undefined, { sensitivity: 'base', numeric: true })))
                : setError(d.error || 'Could not load the shelf'))
            .catch(err => setError(err.message));
    }, []);

    // What "Preload pictures" fetches: each shown game's hover cover and its
    // popup picture (the whole library, whatever the search or system filter)
    const [detailsPicture] = useGdPicture();
    const preloadUrls = useMemo(() => {
        if (!shelves) return [];
        const urls = new Set();
        shelves.forEach(shelf => shelf.games.forEach(g => {
            if (!showAll && !(g.has_metadata && g.rom_exists)) return;
            const cover = pic(g, 'box2d', 480);
            if (cover) urls.add(cover);
            const field = gdPictureField(g, detailsPicture);
            if (field) urls.add(pic(g, field, 480));
        }));
        return [...urls];
    }, [shelves, showAll, detailsPicture]);
    const preload = usePreloader(options.preload, preloadUrls);

    // Every game with the system it's from, and the franchises found among them
    const library = useMemo(() => {
        const games = [];
        (shelves || []).forEach(shelf => shelf.games.forEach(g => games.push({
            ...g, system: shelf.system, fullName: shelf.full_name, key: `${shelf.system}|${g.path}`, title: cleanTitle(g.name),
            stateKey: `${shelf.system}/${g.path.replace(/^(\.\/)+/, '')}`,
            playStatus: libraryState.status[`${shelf.system}/${g.path.replace(/^(\.\/)+/, '')}`] || null,
        })));
        const series = Object.fromEntries(RM.series.assign(games).map(found => [found.key, found]));
        return { games, series };
    }, [shelves, libraryState]);

    const visibleShelves = useMemo(() => {
        if (!shelves) return [];
        const query = search.trim().toLowerCase();
        // A remembered system that's gone shows everything
        const only = shelves.some(s => s.system === systemFilter) ? systemFilter : '';
        const shown = library.games.filter(g => (!only || g.system === only) && (showAll || (g.has_metadata && g.rom_exists)));
        // Shelves that mix systems keep each system's boxes together, since they
        // differ in size; a franchise's shelf is in one run, like a series on a real shelf
        const bySystem = shelfMode === 'generation' || shelfMode === 'maker';
        return groupIntoShelves(shown, shelfMode, library.series, libraryState.collections).map(shelf => {
            const games = shelf.games.sort((a, b) => (bySystem && byText(a.fullName, b.fullName)) || SORTS[sortKey](a, b));
            const matches = query ? new Set(games.filter(g =>
                [g.name, g.genre, g.developer, g.publisher].some(v => (v || '').toLowerCase().includes(query))).map(g => g.key)) : null;
            const boxes = games.map(g => boxFor(g.system));
            return { ...shelf, games, matches, boxes,
                tallest: Math.max(...boxes.map(box => box.h)),
                slots: boxes.map(box => ({ width: Math.max(MIN_SPINE_PX, Math.round(box.d * PX_PER_MM)), height: Math.round(box.h * PX_PER_MM) })) };
        }).filter(s => s.games.length && (!s.matches || s.matches.size));
    }, [shelves, library, libraryState, search, sortKey, showAll, systemFilter, shelfMode]);

    const pullOut = (game, el) => {
        if (pulling || openEntry) return;
        setPulling(true);
        setHovered(null);
        playPullOut(el, () => {
            setPulling(false);
            setOpenEntry({ game, system: game.system, fullName: game.fullName, key: game.key });
        });
        setOutKey(game.key);
    };

    // Closing the card slides the box back into its gap
    const putBack = useCallback(() => {
        setOpenEntry(prev => {
            if (prev) {
                setOutKey(null);
                if (!reducedMotion()) {
                    setReturningKey(prev.key);
                    // Normally cleared when the animation ends; this covers it not running
                    setTimeout(() => setReturningKey(k => (k === prev.key ? null : k)), 500);
                }
                // Keyboard users land back on the box they took out
                setTimeout(() => {
                    const el = document.querySelector(`[data-key="${CSS.escape(prev.key)}"]`);
                    if (el) el.focus({ preventScroll: true });
                }, 0);
            }
            return null;
        });
    }, []);

    const focusSpine = (shelfIndex, gameIndex) => {
        const shelf = visibleShelves[shelfIndex];
        if (!shelf) return;
        const i = Math.min(Math.max(gameIndex, 0), shelf.games.length - 1);
        const el = spineRefs.current[`${shelf.id}|${i}`];
        if (el) { el.focus(); el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
    };

    const keyNav = (shelfIndex, gameIndex) => (e) => {
        if (e.key === 'ArrowRight') { e.preventDefault(); focusSpine(shelfIndex, gameIndex + 1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); focusSpine(shelfIndex, gameIndex - 1); }
        else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const target = shelfIndex + (e.key === 'ArrowDown' ? 1 : -1);
            const shelf = visibleShelves[target];
            if (!shelf) return;
            // Land on the box nearest the same horizontal position
            const x = e.currentTarget.getBoundingClientRect().left;
            let best = 0, bestDist = Infinity;
            shelf.games.forEach((_, i) => {
                const el = spineRefs.current[`${shelf.id}|${i}`];
                if (!el) return;
                const dist = Math.abs(el.getBoundingClientRect().left - x);
                if (dist < bestDist) { bestDist = dist; best = i; }
            });
            focusSpine(target, best);
        }
    };

    const totalGames = visibleShelves.reduce((n, s) => n + (s.matches ? s.matches.size : s.games.length), 0);

    return (
        <>
            <RM.Header active="bookcase" />
            <div className="top-bar">
                <input type="search" placeholder="Search titles, genres, developers" value={search} onChange={e => setSearch(e.target.value)} />
                <select value={shelves && shelves.some(s => s.system === systemFilter) ? systemFilter : ''} onChange={e => pickSystem(e.target.value)} aria-label="System">
                    <option value="">All systems</option>
                    {(shelves || []).filter(s => s.games.some(g => showAll || (g.has_metadata && g.rom_exists))).map(s => (
                        <option key={s.system} value={s.system}>{s.full_name}</option>
                    ))}
                </select>
                <select value={shelfMode} onChange={e => pickShelfMode(e.target.value)} aria-label="Shelves">
                    {SHELF_MODES.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
                <select value={sortKey} onChange={e => setSortKey(e.target.value)} aria-label="Sort">
                    <option value="name">Sort: Name</option>
                    <option value="year">Sort: Year</option>
                    <option value="file">Sort: File name</option>
                </select>
                <label><input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} /> Include games without a gamelist entry</label>
                <OptionsMenu options={options} setOptions={setOptions} progress={preload} />
                <span className="hint">{shelves ? `${totalGames} games` : ''} · click a box to take it out · ← → ↑ ↓ · Enter</span>
            </div>

            {error && <div className="empty">{error}</div>}
            {!error && !shelves && <div className="empty">Loading the shelves...</div>}
            {shelves && !visibleShelves.length && <div className="empty">{search ? 'Nothing matches that search.'
                : shelfMode === 'status' ? 'No game has a play status or a star yet. Set them on a game\'s page in the Library.'
                : shelfMode === 'collection' ? 'No collections yet. Make one on a game\'s page in the Library.' : 'No games to show.'}</div>}

            <div className="bookcase">
                {visibleShelves.map((shelf, shelfIndex) => {
                    const hoveredIndex = hovered && hovered.shelf === shelf.id ? shelf.games.findIndex(g => g.key === hovered.key) : -1;
                    const previous = shelfIndex > 0 ? visibleShelves[shelfIndex - 1].heading : null;
                    return (
                        <React.Fragment key={shelf.id}>
                        {shelf.heading && shelf.heading !== previous && <h2 className="shelf-group">{shelf.heading}</h2>}
                        <section className="shelf" aria-label={shelf.label}>
                            <ShelfScroller minHeight={Math.round(shelf.tallest * PX_PER_MM * 1.14) + 52}
                                slots={shelf.slots}
                                onPoint={i => {
                                    if (i < 0) { setHovered(h => (h && h.shelf === shelf.id ? null : h)); return; }
                                    const g = shelf.games[i];
                                    setHovered(h => (h && h.key === g.key && h.shelf === shelf.id ? h : { key: g.key, shelf: shelf.id, el: spineRefs.current[`${shelf.id}|${i}`], game: g }));
                                }}
                                onPick={i => pullOut(shelf.games[i], spineRefs.current[`${shelf.id}|${i}`])}>
                                {shelf.games.map((game, i) => (
                                            <Spine
                                                key={game.key}
                                                game={game}
                                                box={shelf.boxes[i]}
                                                dimmed={shelf.matches && !shelf.matches.has(game.key)}
                                                hovered={i === hoveredIndex}
                                                out={outKey === game.key}
                                                returning={returningKey === game.key}
                                                onHover={(g, el) => setHovered({ key: g.key, shelf: shelf.id, el, game: g })}
                                                onUnhover={() => setHovered(h => (h && h.key === game.key && h.shelf === shelf.id ? null : h))}
                                                onPull={(g, el) => pullOut(g, el)}
                                                onKeyNav={keyNav(shelfIndex, i)}
                                                onReturned={() => setReturningKey(k => (k === game.key ? null : k))}
                                                registerRef={el => {
                                                    spineRefs.current[`${shelf.id}|${i}`] = el;
                                                    if (el) el.dataset.key = game.key;
                                                }}
                                            />
                                ))}
                            </ShelfScroller>
                            <div className="plank">
                                {/* A console's nameplate opens that console in the Library */}
                                {React.createElement(shelf.system ? 'a' : 'div', {
                                    className: 'shelf-label',
                                    ...(shelf.system ? { href: `/?${new URLSearchParams({ system: shelf.system })}`, title: `Open ${shelf.label} in the Library` } : {}),
                                },
                                    shelf.system && <img src={systemImg(shelf.system)} alt="" onError={e => { e.target.style.display = 'none'; }} />,
                                    shelf.label,
                                    <span className="count">{shelf.matches ? `${shelf.matches.size} of ${shelf.games.length}` : shelf.games.length} games</span>)}
                            </div>
                        </section>
                        </React.Fragment>
                    );
                })}
            </div>

            {hovered && !openEntry && <HoverLabel key={hovered.key} el={hovered.el} game={hovered.game} />}
            <InfoCard entry={openEntry} onClose={putBack} />
        </>
    );
}

ReactDOM.createRoot(document.getElementById('root')).render(<ShelfApp />);
