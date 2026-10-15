// The site's colour themes. Loaded in each page's <head>, before anything is
// drawn, so the page never flashes the default theme first.
//
// A theme is a base ("dark" or "light": data-theme, which each page's own
// colours follow) and, for all but the two originals, a palette
// (data-palette, defined in common/header.css). The choice is remembered in
// this browser as retromanager.theme.
(function () {
    const THEMES = [
        { key: 'dark', label: 'Midnight', base: 'dark', swatch: ['#0a0e27', '#14194f', '#ff6b9d'] },
        { key: 'light', label: 'Daylight', base: 'light', swatch: ['#f4f5fb', '#eceef7', '#d6336c'] },
        { key: 'black', label: 'Black', base: 'dark', swatch: ['#000000', '#17171c', '#ff6b9d'] },
        { key: 'slate', label: 'Slate', base: 'dark', swatch: ['#1b1f27', '#2c323e', '#4fb3d9'] },
        { key: 'terminal', label: 'Terminal', base: 'dark', swatch: ['#050a05', '#0f1f0f', '#39ff6a'] },
        { key: 'sepia', label: 'Sepia', base: 'light', swatch: ['#f3ead8', '#ebdfc6', '#a8452c'] },
        // After the Switch Master EmulationStation theme (assets in frontend/themes/switch/)
        { key: 'switch', label: 'Switch', base: 'dark', swatch: ['#2d2d2d', '#ac42bf', '#fa6122'] },
        { key: 'switch-light', label: 'Switch Light', base: 'light', swatch: ['#d9d9d9', '#3aa5ab', '#334ff0'] },
    ];

    const find = (key) => THEMES.find(t => t.key === key) || THEMES[0];
    const apply = (theme) => {
        const root = document.documentElement;
        if (theme.base === 'light') root.dataset.theme = 'light'; else delete root.dataset.theme;
        if (theme.key !== theme.base) root.dataset.palette = theme.key; else delete root.dataset.palette;
    };
    const current = () => {
        try { return find(localStorage.getItem('retromanager.theme')); } catch (e) { return THEMES[0]; }
    };
    const set = (key) => {
        const theme = find(key);
        apply(theme);
        try { localStorage.setItem('retromanager.theme', theme.key); } catch (e) {}
        return theme;
    };

    apply(current());
    window.RMTheme = { THEMES, current, set };
})();
