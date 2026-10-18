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

// The scraping sources, in Fill the gaps' order to begin with: their names, and what each offers
const SCRAPE_SOURCES = [
    { id: 'screenscraper', label: 'ScreenScraper', title: 'Search on ScreenScraper.fr' },
    { id: 'igdb', label: 'IGDB', title: 'Search on IGDB' },
    { id: 'retroachievements', label: 'RetroAchievements',
      title: 'Identify the ROM by its checksum (ROM hacks included), or search by name' },
    { id: 'steam', label: 'Steam', title: 'Search the Steam store (PC games)' },
    { id: 'steamgriddb', label: 'SteamGridDB', title: 'Community covers, heroes and logos (artwork only)' },
    { id: 'thegamesdb', label: 'TheGamesDB', title: 'Search TheGamesDB: descriptions, box art, fan art, screenshots and logos' },
    { id: 'launchbox', label: 'LaunchBox', title: 'The LaunchBox Games Database: pictures of every kind, cartridges and discs among them (artwork only)' },
    { id: 'gametdb', label: 'GameTDB', title: 'Disc or cartridge, cover and 3D box for this very game, by the ID in its ROM (GameCube, Wii, DS, 3DS, PS3)' },
    { id: 'libretro', label: 'libretro', title: 'libretro thumbnails for this ROM name (artwork only)' },
];
const scrapeSource = (id) => SCRAPE_SOURCES.find(src => src.id === id) || SCRAPE_SOURCES[0];

const localMediaUrl = (path) => `${window.location.origin}/api/media/${path.split('/').map(encodeURIComponent).join('/')}`;

// Readable names for each kind of media
const MEDIA_SOURCE_LABELS = {
    box2d: 'Box 2D', box3d: 'Box 3D', boxside: 'Spine', wheel: 'Wheel', screenshot: 'Screenshot',
    screenshottitle: 'Title screen', fanart: 'Fanart', posters: 'Poster', images: 'Image', mix: 'Mix',
    support: 'Cart / disc',
    manuals: 'Manual', videos: 'Video', cover: 'Cover', icon: 'Icon', header: 'Store header',
};
const mediaSourceLabel = (key) => MEDIA_SOURCE_LABELS[key]
    || key.replace(/_(\d+)$/, ' $1').replace(/^./, c => c.toUpperCase());

const postJson = (url, body) => RM.sendJson(url, 'POST', body);
