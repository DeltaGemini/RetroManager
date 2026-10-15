// Shared by the Bookcase page: box sizes, picture addresses and sorting.
// Part of the Bookcase page (shelf.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const { useState, useEffect, useMemo, useRef, useCallback } = React;
const API_BASE = window.location.origin;

// Physical box size in mm: w = cover width, h = height, d = spine thickness.
// Approximate retail boxes/cases per system (folder name). Unknown systems use DEFAULT_BOX.
const BOX_SIZES = {
    snes: { w: 140, h: 192, d: 32 }, sfc: { w: 140, h: 192, d: 32 },
    nes: { w: 127, h: 178, d: 25 }, famicom: { w: 127, h: 178, d: 25 }, fds: { w: 127, h: 178, d: 25 },
    n64: { w: 190, h: 135, d: 38 },
    gb: { w: 127, h: 127, d: 25 }, gbc: { w: 127, h: 127, d: 25 }, gba: { w: 127, h: 127, d: 25 },
    nds: { w: 125, h: 137, d: 14 }, '3ds': { w: 128, h: 137, d: 14 },
    psx: { w: 142, h: 125, d: 10 }, ps2: { w: 135, h: 190, d: 14 }, ps3: { w: 135, h: 171, d: 14 }, psp: { w: 105, h: 180, d: 14 },
    gc: { w: 135, h: 190, d: 14 }, wii: { w: 135, h: 190, d: 14 }, nsw: { w: 105, h: 170, d: 11 },
    megadrive: { w: 132, h: 184, d: 22 }, genesis: { w: 132, h: 184, d: 22 }, mastersystem: { w: 132, h: 184, d: 22 },
    gamegear: { w: 127, h: 127, d: 25 }, atari2600: { w: 127, h: 178, d: 38 }, atari5200: { w: 150, h: 200, d: 45 },
    nvb: { w: 160, h: 235, d: 50 }, virtualboy: { w: 160, h: 235, d: 50 },
    pokemini: { w: 80, h: 100, d: 18 },
};
const DEFAULT_BOX = { w: 135, h: 190, d: 14 };
const PX_PER_MM = 1.3;
// A spine narrower than this can't show the game's name clearly, so thin
// cases (DVD-style cases, DS and 3DS, jewel cases, Switch) are drawn larger
// than life, in proportion, until theirs is this wide; never more than
// MAX_CASE_SCALE, or the thinnest would tower over everything else
const READABLE_SPINE_PX = 24;
const MAX_CASE_SCALE = 1.5;
const boxFor = (system) => {
    const box = BOX_SIZES[system.toLowerCase()] || DEFAULT_BOX;
    const scale = Math.min(MAX_CASE_SCALE, READABLE_SPINE_PX / (box.d * PX_PER_MM));
    if (scale <= 1) return box;
    return { w: box.w * scale, h: box.h * scale, d: box.d * scale };
};
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const MIN_SPINE_PX = 14;
const SPINE_GAP = 2;   // matches .shelf-row's gap

const systemImg = RM.systems.imageOf;

const encodePath = (p) => p.split('/').map(encodeURIComponent).join('/');
// version: the picture's change time from /api/shelf, so the browser can keep it
const thumb = (mediaPath, height, spine = false, version = null) =>
    `${API_BASE}/api/thumb/${height}/${encodePath(mediaPath)}?${new URLSearchParams({ ...(spine ? { spine: '1' } : {}), ...(version ? { v: String(version) } : {}) })}`;
const pic = (game, field, height, spine = false) => game[field] ? thumb(game[field], height, spine, game.v && game.v[field]) : null;

const cleanTitle = (name) => (name || '').replace(/\s*[\(\[][^\)\]]*[\)\]]/g, '').replace(/\s+/g, ' ').trim() || name;

const SORTS = {
    name: (a, b) => cleanTitle(a.name).localeCompare(cleanTitle(b.name), undefined, { sensitivity: 'base', numeric: true }),
    year: (a, b) => (a.year || '9999').localeCompare(b.year || '9999') || SORTS.name(a, b),
    file: (a, b) => (a.path || '').localeCompare(b.path || '', undefined, { sensitivity: 'base', numeric: true }),
};
