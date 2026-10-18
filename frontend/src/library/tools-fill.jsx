// Tools: Fill the gaps. One system's games (or games picked in the Media viewer, from any
// systems) and what each is missing; for the ones picked,
// every source's version of each picture and detail side by side to choose from (the first
// in the source order chosen already), then the chosen ones put in (backend/routes/fill.py).
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define. This is its
// state and what it does; tools-fill-common.jsx has the kinds and helpers, and the steps are
// drawn by tools-fill-steps.jsx and tools-fill-choose.jsx, given `fx` (below).

// `options`, from elsewhere (the Media viewer, the background scrape): {games: [{system, path}] (picked,
// from any systems), kinds: [what to fill], replace, start (straight to choosing), prepared (looked up
// by the background scrape already), remake (made again)}, or {system, kinds} for one system
function FillGapsPanel({ initialSystem, systems, options, onClose, onChanged, showNotification }) {
    // Games handed over from elsewhere, until "Choose a system instead"
    const [handed, setHanded] = React.useState(() => (options && options.games && options.games.length ? options.games : null));
    const [step, setStep] = React.useState(0);
    const usable = (systems || []).filter(s => s.rom_count > 0);
    const [system, setSystem] = React.useState(() => (usable.find(s => s.name === ((options && options.system) || initialSystem)) || usable[0] || {}).name || '');
    // (opened before the systems had arrived, or from a link: the one being looked at, once there)
    const chosenSystem = useRef(false);
    useEffect(() => {
        if (chosenSystem.current) return;
        const wanted = usable.find(s => s.name === ((options && options.system) || initialSystem)) || (!system && usable[0]);
        if (wanted && wanted.name !== system) setSystem(wanted.name);
    }, [initialSystem, usable.length]);
    const [games, setGames] = React.useState(null);
    const [remembered, setRemembered] = React.useState({});
    const [show, setShow] = React.useState((options && options.show) || 'all');
    const [picked, setPicked] = React.useState({});
    // What's filled. Kinds handed over (from the Media viewer) are for this time only: what's
    // remembered in the browser is the choice made here
    const handedKinds = !!(options && options.kinds && options.kinds.length);
    const [fill, setFillState] = React.useState(() => {
        if (handedKinds) return Object.fromEntries([...FILL_MEDIA, ...Object.keys(FILL_FIELDS)].map(k => [k, options.kinds.includes(k)]));
        try { const saved = JSON.parse(localStorage.getItem(FILL_ON_KEY)); if (saved) return saved; } catch (e) {}
        return Object.fromEntries([...FILL_MEDIA, ...Object.keys(FILL_FIELDS)].map(k => [k, !['box3d', 'boxside', 'fanart', 'screenshottitle', 'manuals', 'videos', 'players', 'rating'].includes(k)]));
    });
    // (a choice remembered before Name could be filled has it on: a name is kept unless another is picked)
    useEffect(() => { if (fill.name === undefined) setFillState(prev => ({ ...prev, name: true })); }, []);
    const setFill = (change) => setFillState(prev => {
        const next = typeof change === 'function' ? change(prev) : change;
        try { localStorage.setItem(FILL_ON_KEY, JSON.stringify(next)); } catch (e) {}
        return next;
    });
    const [replace, setReplace] = React.useState(!!(options && options.replace));
    const [mode, setMode] = React.useState('review');
    // The sources, most trusted first: [{id, on}], remembered in this browser
    const [order, setOrder] = React.useState(() => {
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(FILL_ORDER_KEY)); } catch (e) {}
        const known = (saved || []).filter(s => SCRAPE_SOURCES.some(x => x.id === s.id));
        return [...known, ...SCRAPE_SOURCES.filter(x => !known.some(s => s.id === x.id)).map(x => ({ id: x.id, on: true }))];
    });
    useEffect(() => { try { localStorage.setItem(FILL_ORDER_KEY, JSON.stringify(order)); } catch (e) {} }, [order]);
    const [status, setStatus] = React.useState({});
    const [statusKnown, setStatusKnown] = React.useState(false);
    useEffect(() => {
        fetch(`${API_BASE}/api/scrape-sources`).then(r => r.json())
            .then(d => { if (d.success) setStatus(Object.fromEntries(d.sources.map(s => [s.id, s]))); }).catch(() => {})
            .finally(() => setStatusKnown(true));
    }, []);
    const sourceOn = (s) => s.on && (!status[s.id] || status[s.id].available);
    const activeOrder = order.filter(sourceOn);

    // Step 3: each game's look-up {source: {match, candidates}}, the choices, the game being decided
    const [looks, setLooks] = React.useState({});
    const [looking, setLooking] = React.useState(null); // {done, total}
    const [choice, setChoice] = React.useState({}); // "path|key" -> source id | 'keep' | 'skip'
    const [current, setCurrent] = React.useState(null);
    const [wrong, setWrong] = React.useState(null); // {path, source, query}
    const [zoom, setZoom] = React.useState(null); // {path, key, source}
    const [results, setResults] = React.useState(null);
    const [applying, setApplying] = React.useState(null);
    const stopRef = useRef(false);
    const [reload, setReload] = React.useState(0);
    const topRef = useRef(null);
    // Keys while choosing: ↑↓ (or J K) a row, 1–9 a candidate in it, ←→ (or P N) another game, A apply.
    // The rows and their candidates are the ones on the page, in order; the row is marked (fill-kb-row)
    const [kbRow, setKbRow] = React.useState(0);
    const keysRef = useRef(null);
    useEffect(() => { setKbRow(0); }, [current]);
    useEffect(() => {
        if (step !== 2) return;
        const rows = () => [...(topRef.current?.querySelectorAll('.fill-game [data-row]') || [])];
        rows().forEach((row, i) => row.classList.toggle('fill-kb-row', i === kbRow));
        const onKey = (e) => {
            if (e.ctrlKey || e.metaKey || e.altKey || zoom || (e.target.closest && e.target.closest('input, textarea, select, [contenteditable]'))) return;
            const keys = keysRef.current;
            const list = rows();
            const key = e.key.toLowerCase();
            if (key === 'arrowdown' || key === 'j') setKbRow(r => Math.min(r + 1, Math.max(0, list.length - 1)));
            else if (key === 'arrowup' || key === 'k') setKbRow(r => Math.max(r - 1, 0));
            else if (/^[1-9]$/.test(key)) {
                const pick = list[kbRow]?.querySelectorAll('button.fill-cand:not(:disabled), button.fill-variant')[Number(key) - 1];
                if (!pick) return;
                pick.click();
            } else if (key === 'arrowright' || key === 'n') keys?.next();
            else if (key === 'arrowleft' || key === 'p') keys?.previous();
            else if (key === 'a') keys?.apply();
            else return;
            e.preventDefault();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    });
    // (the marked row kept in sight as it moves; the first is where a game starts anyway)
    useEffect(() => {
        const row = kbRow > 0 && topRef.current?.querySelectorAll('.fill-game [data-row]')[kbRow];
        if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }, [kbRow]);
    // Another game being chosen: back to the top of it (the popup is what scrolls)
    useEffect(() => {
        let box = topRef.current && topRef.current.parentElement;
        while (box && box.scrollHeight <= box.clientHeight) box = box.parentElement;
        if (box) box.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }, [current, step]);

    useEffect(() => {
        const names = handed ? [...new Set(handed.map(h => h.system))] : system ? [system] : [];
        if (!names.length) return;
        setGames(null);
        const wanted = handed ? new Set(handed.map(h => `${h.system}|${fillRom(h.path)}`)) : null;
        Promise.all(names.map(name => fetch(`${API_BASE}/api/systems/${encodeURIComponent(name)}/games`).then(r => r.json())
            .then(d => (d.games || []).filter(g => g.rom_exists !== false && (!wanted || wanted.has(`${name}|${fillRom(g.path)}`)))
                .map(g => ({ ...g, _system: name, _systemName: (usable.find(s => s.name === name) || {}).full_name || name })))
            .catch(() => [])))
            .then(lists => {
                const list = lists.flat().sort((a, b) => a._systemName.localeCompare(b._systemName) || (a.name || a.path).localeCompare(b.name || b.path));
                setGames(list);
                // (handed-over games are all picked: they were picked there)
                setPicked(Object.fromEntries(list.map(g => [fillKey(g), wanted ? true : fillGaps(g, fill).length > 0])));
            });
        Promise.all(names.map(name => fetch(`${API_BASE}/api/fill/remembered?${new URLSearchParams({ system: name })}`).then(r => r.json())
            .then(d => Object.fromEntries(Object.entries(d.games || {}).map(([rom, sources]) => [`${name}|${rom}`, sources]))).catch(() => ({}))))
            .then(parts => setRemembered(Object.assign({}, ...parts)));
    }, [system, reload, handed]);
    const knownOn = (g) => remembered[`${g._system}|${fillRom(g.path)}`] || [];
    const systemsHanded = handed ? new Set(handed.map(h => h.system)).size : 0;

    const all = games || [];
    const chosenGames = all.filter(g => picked[fillKey(g)]);
    // What's looked at for a game: its gaps, and with "replace" what it has too
    const toFill = (g) => [...FILL_MEDIA, ...Object.keys(FILL_FIELDS)].filter(k => fill[k] && (!fillHas(g, k) || replace));
    const candidateOf = (g, k, sid) => {
        const c = looks[fillKey(g)]?.[sid]?.candidates;
        return c ? (FILL_FIELDS[k] ? c.fields?.[k] : c.media?.[k]) : undefined;
    };
    const matchOf = (g, sid) => looks[fillKey(g)]?.[sid]?.match;
    // Pictures made here from the game's own (FILL_MAKES): "game key|kind" ->
    // {status: working | ready | failed, src, error, and a Mix's job and index or a box's token}
    const [made, setMade] = React.useState({});
    const generate = async (g, k = 'mix') => {
        const key = `${fillKey(g)}|${k}`;
        setMade(prev => ({ ...prev, [key]: { status: 'working' } }));
        if (k !== 'mix') {
            try {
                const d = await postJson('/api/boxes/make', { system_name: g._system, rom_path: fillRom(g.path), kind: k });
                if (!d.success) throw new Error(d.error || "It couldn't be made");
                setMade(prev => ({ ...prev, [key]: { status: 'ready', token: d.token, src: `${API_BASE}${d.url}` } }));
            } catch (e) {
                setMade(prev => ({ ...prev, [key]: { status: 'failed', error: e.message } }));
            }
            return;
        }
        try {
            let d = await postJson('/api/mix/jobs', { games: [{ system: g._system, rom_path: fillRom(g.path) }] });
            if (!d.success) throw new Error(d.error || "The Mix couldn't be made");
            let job = d.job;
            for (let tries = 0; tries < 90 && ['pending', 'rendering'].includes(job.items[0].status); tries++) {
                await new Promise(r => setTimeout(r, 700));
                d = await (await fetch(`${API_BASE}/api/mix/jobs/${job.id}`)).json();
                if (!d.success) throw new Error(d.error || 'The preview went missing');
                job = d.job;
            }
            const item = job.items[0];
            if (item.status !== 'ready') throw new Error(item.error || item.reason || (item.status === 'ineligible' ? 'It has no screenshot or box to make one from' : 'It took too long'));
            setMade(prev => ({ ...prev, [key]: { status: 'ready', job: job.id, index: item.index, src: `${API_BASE}/api/mix/preview/${job.id}/${item.index}?r=${item.rev || 0}` } }));
        } catch (e) {
            setMade(prev => ({ ...prev, [key]: { status: 'failed', error: e.message } }));
        }
    };
    const madeFor = (g, k = 'mix') => made[`${fillKey(g)}|${k}`];
    // Found on the web by hand ("From the web"): "game key|kind" -> {status: working | ready | failed,
    // value (its address, or "made:<token>" for a picture pasted in), src, error}
    const [web, setWeb] = React.useState({});
    const webFor = (g, k) => web[`${fillKey(g)}|${k}`];
    const useWeb = (g, k, found) => {
        setWeb(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: found }));
        if (found.status === 'ready') setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'web' }));
    };
    const webAddress = (g, k, text) => {
        const url = String(text || '').trim();
        if (!/^https?:\/\/\S+$/i.test(url)) { useWeb(g, k, { status: 'failed', error: "That isn't a web address (https://…)" }); return; }
        useWeb(g, k, { status: 'ready', value: url, src: url });
    };
    const webPicture = async (g, k, file) => {
        if (!file || !/^image\//.test(file.type)) { useWeb(g, k, { status: 'failed', error: "That isn't a picture" }); return; }
        useWeb(g, k, { status: 'working' });
        try {
            const d = await fetch(`${API_BASE}/api/fill/picture`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file }).then(r => r.json());
            if (!d.success) throw new Error(d.error);
            useWeb(g, k, { status: 'ready', value: `made:${d.token}`, src: `${API_BASE}${d.url}` });
        } catch (e) { useWeb(g, k, { status: 'failed', error: e.message }); }
    };
    const offers = (g, k) => activeOrder.filter(s => candidateOf(g, k, s.id));
    // The default: keep what it has; for a gap, the first source in the order with one, unless its match is unsure
    // Made again (the Media viewer's "Make again"): a fresh one made for what RetroManager made before, and picked
    const remaking = (k) => !!(options && options.remake && (options.kinds || []).includes(k));
    const defaultFor = (g, k) => {
        if (fillHas(g, k)) return remaking(k) && madeFor(g, k)?.status === 'ready' ? 'generated' : 'keep';
        const first = offers(g, k).find(s => !['unsure', 'none'].includes(matchOf(g, s.id)?.confidence));
        if (first) return first.id;
        return FILL_MAKES[k] && madeFor(g, k)?.status === 'ready' ? 'generated' : 'skip';
    };
    const choiceOf = (g, k) => choice[`${fillKey(g)}|${k}`] ?? defaultFor(g, k);
    const changes = (g) => toFill(g).filter(k => {
        const c = choiceOf(g, k);
        return c === 'generated' ? madeFor(g, k)?.status === 'ready' : c === 'web' ? webFor(g, k)?.status === 'ready' : !['keep', 'skip'].includes(c) && candidateOf(g, k, c);
    });
    const sourceLabel = (id, k) => (id === 'generated' ? (FILL_MAKES[k] || FILL_MAKES.mix).label : id === 'web' ? 'the web' : scrapeSource(id).label);

    // Three games at a time (each asks its sources at once), in the list's order
    const lookUp = async (list) => {
        stopRef.current = false;
        setLooking({ done: 0, total: list.length });
        const sources = activeOrder.map(s => s.id);
        const found = {};
        let next = 0, done = 0;
        const worker = async () => {
            while (next < list.length && !stopRef.current) {
                const g = list[next++], key = fillKey(g);
                try {
                    // (from the background scrape: what it found, rather than asking the sources again)
                    const kept = options && options.prepared
                        ? await fetch(`${API_BASE}/api/fill/found?${new URLSearchParams({ system: g._system, rom: fillRom(g.path) })}`).then(r => r.json()).catch(() => null) : null;
                    found[key] = kept && kept.success ? kept.sources : ((await postJson('/api/fill/look', { system_name: g._system, rom_path: g.path, sources })).sources || {});
                } catch (e) {
                    found[key] = {};
                }
                setLooks(prev => ({ ...prev, [key]: found[key] }));
                setLooking({ done: ++done, total: list.length });
            }
        };
        await Promise.all([worker(), worker(), worker()]);
        setLooking(null);
        return found;
    };
    // Switched to everything ticked while choosing: the picked games with nothing missing are looked up too
    const showEverything = (on) => {
        setReplace(on);
        if (on && step === 2 && !looking) {
            const more = chosenGames.filter(g => !looks[fillKey(g)]);
            if (more.length) lookUp(more);
        }
    };

    const start = async () => {
        const list = chosenGames.filter(g => toFill(g).length);
        setLooks({});
        setChoice({});
        setResults(null);
        setCurrent(list[0] ? fillKey(list[0]) : null);
        setStep(2);
        await lookUp(list);
        if (mode === 'auto') apply(list);
    };

    // A Mix, 3D box or spine no source has, for a game missing one: made, one at a time (the game
    // on screen first), and picked, so Apply does the same whether a game was looked at or not.
    // (a box or spine only for a game with a cover to make it from)
    const needsMaking = (g, k) => looks[fillKey(g)] && !madeFor(g, k) && toFill(g).includes(k)
        && (remaking(k) || (!fillHas(g, k) && !offers(g, k).length)) && (k === 'mix' || fillHas(g, 'box2d'));
    const firstToMake = (g) => Object.keys(FILL_MAKES).find(k => needsMaking(g, k));
    const toMake = step === 2 ? chosenGames.reduce((n, g) => n + Object.keys(FILL_MAKES).filter(k => needsMaking(g, k) || madeFor(g, k)?.status === 'working').length, 0) : 0;
    useEffect(() => {
        if (step !== 2 || Object.values(made).some(m => m.status === 'working')) return;
        const onScreen = all.find(x => fillKey(x) === current);
        const next = onScreen && firstToMake(onScreen) ? onScreen : chosenGames.find(firstToMake);
        if (next) generate(next, firstToMake(next));
    }, [step, current, looks, made]);

    // Handed over to start straight away (the Media viewer's "Fill picked"): once the games and sources are known
    const startedRef = useRef(false);
    useEffect(() => {
        if (!options || !options.start || startedRef.current || !games || !statusKnown) return;
        startedRef.current = true;
        if (games.length) start();
    }, [games, statusKnown]);

    // A source being searched again ("wrong game?"): {key, source}, for the button to show it
    const [researching, setResearching] = React.useState(null);
    const researched = async (g, source, body) => {
        const gk = fillKey(g);
        setResearching({ key: gk, source });
        try {
            const d = await postJson('/api/fill/look', { system_name: g._system, rom_path: g.path, sources: [source], rematch: { source, ...body } });
            if (d.sources?.[source]) setLooks(prev => ({ ...prev, [gk]: { ...prev[gk], [source]: d.sources[source] } }));
            // (the choices made from that source go back to the defaults)
            setChoice(prev => Object.fromEntries(Object.entries(prev).filter(([key, v]) => !(key.startsWith(`${gk}|`) && v === source))));
        } catch (e) { showNotification(e.message, 'error'); }
        finally { setResearching(null); }
    };

    const apply = async (list = chosenGames.filter(g => toFill(g).length)) => {
        setApplying({ done: 0, total: list.length });
        for (const name of new Set(list.map(g => g._system))) {
            try { await postJson('/api/backup_gamelist', { system: name }); } catch (e) {}
        }
        const out = [];
        for (let i = 0; i < list.length; i++) {
            const g = list[i];
            const pictures = {}, fields = {}, from = {};
            for (const k of toFill(g)) {
                const c = choiceOf(g, k);
                if (['keep', 'skip'].includes(c)) continue;
                if (c === 'web') {
                    const found = webFor(g, k);
                    if (found?.status === 'ready') { pictures[k] = found.value; from[k] = 'web'; }
                    continue;
                }
                if (c === 'generated' && k !== 'mix') {
                    const box = madeFor(g, k);
                    if (box?.status === 'ready') { pictures[k] = `made:${box.token}`; from[k] = 'generated'; }
                    continue;
                }
                const value = candidateOf(g, k, c);
                if (value === undefined) continue;
                (FILL_FIELDS[k] ? fields : pictures)[k] = value;
                from[k] = c;
            }
            const remember = Object.fromEntries(Object.entries(looks[fillKey(g)] || {}).map(([sid, l]) => [sid, l.match]).filter(([, m]) => m && m.id && !m.remembered));
            let d = { success: true, downloaded: [], filled: [], errors: [] };
            if (Object.keys(pictures).length || Object.keys(fields).length || Object.keys(remember).length) {
                try { d = await postJson('/api/fill/apply', { system_name: g._system, rom_path: g.path, pictures, fields, remember }); }
                catch (e) { d = { success: false, error: e.message, downloaded: [], filled: [], errors: [] }; }
            }
            const generated = toFill(g).includes('mix') && choiceOf(g, 'mix') === 'generated' && madeFor(g)?.status === 'ready' ? madeFor(g) : null;
            if (generated) {
                try {
                    const c = await postJson(`/api/mix/jobs/${generated.job}/commit`, { approve: [generated.index], overwrite: true });
                    const result = (c.results || [])[0] || {};
                    if (result.status === 'committed') {
                        d = { ...d, downloaded: [...(d.downloaded || []), 'mix'], replaced: [...(d.replaced || []), ...(result.replaced ? ['mix'] : [])] };
                        from.mix = 'generated';
                    } else {
                        d = { ...d, errors: [...(d.errors || []), `mix: ${c.error || result.error || "the generated one couldn't be put in"}`] };
                    }
                } catch (e) { d = { ...d, errors: [...(d.errors || []), `mix: ${e.message}`] }; }
            }
            out.push({ game: g, from, ...d });
            setApplying({ done: i + 1, total: list.length });
        }
        setApplying(null);
        setResults(out);
        setStep(3);
        // (the games and what's remembered, as they are now, for going back to them)
        setReload(n => n + 1);
        if (typeof announceGameChange === 'function') announceGameChange();
        onChanged && onChanged();
    };

    // ---- Drawing (tools-fill-steps.jsx, tools-fill-choose.jsx), given what they use of the above ----
    const stepNames = ['Games', 'What to fill', 'Choose', 'Done'];
    const fx = {
        activeOrder, all, apply, applying, candidateOf, changes, choice, choiceOf, chosenGames, chosenSystem,
        current, defaultFor, fill, games, generate, handed, keysRef, knownOn, looking, looks, made, madeFor,
        matchOf, mode, offers, onClose, options, order, picked, remembered, replace, researched, researching,
        results, setChoice, setCurrent, setFill, setHanded, setMode, setOrder, setPicked, setReload, setReplace,
        setShow, setStep, setSystem, setWeb, setWrong, setZoom, show, showEverything, sourceLabel, sourceOn,
        start, status, step, stopRef, system, systems, systemsHanded, toFill, toMake, usable, useWeb, web,
        webAddress, webFor, webPicture, wrong, zoom
    };
    const body = [FillGamesStep, FillWhatStep, FillChooseStep, FillDoneStep][step];
    const zoomed = zoom ? <FillZoom fx={fx} /> : null;
    useEffect(() => {
        if (!zoom) return;
        const key = (e) => { if (e.key === 'Escape') { e.stopPropagation(); setZoom(null); } };
        window.addEventListener('keydown', key, true);
        return () => window.removeEventListener('keydown', key, true);
    }, [zoom]);

    const ledes = [
        'Every game of one system, with what each is missing. Pick the games, then say what to fill: gaps only, or new pictures and text for what they have too.',
        'Tick what to fill, put the sources in the order you trust them, and choose whether to see the candidates first.',
        "Each gap shows every source's version beside what the game has now. The first in your order is picked already: tap another to use that instead.",
        'Filled, and where from. What no source had is listed at the bottom, to look for by hand.',
    ];
    const busy = !!looking || !!applying;
    return (
        <Modal open={true} onClose={busy ? () => {} : onClose}>
            <div className="fill" ref={topRef}>
                <h2 style={{marginBottom: 4}}>Fill the gaps</h2>
                <p className="fill-lede">{ledes[step]}</p>
                <nav className="fill-steps" aria-label="Steps">{stepNames.map((n, i) => (
                    <React.Fragment key={n}>
                        {i > 0 && <span className="fill-arrow" aria-hidden="true">→</span>}
                        <button aria-current={i === step ? 'step' : undefined} className={`fill-step ${i === step ? 'on' : i < step ? 'done' : ''}`}
                            disabled={busy || i > step || (i === 3 && !results)} onClick={() => setStep(i)}>
                            {i < step ? '✓ ' : `${i + 1}. `}{n}</button>
                    </React.Fragment>))}</nav>
                {React.createElement(body, { fx })}
            </div>
            {zoomed}
        </Modal>
    );
}
