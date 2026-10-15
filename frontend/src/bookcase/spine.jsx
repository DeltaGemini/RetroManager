// One box on a shelf, the shelf row it stands in, and the label under a box.
// Part of the Bookcase page (shelf.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Cover shapes (width / height) learned from the loaded images
const coverAspects = {};

function Spine({ game, box, dimmed, hovered, out, returning, onHover, onUnhover, onPull, onKeyNav, onReturned, registerRef }) {
    const spineWidth = Math.max(MIN_SPINE_PX, Math.round(box.d * PX_PER_MM));
    const height = Math.round(box.h * PX_PER_MM);
    const title = cleanTitle(game.name);
    const [aspect, setAspect] = useState(() => game.box2d_ratio || coverAspects[game.box2d]);
    const front = pic(game, 'box2d', 480);
    // Facing you, the box is as wide as its cover (the system's box shape until it loads)
    const width = hovered && front ? Math.round(height * (aspect || box.w / box.h)) : spineWidth;

    const classes = ['spine', hovered && 'hovered', !front && 'no-front', dimmed && 'dimmed', out && 'out', returning && 'returning'].filter(Boolean).join(' ');
    return (
        <div
            ref={registerRef}
            className={classes}
            style={{ width, height }}
            tabIndex={0}
            role="button"
            aria-label={`${title}${game.year ? `, ${game.year}` : ''}`}
            onFocus={(e) => onHover(game, e.currentTarget)}
            onBlur={onUnhover}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPull(game, e.currentTarget); }
                else onKeyNav(e);
            }}
            onAnimationEnd={(e) => { if (e.animationName === 'spine-return') onReturned(); }}
        >
            {game.boxside ? (
                <img className="spine-art" src={pic(game, 'boxside', 320, true)} alt="" loading="lazy" decoding="async" draggable={false} />
            ) : (
                <>
                    {game.box2d && <img className="spine-cover" src={pic(game, 'box2d', 160)} alt="" loading="lazy" decoding="async" draggable={false} />}
                    <div className="spine-title">{title}</div>
                </>
            )}
            {front && hovered && (
                <img className="spine-front" src={front} alt="" decoding="async" draggable={false}
                    onLoad={(e) => {
                        const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
                        // Only when the NAS didn't know the shape, so the box doesn't resize twice
                        if (w && h && !game.box2d_ratio) { coverAspects[game.box2d] = w / h; setAspect(w / h); }
                    }} />
            )}
        </div>
    );
}

// A shelf's row of boxes. It scrolls sideways (touch, trackpad, Shift+wheel,
// arrow keys) with no visible scrollbar; shading and a ‹ › button show at
// an edge where more boxes are out of sight.
//
// Which box the mouse is on comes from its position as if every box were
// closed: `slots` gives each box's closed spine size ({width, height} in
// px), and the box is the one whose slot (spine + gap) holds x.
// Opening a box to show its cover then can't change which box you're on,
// so moving along a shelf never flickers, and one spine-width to the right
// is always the next box. onPoint(index | -1, event), onPick(index).
function ShelfScroller({ minHeight, slots, onPoint, onPick, children }) {
    const ref = useRef(null);
    // Where each closed box starts; one more entry marks the end of the last
    const starts = useMemo(() => {
        const at = [0];
        slots.forEach(slot => at.push(at[at.length - 1] + slot.width + SPINE_GAP));
        return at;
    }, [slots]);
    const [edges, setEdges] = useState({ left: false, right: false });
    const measure = useCallback(() => {
        const el = ref.current;
        if (!el) return;
        const left = el.scrollLeft > 4;
        const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
        setEdges(e => (e.left === left && e.right === right ? e : { left, right }));
    }, []);
    useEffect(() => {
        measure();
        const el = ref.current;
        const ro = new ResizeObserver(measure);
        ro.observe(el);
        // Boxes widen on hover, which changes how far the shelf reaches
        const mo = new MutationObserver(measure);
        mo.observe(el, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
        return () => { ro.disconnect(); mo.disconnect(); };
    }, [measure]);
    const [pointing, setPointing] = useState(false);
    const slotAt = (e) => {
        const el = ref.current;
        const r = el.getBoundingClientRect();
        const pad = parseFloat(getComputedStyle(el).paddingLeft) || 0;
        const x = e.clientX - r.left + el.scrollLeft - pad;
        if (x < 0 || x >= starts[slots.length]) return -1;
        let low = 0, high = slots.length - 1;
        while (low < high) {
            const mid = (low + high + 1) >> 1;
            if (starts[mid] <= x) low = mid; else high = mid - 1;
        }
        // Only over the box: not the empty space above it
        return e.clientY >= r.bottom - (slots[low].height + 12) ? low : -1;
    };
    const nudge = (dir) => {
        const el = ref.current;
        el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: reducedMotion() ? 'auto' : 'smooth' });
    };
    return (
        <div className="shelf-frame">
            <div ref={ref} className={`shelf-row${pointing ? ' pointing' : ''}`} style={{ minHeight }} onScroll={measure}
                onMouseMove={e => { const i = slotAt(e); setPointing(i >= 0); onPoint(i); }}
                onMouseLeave={() => { setPointing(false); onPoint(-1); }}
                onClick={e => { const i = slotAt(e); if (i >= 0) onPick(i); }}>{children}</div>
            <div className={`shelf-fade left${edges.left ? ' show' : ''}`} aria-hidden="true" />
            <div className={`shelf-fade right${edges.right ? ' show' : ''}`} aria-hidden="true" />
            <button className={`shelf-more left${edges.left ? ' show' : ''}`} onClick={() => nudge(-1)}
                aria-label="Scroll this shelf left" tabIndex={edges.left ? 0 : -1} aria-hidden={!edges.left}>‹</button>
            <button className={`shelf-more right${edges.right ? ' show' : ''}`} onClick={() => nudge(1)}
                aria-label="Scroll this shelf right" tabIndex={edges.right ? 0 : -1} aria-hidden={!edges.right}>›</button>
        </div>
    );
}

// The hovered game's name, under its box. Follows the box while it widens
// and while the page or shelf scrolls.
function HoverLabel({ el, game }) {
    const [pos, setPos] = useState(null);
    useEffect(() => {
        if (!el) return;
        let frame, until = performance.now() + 400;
        const place = () => {
            const r = el.getBoundingClientRect();
            setPos({ left: r.left + r.width / 2, top: r.bottom + 8 });
        };
        const follow = () => { place(); if (performance.now() < until) frame = requestAnimationFrame(follow); };
        follow();
        const onScroll = () => { until = performance.now() + 50; cancelAnimationFrame(frame); follow(); };
        window.addEventListener('scroll', onScroll, true);
        window.addEventListener('resize', onScroll);
        return () => {
            cancelAnimationFrame(frame);
            window.removeEventListener('scroll', onScroll, true);
            window.removeEventListener('resize', onScroll);
        };
    }, [el]);
    if (!el || !pos) return null;
    return (
        <div className="hover-label" role="tooltip" style={{ left: pos.left, top: pos.top }}>
            {cleanTitle(game.name)}{game.year && <span className="year">{game.year}</span>}
        </div>
    );
}
