// Changing a game from its Game Details panel (src/common/game-details.jsx):
// saving edited text, the Media and Gamelist sections, and deleting.
// Loaded on every page that shows the panel, sharing one global scope with it,
// so everything here is named gd.../GD... too.

// What the panel's edit mode can change (the gamelist's own fields)
const GD_EDIT_FIELDS = ['name', 'desc', 'developer', 'publisher', 'genre', 'releasedate', 'players', 'rating', 'image', 'thumbnail', 'video'];
// A game's media, in the order the Media section shows it
const GD_MEDIA = [
    ['box2d', '2D box'], ['box3d', '3D box'], ['boxside', 'Spine'], ['support', 'Cart / disc'], ['wheel', 'Logo'],
    ['screenshot', 'Screenshot'], ['screenshottitle', 'Title screen'], ['mix', 'Mix'], ['images', 'Image'],
    ['fanart', 'Fan art'], ['posters', 'Poster'], ['manuals', 'Manual'], ['videos', 'Video'],
];
const GD_MEDIA_ACCEPT = { manuals: 'application/pdf', videos: 'video/mp4,video/webm,video/avi,video/mkv' };
// Media folders that fill <image>, <thumbnail> and <video>, best first.
// Keep in step with LINK_PREFERENCES in backend/media_index.py.
const GD_LINKS = {
    image: ['images', 'mix', 'box2d', 'screenshot'],
    thumbnail: ['screenshottitle', 'screenshot', 'box2d', 'wheel'],
    video: ['videos'],
};

// Media folder of a path like "Nintendo 3DS/images/x.png"
const gdMediaFolder = (path) => {
    const parts = typeof path === 'string' ? path.split('/') : [];
    return parts.length >= 3 ? parts[parts.length - 2] : '';
};
// Fill empty <image>/<thumbnail>/<video> from the game's own media files
const gdAutoFill = (game) => {
    const filled = { ...game };
    let changed = 0;
    Object.entries(GD_LINKS).forEach(([field, folders]) => {
        if (filled[field]) return;
        const folder = folders.find(f => typeof filled[f] === 'string' && filled[f]);
        if (folder) { filled[field] = filled[folder]; changed++; }
    });
    return { game: filled, changed };
};
const gdSame = (a, b) => ((a === undefined || a === null) ? '' : String(a)) === ((b === undefined || b === null) ? '' : String(b));
const gdIsPlayer = () => document.documentElement.classList.contains('rm-player');
// Whether the open panel has unsaved edits, for the popup's close and leaving the page
const gdUnsaved = { dirty: false };
window.addEventListener('beforeunload', (e) => { if (gdUnsaved.dirty) { e.preventDefault(); e.returnValue = ''; } });

// Write a game's entry to its gamelist (a new entry when it has none).
// Returns {ok, game} or {ok: false, error}.
async function gdSaveGame(system, game) {
    const payload = gdAutoFill(game).game;
    const url = `${GD_API}/api/systems/${encodeURIComponent(system)}/games${game.has_metadata ? `/${gdEncode(game.path)}` : ''}`;
    try {
        const res = await fetch(url, { method: game.has_metadata ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const d = await res.json();
        return d.success ? { ok: true, game: payload } : { ok: false, error: d.error || 'The game couldn’t be saved' };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}

// Five stars to click for a 0-1 rating; clicking the current one clears it
function GDRatingEdit({ value, onChange }) {
    const rating = typeof value === 'number' && !isNaN(value) ? Math.min(Math.max(value, 0), 1) : null;
    const stars = rating === null ? 0 : rating * 5;
    return (
        <div className="gd-stars gd-stars-edit" role="radiogroup" aria-label="Rating">
            {[1, 2, 3, 4, 5].map(n => {
                const worth = Math.round(n * 0.2 * 100) / 100;
                return (
                    <button key={n} type="button" role="radio" aria-checked={Math.round(stars) === n} title={`${n} star${n > 1 ? 's' : ''}`}
                        onClick={() => onChange(rating !== null && Math.abs(rating - worth) < 0.001 ? undefined : worth)}>
                        ★<span style={{width: `${Math.min(Math.max(stars - (n - 1), 0), 1) * 100}%`}}>★</span>
                    </button>
                );
            })}
            <span className="gd-note">{rating === null ? 'Not rated' : `${Math.round(stars * 10) / 10} / 5`}</span>
        </div>
    );
}

// The facts beside the picture, as fields
function GDFactsEdit({ draft, set }) {
    const date = draft.releasedate && draft.releasedate.length >= 8 ? `${draft.releasedate.slice(0, 4)}-${draft.releasedate.slice(4, 6)}-${draft.releasedate.slice(6, 8)}` : '';
    const text = (field) => <input className="gd-input" type="text" value={draft[field] || ''} onChange={e => set(field, e.target.value)} />;
    return (
        <dl className="gd-facts gd-facts-edit">
            <dt>Developer</dt><dd>{text('developer')}</dd>
            <dt>Publisher</dt><dd>{text('publisher')}</dd>
            <dt>Released</dt>
            {/* YYYY-MM-DD -> EmulationStation's YYYYMMDDT000000 */}
            <dd><input className="gd-input" type="date" value={date} onChange={e => set('releasedate', e.target.value ? `${e.target.value.replace(/-/g, '')}T000000` : undefined)} /></dd>
            <dt>Genre</dt><dd>{text('genre')}</dd>
            <dt>Players</dt><dd>{text('players')}</dd>
        </dl>
    );
}

// Every picture, the manual and the video a game has. An admin can add or
// replace one: the file is saved straight away, named after the ROM like
// scraped media.
function GDMedia({ system, game, notify, onUploaded }) {
    const [busy, setBusy] = React.useState(null);
    const [stamps, setStamps] = React.useState({});   // folder -> when it was replaced here, so the new picture shows
    React.useEffect(() => { setStamps({}); setBusy(null); }, [system, game.path]);
    const have = GD_MEDIA.filter(([folder]) => game[folder]).length;

    const upload = async (folder, label, file) => {
        if (!file) return;
        setBusy(folder);
        try {
            const body = new FormData();
            body.append('rom_path', String(game.path).replace(/^(\.\/)+/, ''));
            body.append('folder', folder);
            body.append('file', file);
            const up = await (await fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/media/upload`, { method: 'POST', body })).json();
            if (!up.success) throw new Error(up.error || 'upload failed');
            // The gamelist's image, thumbnail or video that showed this folder's old
            // file now shows the new one, and an empty one is filled
            const changed = { [folder]: up.path };
            ['image', 'thumbnail', 'video'].forEach(field => {
                if (gdMediaFolder(game[field]) === folder && game[field] !== up.path) changed[field] = up.path;
            });
            const filled = gdAutoFill({ ...game, ...changed }).game;
            ['image', 'thumbnail', 'video'].forEach(field => { if (filled[field] !== game[field]) changed[field] = filled[field]; });
            if (game.has_metadata && ['image', 'thumbnail', 'video'].some(field => field in changed)) {
                const saved = await gdSaveGame(system, { ...game, ...changed });
                if (!saved.ok) notify(`${label} was added, but the gamelist wasn’t updated: ${saved.error}`, 'error');
            }
            if (folder === 'mix') changed.mix_generated = false;
            setStamps(prev => ({ ...prev, [folder]: Date.now() }));
            notify(`${label} ${game[folder] ? 'replaced' : 'added'}`, 'success');
            onUploaded(changed);
        } catch (e) {
            notify(`Couldn’t add the ${label.toLowerCase()}: ${e.message}`, 'error');
        }
        setBusy(null);
    };

    return (
        <GDSection id="media" title="Media" summary={`${have} of ${GD_MEDIA.length}`}>
            <div className="gd-media">
                {GD_MEDIA.map(([folder, label]) => {
                    const path = game[folder];
                    const icon = folder === 'manuals' ? '📖' : folder === 'videos' ? '🎬' : null;
                    // Where a downloaded one came from (not one replaced here since: that's a file of yours)
                    const from = path && !stamps[folder] && game.media_sources && game.media_sources[folder];
                    return (
                        <div key={folder} className={`gd-media-tile${path ? '' : ' gd-media-missing'}`}>
                            {path ? (
                                <a href={gdMedia(path)} target="_blank" rel="noopener noreferrer" title={`Open the ${label.toLowerCase()}`}>
                                    {icon ? <span className="gd-media-icon" aria-hidden="true">{icon}</span>
                                        : <img src={gdThumb(path, 160, stamps[folder])} alt="" loading="lazy" draggable={false} />}
                                </a>
                            ) : <span className="gd-media-none" aria-hidden="true">–</span>}
                            <div className="gd-media-label">
                                <span>{label}{folder === 'mix' && path && game.mix_generated && <span className="gd-badge" title="Made by RetroManager from this game’s other media, not scraped">generated</span>}</span>
                                <label className="gd-media-add admin-only" title={`${path ? 'Replace' : 'Add'} the ${label.toLowerCase()} with a file of yours. It’s saved straight away.`}>
                                    {busy === folder ? '…' : path ? '⟳' : '+'}
                                    <input type="file" accept={GD_MEDIA_ACCEPT[folder] || 'image/*'} disabled={!!busy}
                                        onChange={e => { const file = e.target.files[0]; e.target.value = ''; upload(folder, label, file); }} />
                                </label>
                            </div>
                            {from && <div className="gd-media-from" title={`Downloaded from ${from.source} on ${new Date(from.at * 1000).toLocaleDateString()}`}>from {from.source}</div>}
                        </div>
                    );
                })}
            </div>
        </GDSection>
    );
}

// PC games (DOS, Windows, ScummVM) are folders; pick which program in the
// folder is the game. Nothing shows for other systems.
function GDLaunchFile({ system, game, notify, onChanged }) {
    const [files, setFiles] = React.useState([]);
    const [choice, setChoice] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const current = String(game.path || '').replace(/^(\.\/)+/, '');
    React.useEffect(() => {
        setFiles([]);
        let cancelled = false;
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/launch-files?${new URLSearchParams({ rom: game.path })}`).then(r => r.json())
            .then(d => { if (!cancelled && d.success) { setFiles(d.files); setChoice(current); } })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [system, game.path]);
    if (files.length < 2) return null;
    const apply = async () => {
        setBusy(true);
        try {
            const res = await fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/launch-file`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from: current, to: choice }) });
            const d = await res.json();
            if (d.success) { notify(`Now launches ${choice.split('/').pop()}. Gamelist backed up first.`, 'success'); onChanged(`./${choice}`); }
            else notify(d.error || 'Could not change the launch file', 'error');
        } catch (e) { notify(e.message, 'error'); }
        setBusy(false);
    };
    return (
        <div className="gd-group">
            <div className="gd-group-head">Launch file <span className="gd-note">This game is a folder. The gamelist points at one program in it; setup, uninstallers and DOSBox are marked.</span></div>
            <div className="gd-pick">
                <select value={choice} onChange={e => setChoice(e.target.value)}>
                    {files.map(f => <option key={f.path} value={f.path}>{f.path.split('/').slice(1).join('/')}{f.helper ? '  (helper)' : ''}{f.path === current ? '  ← current' : ''}</option>)}
                </select>
                <button className="gd-btn small" disabled={busy || !choice || choice === current} onClick={apply}>{busy ? 'Changing...' : 'Use this file'}</button>
            </div>
        </div>
    );
}

// The <game> entry a save would write, asked of the backend when unfolded
function GDXmlPreview({ system, payload }) {
    const [open, setOpen] = React.useState(false);
    const [xml, setXml] = React.useState('');
    const [error, setError] = React.useState(null);
    const body = JSON.stringify(payload);
    React.useEffect(() => {
        if (!open) return;
        let cancelled = false;
        setError(null);
        fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/games/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
            .then(r => r.json())
            .then(d => { if (!cancelled) { if (d.success) setXml(d.xml); else setError(d.error || 'Preview failed'); } })
            .catch(e => { if (!cancelled) setError(e.message); });
        return () => { cancelled = true; };
    }, [open, body, system]);
    return (
        <details className="gd-group" onToggle={e => setOpen(e.target.open)}>
            <summary className="gd-note">Preview the gamelist.xml entry</summary>
            <div className="gd-note">Exactly what Save writes, including tags RetroManager keeps but doesn’t edit.</div>
            {error ? <div className="gd-note gd-error">{error}</div> : <pre className="gd-xml">{xml || 'Loading...'}</pre>}
        </details>
    );
}

// What EmulationStation is told about the game: which media its <image>,
// <thumbnail> and <video> use (changed in edit mode), a PC game's launch
// file, and the entry itself. For admins.
function GDGamelist({ system, game, draft, set, notify, onMoved }) {
    const shown = draft ? { ...game, ...draft } : game;
    const options = GD_MEDIA.map(([folder, label]) => ({ folder, label, path: typeof game[folder] === 'string' ? game[folder] : null }));
    const select = (field, allowed) => {
        const current = shown[field];
        const folder = current ? gdMediaFolder(current) : '';
        const offered = options.filter(o => allowed(o.folder));
        const value = !current ? '' : offered.some(o => o.folder === folder) ? folder : '__other';
        return (
            <select value={value} disabled={!draft} onChange={e => {
                const picked = offered.find(o => o.folder === e.target.value);
                if (e.target.value === '') set(field, undefined);
                else if (picked && picked.path) set(field, picked.path);
            }}>
                <option value="">None</option>
                {value === '__other' && <option value="__other">Other file: {String(current).split('/').pop()}</option>}
                {offered.map(o => <option key={o.folder} value={o.folder} disabled={!o.path}>{o.label}{o.path ? '' : ' (none)'}</option>)}
            </select>
        );
    };
    const pictures = (folder) => folder !== 'videos' && folder !== 'manuals';
    const fill = () => {
        const { game: filled, changed } = gdAutoFill(shown);
        ['image', 'thumbnail', 'video'].forEach(field => { if (filled[field] !== shown[field]) set(field, filled[field]); });
        notify(changed ? `Filled ${changed} field${changed > 1 ? 's' : ''}. Save to write them.` : 'Nothing to fill: the fields are set, or the game has no media for them', 'success');
    };
    return (
        <div className="admin-only">
            <GDSection id="gamelist" title="Gamelist" summary={String(game.path || '').replace(/^(\.\/)+/, '')}>
                <div className="gd-note" style={{marginBottom: 8}}>
                    What EmulationStation shows for this game; media files alone aren’t enough. {draft ? '' : 'Press ✏ to change these.'}
                </div>
                <dl className="gd-facts gd-facts-edit">
                    <dt>Image</dt><dd>{select('image', pictures)}</dd>
                    <dt>Thumbnail</dt><dd>{select('thumbnail', pictures)}</dd>
                    <dt>Video</dt><dd>{select('video', folder => folder === 'videos')}</dd>
                </dl>
                {draft && <button className="gd-btn small" style={{marginTop: 8}} onClick={fill} title="Fill the empty ones from this game’s media files">Auto-fill</button>}
                <GDLaunchFile system={system} game={game} notify={notify} onChanged={onMoved} />
                <GDXmlPreview system={system} payload={shown} />
            </GDSection>
        </div>
    );
}

// A dialog over everything, the Game Details popup included
function GDDialog({ onClose, label, children }) {
    React.useEffect(() => {
        // Before the popup's own Escape, which would close the whole panel
        const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
        document.addEventListener('keydown', esc, true);
        return () => document.removeEventListener('keydown', esc, true);
    }, [onClose]);
    return ReactDOM.createPortal(
        <div className="gd-backdrop gd-dialog-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
            <div className="gd gd-popup gd-dialog" role="dialog" aria-modal="true" aria-label={label}>{children}</div>
        </div>, document.body);
}

// Remove a game: its gamelist entry, and if asked its ROM file and media too
function GDDelete({ system, game, notify, onClose, onDeleted }) {
    const [rom, setRom] = React.useState(false);
    const [media, setMedia] = React.useState(false);
    const [typed, setTyped] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const files = rom || media;
    const name = game.name || '';
    const confirmed = !files || typed.trim() === name.trim();
    const remove = async () => {
        setBusy(true);
        try {
            const params = new URLSearchParams();
            if (rom) params.set('delete_rom', '1');
            if (media) params.set('delete_media', '1');
            const d = await (await fetch(`${GD_API}/api/systems/${encodeURIComponent(system)}/games/${gdEncode(game.path)}?${params}`, { method: 'DELETE' })).json();
            if (!d.success) throw new Error(d.error || 'Failed to delete game');
            const count = d.deleted_files ? d.deleted_files.length : 0;
            const parts = [d.removed_entry ? 'gamelist entry removed' : null, count ? `${count} file${count > 1 ? 's' : ''} deleted` : null].filter(Boolean);
            notify(`${name}: ${parts.join(', ') || 'nothing to remove'}`, d.errors && d.errors.length ? 'error' : 'success');
            onDeleted();
        } catch (e) {
            notify(e.message, 'error');
            setBusy(false);
        }
    };
    return (
        <GDDialog onClose={() => !busy && onClose()} label={`Remove ${name}`}>
            <h2 className="gd-title" style={{fontSize: 20}}>Remove {name}</h2>
            <div className="gd-note" style={{fontFamily: 'monospace', margin: '4px 0 16px'}}>{game.path}</div>
            <label className="gd-check" style={{opacity: game.has_metadata ? 1 : 0.5}}>
                <input type="checkbox" checked={!!game.has_metadata} disabled />
                <span><b>Remove the gamelist entry</b><br /><span className="gd-note">{game.has_metadata ? 'Its name, description and other details are lost. The gamelist keeps working without it.' : 'This game has no gamelist entry.'}</span></span>
            </label>
            <label className="gd-check">
                <input type="checkbox" checked={rom} onChange={e => setRom(e.target.checked)} disabled={game.rom_exists === false} />
                <span><b>Also delete the ROM file</b><br /><span className="gd-note">{game.rom_exists === false ? 'The ROM file is already missing.' : 'Permanently deletes the file from the NAS.'}</span></span>
            </label>
            <label className="gd-check">
                <input type="checkbox" checked={media} onChange={e => setMedia(e.target.checked)} />
                <span><b>Also delete its media files</b><br /><span className="gd-note">Permanently deletes images, video and manual named exactly after this ROM. Files shared with another region’s ROM are kept.</span></span>
            </label>
            {files && (
                <div className="gd-warning">
                    <div>Files can’t be recovered. Type <b style={{userSelect: 'text'}}>{name}</b> to confirm.</div>
                    <input className="gd-input" type="text" value={typed} onChange={e => setTyped(e.target.value)} autoFocus />
                </div>
            )}
            <div className="gd-actions" style={{justifyContent: 'flex-end', marginTop: 16}}>
                <button className="gd-btn" onClick={onClose} disabled={busy}>Cancel</button>
                <button className="gd-btn primary" onClick={remove} disabled={busy || !confirmed || (!game.has_metadata && !files)}>
                    {busy ? 'Removing...' : files ? 'Delete permanently' : 'Remove from gamelist'}
                </button>
            </div>
        </GDDialog>
    );
}
