// Fill the gaps (tools-fill.jsx): the Choose step, every source's version of each gap side by side,
// and the "From the web" tile. Part of the library page (index.html).

// "From the web": search Google for it, then paste the picture (or its address) or drop it here
function FillWebTile({ fx, g, k, wide, chosen }) {
    const { fill, setChoice, setWeb, setZoom, status, useWeb, web, webAddress, webFor, webPicture } = fx;
    const isFile = fillIsFile, fileArt = fillFileArt, seeIt = (z) => fillSeeIt(z, setZoom);
    const found = webFor(g, k);
    const file = isFile(k);
    const drop = (e) => {
        e.preventDefault();
        const dropped = e.dataTransfer.files && e.dataTransfer.files[0];
        if (dropped && !file) webPicture(g, k, dropped);
        else webAddress(g, k, e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain'));
    };
    const paste = (e) => {
        const pasted = [...(e.clipboardData?.files || [])].find(f => /^image\//.test(f.type));
        if (pasted && !file) { e.preventDefault(); webPicture(g, k, pasted); }
    };
    if (found?.status === 'ready') {
        return (
            <button className={`fill-cand ${wide ? 'wide' : ''} ${chosen === 'web' ? 'on' : ''}`} aria-pressed={chosen === 'web'}
                onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'web' }))}>
                <span className="art">{fileArt(k) || <img alt={`${fillLabel(k)} from the web`} src={found.src} onError={() => useWeb(g, k, { status: 'failed', error: "That address didn't give a picture: paste the picture itself instead" })} />}</span>
                <span className="src">From the web</span>
                <span className="info"><span role="button" tabIndex={0} className="fill-link" onClick={e => { e.stopPropagation(); setWeb(prev => { const next = { ...prev }; delete next[`${fillKey(g)}|${k}`]; return next; }); }}>Another</span></span>
                {file && seeIt({ key: fillKey(g), kind: k, source: 'web' })}
            </button>
        );
    }
    return (
        <div className={`fill-cand fill-web ${wide ? 'wide' : ''}`} onDragOver={e => e.preventDefault()} onDrop={drop}>
            <span className="art">
                <a className="btn btn-secondary btn-small" href={fillSearchUrl(g, k)} target="_blank" rel="noopener noreferrer"
                    title={`Search Google ${file ? '' : 'Images '}for it in a new tab`}>🔎 Search Google</a>
                <input type="text" className="fill-web-paste" aria-label={`Paste the ${fillLabel(k).toLowerCase()} or its address`}
                    placeholder={file ? 'Paste its address' : 'Paste it, or its address'} disabled={found?.status === 'working'}
                    onPaste={paste} onKeyDown={e => { if (e.key === 'Enter') webAddress(g, k, e.target.value); }}
                    onBlur={e => { if (e.target.value.trim()) webAddress(g, k, e.target.value); }} />
                {!file && <label className="fill-link">or choose a file<input type="file" accept="image/*" hidden onChange={e => webPicture(g, k, e.target.files[0])} /></label>}
                {found?.status === 'working' && <span className="muted">Taking it…</span>}
                {found?.status === 'failed' && <span className="fill-error">{found.error}</span>}
            </span>
            <span className="src">From the web</span><span className="info">{file ? 'paste its address' : 'paste or drop it here'}</span>
        </div>
    );
}

// Step 3: one game at a time, each gap's candidates to pick from
function FillChooseStep({ fx }) {
    const { activeOrder, apply, applying, candidateOf, changes, choice, choiceOf, chosenGames, current,
        defaultFor, fill, games, generate, keysRef, looking, looks, made, madeFor, matchOf, offers, onClose,
        options, order, picked, remembered, replace, researched, researching, results, setChoice, setCurrent,
        setWrong, setZoom, show, showEverything, stopRef, system, systemsHanded, toFill, toMake, web, wrong } = fx;
    const field = FILL_FIELD_STYLE, chip = fillChip, confChip = fillConfChip;
    const isFile = fillIsFile, fileArt = fillFileArt, seeIt = (z) => fillSeeIt(z, setZoom);
    const list = chosenGames.filter(g => toFill(g).length);
    const g = list.find(x => fillKey(x) === current) || list[0];
    const i = g ? list.indexOf(g) : -1;
    const look = g && looks[fillKey(g)];
    const total = list.reduce((n, x) => n + changes(x).length, 0);
    const tiles = (k) => {
        const wide = FILL_WIDE.has(k);
        const chosen = choiceOf(g, k), def = defaultFor(g, k);
        const from = offers(g, k);
        // (a row is shown even when no source offers another of what it has: one can be found on the web)
        const makes = FILL_MAKES[k];
        const mine = makes && madeFor(g, k);
        return (
            <div className="fill-kind" key={k} data-row={k}>
                <div className="fill-kind-head"><h4>{fillLabel(k)}</h4><span className="muted">{fillHas(g, k) ? 'it has one: ' : 'missing: '}{from.length ? `${from.length} source${from.length === 1 ? ' has' : 's have'} one` : look ? 'no source has one' : 'looking…'}</span></div>
                <div className="fill-cands">
                    {fillHas(g, k) ? (
                        <button className={`fill-cand ${wide ? 'wide' : ''} ${chosen === 'keep' ? 'on' : ''}`} aria-pressed={chosen === 'keep'} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'keep' }))}>
                            <span className="art">{fileArt(k) || <img alt="What it has now" src={thumbUrl(320, g[k])} />}</span><span className="src">Now: keep it</span>
                            {isFile(k) && seeIt({ key: fillKey(g), kind: k, source: 'now' })}
                        </button>
                    ) : (
                        <div className={`fill-cand now ${wide ? 'wide' : ''}`}><span className="art"><span className="muted" style={{fontSize: 12}}>None yet</span></span><span className="src">Now</span></div>
                    )}
                    {from.map(s => (
                        <button key={s.id} className={`fill-cand ${wide ? 'wide' : ''} ${chosen === s.id ? 'on' : ''}`} aria-pressed={chosen === s.id} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: s.id }))}>
                            {s.id === def && <span className="badge">1st in order</span>}
                            <span className="art">{fileArt(k) || <img alt={`${scrapeSource(s.id).label}: ${fillLabel(k)}`} loading="lazy" src={candidateOf(g, k, s.id)} />}</span>
                            <span className="src">{scrapeSource(s.id).label} {confChip(matchOf(g, s.id))}</span>
                            {seeIt({ key: fillKey(g), kind: k, source: s.id })}
                        </button>
                    ))}
                    {makes && (mine && mine.status === 'ready' ? (
                        <button className={`fill-cand ${wide ? 'wide' : ''} ${chosen === 'generated' ? 'on' : ''}`} aria-pressed={chosen === 'generated'} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'generated' }))}>
                            {def === 'generated' && <span className="badge">made here</span>}
                            <span className="art"><img alt={`A ${fillLabel(k)} made from its own pictures`} src={mine.src} /></span>
                            <span className="src">Generated</span><span className="info">{makes.made}</span>
                        </button>
                    ) : (
                        <button className={`fill-cand ${wide ? 'wide' : ''} skip`} disabled={mine && mine.status === 'working'} onClick={() => generate(g, k)} title={makes.title}>
                            <span className="art">{mine && mine.status === 'working' ? 'Making one…' : mine && mine.status === 'failed' ? `Couldn't: ${mine.error}. Try again?` : '✨ Generate one'}</span>
                            <span className="src">{makes.maker}</span><span className="info">{makes.from}</span>
                        </button>
                    ))}
                    <FillWebTile fx={fx} g={g} k={k} wide={wide} chosen={chosen} />
                    {!fillHas(g, k) && (
                        <button className={`fill-cand skip ${wide ? 'wide' : ''} ${chosen === 'skip' ? 'on' : ''}`} aria-pressed={chosen === 'skip'} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'skip' }))}>
                            <span className="art">Leave it empty</span><span className="src">None</span>
                        </button>
                    )}
                </div>
            </div>
        );
    };
    const textRow = (k) => {
        const chosen = choiceOf(g, k);
        const from = offers(g, k);
        if (fillHas(g, k) && look && !from.length) return null;
        return (
            <div className="fill-field" key={k} data-row={k}>
                <div className="fl">{fillLabel(k)}{!fillHas(g, k) && <><br /><span className="muted" style={{fontSize: 11, fontWeight: 400, textTransform: 'none', letterSpacing: 0}}>missing</span></>}</div>
                <div className="fill-variants">
                    {fillHas(g, k) && (
                        <button className={`fill-variant ${chosen === 'keep' ? 'on' : ''}`} aria-pressed={chosen === 'keep'} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'keep' }))}>
                            <span className="src">Now: keep it</span><span className="val">{fillText(k, g[k])}</span>
                        </button>
                    )}
                    {from.map(s => (
                        <button key={s.id} className={`fill-variant ${chosen === s.id ? 'on' : ''}`} aria-pressed={chosen === s.id} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: s.id }))}>
                            <span className="src">{scrapeSource(s.id).label}<br />{confChip(matchOf(g, s.id))}</span><span className="val">{fillText(k, candidateOf(g, k, s.id))}</span>
                        </button>
                    ))}
                    {!from.length && <span className="muted" style={{fontSize: 13}}>{look ? 'No source has it.' : 'Looking…'}</span>}
                    {!fillHas(g, k) && from.length > 0 && (
                        <button className={`fill-variant ${chosen === 'skip' ? 'on' : ''}`} aria-pressed={chosen === 'skip'} onClick={() => setChoice(prev => ({ ...prev, [`${fillKey(g)}|${k}`]: 'skip' }))}>
                            <span className="src">None</span><span className="val muted">Leave it empty</span>
                        </button>
                    )}
                </div>
            </div>
        );
    };
    const w = wrong && g && wrong.key === fillKey(g) ? wrong : null;
    // Something there's a choice for: a gap, or (looked up) another version of what it has
    const choosable = (k) => !FILL_FIELDS[k] || !(fillHas(g, k) && look && !offers(g, k).length);
    const nothingToChoose = look && !toFill(g).some(choosable);
    const wm = w ? matchOf(g, w.source) : null;
    const searchingHere = !!(w && researching && researching.key === w.key && researching.source === w.source);
    keysRef.current = {
        next: () => { if (i < list.length - 1) { setCurrent(fillKey(list[i + 1])); setWrong(null); } },
        previous: () => { if (i > 0) { setCurrent(fillKey(list[i - 1])); setWrong(null); } },
        apply: () => { if (!looking && !applying && !toMake) apply(list); },
    };
    return !g ? <div className="muted">None of the picked games has anything to fill.</div> : (
        <div className="fill-review">
            <div className="fill-list" role="list">{list.map(x => {
                const looked = !!looks[fillKey(x)];
                return (
                    <button key={fillKey(x)} role="listitem" className={`fill-gitem ${fillKey(x) === fillKey(g) ? 'on' : ''}`} onClick={() => { setCurrent(fillKey(x)); setWrong(null); }}>
                        <span className="fill-thumb">{x.box2d && <img alt="" loading="lazy" src={thumbUrl(160, x.box2d)} />}</span>
                        <span className="meta"><span className="nm">{splitGameName(x.name || x.path).title}</span>
                            <span className="st">{systemsHanded > 1 ? `${x._systemName} · ` : ''}{looked ? `${changes(x).length} change${changes(x).length === 1 ? '' : 's'}` : 'looking…'}</span></span>
                    </button>
                );
            })}</div>
            <div className="fill-game">
                {looking && <div className="fill-progress"><div style={{width: `${(looking.done / looking.total) * 100}%`}} /><span>Looking up {looking.done} of {looking.total}…</span>
                    <button className="btn btn-secondary btn-small" onClick={() => { stopRef.current = true; }}>Stop after this game</button></div>}
                <div className="fill-game-head"><h3>{splitGameName(g.name || g.path).title}</h3><span className="muted">{(g.releasedate || '').slice(0, 4)} · {i + 1} of {list.length}</span>
                    <a href={gameLink(g._system, g.path)} className="muted" style={{fontSize: 12}}>Open the game ↗</a></div>
                <div className="fill-matches"><span className="muted" style={{fontSize: 12}}>Matched on</span>
                    {activeOrder.map(s => {
                        const m = matchOf(g, s.id);
                        return (
                            <button key={s.id} className={`fill-chip conf-${m ? m.confidence : 'wait'}`} title={m?.error || (m?.name ? `${scrapeSource(s.id).label}: ${m.name}` : '')}
                                onClick={() => setWrong(w && w.source === s.id ? null : { key: fillKey(g), source: s.id, query: splitGameName(g.name || g.path).title })}>
                                {scrapeSource(s.id).label}{m ? ` · ${m.error ? 'error' : FILL_CONF[m.confidence] || m.confidence}` : ' · …'}{m?.remembered ? ' ✓' : ''}
                            </button>
                        );
                    })}
                    <span className="muted" style={{fontSize: 11}}>tap one if it's the wrong game</span>
                </div>
                {w && (
                    <div className="fill-wrong">
                        <div className="muted" style={{fontSize: 12}}>{scrapeSource(w.source).label} has it as <b>{wm?.name || 'nothing'}</b>{wm?.error ? ` (${wm.error})` : ''}.</div>
                        {(wm?.alternatives || []).length > 1 && (
                            <select style={field} value={wm.id || ''} aria-label="Another of its results" disabled={searchingHere} onChange={e => researched(g, w.source, { id: e.target.value, query: w.query })}>
                                {wm.alternatives.map(a => <option key={a.id} value={a.id}>{a.name}{a.year ? ` · ${a.year}` : ''}{a.platform ? ` · ${a.platform}` : ''}</option>)}
                            </select>
                        )}
                        <input style={{...field, flex: '1 1 180px', minWidth: 0}} value={w.query} aria-label="Name to search for" onChange={e => setWrong({ ...w, query: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter' && !searchingHere) researched(g, w.source, { query: w.query }); }} />
                        <button className="btn btn-secondary btn-small fill-search" disabled={searchingHere} aria-busy={searchingHere} onClick={() => researched(g, w.source, { query: w.query })}>
                            {searchingHere ? <><span className="fill-spin" aria-hidden="true"></span>Searching…</> : `Search ${scrapeSource(w.source).label}`}</button>
                    </div>
                )}
                <div className="fill-show" role="radiogroup" aria-label="Show">
                    <span className="fill-keys muted" title="Keys while choosing">↑↓ row · 1–9 pick · ←→ game · A apply</span>
                    <span className="muted">Show</span>
                    <button role="radio" aria-checked={!replace} className={!replace ? 'on' : ''} onClick={() => showEverything(false)}>Only what's missing</button>
                    <button role="radio" aria-checked={replace} className={replace ? 'on' : ''} onClick={() => showEverything(true)}>Everything ticked</button>
                </div>
                {toFill(g).some(k => FILL_PICTURES.includes(k) && choosable(k)) && <h3 className="fill-section">Images</h3>}
                {toFill(g).filter(k => FILL_PICTURES.includes(k)).map(tiles)}
                {toFill(g).some(k => isFile(k) && choosable(k)) && <h3 className="fill-section">Manuals and videos <span className="muted">⤢ to read or play one</span></h3>}
                {toFill(g).filter(isFile).map(tiles)}
                {toFill(g).some(k => FILL_FIELDS[k] && choosable(k)) && (
                    <>
                        <h3 className="fill-section">Text <span className="muted">tap the one to use</span></h3>
                        <div className="fill-kind">{toFill(g).filter(k => FILL_FIELDS[k]).map(textRow)}</div>
                    </>
                )}
                {nothingToChoose && <p className="muted" style={{fontSize: 13}}>No source has anything to offer for what's ticked. Tap a source above if it found the wrong game.</p>}
                <div className="fill-bar fill-foot">
                    <button className="btn btn-secondary" disabled={i <= 0} onClick={() => { setCurrent(fillKey(list[i - 1])); setWrong(null); }}>‹ Previous game</button>
                    <button className="btn btn-secondary" disabled={i >= list.length - 1} onClick={() => { setCurrent(fillKey(list[i + 1])); setWrong(null); }}>Next game ›</button>
                    <span className="grow muted" style={{fontSize: 12}}>{total} change{total === 1 ? '' : 's'} across {list.length} game{list.length === 1 ? '' : 's'} · matches are remembered when you apply</span>
                    {applying ? <span className="muted">Applying {applying.done} of {applying.total}…</span>
                        : toMake ? <span className="muted">Making {toMake} picture{toMake === 1 ? '' : 's'}…</span>
                        : <button className="btn btn-primary" disabled={!!looking} onClick={() => apply(list)}>Apply {list.length} game{list.length === 1 ? '' : 's'}</button>}
                </div>
            </div>
        </div>
    );
}
