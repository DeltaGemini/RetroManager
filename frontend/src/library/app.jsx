// The page itself: loads the library, holds what's selected and which tool is open.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function App() {
    const [systems, setSystems] = useState([]);
    const [selectedSystem, setSelectedSystem] = useState(null);
    const [games, setGames] = useState([]);
    const [selectedGame, setSelectedGame] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notification, setNotification] = useState(null);
    const [columnWidths, setColumnWidths] = React.useState({ sidebar: 375, gameList: 500, detailPanel: 0 });
    const [resizing, setResizing] = React.useState(null);
    const [mobileStep, setMobileStep] = React.useState(0); // 0: sidebar, 1: game list, 2: details
    const [isMobile, setIsMobile] = React.useState(window.innerWidth < 900);
    const [scanResult, setScanResult] = useState(null);
    // Which Tools panel is open: health | scrape | media | history | saves | backups
    const [tool, setTool] = useState(null);
    // A system a tool opens on, when another panel sent us there (Scan's duplicates, say)
    const [toolSystem, setToolSystem] = useState(null);
    // ...and anything else it's handed (the Media viewer's picked games for Fill the gaps, say)
    const [toolOptions, setToolOptions] = useState(null);
    useEffect(() => {
        // window.dispatchEvent(new CustomEvent('retromanager:open-tool', {detail: {tool, system, options}})) from any panel
        const open = (e) => { setScanResult(null); setToolSystem(e.detail?.system || null); setToolOptions(e.detail?.options || null); setTool(e.detail?.tool || null); };
        window.addEventListener('retromanager:open-tool', open);
        return () => window.removeEventListener('retromanager:open-tool', open);
    }, []);
    const [scrapeStatus, refreshScrapeStatus] = useScrapeQueue();
    const [scanning, setScanning] = useState(false);
    // A navigation waiting on the unsaved-changes prompt
    const [pendingAction, setPendingAction] = useState(null);
    const [savingPending, setSavingPending] = useState(false);
    // The details panel keeps {dirty, save} here so navigation can check it
    const detailStateRef = React.useRef({ dirty: false });
    const [stats, setStats] = useState(null);
    const [lastScans, setLastScans] = useState(() => {
        try { return JSON.parse(localStorage.getItem('retromanager.lastScans') || '{}'); } catch (e) { return {}; }
    });

    useEffect(() => {
        const handleResize = () => setIsMobile(window.innerWidth < 900);
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    useEffect(() => {
        loadSystems();
    }, []);

    // /?tool=health (from the Tools menu on another page) opens that panel
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        // (tools since folded into others open where they went)
        const wanted = ({ media: 'viewer', backups: 'storage' })[params.get('tool')] || params.get('tool');
        if (wanted && RM.TOOLS.some(t => t.key === wanted)) {
            setTool(wanted);
            params.delete('tool');
            const rest = params.toString();
            window.history.replaceState(window.history.state, '', window.location.pathname + (rest ? `?${rest}` : ''));
        }
    }, []);

    // Links like /?system=snes&game=./Chrono Trigger (USA).sfc (from the Bookcase or Timeline) open that game.
    // The address then follows what's open (below), so a reload comes back to it.
    const deepLinkDone = useRef(false);
    useEffect(() => {
        if (deepLinkDone.current || !systems.length) return;
        deepLinkDone.current = true;
        const params = new URLSearchParams(window.location.search);
        const target = systems.find(sys => sys.name === params.get('system'));
        if (!target) return;
        // &scrape=1 (Scrape on another page) opens the scraper for it too
        // (Scrape, pressed on another page: Fill the gaps for the game, as the game's own Scrape does here)
        if (params.get('game') && params.get('scrape')) {
            window.dispatchEvent(new CustomEvent('retromanager:open-tool', { detail: { tool: 'fill',
                options: { games: [{ system: target.name, path: params.get('game') }], replace: true, start: true, single: true } } }));
        }
        setSelectedSystem(target);
        loadGames(target.name, params.get('game') || null);
        if (isMobile) goStep(params.get('game') ? 2 : 1);
    }, [systems]);
    // The address names the system and game open (on a phone, the ones on screen:
    // the systems list, a system's games, or a game), kept in place rather than added
    // to the history, which the phone's steps use
    useEffect(() => {
        if (!deepLinkDone.current) return;
        const params = new URLSearchParams();
        if (selectedSystem && (!isMobile || mobileStep >= 1)) {
            params.set('system', selectedSystem.name);
            if (selectedGame && (!isMobile || mobileStep >= 2)) params.set('game', selectedGame.path);
        }
        const query = params.toString();
        const address = window.location.pathname + (query ? `?${query}` : '');
        if (address !== window.location.pathname + window.location.search) {
            try { window.history.replaceState(window.history.state, '', address); } catch (e) {}
        }
    }, [selectedSystem?.name, selectedGame?.path, mobileStep, isMobile, systems.length]);

    useEffect(() => {
        if (!resizing) return;

        // provide visual feedback and prevent text selection while resizing
        const prevCursor = document.body.style.cursor;
        const prevUserSelect = document.body.style.userSelect;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        const handleMouseMove = (e) => {
            if (resizing === 'sidebar') {
                const newWidth = Math.max(150, Math.min(500, e.clientX));
                setColumnWidths(prev => ({ ...prev, sidebar: newWidth }));
            } else if (resizing === 'detailPanel') {
                const newWidth = Math.max(250, Math.min(600, window.innerWidth - e.clientX));
                setColumnWidths(prev => ({ ...prev, detailPanel: newWidth }));
            }
        };

        const handleMouseUp = () => {
            setResizing(null);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);

        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = prevCursor;
            document.body.style.userSelect = prevUserSelect;
        };
    }, [resizing]);

    const loadStats = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/stats`);
            if (res.ok) setStats(await res.json());
        } catch (err) {
            console.error('Failed to load stats:', err);
        }
    };

    const loadSystems = async () => {
        loadStats();
        try {
            const res = await fetch(`${API_BASE}/api/systems`);
            const data = await res.json();
            if (data.success) {
                setSystems(data.systems);
                // Keep the selected system's counts current
                setSelectedSystem(prev => prev ? (data.systems.find(sys => sys.name === prev.name) || prev) : prev);
            }
        } catch (err) {
            console.error('Failed to load systems:', err);
            showNotification('Failed to load systems', 'error');
        } finally {
            setLoading(false);
        }
    };

    // keepPath: re-select this game after reloading (e.g. after a save)
    const loadGames = async (systemName, keepPath = null) => {
        if (!keepPath) setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/systems/${systemName}/games`);
            const data = await res.json();
            if (data.success) {
                setGames(data.games);
                setSelectedGame(keepPath ? (data.games.find(g => g.path === keepPath) || null) : null);
            }
        } catch (err) {
            console.error('Failed to load games:', err);
            showNotification('Failed to load games', 'error');
        } finally {
            setLoading(false);
        }
    };

    // Run an action that leaves the current game, asking first if it has unsaved edits
    const guardUnsaved = (action) => {
        if (detailStateRef.current.dirty) setPendingAction(() => action);
        else action();
    };
    const resolvePending = async (choice) => {
        const action = pendingAction;
        if (choice === 'cancel') { setPendingAction(null); return; }
        if (choice === 'save') {
            setSavingPending(true);
            const ok = await detailStateRef.current.save();
            setSavingPending(false);
            if (!ok) return; // keep the prompt open; the save error is already shown
        }
        detailStateRef.current = { dirty: false };
        setPendingAction(null);
        action();
    };

    // Ctrl/Cmd+S saves the open game from anywhere on the page
    useEffect(() => {
        const onKey = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                e.preventDefault();
                if (detailStateRef.current.dirty && detailStateRef.current.save) detailStateRef.current.save();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    // After a delete or add: refresh the list without reloading the page
    const reloadGamesAndSystems = () => {
        detailStateRef.current = { dirty: false };
        if (selectedSystem) loadGames(selectedSystem.name);
        loadSystems();
    };

    // After a Tools panel changed gamelists: refresh, keeping the open game
    const refreshLibrary = () => {
        if (selectedSystem) loadGames(selectedSystem.name, selectedGame?.path);
        loadSystems();
        loadStats();
    };

    useEffect(() => {
        // Browser refresh/close with unsaved edits
        const warn = (e) => {
            if (detailStateRef.current.dirty) { e.preventDefault(); e.returnValue = ''; }
        };
        window.addEventListener('beforeunload', warn);
        return () => window.removeEventListener('beforeunload', warn);
    }, []);

    const handleSystemSelect = (system) => guardUnsaved(() => {
        setSelectedSystem(system);
        loadGames(system.name);
        if (isMobile) goStep(1);
    });
    // A game found by the sidebar's search, in any system
    const openGame = (systemName, path) => guardUnsaved(() => {
        const target = systems.find(s => s.name === systemName);
        if (!target) return;
        setSelectedSystem(target);
        loadGames(target.name, path);
        if (isMobile) goStep(2);
    });
    const handleGameSelect = (game) => guardUnsaved(() => {
        setSelectedGame(game);
        if (isMobile) goStep(2);
    });
    // On phones each step (systems → games → details) is a browser history
    // entry, so the phone's own Back gesture steps back instead of leaving
    const mobileStepRef = useRef(0);
    mobileStepRef.current = mobileStep;
    const skipBackGuard = useRef(false);
    const goStep = (step) => {
        setMobileStep(step);
        for (let s = (window.history.state?.rmStep || 0) + 1; s <= step; s++) {
            window.history.pushState({ rmStep: s }, '');
        }
    };
    useEffect(() => {
        const onPop = (e) => {
            const target = e.state?.rmStep || 0;
            if (target >= mobileStepRef.current) { setMobileStep(target); return; }
            if (mobileStepRef.current === 2 && detailStateRef.current.dirty && !skipBackGuard.current) {
                // Stay put until the unsaved-changes prompt is answered
                window.history.pushState({ rmStep: 2 }, '');
                guardUnsaved(() => { skipBackGuard.current = true; window.history.back(); });
                return;
            }
            skipBackGuard.current = false;
            setMobileStep(target);
        };
        window.addEventListener('popstate', onPop);
        return () => window.removeEventListener('popstate', onPop);
    }, []);
    const handleBack = () => {
        if ((window.history.state?.rmStep || 0) === mobileStep && mobileStep > 0) {
            window.history.back();
        } else if (mobileStep === 2) guardUnsaved(() => setMobileStep(1));
        else if (mobileStep === 1) setMobileStep(0);
    };

    const runScan = async (systemName) => {
        const res = await fetch(`${API_BASE}/api/systems/${encodeURIComponent(systemName)}/scan`, { method: 'POST' });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Scan failed');
        return data.result;
    };

    const handleScanSystem = async () => {
        if (!selectedSystem) return;
        setScanning(true);
        try {
            setScanResult(await runScan(selectedSystem.name));
            setLastScans(prev => {
                const next = { ...prev, [selectedSystem.name]: Date.now() };
                try { localStorage.setItem('retromanager.lastScans', JSON.stringify(next)); } catch (e) {}
                return next;
            });
        } catch (err) {
            console.error('Scan failed:', err);
            showNotification(`Scan failed: ${err.message}`, 'error');
        } finally {
            setScanning(false);
        }
    };

    // From Library health: go to a system and open its Scan panel
    const reviewSystem = (systemName) => {
        const target = systems.find(sys => sys.name === systemName);
        if (!target) return;
        guardUnsaved(async () => {
            setTool(null);
            setSelectedSystem(target);
            loadGames(target.name);
            if (isMobile) goStep(1);
            setScanning(true);
            try {
                setScanResult(await runScan(target.name));
            } catch (err) {
                showNotification(`Scan failed: ${err.message}`, 'error');
            } finally {
                setScanning(false);
            }
        });
    };

    // After a scan action: refresh the results, the game list and the sidebar counts
    const handleScanChanged = async () => {
        if (!selectedSystem) return;
        try {
            setScanResult(await runScan(selectedSystem.name));
        } catch (err) {
            showNotification(`Rescan failed: ${err.message}`, 'error');
        }
        loadGames(selectedSystem.name, selectedGame?.path);
        loadSystems();
    };

    // The details panel saved the game (or added media to it): show it everywhere
    const handleGameSaved = async (path) => {
        if (!selectedSystem) return;
        detailStateRef.current = { dirty: false };
        loadSystems();
        // Wait, so a navigation queued behind a save runs after the reload
        await loadGames(selectedSystem.name, path);
    };

    const showNotification = (message, type = 'info') => {
        setNotification({ message, type });
        setTimeout(() => setNotification(null), 3000);
    };

    const onResizeStart = (column, e) => {
        if (e && e.preventDefault) e.preventDefault();
        setResizing(column);
    };

    if (loading && systems.length === 0) return (
        <div className="loading"><div className="spinner"></div></div>
    );

    const lastScan = selectedSystem ? lastScans[selectedSystem.name] : null;
    return (
        <div className="app-shell">
        <RM.Header active="library" onTool={setTool} />
        <LibraryBar stats={stats} system={selectedSystem} game={selectedGame} lastScan={lastScan} isMobile={isMobile}
            onBack={isMobile && mobileStep > 0 ? handleBack : null}
            context={isMobile && mobileStep > 0 ? (selectedSystem?.full_name || selectedSystem?.name) : null} />
        <div className="app-container" style={{
            gridTemplateColumns: isMobile ? '1fr' : `${columnWidths.sidebar}px ${columnWidths.gameList}px 1fr`
        }}>
            {isMobile ? (
                mobileStep === 0 ? <Sidebar systems={systems} selectedSystem={selectedSystem} onSystemSelect={handleSystemSelect} onOpenGame={openGame} onResizeStart={onResizeStart} /> : null
            ) : (
                <Sidebar systems={systems} selectedSystem={selectedSystem} onSystemSelect={handleSystemSelect} onOpenGame={openGame} onResizeStart={onResizeStart} />
            )}
            {isMobile ? (
                mobileStep === 1 ? (
                    <div style={{ position: 'relative', height: '100%', minHeight: 0 }}>
                        <GameList games={games} selectedGame={selectedGame} onGameSelect={handleGameSelect} onScan={handleScanSystem} onReload={reloadGamesAndSystems} scanning={scanning} loading={loading} system={selectedSystem} showNotification={showNotification} />
                    </div>
                ) : null
            ) : (
                <GameList games={games} selectedGame={selectedGame} onGameSelect={handleGameSelect} onScan={handleScanSystem} onReload={reloadGamesAndSystems} scanning={scanning} loading={loading} system={selectedSystem} showNotification={showNotification} />
            )}
            {isMobile ? (
                mobileStep === 2 ? (
                    <div style={{ position: 'relative', height: '100%', minHeight: 0 }}>
                        <DetailPanel game={selectedGame} system={selectedSystem} onSaved={handleGameSaved} onDeleted={reloadGamesAndSystems} showNotification={showNotification} detailStateRef={detailStateRef} />
                    </div>
                ) : null
            ) : (
                <DetailPanel game={selectedGame} system={selectedSystem} onSaved={handleGameSaved} onDeleted={reloadGamesAndSystems} showNotification={showNotification} detailStateRef={detailStateRef} />
            )}
            {scanResult && selectedSystem && (
                <ScanPanel result={scanResult} system={selectedSystem} onClose={() => setScanResult(null)} onChanged={handleScanChanged} showNotification={showNotification} />
            )}
            {tool === 'health' && (
                <HealthPanel
                    onClose={() => setTool(null)}
                    onReview={reviewSystem}
                    onChanged={() => { if (selectedSystem) loadGames(selectedSystem.name, selectedGame?.path); loadSystems(); }}
                    showNotification={showNotification}
                />
            )}
            {tool === 'scrape' && (
                <LibraryScrapePanel status={scrapeStatus} refresh={refreshScrapeStatus} onClose={() => setTool(null)} onChanged={refreshLibrary} />
            )}
            {tool === 'viewer' && <MediaViewerPanel options={toolOptions} onClose={() => { setTool(null); setToolOptions(null); refreshLibrary(); }} />}
            {tool === 'storage' && <StoragePanel initialSystem={toolSystem} onClose={() => { setTool(null); setToolSystem(null); refreshLibrary(); }} showNotification={showNotification} />}
            {tool === 'history' && <PlayHistoryPanel onClose={() => setTool(null)} />}
            {tool === 'achievements' && <AchievementOverviewPanel onClose={() => setTool(null)} />}
            {tool === 'profiles' && <ProfilesPanel onClose={() => setTool(null)} showNotification={showNotification} />}
            {tool === 'series' && <SeriesPanel onClose={() => setTool(null)} showNotification={showNotification} />}
            {tool === 'collections' && <CollectionsPanel onClose={() => setTool(null)} />}
            {tool === 'roms' && <RomCheckPanel onClose={() => setTool(null)} />}
            {tool === 'fill' && <FillGapsPanel initialSystem={toolSystem || selectedSystem?.name} systems={systems} options={toolOptions} showNotification={showNotification}
                // (sent from the Media viewer: back to it)
                onClose={() => { const back = toolOptions && toolOptions.from === 'viewer'; setToolSystem(null); setToolOptions(back ? toolOptions.viewer || null : null); setTool(back ? 'viewer' : null); }} onChanged={() => { loadSystems(); if (selectedSystem) loadGames(selectedSystem.name, selectedGame?.path); }} />}
            {tool === 'duplicates' && <DuplicatesPanel initialSystem={toolSystem} onClose={() => { setTool(null); setToolSystem(null); }} showNotification={showNotification}
                onChanged={() => { loadSystems(); if (selectedSystem) loadGames(selectedSystem.name); }} />}
            {tool === 'settings' && <SettingsPanel onClose={() => setTool(null)} showNotification={showNotification} />}
            {tool === 'saves' && <SavesToolPanel systems={systems} onClose={() => setTool(null)} showNotification={showNotification} />}
            {pendingAction && (
                <UnsavedChangesModal
                    gameName={selectedGame?.name}
                    saving={savingPending}
                    onSave={() => resolvePending('save')}
                    onDiscard={() => resolvePending('discard')}
                    onCancel={() => resolvePending('cancel')}
                />
            )}
            {notification && <Notification message={notification.message} type={notification.type} />}
        </div>
        </div>
    );
}

// "5 minutes ago" style text for a timestamp
const timeAgo = (ms) => {
    const minutes = Math.round((Date.now() - ms) / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    return new Date(ms).toLocaleDateString();
};

// The library's row under the shared header (RM.Header, common/header.js)
function LibraryBar({ stats, system, game, lastScan, isMobile, onBack, context }) {
    return (
        <div className="rm-subbar library-bar">
            {onBack && <button className="btn btn-small btn-secondary library-bar-back" onClick={onBack} aria-label="Back">‹ Back</button>}
            {isMobile && context && <span className="library-bar-context">{context}</span>}
            {stats && !stats.error && (
                <span className="library-bar-stats">
                    <b>{stats.systems_with_roms}</b> systems · <b>{stats.total_games}</b> games · <b>{stats.games_missing_metadata}</b> missing metadata
                </span>
            )}
            {system && (
                <span className="library-bar-scan">
                    {system.full_name || system.name}: last scan {lastScan ? timeAgo(lastScan) : 'never (on this browser)'}
                </span>
            )}
            {system && (
                <a className="library-bar-console" title="The same place on the Console page, for browsing and playing"
                    href={`/console?${new URLSearchParams({ system: system.name, ...(game ? { game: game.path } : {}) })}`}>🕹️ Open in Console</a>
            )}
            <span className="library-bar-hint">
                {!isMobile && <><kbd>↑</kbd> <kbd>↓</kbd> or <kbd>W</kbd> <kbd>S</kbd> games · <kbd>Enter</kbd> play · <kbd>E</kbd> edit · <kbd>/</kbd> search · <kbd>Ctrl</kbd>+<kbd>S</kbd> save</>}
            </span>
        </div>
    );
}
