// Tools: generate Mix pictures for games that have none (opened from the Media viewer).
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Why a game's Mix can't be made, or wasn't
const MIX_REASONS = {
    no_screenshot: 'No screenshot',
    screenshot_only: 'Only a screenshot: it needs a box or a logo too',
    no_box_or_wheel: 'No box or logo',
    asset_unreadable: 'A picture it needs can’t be read',
    interrupted: 'A restart interrupted it',
    render_error: 'It couldn’t be drawn',
    template: 'The template is missing',
};
const MIX_ROLES = [['screenshot', 'Screenshot'], ['box', 'Box'], ['media', 'Cart / disc'], ['wheel', 'Logo']];
const MIX_FILTERS = [
    ['all', 'All', () => true],
    ['ready', 'Ready', i => i.status === 'ready'],
    ['failed', 'Failed', i => i.status === 'failed'],
    ['ineligible', 'Can’t be made', i => i.status === 'ineligible'],
    ['committed', 'In the library', i => i.status === 'committed'],
];
const mixPreviewUrl = (job, item) => `${API_BASE}/api/mix/preview/${job.id}/${item.index}?rev=${item.rev}`;
const mixReason = (item) => MIX_REASONS[item.reason] || item.reason || '';

// One preview, large: what it was made from, and making it again another way
function MixPreviewDetail({ job, item, templates, onBack, onRegenerate }) {
    const [template, setTemplate] = React.useState(item.template);
    const [options, setOptions] = React.useState(item.options || {});
    useEffect(() => { setTemplate(item.template); setOptions(item.options || {}); }, [item.index, item.rev]);
    const has = (folder) => !!item.available[folder];
    const set = (key, value) => setOptions(prev => {
        const next = { ...prev };
        if (value === undefined) delete next[key]; else next[key] = value;
        return next;
    });
    const busy = item.status === 'pending' || item.status === 'rendering';
    const assets = (item.record && item.record.assets) || {};

    return (
        <div>
            <div style={{display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12}}>
                <button className="btn btn-secondary btn-small" onClick={onBack}>‹ All previews</button>
                <b>{item.name}</b>
                <span style={{color: 'var(--text-secondary)', fontSize: 13}}>{item.system_name}</span>
            </div>
            <div style={{display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-start'}}>
                <div style={{flex: '2 1 420px', minWidth: 0, background: 'var(--bg-secondary)', borderRadius: 6, aspectRatio: '4 / 3', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                    {item.status === 'ready'
                        ? <img src={mixPreviewUrl(job, item)} alt="" style={{width: '100%', height: '100%', objectFit: 'contain'}} />
                        : <span style={{color: 'var(--text-secondary)', padding: 20, textAlign: 'center'}}>{busy ? 'Making it…' : (mixReason(item) || item.status)}</span>}
                </div>
                <div style={{flex: '1 1 240px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14, fontSize: 13}}>
                    {item.status === 'ready' && (
                        <div>
                            <div style={{color: 'var(--text-secondary)', marginBottom: 6}}>Made from</div>
                            <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                                {MIX_ROLES.filter(([role]) => assets[role]).map(([role, label]) => (
                                    <a key={role} href={localMediaUrl(assets[role])} target="_blank" rel="noopener noreferrer" title={assets[role]}
                                        style={{textDecoration: 'none', color: 'inherit', textAlign: 'center', fontSize: 11}}>
                                        <img src={thumbUrl(160, assets[role])} alt="" style={{height: 64, maxWidth: 110, objectFit: 'contain', display: 'block', background: 'var(--bg-secondary)', borderRadius: 4}} />
                                        {label}<br /><span style={{color: 'var(--text-secondary)'}}>{mediaSourceLabel(item.used[role])}</span>
                                    </a>
                                ))}
                            </div>
                        </div>
                    )}
                    {(item.warnings || []).map(w => <div key={w} style={{color: 'var(--accent-orange)'}}>Skipped {w}</div>)}
                    {item.status === 'failed' && item.error && <div style={{color: 'var(--accent-pink)'}}>{item.error}</div>}
                    {item.status !== 'committed' && (
                        <div style={{display: 'flex', flexDirection: 'column', gap: 8}}>
                            <div style={{color: 'var(--text-secondary)'}}>Make it another way</div>
                            <label>Template <select value={template} onChange={e => setTemplate(e.target.value)}>
                                {templates.map(t => <option key={t.name} value={t.name}>{t.label}</option>)}
                            </select></label>
                            {[['box', 'Box', has('box3d') || has('box2d')], ['media', 'Cart / disc', has('support')], ['wheel', 'Logo', has('wheel')]].map(([key, label, there]) => (
                                <label key={key} style={{opacity: there ? 1 : 0.5}} title={there ? '' : 'This game has none'}>
                                    <input type="checkbox" disabled={!there} checked={there && options[key] !== false}
                                        onChange={e => set(key, e.target.checked ? undefined : false)} /> {label}
                                </label>
                            ))}
                            {has('box3d') && has('box2d') && (
                                <label>Box <select value={options.box_type || ''} onChange={e => set('box_type', e.target.value || undefined)}>
                                    <option value="">Template’s choice</option><option value="3d">3D box</option><option value="2d">2D box</option>
                                </select></label>
                            )}
                            {has('screenshot') && has('screenshottitle') && (
                                <label>Screenshot <select value={options.screenshot || ''} onChange={e => set('screenshot', e.target.value || undefined)}>
                                    <option value="">Template’s choice</option><option value="screenshot">In-game</option><option value="title">Title screen</option>
                                </select></label>
                            )}
                            <button className="btn btn-primary btn-small" style={{alignSelf: 'flex-start'}} disabled={busy}
                                onClick={() => onRegenerate(item.index, template, options)}>⟳ Regenerate</button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// Inventory -> previews -> review -> commit. selection is what's sent to the
// backend: {games: [{system, rom_path}]} for the games picked in the Media viewer,
// or {generated: true, systems?} to make the generated ones again.
function MixGeneratePanel({ selection, onBack, onClose, onDone }) {
    const [templates, setTemplates] = React.useState([]);
    const [template, setTemplate] = React.useState('');
    const [report, setReport] = React.useState(null);
    const [job, setJob] = React.useState(null);
    const [decisions, setDecisions] = React.useState({});   // preview index -> 'approve' | 'reject'
    const [filter, setFilter] = React.useState('all');
    const [open, setOpen] = React.useState(null);
    const [overwrite, setOverwrite] = React.useState(false);
    const [busy, setBusy] = React.useState(false);
    const [outcome, setOutcome] = React.useState(null);
    const [error, setError] = React.useState(null);
    const changed = useRef(false);

    useEffect(() => {
        fetch(`${API_BASE}/api/mix/templates`).then(r => r.json())
            .then(d => d.success && setTemplates(d.templates)).catch(() => {});
    }, []);
    // What generating would make; nothing is written
    useEffect(() => {
        if (job) return;
        setReport(null);
        postJson('/api/mix/inventory', { ...selection, template: template || undefined })
            .then(d => d.success ? setReport(d) : setError(d.error))
            .catch(e => setError(e.message));
    }, [template]);
    // Follow the previews while they're being made
    useEffect(() => {
        if (!job || !job.running) return;
        const timer = setInterval(async () => {
            try {
                const d = await (await fetch(`${API_BASE}/api/mix/jobs/${job.id}`)).json();
                if (d.success) setJob(d.job); else setError(d.error);
            } catch (e) { /* try again next time */ }
        }, 1000);
        return () => clearInterval(timer);
    }, [job && job.id, job && job.running]);

    const call = async (work) => {
        setBusy(true);
        setError(null);
        try { await work(); } catch (e) { setError(e.message); }
        setBusy(false);
    };
    const start = () => call(async () => {
        const d = await postJson('/api/mix/jobs', { ...selection, template: template || undefined });
        if (d.success) setJob(d.job); else setError(d.error || 'Could not start');
    });
    const regenerate = (index, name, options) => call(async () => {
        const d = await postJson(`/api/mix/jobs/${job.id}/regenerate`, { items: [{ index, template: name, options }] });
        if (!d.success) return setError(d.error || 'Could not make it again');
        setJob(d.job);
        setDecisions(prev => { const next = { ...prev }; delete next[index]; return next; });
    });
    // Leaving throws the previews away; the library only has what was committed
    const leave = async (then) => {
        if (job) { try { await fetch(`${API_BASE}/api/mix/jobs/${job.id}`, { method: 'DELETE' }); } catch (e) { /* cleared by age anyway */ } }
        if (changed.current && onDone) onDone();
        then();
    };

    const items = job ? job.items : [];
    const ready = items.filter(i => i.status === 'ready');
    const approved = ready.filter(i => decisions[i.index] === 'approve');
    const rejected = ready.filter(i => decisions[i.index] === 'reject');
    const replacing = approved.filter(i => i.has_mix && !i.mix_generated);
    const decide = (index, what) => setDecisions(prev => ({ ...prev, [index]: prev[index] === what ? undefined : what }));
    const commit = () => call(async () => {
        const d = await postJson(`/api/mix/jobs/${job.id}/commit`,
            { approve: approved.map(i => i.index), reject: rejected.map(i => i.index), overwrite });
        if (!d.success) return setError(d.error || 'Could not commit');
        if (d.committed) changed.current = true;
        setJob(d.job);
        setOutcome(d);
        const kept = new Set(d.results.filter(r => r.status === 'needs_overwrite').map(r => r.index));
        setDecisions(prev => Object.fromEntries(Object.entries(prev).filter(([index]) => kept.has(Number(index)))));
    });

    let body;
    if (!job) {
        const counts = report ? report.systems.reduce((sum, s) => ({ full: sum.full + s.full, partial: sum.partial + s.partial, ineligible: sum.ineligible + s.ineligible }), { full: 0, partial: 0, ineligible: 0 }) : null;
        const cannot = report ? report.games.filter(g => g.tier === 'ineligible') : [];
        const existing = report ? report.games.filter(g => g.has_mix && !g.mix_generated) : [];
        body = !report ? <div style={{color: 'var(--text-secondary)'}}>{error ? '' : 'Checking what each game has…'}</div> : (
            <>
                <div style={{display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14}}>
                    {[['Full', counts.full, 'Screenshot, box, cart or disc, and logo', 'var(--success)'],
                      ['Partial', counts.partial, 'Screenshot with a box or a logo', 'var(--accent-orange)'],
                      ['Can’t be made', counts.ineligible, 'No screenshot, or nothing to go with it', 'var(--accent-pink)']].map(([label, n, help, color]) => (
                        <div key={label} title={help} style={{flex: '1 1 130px', background: 'var(--bg-tertiary)', borderRadius: 6, padding: '10px 14px'}}>
                            <div style={{fontSize: 24, fontWeight: 700, color}}>{n}</div>
                            <div style={{fontSize: 13}}>{label}</div>
                            <div style={{fontSize: 11, color: 'var(--text-secondary)'}}>{help}</div>
                        </div>
                    ))}
                </div>
                {report.systems.length > 1 && (
                    <div style={{fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12}}>
                        {report.systems.map(s => `${s.full_name}: ${s.full} full, ${s.partial} partial, ${s.ineligible} can’t`).join(' · ')}
                    </div>
                )}
                {existing.length > 0 && (
                    <div style={{fontSize: 13, color: 'var(--accent-orange)', marginBottom: 12}}>
                        {existing.length} already {existing.length === 1 ? 'has' : 'have'} a Mix that wasn’t generated. It’s only replaced if you say so when committing.
                    </div>
                )}
                {cannot.length > 0 && (
                    <details style={{marginBottom: 14, fontSize: 13}}>
                        <summary style={{cursor: 'pointer'}}>The {cannot.length} that can’t be made, and why</summary>
                        <div style={{maxHeight: '30vh', overflowY: 'auto', marginTop: 6}}>
                            {cannot.map(g => (
                                <div key={`${g.system}/${g.rom_path}`} style={{display: 'flex', gap: 10, padding: '3px 0', borderBottom: '1px solid var(--border-color)'}}>
                                    <a href={gameLink(g.system, g.rom_path)} style={{flex: 1, minWidth: 0, color: 'inherit', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{g.name}</a>
                                    <span style={{color: 'var(--text-secondary)'}}>{mixReason(g)}</span>
                                </div>
                            ))}
                        </div>
                    </details>
                )}
                <div style={{display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap'}}>
                    {templates.length > 1 && (
                        <label style={{fontSize: 13}}>Template <select value={template} onChange={e => setTemplate(e.target.value)}>
                            <option value="">Each system’s own</option>
                            {templates.map(t => <option key={t.name} value={t.name}>{t.label}</option>)}
                        </select></label>
                    )}
                    <button className="btn btn-primary" disabled={busy || !(counts.full + counts.partial)} onClick={start}>
                        Make {counts.full + counts.partial} preview{counts.full + counts.partial === 1 ? '' : 's'}
                    </button>
                    <span style={{fontSize: 12, color: 'var(--text-secondary)'}}>Previews aren’t put in the library until you approve them.</span>
                </div>
            </>
        );
    } else if (open !== null && items[open]) {
        body = <MixPreviewDetail job={job} item={items[open]} templates={templates} onBack={() => setOpen(null)} onRegenerate={regenerate} />;
    } else {
        const test = MIX_FILTERS.find(f => f[0] === filter)[2];
        const shown = items.filter(test);
        const results = outcome ? outcome.results : [];
        const blocked = results.filter(r => r.status === 'needs_overwrite').length;
        body = (
            <>
                <div style={{marginBottom: 12}}>
                    <div style={{height: 8, background: 'var(--border-color)', borderRadius: 4, overflow: 'hidden'}}>
                        <div style={{height: '100%', width: `${job.total ? 100 * job.done / job.total : 100}%`, background: job.running ? 'var(--accent-orange)' : 'var(--success)', transition: 'width 0.3s'}} />
                    </div>
                    <div style={{fontSize: 12, color: 'var(--text-secondary)', marginTop: 4}}>
                        {job.running ? 'Making previews: ' : ''}{job.done} of {job.total} done{job.failed ? `, ${job.failed} failed` : ''}{job.ineligible ? ` · ${job.ineligible} can’t be made` : ''}
                    </div>
                </div>
                {outcome && (
                    <div style={{fontSize: 13, marginBottom: 12, padding: '8px 12px', background: 'var(--bg-tertiary)', borderRadius: 6}}>
                        {outcome.committed} put in the library
                        {outcome.linked ? `, ${outcome.linked} set as the gamelist’s image` : ''}
                        {outcome.backup ? `. What was replaced is in ${outcome.backup}` : ''}.
                        {blocked > 0 && <span style={{color: 'var(--accent-orange)'}}> {blocked} already {blocked === 1 ? 'has' : 'have'} a Mix that wasn’t generated: tick Replace to commit {blocked === 1 ? 'it' : 'them'}.</span>}
                        {results.some(r => r.status === 'failed') && <span style={{color: 'var(--accent-pink)'}}> {results.filter(r => r.status === 'failed').length} couldn’t be written.</span>}
                    </div>
                )}
                <div style={{display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12}}>
                    {MIX_FILTERS.map(([key, label, match]) => {
                        const n = items.filter(match).length;
                        return (key === 'all' || n > 0) && (
                            <button key={key} className="fchip" aria-pressed={filter === key} onClick={() => setFilter(key)}>{label} <span className="n">{n}</span></button>
                        );
                    })}
                    <span style={{flex: 1}} />
                    {replacing.length > 0 && (
                        <label style={{fontSize: 12}} title="The pictures replaced are put in a backup first">
                            <input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} /> Replace {replacing.length} existing Mix
                        </label>
                    )}
                    <button className="btn btn-secondary btn-small" disabled={!ready.length}
                        onClick={() => setDecisions(Object.fromEntries(ready.map(i => [i.index, 'approve'])))}>Approve all</button>
                    <button className="btn btn-primary btn-small" disabled={busy || job.running || !(approved.length + rejected.length)} onClick={commit}
                        title={job.running ? 'Wait for the previews to finish' : 'Put the approved previews in the library and throw the rejected ones away'}>
                        Commit {approved.length} approved
                    </button>
                </div>
                {shown.length === 0 ? <div style={{color: 'var(--text-secondary)', padding: '20px 0'}}>None.</div> : (
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10, maxHeight: '58vh', overflowY: 'auto'}}>
                        {shown.map(item => {
                            const decision = decisions[item.index];
                            const waiting = item.status === 'pending' || item.status === 'rendering';
                            return (
                                <div key={item.index} style={{background: 'var(--bg-tertiary)', borderRadius: 6, overflow: 'hidden', display: 'flex', flexDirection: 'column',
                                    outline: decision === 'approve' ? '2px solid var(--success)' : decision === 'reject' ? '2px solid var(--accent-pink)' : 'none', outlineOffset: -2,
                                    opacity: decision === 'reject' || item.status === 'rejected' ? 0.55 : 1}}>
                                    <div onClick={() => setOpen(item.index)} title="Look closer, or make it another way"
                                        style={{aspectRatio: '4 / 3', background: 'var(--bg-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', position: 'relative'}}>
                                        {item.status === 'ready'
                                            ? <img src={mixPreviewUrl(job, item)} alt="" loading="lazy" style={{width: '100%', height: '100%', objectFit: 'contain'}} />
                                            : <span style={{fontSize: 12, padding: 10, textAlign: 'center', color: item.status === 'failed' ? 'var(--accent-pink)' : 'var(--text-secondary)'}}>
                                                {waiting ? 'Making it…' : item.status === 'committed' ? '✓ In the library' : item.status === 'rejected' ? 'Rejected' : mixReason(item)}
                                              </span>}
                                        {item.has_mix && !item.mix_generated && item.status !== 'committed' && (
                                            <span className="status-badge" style={{position: 'absolute', top: 6, left: 6, color: 'var(--accent-orange)'}} title="This game already has a Mix that wasn’t generated">has a Mix</span>
                                        )}
                                    </div>
                                    <div style={{padding: '6px 8px', fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4}}>
                                        <div style={{fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}} title={item.name}>{item.name}</div>
                                        {item.status === 'ready' ? (
                                            <div style={{display: 'flex', gap: 4}}>
                                                <button className="fchip" style={{whiteSpace: 'nowrap'}} aria-pressed={decision === 'approve'} onClick={() => decide(item.index, 'approve')}>✓ Approve</button>
                                                <button className="fchip" style={{whiteSpace: 'nowrap'}} aria-pressed={decision === 'reject'} onClick={() => decide(item.index, 'reject')}>✕ Reject</button>
                                                <button className="fchip" style={{marginLeft: 'auto'}} onClick={() => setOpen(item.index)} title="Make it another way">⟳</button>
                                            </div>
                                        ) : (
                                            <div style={{color: 'var(--text-secondary)', fontSize: 11}}>
                                                {item.status === 'failed' ? <button className="link-button" style={{padding: 0}} onClick={() => regenerate(item.index, item.template, item.options)}>Try again</button>
                                                    : item.status === 'ineligible' ? 'Can’t be made' : item.tier === 'full' ? 'Full' : item.tier === 'partial' ? 'Partial' : ''}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </>
        );
    }

    return (
        <Modal open={true} onClose={() => leave(onClose)}>
            <h2 style={{marginBottom: 4}}>Generate Mix</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12}}>
                {selection.generated
                    ? 'The Mix pictures RetroManager generated, made again with the template as it is now. The ones you approve replace the old ones, which are backed up first.'
                    : `A Mix made from each game’s own screenshot, box, cart or disc, and logo. ${selection.games.length} game${selection.games.length === 1 ? '' : 's'} picked.`}
            </div>
            <div style={{marginBottom: 12}}>
                <button className="btn btn-secondary btn-small" onClick={() => leave(onBack)}>‹ Media viewer</button>
                {job && <span style={{fontSize: 12, color: 'var(--text-secondary)', marginLeft: 10}}>Leaving throws away previews you haven’t committed.</span>}
            </div>
            {error && <div style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {body}
        </Modal>
    );
}
