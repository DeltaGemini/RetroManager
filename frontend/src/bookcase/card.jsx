// Pulling a box out, the options menu and the card that opens.
// Part of the Bookcase page (shelf.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Plays the pull-out: a copy of the spine (the real one is hidden, leaving
// a gap) slides up out of the shelf and flies to the middle of the screen.
// Calls done() when it's finished.
function playPullOut(el, done) {
    if (reducedMotion()) { done(); return; }
    const rect = el.getBoundingClientRect();
    const clone = el.cloneNode(true);
    clone.className = 'spine spine-clone';
    clone.removeAttribute('tabindex');
    clone.removeAttribute('role');
    clone.setAttribute('aria-hidden', 'true');
    Object.assign(clone.style, {
        left: `${rect.left}px`,
        top: `${rect.top}px`,
        width: `${rect.width}px`,
        height: `${rect.height}px`,
    });
    // Fly from the spine's centre to the middle of the screen
    clone.style.setProperty('--tx', `${window.innerWidth / 2 - (rect.left + rect.width / 2)}px`);
    clone.style.setProperty('--ty', `${window.innerHeight / 2 - (rect.top + rect.height / 2)}px`);
    document.body.appendChild(clone);
    let finished = false;
    const finish = () => {
        if (finished) return;
        finished = true;
        clone.remove();
        done();
    };
    clone.addEventListener('animationend', finish);
    setTimeout(finish, 900); // in case the animation never reports finishing
}

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

// What the bookcase is made of (data-bookcase; mahogany is the page's own colours)
const FINISHES = [['mahogany', 'Mahogany'], ['oak', 'Oak'], ['walnut', 'Walnut'], ['ebony', 'Ebony'], ['white', 'White'], ['arcade', 'Neon arcade'], ['glass', 'Frosted glass']];
const DEFAULT_OPTIONS = { preload: false, finish: 'mahogany' };
function useBookcaseOptions() {
    const [options, setOptions] = useState(() => {
        try { return { ...DEFAULT_OPTIONS, ...JSON.parse(localStorage.getItem('retromanager.bookcase.options') || '{}') }; }
        catch (e) { return DEFAULT_OPTIONS; }
    });
    const update = (changes) => setOptions(o => {
        const next = { ...o, ...changes };
        try { localStorage.setItem('retromanager.bookcase.options', JSON.stringify(next)); } catch (e) {}
        return next;
    });
    return [options, update];
}

// Fetches pictures in the background (4 at a time) so the browser has them
// before they're needed. Returns progress; stops when switched off.
function usePreloader(enabled, urls) {
    const [progress, setProgress] = useState({ done: 0, failed: 0, total: 0 });
    const key = enabled ? urls.join('\n') : '';
    useEffect(() => {
        if (!enabled || !urls.length) { setProgress({ done: 0, failed: 0, total: 0 }); return; }
        let cancelled = false, next = 0, done = 0, failed = 0;
        setProgress({ done: 0, failed: 0, total: urls.length });
        const worker = () => new Promise(resolve => {
            const step = () => {
                if (cancelled || next >= urls.length) return resolve();
                const img = new Image();
                img.decoding = 'async';
                const finish = (ok) => {
                    ok ? done++ : failed++;
                    if (!cancelled && ((done + failed) % 10 === 0 || done + failed === urls.length)) setProgress({ done, failed, total: urls.length });
                    step();
                };
                img.onload = () => finish(true);
                img.onerror = () => finish(false);
                img.src = urls[next++];
            };
            step();
        });
        Promise.all([worker(), worker(), worker(), worker()]).then(() => { if (!cancelled) setProgress({ done, failed, total: urls.length }); });
        return () => { cancelled = true; };
    }, [key]);
    return progress;
}

function OptionsMenu({ options, setOptions, progress }) {
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
    const busy = options.preload && progress.total > 0 && progress.done + progress.failed < progress.total;
    return (
        <div className="opts-wrap" ref={ref}>
            <button onClick={() => setOpen(o => !o)} aria-haspopup="dialog" aria-expanded={open} title="Bookcase options">
                ⚙ Options{busy ? ` · ${Math.floor(((progress.done + progress.failed) / progress.total) * 100)}%` : ''}
            </button>
            {open && (
                <div className="opts-menu" role="dialog" aria-label="Bookcase options">
                    <fieldset>
                        <legend>Bookcase</legend>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                            {FINISHES.map(([key, label]) => (
                                <label key={key}>
                                    <input type="radio" name="bookcase-finish" checked={options.finish === key} onChange={() => setOptions({ finish: key })} /> {label}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                    <fieldset>
                        <legend>Speed</legend>
                        <label>
                            <input type="checkbox" checked={options.preload} onChange={e => setOptions({ preload: e.target.checked })} /> Preload pictures
                        </label>
                        <div className="opts-help">
                            Downloads every box's cover and popup picture in the background, so hovering and opening are instant. Kept by the browser, so later visits only fetch new ones.
                        </div>
                        {options.preload && progress.total > 0 && (
                            <div className="opts-progress">
                                <div className="bar"><div style={{ width: `${((progress.done + progress.failed) / progress.total) * 100}%` }} /></div>
                                <span>
                                    {progress.done + progress.failed < progress.total
                                        ? `${progress.done + progress.failed} of ${progress.total} pictures`
                                        : `All ${progress.done} pictures ready`}
                                    {progress.failed ? ` · ${progress.failed} couldn't load` : ''}
                                </span>
                            </div>
                        )}
                    </fieldset>
                </div>
            )}
        </div>
    );
}

// The pulled-out game: the Game Details panel every page shares (src/common/game-details.jsx)
function InfoCard({ entry, onClose }) {
    if (!entry) return null;
    const { game, system, fullName } = entry;
    return (
        <GameDetailsPopup open={true} onClose={onClose} label={game.name}>
            {/* A removed game is gone from the shelf too, once the page has loaded again */}
            <GameDetails system={system} systemLabel={fullName} path={game.path} seed={game} onDeleted={() => window.location.reload()}
                actions={<button className="gd-btn" onClick={onClose} autoFocus>Put it back</button>} />
        </GameDetailsPopup>
    );
}
