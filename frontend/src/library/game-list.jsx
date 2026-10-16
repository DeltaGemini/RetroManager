// The Library's game list: the shared list (src/common/game-list.jsx) with the
// Library's own buttons (Scan, Bulk, Add, gamelist backups) and their popups.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function GameList({ games, selectedGame, onGameSelect, onScan, onReload, scanning, loading, system, showNotification }) {
    const [settingsOpen, setSettingsOpen] = React.useState(false);
    const [bulkOpen, setBulkOpen] = React.useState(false);
    const [collectOpen, setCollectOpen] = React.useState(false);
    // The header's "Bulk" menu closes on a click outside it, or Escape
    const [bulkMenu, setBulkMenu] = React.useState(false);
    const bulkMenuRef = React.useRef(null);
    useEffect(() => {
        if (!bulkMenu) return;
        const close = (e) => { if (bulkMenuRef.current && !bulkMenuRef.current.contains(e.target)) setBulkMenu(false); };
        const esc = (e) => { if (e.key === 'Escape') setBulkMenu(false); };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', esc);
        return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
    }, [bulkMenu]);
    const handleBackupGamelist = async () => {
        if (!system) return;
        try {
            const res = await fetch(`${API_BASE}/api/backup_gamelist`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ system: system.name })
            });
            const data = await res.json();
            if (data.success) {
                if (typeof showNotification === 'function') showNotification(`Backup created: ${data.backup}`, 'success');
            } else {
                if (typeof showNotification === 'function') showNotification(data.error || 'Backup failed', 'error');
            }
        } catch (err) {
            if (typeof showNotification === 'function') showNotification('Backup failed', 'error');
        }
    };

    // E (or Enter on a game the browser can't play) opens the details pane's form
    const editGame = React.useCallback((game) => {
        if (game.path !== selectedGame?.path) onGameSelect(game);
        window.dispatchEvent(new Event('retromanager:edit-game'));
    }, [selectedGame, onGameSelect]);
    return (
        <SharedGameList games={games} selectedGame={selectedGame} onGameSelect={onGameSelect} loading={loading} system={system} onEdit={editGame}
            actions={<>
                        <button className="btn btn-secondary btn-small" onClick={onScan} disabled={scanning || !system}>{scanning ? 'Scanning...' : 'Scan'}</button>
                        <span ref={bulkMenuRef} style={{position: 'relative'}}>
                            <button className="btn btn-secondary btn-small" onClick={() => setBulkMenu(o => !o)} disabled={!system || !games.length}
                                aria-haspopup="menu" aria-expanded={bulkMenu} title="Work on many games at once">Bulk ▾</button>
                            {bulkMenu && (
                                <div role="menu" className="rm-menu" style={{width: 240}}>
                                    <button role="menuitem" onClick={() => { setBulkMenu(false); setBulkOpen(true); }}>
                                        <span style={{fontSize: 16}} aria-hidden="true">🔎</span>
                                        <span><span style={{display: 'block'}}>Scrape...</span><span className="rm-help">Match many games, review, then fill them in</span></span>
                                    </button>
                                    <button role="menuitem" onClick={() => { setBulkMenu(false); setCollectOpen(true); }}>
                                        <span style={{fontSize: 16}} aria-hidden="true">📁</span>
                                        <span><span style={{display: 'block'}}>Add to a collection...</span><span className="rm-help">Tick games and add them all at once</span></span>
                                    </button>
                                </div>
                            )}
                        </span>
                        <a className="btn btn-primary btn-small" href={`/import${system ? `?system=${encodeURIComponent(system.name)}` : ''}`} style={{textDecoration:'none'}} title="Upload games, or add them from the inbox folder">Add</a>
                        <button className="btn btn-icon-blue btn-small" title="Settings" style={{marginLeft:4}} onClick={()=>setSettingsOpen(true)} disabled={!system}>
                            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M10 13.5A3.5 3.5 0 1 0 10 6.5a3.5 3.5 0 0 0 0 7z" stroke="#fff" strokeWidth="1.5"/>
                                <path d="M17.5 10a7.5 7.5 0 0 0-.13-1.38l1.6-1.25a.5.5 0 0 0 .12-.65l-1.5-2.6a.5.5 0 0 0-.61-.23l-1.88.76a7.5 7.5 0 0 0-1.19-.7l-.28-2A.5.5 0 0 0 12.5 1h-3a.5.5 0 0 0-.5.42l-.28 2a7.5 7.5 0 0 0-1.19.7l-1.88-.76a.5.5 0 0 0-.61.23l-1.5 2.6a.5.5 0 0 0 .12.65l1.6 1.25A7.5 7.5 0 0 0 2.5 10c0 .47.04.93.13 1.38l-1.6 1.25a.5.5 0 0 0-.12.65l1.5 2.6a.5.5 0 0 0 .61.23l1.88-.76c.37.27.77.51 1.19.7l.28 2A.5.5 0 0 0 7.5 19h3a.5.5 0 0 0 .5-.42l.28-2c.42-.19.82-.43 1.19-.7l1.88.76a.5.5 0 0 0 .61-.23l1.5-2.6a.5.5 0 0 0-.12-.65l-1.6-1.25c.09-.45.13-.91.13-1.38z" stroke="#fff" strokeWidth="1.5"/>
                            </svg>
                        </button>
            </>}>
            {collectOpen && system && <BulkCollectPanel system={system} games={games} onClose={() => setCollectOpen(false)} />}
            {bulkOpen && system && (
                <BulkScrapePanel system={system} games={games} onClose={() => setBulkOpen(false)} onDone={() => onReload && onReload()} />
            )}
            <Modal open={settingsOpen} onClose={()=>setSettingsOpen(false)}>
                <h2 style={{marginBottom:16}}>Game List Settings</h2>
                <div style={{marginBottom:24}}>
                    <b>Backup and maintenance options for this system's gamelist.</b>
                </div>
                <button className="btn btn-primary" style={{marginBottom:12}} onClick={handleBackupGamelist}>Back up gamelist.xml</button>
                <div style={{color:'var(--text-secondary)',fontSize:13,marginBottom:16}}>Backup will create a dated copy of gamelist.xml in the system folder.</div>
                <div style={{marginBottom:8,fontWeight:'bold'}}>Earlier copies</div>
                <button className="btn btn-secondary" style={{marginBottom:8}}
                    onClick={() => { setSettingsOpen(false); window.dispatchEvent(new CustomEvent('retromanager:open-tool', { detail: { tool: 'storage', system: system.name } })); }}>
                    Compare and put one back
                </button>
                <div style={{color:'var(--text-secondary)',fontSize:12}}>Opens this system's gamelist backups in Tools › Storage, each beside the gamelist now.</div>
            </Modal>
        </SharedGameList>
    );
}
