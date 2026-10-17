// Shared by the library page's panels: React hooks, the API address, backdrop handling and scraped-media helpers.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const { useState, useEffect, useRef } = React;

const stripDotSlash = (path) => String(path || '').replace(/^(\.\/)+/, '');
const API_BASE = window.location.origin;

// Closes an overlay only when the press AND the release are both on its backdrop.
// A plain onClick also fires when you press inside (e.g. selecting text in a
// field) and let go over the backdrop, which closed popups by accident.
let backdropPressTarget = null;
const backdropClose = (onClose) => ({
    onMouseDown: (e) => { backdropPressTarget = e.target; },
    onClick: (e) => {
        const pressedHere = backdropPressTarget === e.currentTarget;
        backdropPressTarget = null;
        if (onClose && pressedHere && e.target === e.currentTarget) onClose();
    },
});

// Where each scraped image goes by default. ScreenScraper media already use
// folder names (as do RetroAchievements, Steam and libretro where one fits);
// IGDB's cover/screenshots/artwork and SteamGridDB's grids/heroes/logos are
// mapped. Videos are left on Skip (large and slow), as are extra screenshots,
// artwork and alternative covers.
const DEFAULT_MEDIA_TARGET = {
    box2d: 'box2d', box3d: 'box3d', boxside: 'boxside', wheel: 'wheel',
    screenshot: 'screenshot', screenshottitle: 'screenshottitle', fanart: 'fanart',
    posters: 'posters', images: 'images', mix: 'mix', support: 'support', manuals: 'manuals',
    cover: 'box2d', screenshot_1: 'screenshot', artwork_1: 'fanart',
    grid_1: 'box2d', hero_1: 'fanart', logo_1: 'wheel',
};

// Sources the Scrape popup can search. ScreenScraper and IGDB have routes of
// their own; the rest share /api/sources/<id>/...
const SCRAPE_SOURCES = [
    { id: 'screenscraper', label: 'ScreenScraper', color: 'var(--accent-pink)',
      search: '/api/scraper/search', info: '/api/scraper/game-info', title: 'Search on ScreenScraper.fr' },
    { id: 'igdb', label: 'IGDB', color: 'var(--accent-blue)',
      search: '/api/igdb/search', info: '/api/igdb/game-info', title: 'Search on IGDB' },
    { id: 'retroachievements', label: 'RetroAchievements', color: 'var(--accent-orange)',
      title: 'Identify the ROM by its checksum (ROM hacks included), or search by name' },
    { id: 'steam', label: 'Steam', color: 'var(--accent-blue)', title: 'Search the Steam store (PC games)' },
    { id: 'steamgriddb', label: 'SteamGridDB', color: 'var(--accent-blue)', title: 'Community covers, heroes and logos (artwork only)' },
    { id: 'thegamesdb', label: 'TheGamesDB', color: 'var(--accent-pink)', title: 'Search TheGamesDB: descriptions, box art, fan art, screenshots and logos' },
    { id: 'launchbox', label: 'LaunchBox', color: 'var(--accent-orange)', title: 'The LaunchBox Games Database: pictures of every kind, cartridges and discs among them (artwork only)' },
    { id: 'gametdb', label: 'GameTDB', color: 'var(--accent-blue)', title: 'Disc or cartridge, cover and 3D box for this very game, by the ID in its ROM (GameCube, Wii, DS, 3DS, PS3)' },
    { id: 'libretro', label: 'libretro', color: 'var(--accent-orange)', title: 'libretro thumbnails for this ROM name (artwork only)' },
].map(src => ({ search: `/api/sources/${src.id}/search`, info: `/api/sources/${src.id}/game-info`, ...src }));
const scrapeSource = (id) => SCRAPE_SOURCES.find(src => src.id === id) || SCRAPE_SOURCES[0];

// The game's current file for a media folder, if it has one
const existingMediaPath = (game, folder) =>
    folder && typeof game?.[folder] === 'string' && game[folder] ? game[folder] : null;
const localMediaUrl = (path) => `${window.location.origin}/api/media/${path.split('/').map(encodeURIComponent).join('/')}`;
// Media that can't be shown as a picture
const NON_IMAGE_MEDIA = new Set(['videos', 'manuals']);

// Readable names for scraped media on the Assign Media cards
const MEDIA_SOURCE_LABELS = {
    box2d: 'Box 2D', box3d: 'Box 3D', boxside: 'Spine', wheel: 'Wheel', screenshot: 'Screenshot',
    screenshottitle: 'Title screen', fanart: 'Fanart', posters: 'Poster', images: 'Image', mix: 'Mix',
    support: 'Cart / disc',
    manuals: 'Manual', videos: 'Video', cover: 'Cover', icon: 'Icon', header: 'Store header',
};
const mediaSourceLabel = (key) => MEDIA_SOURCE_LABELS[key]
    || key.replace(/_(\d+)$/, ' $1').replace(/^./, c => c.toUpperCase());

// What a Background scrape can download (videos are left out: large and slow)
const BULK_MEDIA = [
    { key: 'box2d', label: 'Box 2D' },
    { key: 'screenshot', label: 'Screenshot' },
    { key: 'screenshottitle', label: 'Title screen' },
    { key: 'wheel', label: 'Wheel' },
    { key: 'mix', label: 'Mix' },
    { key: 'box3d', label: 'Box 3D' },
    { key: 'boxside', label: 'Spine' },
    { key: 'support', label: 'Cart / disc' },
    { key: 'fanart', label: 'Fanart' },
    { key: 'manuals', label: 'Manual' },
];

// How sure a match is (Background scrape)
const CONFIDENCE = {
    exact: { label: 'Exact', color: 'var(--success)', help: 'This exact ROM file was recognised, by its name or its checksum' },
    likely: { label: 'Likely', color: 'var(--accent-orange)', help: "The game's name closely matches the ROM" },
    unsure: { label: 'Unsure', color: 'var(--accent-pink)', help: 'The names differ: check before applying' },
    none: { label: 'No match', color: 'var(--text-secondary)', help: 'Nothing found. Try searching another name' },
};

const postJson = async (url, body) => {
    const res = await fetch(`${API_BASE}${url}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return res.json();
};
