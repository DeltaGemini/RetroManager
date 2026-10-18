// Fill the gaps (tools-fill.jsx): its Games, What to fill and Done steps, and the enlarged view.
// Each takes `fx`, the panel's state and what it does. Part of the library page (index.html).

// Step 1: the games, what each is missing, and which to fill
function FillGamesStep({ fx }) {
    const { all, chosenGames, chosenSystem, fill, games, handed, knownOn, options, picked, setHanded, setPicked,
        setShow, setStep, setSystem, show, step, system, systems, systemsHanded, usable } = fx;
    const field = FILL_FIELD_STYLE, chip = fillChip, confChip = fillConfChip;
    const shown = all.filter(g => show === 'all' || (show === 'gaps' ? fillGaps(g, fill).length : !fillGaps(g, fill).length));
    const withGaps = all.filter(g => fillGaps(g, fill).length).length;
    const counted = [...FILL_MEDIA, ...Object.keys(FILL_FIELDS)].filter(k => fill[k]);
return (
        <>
            <div className="fill-bar">
                {handed ? (
                    <>
                        <span>{options && options.from === 'viewer' ? 'From the Media viewer: ' : options && options.from === 'background' ? 'Found by the background scrape: ' : 'Picked: '}<b>{all.length || handed.length} game{(all.length || handed.length) === 1 ? '' : 's'}</b>{systemsHanded > 1 ? ` in ${systemsHanded} systems` : ''}</span>
                        <button className="btn btn-secondary btn-small" onClick={() => { chosenSystem.current = true; setSystem(handed[0].system); setHanded(null); }}>Choose a system instead</button>
                    </>
                ) : (
                    <>
                        <label className="muted" htmlFor="fill-system">System</label>
                        <select id="fill-system" style={field} value={system} onChange={e => { chosenSystem.current = true; setSystem(e.target.value); }}>
                            {usable.map(s => <option key={s.name} value={s.name}>{s.full_name || s.name}</option>)}
                        </select>
                    </>
                )}
                <label className="muted" htmlFor="fill-show">Show</label>
                <select id="fill-show" style={field} value={show} onChange={e => setShow(e.target.value)}>
                    <option value="all">All {all.length} games</option>
                    <option value="gaps">The {withGaps} with gaps</option>
                    <option value="complete">The {all.length - withGaps} complete</option>
                </select>
            </div>
            <p className="fill-note" style={{margin: '0 0 12px'}}>Missing means without: {counted.map(fillLabel).join(', ') || 'nothing'} (what's filled, chosen in the next step).
                {!handed && FILL_PICTURES.some(k => fill[k]) && <>{' '}<button className="fill-link" onClick={() => window.dispatchEvent(new CustomEvent('retromanager:open-tool',
                    { detail: { tool: 'viewer', options: { system, kind: FILL_PICTURES.find(k => fill[k]), show: 'missing' } } }))}>See them as pictures</button></>}</p>
            {!games ? <div className="muted">Loading the games…</div> : (
                <div className="fill-table-wrap"><table className="fill-table">
                    <thead><tr>
                        <th><input type="checkbox" aria-label="Pick all shown" checked={shown.length > 0 && shown.every(g => picked[fillKey(g)])}
                            onChange={e => setPicked(prev => ({ ...prev, ...Object.fromEntries(shown.map(g => [fillKey(g), e.target.checked])) }))} /></th>
                        <th></th><th>Game</th><th>Missing</th><th>Matched before</th>
                    </tr></thead>
                    <tbody>{shown.map((g, row) => {
                        const gaps = fillGaps(g, fill);
                        const known = knownOn(g);
                        const heading = systemsHanded > 1 && (row === 0 || shown[row - 1]._system !== g._system);
                        return (
                            <React.Fragment key={fillKey(g)}>
                            {heading && <tr className="fill-group"><td colSpan={5}>{g._systemName}</td></tr>}
                            <tr>
                                <td><input type="checkbox" aria-label={`Pick ${g.name}`} checked={!!picked[fillKey(g)]} onChange={e => setPicked(prev => ({ ...prev, [fillKey(g)]: e.target.checked }))} /></td>
                                <td><div className="fill-thumb">{g.box2d && <img alt="" loading="lazy" src={thumbUrl(160, g.box2d)} />}</div></td>
                                <td><b>{splitGameName(g.name || g.path).title}</b> <span className="muted">{(g.releasedate || '').slice(0, 4)}</span></td>
                                <td><div className="fill-chips">{gaps.length ? gaps.map(k => chip(k)) : <span className="fill-known">✓ Complete</span>}</div></td>
                                <td>{known.length ? <span className="fill-known" title={known.map(id => scrapeSource(id).label).join(', ')}>✓ on {known.length} source{known.length === 1 ? '' : 's'}</span> : <span className="muted" style={{fontSize: 11}}>not yet</span>}</td>
                            </tr>
                            </React.Fragment>
                        );
                    })}</tbody>
                </table></div>
            )}
            <div className="fill-bar fill-foot"><span className="grow muted">{chosenGames.length} of {all.length} games picked</span>
                <button className="btn btn-primary" disabled={!chosenGames.length} onClick={() => setStep(1)}>Next: what to fill</button></div>
        </>
);
}

// Step 2: what to fill, the sources' order, and whether to choose
function FillWhatStep({ fx }) {
    const { activeOrder, chosenGames, fill, games, knownOn, made, mode, order, picked, replace, setFill,
        setMode, setOrder, setReplace, setStep, sourceOn, start, status, toFill } = fx;
    const count = (k) => chosenGames.filter(g => !fillHas(g, k)).length;
    const nothing = chosenGames.filter(g => !toFill(g).length).length;
    const before = chosenGames.filter(g => knownOn(g).length).length;
    const move = (i, by) => setOrder(prev => { const next = [...prev]; [next[i], next[i + by]] = [next[i + by], next[i]]; return next; });
return (
        <>
            <div className="fill-cols">
                <div className="fill-box"><h3>Fill</h3>
                    <div className="fill-radios" style={{marginBottom: 14}}>
                        <label><input type="radio" name="fill-which" checked={!replace} onChange={() => setReplace(false)} /> Only what each game is missing
                            <small>A game shows just its gaps among the kinds ticked below</small></label>
                        <label><input type="radio" name="fill-which" checked={replace} onChange={() => setReplace(true)} /> Everything ticked
                            <small>What each game has too, beside every source's, to keep or replace</small></label>
                    </div>
                    <h4 className="fill-subhead">Images</h4>
                    <div className="fill-checks">{FILL_PICTURES.map(k => (
                        <label key={k}><input type="checkbox" checked={!!fill[k]} onChange={e => setFill(prev => ({ ...prev, [k]: e.target.checked }))} /> {fillLabel(k)} <span className="fill-count">{count(k)}</span></label>))}</div>
                    <h4 className="fill-subhead">Manuals and videos</h4>
                    <div className="fill-checks">{FILL_FILES.map(k => (
                        <label key={k}><input type="checkbox" checked={!!fill[k]} onChange={e => setFill(prev => ({ ...prev, [k]: e.target.checked }))} /> {fillLabel(k)} <span className="fill-count">{count(k)}</span></label>))}</div>
                    <h4 className="fill-subhead">Text</h4>
                    <div className="fill-checks">{Object.keys(FILL_FIELDS).map(k => (
                        <label key={k}><input type="checkbox" checked={!!fill[k]} onChange={e => setFill(prev => ({ ...prev, [k]: e.target.checked }))} /> {fillLabel(k)} <span className="fill-count">{count(k)}</span></label>))}</div>
                    <p className="fill-note">Numbers are how many of the {chosenGames.length} picked games are missing each.
                        {nothing && !replace ? ` ${nothing} picked game${nothing === 1 ? ' has' : 's have'} none of these missing, so ${nothing === 1 ? "it's" : "they're"} left out: choose Everything ticked to see ${nothing === 1 ? 'it' : 'them'}.` : replace ? ' What a game has stays unless you pick another.' : ''}</p>
                </div>
                <div className="fill-box"><h3>Sources, most trusted first</h3>
                    <ol className="fill-order">{order.map((s, i) => {
                        const off = status[s.id] && !status[s.id].available;
                        return (
                            <li key={s.id} className={sourceOn(s) ? '' : 'off'} title={off ? status[s.id].hint : scrapeSource(s.id).title}>
                                <span className="pos">{i + 1}</span><span className="grow">{scrapeSource(s.id).label}{off ? ' (not set up)' : ''}</span>
                                <button onClick={() => move(i, -1)} disabled={!i} aria-label={`Move ${scrapeSource(s.id).label} up`}>▲</button>
                                <button onClick={() => move(i, 1)} disabled={i === order.length - 1} aria-label={`Move ${scrapeSource(s.id).label} down`}>▼</button>
                                <input type="checkbox" checked={s.on} disabled={off} aria-label={`Use ${scrapeSource(s.id).label}`}
                                    onChange={e => setOrder(prev => prev.map(x => (x.id === s.id ? { ...x, on: e.target.checked } : x)))} />
                            </li>
                        );
                    })}</ol>
                    <p className="fill-note">Each gap starts with the first source here that has it. Kept in this browser.</p>
                </div>
                <div className="fill-box"><h3>Then</h3>
                    <div className="fill-radios">
                        <label><input type="radio" name="fill-mode" checked={mode === 'review'} onChange={() => setMode('review')} /> Let me choose
                            <small>Every source's pictures and text side by side, the first choices made</small></label>
                        <label><input type="radio" name="fill-mode" checked={mode === 'auto'} onChange={() => setMode('auto')} /> Fill from the order
                            <small>No choosing. A source whose match is Unsure isn't used</small></label>
                    </div>
                    <p className="fill-note">{before} of {chosenGames.length} games were matched before and aren't looked up again on those sources.</p>
                </div>
            </div>
            <div className="fill-bar fill-foot"><button className="btn btn-secondary" onClick={() => setStep(0)}>Back</button><span className="grow"></span>
                <button className="btn btn-primary" disabled={!activeOrder.length || !chosenGames.some(g => toFill(g).length)} onClick={start}>{mode === 'review' ? 'Find candidates' : 'Fill them'}</button></div>
        </>
);
}

// Step 4: what was filled and where from, and what no source had
function FillDoneStep({ fx }) {
    const { applying, fill, games, results, setReload, setStep, sourceLabel, toFill } = fx;
    const chip = fillChip;
    const still = [];
return (
        <>
            {applying && <div className="muted">Applying {applying.done} of {applying.total}…</div>}
            <div className="fill-report">{(results || []).map(r => {
                const gaps = toFill(r.game).filter(k => !fillHas(r.game, k) && !r.from[k]);
                gaps.forEach(k => still.push({ game: r.game, key: k }));
                const done = [...(r.downloaded || []), ...(r.filled || [])];
                return (
                    <div className="fill-rrow" key={fillKey(r.game)}>
                        <div><b>{splitGameName(r.game.name || r.game.path).title}</b></div>
                        <div className="fill-chips">
                            {done.length ? done.map(k => chip(k, <span className="from"> {(r.replaced || []).includes(k) || fillHas(r.game, k) ? 'replaced' : 'filled'} from {sourceLabel(r.from[k], k)}</span>)) : <span className="muted">Nothing changed</span>}
                            {(r.errors || []).map((e, j) => <span key={j} className="fill-error">{e}</span>)}
                            {!r.success && r.error && <span className="fill-error">{r.error}</span>}
                        </div>
                    </div>
                );
            })}</div>
            <div className="fill-box" style={{marginTop: 16}}><h3>Still missing</h3>
                {still.length ? (
                    <>
                        <p className="muted" style={{margin: '0 0 6px', fontSize: 13}}>No source had these, or you left them empty. Open the game to look for them by hand.</p>
                        <ul style={{margin: 0, paddingLeft: 18, fontSize: 13}}>{still.map((s, j) => <li key={j}><a href={gameLink(s.game._system, s.game.path)}>{splitGameName(s.game.name || s.game.path).title}</a>: {fillLabel(s.key).toLowerCase()}</li>)}</ul>
                    </>
                ) : <p className="muted" style={{margin: 0, fontSize: 13}}>Nothing: every gap was filled.</p>}
            </div>
            <div className="fill-bar fill-foot"><button className="btn btn-secondary" onClick={() => { setStep(0); setReload(n => n + 1); }}>Back to the games</button></div>
        </>
);
}

// The enlarged comparison: what it has beside a source's version, stepping through that gap's sources
function FillZoom({ fx }) {
    const { all, candidateOf, choiceOf, fill, matchOf, offers, setChoice, setZoom, web, webFor } = fx;
    const zoom = fx.zoom;
    if (!zoom) return null;
    const g = all.find(x => fillKey(x) === zoom.key);
    if (!g) return null;
    const from = offers(g, zoom.kind);
    const close = () => setZoom(null);
    const kind = zoom.kind;
    // A manual or a video, read or played where it is
    const shown = (src) => (kind === 'videos' ? <video controls autoPlay={zoom.source !== 'now'} preload="metadata" src={src} />
        : kind === 'manuals' ? <><iframe title={fillLabel(kind)} src={src} /><a href={src} target="_blank" rel="noopener" className="fill-link">Open it in a new tab ↗</a></>
        : <img alt="" src={src} />);
    if (zoom.source === 'now' || zoom.source === 'web') {
        const src = zoom.source === 'web' ? webFor(g, kind)?.src : fillHas(g, kind) && localMediaUrl(g[kind]);
        if (!src) return null;
        return ReactDOM.createPortal(
            <div className="fill-lightbox" onClick={e => { e.stopPropagation(); close(); }}>
                <div className="fill-lb" role="dialog" aria-label={fillLabel(kind)} onClick={e => e.stopPropagation()}>
                    <div className="fill-bar"><div className="grow"><b>{splitGameName(g.name || g.path).title}</b> <span className="muted">· {fillLabel(kind)} {zoom.source === 'web' ? 'from the web' : 'it has now'}</span></div>
                        <button className="btn btn-secondary btn-small" onClick={close}>Close</button></div>
                    <div className="fill-lb-panes one"><div className="fill-lb-pane"><div className="art">{shown(src)}</div></div></div>
                </div>
            </div>,
            document.body
        );
    }
    const idx = from.findIndex(s => s.id === zoom.source);
    const s = from[idx];
    if (!s) return null;
    return ReactDOM.createPortal(
        <div className="fill-lightbox" onClick={e => { e.stopPropagation(); close(); }}>
            <div className="fill-lb" role="dialog" aria-label={`Compare ${fillLabel(zoom.kind)}`} onClick={e => e.stopPropagation()}>
                <div className="fill-bar"><div className="grow"><b>{splitGameName(g.name || g.path).title}</b> <span className="muted">· {fillLabel(zoom.kind)} · {idx + 1} of {from.length} sources</span></div>
                    <button className="btn btn-secondary btn-small" onClick={close}>Close</button></div>
                <div className={`fill-lb-panes ${FILL_FILES.includes(kind) && !fillHas(g, kind) ? 'one' : ''}`}>
                    {!(FILL_FILES.includes(kind) && !fillHas(g, kind)) && <div className="fill-lb-pane"><span className="muted" style={{fontSize: 12, fontWeight: 700}}>NOW</span>
                        <div className="art">{fillHas(g, kind) ? shown(localMediaUrl(g[kind])) : 'None yet'}</div></div>}
                    <div className="fill-lb-pane"><span style={{fontSize: 12, fontWeight: 700}}>{scrapeSource(s.id).label.toUpperCase()} · {FILL_CONF[matchOf(g, s.id)?.confidence] || ''}</span>
                        <div className="art">{shown(candidateOf(g, kind, s.id))}</div></div>
                </div>
                <div className="fill-bar">
                    <button className="btn btn-secondary" disabled={idx <= 0} onClick={() => setZoom({ ...zoom, source: from[idx - 1].id })}>‹ Previous source</button><span className="grow"></span>
                    <button className="btn btn-primary" onClick={() => { setChoice(prev => ({ ...prev, [`${fillKey(g)}|${zoom.kind}`]: s.id })); close(); }}>{choiceOf(g, zoom.kind) === s.id ? 'Chosen ✓' : 'Use this one'}</button><span className="grow"></span>
                    <button className="btn btn-secondary" disabled={idx >= from.length - 1} onClick={() => setZoom({ ...zoom, source: from[idx + 1].id })}>Next source ›</button>
                </div>
            </div>
        </div>,
        document.body
    );
}
