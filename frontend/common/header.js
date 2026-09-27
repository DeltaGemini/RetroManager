// The header every RetroManager page shares: brand, Library / Bookcase /
// Timeline, and the actions (library-scrape progress, Add games, Tools, theme).
// Plain JavaScript (no JSX) so any page can load it after React:
//     <RM.Header active="timeline" />
// On the library page, pass onTool to open a Tools panel in place; elsewhere
// the Tools menu goes to the library with ?tool=<name>.
(function () {
    const h = React.createElement;
    const { useState, useEffect, useRef } = React;

    const PAGES = [
        { key: 'library', label: 'Library', icon: '🎮', href: '/' },
        { key: 'bookcase', label: 'Bookcase', icon: '📚', href: '/shelf' },
        { key: 'timeline', label: 'Timeline', icon: '🕰️', href: '/timeline' },
    ];

    const TOOLS = [
        { key: 'health', icon: '🩺', label: 'Library health', help: 'Every system’s Scan in one place' },
        { key: 'scrape', icon: '🔎', label: 'Library scrape', help: 'Scrape every system in the background' },
        { key: 'media', icon: '🖼️', label: 'Missing media', help: 'Which games lack a box, screenshot, spine...' },
        { key: 'history', icon: '🕹️', label: 'Play history', help: 'What’s been played, and by whom' },
        { key: 'saves', icon: '💾', label: 'Saves', help: 'Sync conflicts and save backups' },
        { key: 'backups', icon: '🗂️', label: 'Gamelist backups', help: 'See what changed and restore' },
    ];

    function ThemeToggle() {
        const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
        const next = theme === 'light' ? 'dark' : 'light';
        const toggle = () => {
            if (next === 'light') document.documentElement.dataset.theme = 'light';
            else delete document.documentElement.dataset.theme;
            try { localStorage.setItem('retromanager.theme', next); } catch (e) {}
            setTheme(next);
        };
        return h('button', { className: 'rm-btn', onClick: toggle, title: `Switch to ${next} mode`, 'aria-label': `Switch to ${next} mode` },
            theme === 'light' ? '🌙' : '☀️', h('span', { className: 'rm-label' }, theme === 'light' ? 'Dark' : 'Light'));
    }

    function ToolsMenu({ onTool }) {
        const [open, setOpen] = useState(false);
        const ref = useRef(null);
        useEffect(() => {
            if (!open) return;
            const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
            const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
            document.addEventListener('mousedown', close);
            document.addEventListener('keydown', esc);
            return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
        }, [open]);
        const pick = (key) => {
            setOpen(false);
            if (onTool) onTool(key);
            else window.location.href = `/?tool=${encodeURIComponent(key)}`;
        };
        return h('div', { ref, className: 'rm-menu-wrap' },
            h('button', { className: 'rm-btn', onClick: () => setOpen(o => !o), 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': 'Tools', title: 'Tools' },
                '🧰', h('span', { className: 'rm-label' }, 'Tools')),
            open && h('div', { role: 'menu', className: 'rm-menu' },
                TOOLS.map(t => h('button', { key: t.key, role: 'menuitem', onClick: () => pick(t.key) },
                    h('span', { style: { fontSize: 16 }, 'aria-hidden': true }, t.icon),
                    h('span', null, h('span', { style: { display: 'block' } }, t.label), h('span', { className: 'rm-help' }, t.help))))));
    }

    // Library-scrape progress: checked every minute, every 3 s while it runs.
    // The library page passes its own status instead.
    function useScrapeStatus(enabled) {
        const [status, setStatus] = useState(null);
        useEffect(() => {
            if (!enabled) return;
            let timer, stopped = false;
            const tick = async () => {
                let running = false;
                try {
                    const d = await (await fetch('/api/scrape-queue')).json();
                    if (d.success && !stopped) { setStatus(d); running = d.running; }
                } catch (e) {}
                if (!stopped) timer = setTimeout(tick, running ? 3000 : 60000);
            };
            tick();
            return () => { stopped = true; clearTimeout(timer); };
        }, [enabled]);
        return status;
    }

    function Header({ active, onTool, scrapeStatus }) {
        const own = useScrapeStatus(scrapeStatus === undefined);
        const status = scrapeStatus === undefined ? own : scrapeStatus;
        return h('header', { className: 'rm-header' },
            h('a', { className: 'rm-brand', href: '/', 'aria-label': 'RetroManager library' },
                h('img', { src: '/icons/icon-192.png', alt: '' }), h('span', null, 'RetroManager')),
            h('nav', { className: 'rm-nav', 'aria-label': 'Views' },
                PAGES.map(p => h('a', { key: p.key, href: p.href, 'aria-current': active === p.key ? 'page' : undefined, title: p.label, 'aria-label': p.label },
                    h('span', { 'aria-hidden': true }, p.icon), h('span', { className: 'rm-label' }, p.label)))),
            h('div', { className: 'rm-actions' },
                status && status.running && h('button', {
                    className: 'rm-btn rm-chip', title: 'Library scrape in progress',
                    onClick: () => onTool ? onTool('scrape') : (window.location.href = '/?tool=scrape'),
                }, '⏳', h('span', { className: 'rm-label' }, 'Scraping'), ` ${status.done}/${status.total}`),
                h('a', { className: 'rm-btn', href: '/import', 'aria-current': active === 'import' ? 'page' : undefined, title: 'Add games', 'aria-label': 'Add games' },
                    '➕', h('span', { className: 'rm-label' }, 'Add games')),
                h(ToolsMenu, { onTool }),
                h(ThemeToggle)));
    }

    window.RM = { Header, ThemeToggle, TOOLS, PAGES };
})();
