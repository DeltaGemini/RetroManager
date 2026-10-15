// Touch controls for the play page, drawn from RetroArch overlay files
// (frontend/overlays/*.cfg with the images in frontend/overlays/images/), so a
// layout made for RetroArch on a phone works here as it is. layouts.json says
// which layouts there are and which systems each is the usual one for.
//
// What's read from a .cfg: each overlay's name and its buttons
//   overlayN_descM = "input,x,y,shape,rx,ry"   centre and half-size, 0-1 of the screen
//   ..._overlay (image)  ..._next_target  ..._range_mod  ..._saturate_pct
// Inputs: the pad's buttons (a b x y l r start select up down left right, joined
// with | for diagonals; r_x_plus and the like for the right stick's directions),
// analog_left (a thumbstick), overlay_next (switch to
// another overlay: analogue/digital, left- or right-handed), and RetroArch's
// menu_toggle, toggle_fast_forward, save_state and exit_emulator.
// The overlay named "landscape..." or "portrait..." is used to suit the screen.
(function () {
    // RetroPad button -> EmulatorJS input number
    const BUTTONS = { b: 0, y: 1, select: 2, start: 3, up: 4, down: 5, left: 6, right: 7, a: 8, x: 9, l: 10, r: 11, l2: 12, r2: 13, l3: 14, r3: 15 };
    const STICK = { right: 16, left: 17, down: 18, up: 19 };   // the left stick's four directions
    // The right stick's directions as buttons (an N64's C buttons): held, they're a full tilt
    Object.assign(BUTTONS, { r_x_plus: 20, r_x_minus: 21, r_y_plus: 22, r_y_minus: 23 });
    const FULL_TILT = new Set([20, 21, 22, 23]);
    const ACTIONS = ['overlay_next', 'menu_toggle', 'toggle_fast_forward', 'save_state', 'exit_emulator'];

    function parse(text) {
        const values = {};
        text.split(/\r?\n/).forEach(line => {
            const m = line.match(/^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/);
            if (m) values[m[1]] = m[2].replace(/^"(.*)"$/, '$1');
        });
        const overlays = [];
        for (let i = 0; i < Number(values.overlays || 0); i++) {
            const at = `overlay${i}_`;
            const overlay = { name: values[`${at}name`] || `overlay${i}`, rangeMod: Number(values[`${at}range_mod`]) || 1, descs: [] };
            for (let d = 0; d < Number(values[`${at}descs`] || 0); d++) {
                const key = `${at}desc${d}`;
                const parts = (values[key] || '').split(',').map(s => s.trim());
                if (parts.length < 6) continue;
                const [input, x, y, shape, rx, ry] = parts;
                overlay.descs.push({
                    input, x: Number(x), y: Number(y), shape, rx: Number(rx), ry: Number(ry),
                    image: values[`${key}_overlay`] || null,
                    next: values[`${key}_next_target`] || null,
                    rangeMod: Number(values[`${key}_range_mod`]) || overlay.rangeMod,
                    saturate: Number(values[`${key}_saturate_pct`]) || 1,
                });
            }
            overlays.push(overlay);
        }
        return overlays;
    }

    // The parts of a portrait screen the controls leave free, top to bottom, as
    // [start, end] (0-1). The game goes in the first; a second one below the
    // controls is where a two-screen system's lower screen belongs.
    function freeBands(overlay) {
        const taken = overlay.descs.filter(d => d.rx > 0 && d.ry > 0 && (d.image || BUTTONS[d.input.split('|')[0]] !== undefined))
            .map(d => [d.y - d.ry, d.y + d.ry]).sort((a, b) => a[0] - b[0]);
        const bands = [];
        let edge = 0;
        taken.forEach(([top, bottom]) => {
            if (top - edge >= 0.15) bands.push([edge, top]);
            edge = Math.max(edge, bottom);
        });
        if (1 - edge >= 0.15) bands.push([edge, 1]);
        return bands;
    }

    async function load(layout) {
        const text = await (await fetch(`/overlays/${layout.file}`)).text();
        return { ...layout, overlays: parse(text) };
    }
    async function layouts() {
        try { return (await (await fetch('/overlays/layouts.json')).json()).layouts || []; } catch (e) { return []; }
    }

    // Draws a layout over `stage` and feeds the emulator.
    //   stage      the element the game fills (the controls cover it)
    //   game       the element EmulatorJS draws in (moved to the part of a portrait screen the controls leave free)
    //   press(input, value)   sends an EmulatorJS input (value 0/1, or 0-0x7fff for the stick)
    //   actions    { menu, fastForward, saveState, exit }
    function attach({ stage, game, layout, press, actions }) {
        const root = document.createElement('div');
        root.className = 'rm-pad';
        stage.appendChild(root);
        let variant = '';          // "", "-analog", "-left", "-left-analog"...: what follows landscape/portrait in the overlay's name
        let overlay = null;
        let controls = [];         // [{ desc, el, knob }]
        const touches = new Map(); // touch id -> { x, y, stick: control or null, spent }
        let held = {};             // input number -> value last sent

        const portrait = () => stage.clientHeight > stage.clientWidth;
        const named = (name) => layout.overlays.find(o => o.name === name);
        const pick = () => {
            const side = portrait() ? 'portrait' : 'landscape';
            // A left- or right-handed variant only exists upright: lying down falls back to the plain one
            return named(side + variant) || named(side + variant.replace(/-(left|right)/, '')) || named(side) || layout.overlays[0];
        };

        const placeGame = () => {
            game.style.cssText = '';
            if (!overlay || !portrait()) return;
            const bands = freeBands(overlay);
            if (!bands.length || bands[0][0] > 0.05) return;
            const width = stage.clientWidth, height = stage.clientHeight;
            let bottom = bands[0][1] * height;
            // Two free bands and a two-screen system: the picture spans both, with the
            // gap between the screens (set when the game started) falling behind the controls
            if (layout.screenGap && bands.length > 1) bottom = Math.min(bands[1][1] * height, width * 0.75 * 2 + layout.screenGap * (width / 256));
            game.style.cssText = `position:absolute;left:0;top:0;width:100%;height:${Math.round(bottom)}px;`;
        };

        const send = (input, value) => {
            if ((held[input] || 0) === value) return;
            held[input] = value;
            press(input, value);
        };
        const releaseAll = () => {
            Object.keys(held).forEach(input => send(Number(input), 0));
            controls.forEach(c => { c.el.classList.remove('down'); if (c.knob) c.knob.style.transform = ''; });
        };

        const build = () => {
            releaseAll();
            touches.clear();
            overlay = pick();
            root.innerHTML = '';
            controls = [];
            if (!overlay) return;
            overlay.descs.forEach(desc => {
                if (!(desc.rx > 0 && desc.ry > 0)) return;   // RetroArch's invisible "rotate" hot spots
                const el = document.createElement('div');
                el.className = `rm-pad-ctl${desc.input === 'null' ? ' still' : ''}${desc.shape === 'radial' ? ' round' : ''}`;
                el.style.cssText = `left:${(desc.x - desc.rx) * 100}%;top:${(desc.y - desc.ry) * 100}%;width:${desc.rx * 200}%;height:${desc.ry * 200}%;`;
                let knob = null;
                if (desc.image) {
                    knob = el.appendChild(Object.assign(document.createElement('img'), { src: `/overlays/images/${encodeURIComponent(desc.image)}`, alt: '', draggable: false }));
                }
                root.appendChild(el);
                controls.push({ desc, el, knob: desc.input === 'analog_left' ? knob : null });
            });
            placeGame();
            window.dispatchEvent(new Event('resize'));   // EmulatorJS fits the picture to its element again
        };

        // Is the point (0-1 of the stage) on this control? The touch area is the
        // drawn one made bigger by range_mod, as in RetroArch
        const hit = (desc, x, y) => {
            const dx = (x - desc.x) / (desc.rx * desc.rangeMod), dy = (y - desc.y) / (desc.ry * desc.rangeMod);
            return desc.shape === 'radial' ? dx * dx + dy * dy <= 1 : Math.abs(dx) <= 1 && Math.abs(dy) <= 1;
        };
        // Of the controls under a point, the one whose centre is nearest (touch areas overlap)
        const under = (x, y, wanted) => controls.filter(c => wanted(c.desc) && hit(c.desc, x, y))
            .sort((a, b) => Math.hypot(x - a.desc.x, y - a.desc.y) - Math.hypot(x - b.desc.x, y - b.desc.y))[0];

        const act = (desc) => {
            if (desc.input === 'overlay_next') {
                const target = desc.next || '';
                variant = target.replace(/^(landscape|portrait)/, '');
                build();
            } else if (desc.input === 'menu_toggle') actions.menu();
            else if (desc.input === 'toggle_fast_forward') actions.fastForward();
            else if (desc.input === 'save_state') actions.saveState();
            else if (desc.input === 'exit_emulator') actions.exit();
        };

        const refresh = () => {
            const want = {};
            const lit = new Set();
            touches.forEach(touch => {
                if (touch.spent) return;
                if (touch.stick) {
                    const d = touch.stick.desc, box = root.getBoundingClientRect();
                    // Full tilt at saturate_pct of the stick's reach
                    const reachX = d.rx * d.rangeMod * d.saturate, reachY = d.ry * d.rangeMod * d.saturate;
                    let ax = (touch.x - d.x) / reachX, ay = (touch.y - d.y) / reachY;
                    const length = Math.hypot(ax, ay);
                    if (length > 1) { ax /= length; ay /= length; }
                    const full = 0x7fff;
                    want[STICK.right] = ax > 0 ? Math.round(ax * full) : 0;
                    want[STICK.left] = ax < 0 ? Math.round(-ax * full) : 0;
                    want[STICK.down] = ay > 0 ? Math.round(ay * full) : 0;
                    want[STICK.up] = ay < 0 ? Math.round(-ay * full) : 0;
                    // On a system with no stick of its own, it works the D-pad too
                    if (layout.stick_is_dpad !== false) {
                        if (ax > 0.4) want[BUTTONS.right] = 1; else if (ax < -0.4) want[BUTTONS.left] = 1;
                        if (ay > 0.4) want[BUTTONS.down] = 1; else if (ay < -0.4) want[BUTTONS.up] = 1;
                    }
                    if (touch.stick.knob) touch.stick.knob.style.transform = `translate(${ax * d.rx * box.width * 0.6}px, ${ay * d.ry * box.height * 0.6}px)`;
                    lit.add(touch.stick);
                    return;
                }
                const control = under(touch.x, touch.y, d => d.input.split('|').every(name => BUTTONS[name] !== undefined));
                if (!control) return;
                control.desc.input.split('|').forEach(name => { want[BUTTONS[name]] = FULL_TILT.has(BUTTONS[name]) ? 0x7fff : 1; });
                lit.add(control);
            });
            Object.keys({ ...held, ...want }).forEach(input => send(Number(input), want[input] || 0));
            controls.forEach(c => {
                c.el.classList.toggle('down', lit.has(c));
                if (c.knob && !lit.has(c)) c.knob.style.transform = '';
            });
        };

        const point = (clientX, clientY) => {
            const box = root.getBoundingClientRect();
            return { x: (clientX - box.left) / box.width, y: (clientY - box.top) / box.height };
        };
        const begin = (id, clientX, clientY) => {
            const { x, y } = point(clientX, clientY);
            const action = under(x, y, d => ACTIONS.includes(d.input));
            const button = under(x, y, d => d.input.split('|').every(name => BUTTONS[name] !== undefined));
            const stick = under(x, y, d => d.input === 'analog_left');
            // A small button drawn over a big one's touch area wins if it's the nearer
            const nearest = [action, button, stick].filter(Boolean)
                .sort((a, b) => Math.hypot(x - a.desc.x, y - a.desc.y) - Math.hypot(x - b.desc.x, y - b.desc.y))[0];
            if (!nearest) return false;
            if (nearest === action) { touches.set(id, { x, y, spent: true }); act(action.desc); return true; }
            touches.set(id, { x, y, stick: nearest === stick ? stick : null });
            refresh();
            return true;
        };
        const move = (id, clientX, clientY) => {
            const touch = touches.get(id);
            if (!touch) return;
            Object.assign(touch, point(clientX, clientY));
            refresh();
        };
        const end = (id) => { if (touches.delete(id)) refresh(); };

        // Touches that start on a control are the pad's (and may slide from one
        // button to the next); any others go through to the game (a DS's touch screen)
        const onTouchStart = (e) => {
            if (!e.target.closest('.rm-pad-ctl')) return;
            let taken = false;
            [...e.changedTouches].forEach(t => { if (begin(t.identifier, t.clientX, t.clientY)) taken = true; });
            if (taken) e.preventDefault();
        };
        const onTouchMove = (e) => {
            let ours = false;
            [...e.changedTouches].forEach(t => { if (touches.has(t.identifier)) { ours = true; move(t.identifier, t.clientX, t.clientY); } });
            if (ours) e.preventDefault();
        };
        const onTouchEnd = (e) => { [...e.changedTouches].forEach(t => end(t.identifier)); };
        // A mouse works too, for trying a layout out on a computer
        const onMouseDown = (e) => { if (e.button === 0 && e.target.closest('.rm-pad-ctl') && begin('mouse', e.clientX, e.clientY)) e.preventDefault(); };
        const onMouseMove = (e) => move('mouse', e.clientX, e.clientY);
        const onMouseUp = () => end('mouse');
        let resizeTimer = null;
        const onResize = (e) => {
            if (!e.isTrusted) return;   // not the one build() sends for EmulatorJS
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => { if (pick() !== overlay) build(); else placeGame(); }, 120);
        };

        root.addEventListener('touchstart', onTouchStart, { passive: false });
        window.addEventListener('touchmove', onTouchMove, { passive: false });
        window.addEventListener('touchend', onTouchEnd);
        window.addEventListener('touchcancel', onTouchEnd);
        root.addEventListener('mousedown', onMouseDown);
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        window.addEventListener('resize', onResize);
        root.addEventListener('contextmenu', e => e.preventDefault());
        build();

        return {
            // For tests and the page: which overlay is showing, and what's held down
            state: () => ({ overlay: overlay && overlay.name, held: Object.keys(held).filter(k => held[k]).map(Number) }),
            remove: () => {
                releaseAll();
                window.removeEventListener('touchmove', onTouchMove);
                window.removeEventListener('touchend', onTouchEnd);
                window.removeEventListener('touchcancel', onTouchEnd);
                window.removeEventListener('mousemove', onMouseMove);
                window.removeEventListener('mouseup', onMouseUp);
                window.removeEventListener('resize', onResize);
                root.remove();
                game.style.cssText = '';
            },
        };
    }

    window.RMOverlay = { layouts, load, attach, parse, freeBands };
})();
