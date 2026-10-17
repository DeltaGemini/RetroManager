// The Library's details pane: the Game Details panel every page shares
// (src/common/game-details.jsx), over the game's screenshot. Editing, media,
// scraping and deleting all happen in that panel.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function DetailPanel({ game, system, onSaved, onDeleted, showNotification, detailStateRef }) {
    if (!game) return (
        <div className="detail-panel">
            <div className="empty-state">
                <div className="empty-icon">📋</div>
                <p>Select a game to view and edit metadata</p>
            </div>
        </div>
    );
    const screenshotUrl = typeof game.screenshot === 'string' && game.screenshot ? localMediaUrl(game.screenshot) : null;
    return (
        <div className="detail-panel" style={{position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column', height: '100%'}}>
            {/* The screenshot behind everything, dimmed */}
            {screenshotUrl && (
                <React.Fragment>
                    <div style={{position: 'absolute', zIndex: 0, inset: 0, backgroundImage: `url('${screenshotUrl}')`, backgroundSize: 'cover',
                        backgroundPosition: 'center', backgroundRepeat: 'no-repeat', pointerEvents: 'none'}} />
                    <div style={{position: 'absolute', zIndex: 1, inset: 0, background: 'var(--panel-scrim)', pointerEvents: 'none'}} />
                </React.Fragment>
            )}
            {/* The scrolling area reaches the pane's right edge (past its 20px padding), so the scrollbar sits at the edge */}
            <div style={{position: 'relative', zIndex: 2, flex: 1, overflowY: 'auto', minHeight: 0, marginRight: -20, paddingRight: 20}}>
                <GameDetails system={system.name} systemLabel={system.full_name || system.name} game={game} notify={showNotification}
                    onSaved={onSaved} onDeleted={onDeleted} editState={detailStateRef} Scraper={ScraperSearchPopup}
                    onScrape={(g) => window.dispatchEvent(new CustomEvent('retromanager:open-tool', { detail: { tool: 'fill',
                        options: { games: [{ system: system.name, path: g.path }], replace: true, start: true, single: true } } }))} />
            </div>
        </div>
    );
}
