// Fill the gaps (tools-fill.jsx): what its parts share, the kinds and sources and how they're shown.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const FILL_PICTURES = ['box2d', 'mix', 'wheel', 'screenshot', 'screenshottitle', 'box3d', 'boxside', 'support', 'fanart'];
// Files, not pictures: a manual (PDF) and a video, shown as a tile to open (ScreenScraper has them)
const FILL_FILES = ['manuals', 'videos'];
const FILL_FILE_ICONS = { manuals: '📄', videos: '🎬' };
const FILL_MEDIA = [...FILL_PICTURES, ...FILL_FILES];
const FILL_FIELDS = { name: 'Name', desc: 'Description', releasedate: 'Released', developer: 'Developer', publisher: 'Publisher', genre: 'Genre', players: 'Players', rating: 'Rating' };
// Pictures wider than tall, shown so
const FILL_WIDE = new Set(['mix', 'wheel', 'screenshot', 'screenshottitle', 'fanart']);
const FILL_ORDER_KEY = 'rm-fill-order';
// Kinds RetroManager can make from a game's own pictures: a Mix (the Mix generator), and a 3D box
// or a spine from its cover (backend/box_generator.py)
const FILL_MAKES = {
    mix: { maker: 'Mix generator', from: 'from its own pictures', made: 'from the pictures it has now', label: 'the Mix generator',
        title: "Make a Mix from this game's own screenshot, box, cart and logo" },
    box3d: { maker: 'Box maker', from: 'from its cover and spine', made: 'from its cover and spine', label: 'RetroManager (made here)',
        title: "Make a 3D box from this game's cover, with its spine (or one made for it)" },
    boxside: { maker: 'Box maker', from: 'from its cover and logo', made: "its cover's colour and its logo", label: 'RetroManager (made here)',
        title: "Make a spine from this game's cover colour, its logo and the look of the system's case" },
};
const FILL_ON_KEY = 'rm-fill-what';
const FILL_CONF = { exact: 'Exact', likely: 'Likely', unsure: 'Unsure', chosen: 'Chosen', none: 'No match' };

// What a web search adds to the game's name to find each kind
const FILL_SEARCH_WORDS = { box2d: 'box art', box3d: '3d box', boxside: 'box spine', support: 'cartridge disc', screenshot: 'screenshot',
    screenshottitle: 'title screen', wheel: 'logo png', fanart: 'artwork wallpaper', mix: 'box art', manuals: 'manual pdf', videos: 'gameplay video mp4' };
const fillSearchUrl = (g, k) => {
    const q = `"${splitGameName(g.name || g.path).title}" ${g._systemName || ''} ${FILL_SEARCH_WORDS[k] || ''}`.trim();
    return `https://www.google.com/search?${new URLSearchParams(FILL_FILES.includes(k) ? { q } : { q, tbm: 'isch' })}`;
};
const fillLabel = (k) => FILL_FIELDS[k] || mediaSourceLabel(k);
const fillHas = (g, k) => {
    const v = g[k];
    return !(v === undefined || v === null || v === '' || (k === 'rating' && (v === '0' || v === 0)));
};
// What a game is missing, of the kinds being filled
const fillGaps = (g, fill) => [...FILL_MEDIA, ...Object.keys(FILL_FIELDS)].filter(k => fill[k] && !fillHas(g, k));
const fillWhen = (v) => (/^\d{8}T/.test(String(v || '')) ? `${v.slice(6, 8)}/${v.slice(4, 6)}/${v.slice(0, 4)}` : v);
const fillText = (k, v) => (k === 'releasedate' ? fillWhen(v) : k === 'rating' ? `${Math.round(Number(v) * 100)}%` : String(v));
// A game is known by its system and its file (games from several systems can be in one list)
const fillKey = (g) => `${g._system}|${g.path}`;
const fillRom = (path) => String(path).replace(/^\.\//, '');

const FILL_FIELD_STYLE = { padding: 6, borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13 };
const fillChip = (k, extra) => <span key={k} className={`fill-chip ${FILL_FIELDS[k] ? 'text' : 'pic'}`}>{fillLabel(k)}{extra}</span>;
const fillConfChip = (m) => m && <span className={`fill-chip conf-${m.confidence}`}>{FILL_CONF[m.confidence] || m.confidence}</span>;
const fillIsFile = (k) => FILL_FILES.includes(k);
// A manual or video has no picture to show: its kind, to open (⤢) and look at
const fillFileArt = (k) => fillIsFile(k) && <span className="fill-file"><span aria-hidden="true">{FILL_FILE_ICONS[k]}</span>{k === 'videos' ? 'Play it' : 'Read it'} with ⤢</span>;
// ⤢ on a tile: it larger, or the manual or video opened
const fillSeeIt = (z, setZoom) => (
    <span className="zoom" role="button" tabIndex={0} aria-label={fillIsFile(z.kind) ? `Open the ${fillLabel(z.kind).toLowerCase()}` : 'See it larger'}
        onClick={e => { e.stopPropagation(); setZoom(z); }} onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); setZoom(z); } }}>⤢</span>
);
