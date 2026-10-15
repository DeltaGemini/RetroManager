// What RetroManager knows about each system folder: who made it, what kind of
// machine it is and which console generation it belongs to. Shared by the
// Library (sidebar filters and sorting), the Bookcase (shelf order) and the
// Timeline (generation filter). Plain JavaScript, loaded after header.js:
//     const { generationGroup } = RM.systems;
(function () {
    // Who made each system, and what kind it is
    const SYSTEM_MAKERS = {
        Nintendo: ['nes', 'famicom', 'fds', 'snes', 'sfc', 'n64', 'gb', 'gbc', 'gba', 'nds', '3ds', 'n3ds', 'gc', 'ngc', 'wii', 'wiiu', 'nsw', 'switch', 'nvb', 'virtualboy', 'pokemini', 'gameandwatch', 'gw'],
        Sega: ['mastersystem', 'sms', 'megadrive', 'genesis', 'gamegear', 'sega32x', 'segacd', 'saturn', 'dreamcast', 'sg-1000', 'sg1000', 'naomi'],
        Sony: ['psx', 'ps1', 'ps2', 'ps3', 'psp', 'psvita'],
        Atari: ['atari2600', 'atari5200', 'atari7800', 'atari800', 'atarilynx', 'lynx', 'atarijaguar', 'jaguar', 'atarist'],
        Computers: ['dos', 'pc', 'winxp', 'win', 'windows', 'scummvm', 'steam', 'amiga', 'c64', 'msx', 'zxspectrum', 'amstradcpc', 'x68000', 'ports'],
    };
    const HANDHELDS = ['gb', 'gbc', 'gba', 'nds', '3ds', 'n3ds', 'nvb', 'virtualboy', 'pokemini', 'gameandwatch', 'gw', 'gamegear', 'psp', 'psvita', 'atarilynx', 'lynx', 'ngp', 'ngpc', 'wonderswan', 'wonderswancolor'];
    const ATARI_COMPUTERS = ['atari800', 'atarist', 'atarixe'];
    const ARCADE = ['arcade', 'mame', 'mame-libretro', 'fba', 'fbneo', 'neogeo', 'naomi', 'cps1', 'cps2', 'cps3', 'daphne'];
    const makerOf = (name) => Object.keys(SYSTEM_MAKERS).find(m => SYSTEM_MAKERS[m].includes(name.toLowerCase())) || 'Other';
    const typeOf = (name) => {
        const n = name.toLowerCase();
        if (HANDHELDS.includes(n)) return 'Handheld';
        if (ARCADE.includes(n)) return 'Arcade';
        if (SYSTEM_MAKERS.Computers.includes(n) || ATARI_COMPUTERS.includes(n)) return 'Computer';
        return 'Console';
    };
    // Console generations. Handhelds sit with the home consoles of their time;
    // add-ons with the console they plug into. Computers and arcade boards have
    // no generation and are grouped after the consoles.
    const SYSTEM_GENERATIONS = {
        1: ['pong', 'odyssey'],
        2: ['atari2600', 'atari5200', 'channelf', 'coleco', 'colecovision', 'intellivision', 'vectrex', 'ody2', 'odyssey2', 'videopac', 'astrocade', 'arcadia', 'gameandwatch', 'gw'],
        3: ['nes', 'famicom', 'fds', 'mastersystem', 'sms', 'sg-1000', 'sg1000', 'atari7800'],
        4: ['snes', 'sfc', 'megadrive', 'genesis', 'segacd', 'sega32x', 'pcengine', 'pcenginecd', 'tg16', 'tg-cd', 'supergrafx', 'neogeo', 'neogeocd', 'cdi', 'gb', 'gamegear', 'atarilynx', 'lynx'],
        5: ['psx', 'ps1', 'n64', 'saturn', '3do', 'atarijaguar', 'jaguar', 'atarijaguarcd', 'pcfx', 'gbc', 'nvb', 'virtualboy', 'ngp'],
        6: ['ps2', 'gc', 'ngc', 'gamecube', 'dreamcast', 'xbox', 'gba', 'ngpc', 'wonderswan', 'wonderswancolor', 'pokemini'],
        7: ['wii', 'ps3', 'xbox360', 'nds', 'psp'],
        8: ['wiiu', 'ps4', 'xboxone', '3ds', 'n3ds', 'psvita', 'nsw', 'switch'],
        9: ['ps5', 'xboxseriesx', 'switch2'],
    };
    // When each generation's first console came out, to when the next one's did
    const GENERATION_YEARS = { 1: '1972–1976', 2: '1976–1983', 3: '1983–1987', 4: '1987–1993', 5: '1993–1998', 6: '1998–2005', 7: '2005–2012', 8: '2012–2020', 9: '2020–' };
    const generationOf = (name) => Number(Object.keys(SYSTEM_GENERATIONS).find(g => SYSTEM_GENERATIONS[g].includes(name.toLowerCase()))) || null;
    const ordinal = (n) => n + (['th', 'st', 'nd', 'rd'][n % 10 > 3 || (n % 100 >= 11 && n % 100 <= 13) ? 0 : n % 10]);
    // Sort position and heading: generations oldest first, then Arcade, Computers, Other
    const generationGroup = (name) => {
        const generation = generationOf(name);
        if (generation) return { rank: generation, label: `${ordinal(generation)} generation (${GENERATION_YEARS[generation]})` };
        const type = typeOf(name);
        if (type === 'Arcade') return { rank: 101, label: 'Arcade' };
        if (type === 'Computer') return { rank: 102, label: 'Computers' };
        return { rank: 103, label: 'Other' };
    };

    window.RM = window.RM || {};
    // A system's picture (frontend/imgs/), for folders named differently from it
    const SYSTEM_IMG_ALIASES = { nvb: 'virtualboy' };
    // Which pictures the systems have: RetroManager's own drawn tiles
    // (frontend/tiles/) or the ones in frontend/imgs/ ("theme": from a Switch
    // EmulationStation theme, where they're installed). The server has a
    // setting for which; a browser can choose the other for itself in the
    // Console settings (kept here; null until it has), and a system with no
    // picture in imgs/ gets its drawn tile either way.
    const systemPictures = {
        KEY: 'retromanager.systemPictures',
        OPTIONS: [['drawn', 'Drawn tiles'], ['theme', 'Switch theme pictures']],
        get() {
            try { const saved = localStorage.getItem(this.KEY); return saved === 'drawn' || saved === 'theme' ? saved : null; } catch (e) { return null; }
        },
        set(key) {
            try { localStorage.setItem(this.KEY, key === 'theme' ? 'theme' : 'drawn'); } catch (e) {}
            window.dispatchEvent(new Event('retromanager:system-pictures'));
        },
    };
    const imageOf = (name) => `/imgs/${SYSTEM_IMG_ALIASES[name.toLowerCase()] || name.toLowerCase()}.jpg${systemPictures.get() ? `?${systemPictures.get()}=1` : ''}`;

    window.RM.systems = { SYSTEM_MAKERS, HANDHELDS, ARCADE, makerOf, typeOf, SYSTEM_GENERATIONS, GENERATION_YEARS, generationOf, generationGroup, imageOf, systemPictures };
})();
