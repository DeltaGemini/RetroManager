// Tools: profiles and login.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Tools > Profiles and login: who uses RetroManager (a profile per saves
// folder), each one's photo, role and PIN, and whether signing in is on
// (backend/accounts.py). An admin's tool; anyone's while login is off.
function ProfilesPanel({ onClose, showNotification }) {
    const [me, setMe] = React.useState(null);
    const [error, setError] = React.useState(null);
    const [pinFor, setPinFor] = React.useState(null);     // the profile whose PIN is being typed
    const [pin, setPin] = React.useState('');
    const [newName, setNewName] = React.useState('');
    // The saves and states that are nobody's in particular ({saves, states}), and whether the new person takes them
    const [shared, setShared] = React.useState(null);
    const [takeShared, setTakeShared] = React.useState(false);
    const countShared = () => fetch(`${API_BASE}/api/accounts/shared-saves`).then(r => r.json()).then(d => { if (d.success) setShared(d); }).catch(() => {});
    useEffect(() => { countShared(); }, []);
    const [turningOn, setTurningOn] = React.useState(false);
    const [onAs, setOnAs] = React.useState('');
    const [onPin, setOnPin] = React.useState('');
    useEffect(() => {
        fetch(`${API_BASE}/api/accounts/me`).then(r => r.json()).then(setMe).catch(e => setError(e.message));
    }, []);

    const call = async (url, options, done) => {
        setError(null);
        try {
            const d = await (await fetch(`${API_BASE}${url}`, options)).json();
            if (!d.success) { setError(d.error || "That didn't work"); return null; }
            setMe(d);
            if (done) done(d);
            return d;
        } catch (e) { setError(e.message); return null; }
    };
    const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const change = (name, changes) => call('/api/accounts/profile', json('PUT', { name, ...changes }));
    const upload = (name, file) => {
        const form = new FormData();
        form.append('name', name);
        if (file) form.append('file', file);
        call('/api/accounts/photo', { method: 'POST', body: form });
    };
    const add = () => call('/api/accounts/people', json('POST', { name: newName.trim(), take_shared: takeShared }), (d) => {
        if (showNotification) showNotification(d.moved ? `${newName.trim()} added, with ${d.moved} file${d.moved === 1 ? '' : 's'} moved to their folders` : `${newName.trim()} added`, 'success');
        setNewName('');
        setTakeShared(false);
        countShared();
    });
    const savePin = async (name) => {
        if (await change(name, { pin })) { setPinFor(null); setPin(''); if (showNotification) showNotification(`${name}'s PIN is set`, 'success'); }
    };
    // Login changes what every page shows, so the page starts again
    const turnOn = () => call('/api/accounts/enabled', json('PUT', { enabled: true, profile: onAs, pin: onPin }), () => window.location.reload());
    const turnOff = () => { if (window.confirm('Switch login off? Everyone can then change everything again.')) call('/api/accounts/enabled', json('PUT', { enabled: false }), () => window.location.reload()); };

    const input = { padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border-color)', background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 13 };
    const admins = me ? me.profiles.filter(p => p.role === 'admin' && p.has_pin) : [];
    return (
        <Modal open={true} onClose={onClose}>
            <h2 style={{marginBottom: 4}}>Profiles and login</h2>
            <div style={{color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, maxWidth: 680}}>
                A profile for each person, the same people the saves folders are for. With login on, each device says who's using it:
                play status, the want list, achievements and preferences are then that person's own, and only an admin can change the library.
                A player just taps their photo; an admin needs their PIN.
            </div>
            {error && <div role="alert" style={{color: 'var(--accent-pink)', marginBottom: 12}}>{error}</div>}
            {!me && !error && <div style={{color: 'var(--text-secondary)'}}>Loading...</div>}
            {me && (
                <div className="gd" style={{containerType: 'normal'}}>
                    <div className="gd-row" style={{padding: '10px 12px', borderRadius: 6, background: 'var(--bg-tertiary)', marginBottom: 14}}>
                        <span style={{flex: 1, minWidth: 220}}>
                            <b>Login is {me.enabled ? 'on' : 'off'}.</b>{' '}
                            <span className="gd-note">{me.enabled ? `This device is signed in as ${me.profile}.` : 'Everyone shares one set of everything, and anyone can change anything.'}</span>
                        </span>
                        {me.enabled
                            ? <button className="gd-btn small" onClick={turnOff}>Switch login off</button>
                            : <button className="gd-btn small primary" disabled={!admins.length} onClick={() => { setTurningOn(true); setOnAs(admins[0] ? admins[0].name : ''); }}
                                title={admins.length ? '' : 'Make someone an admin and give them a PIN first'}>Switch login on</button>}
                    </div>
                    {!me.enabled && !admins.length && <div className="gd-note" style={{marginBottom: 12}}>To switch login on, first make someone an admin below and give them a PIN.</div>}
                    {turningOn && !me.enabled && (
                        <div className="gd-row" style={{marginBottom: 14}}>
                            <span>Sign this device in as</span>
                            <select value={onAs} onChange={e => setOnAs(e.target.value)} style={input}>{admins.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}</select>
                            <input type="password" inputMode="numeric" maxLength={8} placeholder="PIN" value={onPin} onChange={e => setOnPin(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') turnOn(); }} style={{...input, width: 110}} autoFocus />
                            <button className="gd-btn small primary" onClick={turnOn} disabled={!onPin}>Switch on</button>
                            <button className="gd-btn small" onClick={() => setTurningOn(false)}>Cancel</button>
                            <span className="gd-note" style={{flexBasis: '100%'}}>The play statuses and want list kept so far become {onAs || 'theirs'}.</span>
                        </div>
                    )}
                    <div style={{display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '48vh', overflowY: 'auto', paddingRight: 6}}>
                        {me.profiles.map(p => {
                            const look = RM.avatar(p);
                            return (
                                <div key={p.name} className="gd-row" style={{padding: 8, borderRadius: 6, background: 'var(--bg-tertiary)', marginBottom: 0}}>
                                    <label title="Choose a photo" style={{cursor: 'pointer', display: 'flex'}}>
                                        <span className="rm-face" style={{width: 52, height: 52, fontSize: 24, background: look.photo ? 'none' : look.colour}}>
                                            {look.photo ? <img src={look.photo} alt="" /> : look.initial}
                                        </span>
                                        <input type="file" accept="image/*" hidden onChange={e => { if (e.target.files[0]) upload(p.name, e.target.files[0]); e.target.value = ''; }} />
                                    </label>
                                    <span style={{flex: 1, minWidth: 120}}>
                                        <b>{p.name}</b>
                                        <span className="gd-note" style={{display: 'block'}}>
                                            {p.role === 'admin' ? (p.has_pin ? 'Admin · has a PIN' : 'Admin · needs a PIN') : 'Player · no PIN needed'}
                                            {p.photo && <> · <button className="gd-linkbutton" onClick={() => upload(p.name, null)}>remove photo</button></>}
                                        </span>
                                    </span>
                                    <select value={p.role} onChange={e => change(p.name, { role: e.target.value })} aria-label={`${p.name}'s role`} style={input}>
                                        <option value="player">Player</option>
                                        <option value="admin">Admin</option>
                                    </select>
                                    {p.role === 'admin' && (pinFor === p.name ? (
                                        <>
                                            <input type="password" inputMode="numeric" maxLength={8} placeholder="4 to 8 digits" value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))}
                                                onKeyDown={e => { if (e.key === 'Enter') savePin(p.name); }} style={{...input, width: 120}} autoFocus />
                                            <button className="gd-btn small primary" onClick={() => savePin(p.name)} disabled={pin.length < 4}>Save PIN</button>
                                            <button className="gd-btn small" onClick={() => { setPinFor(null); setPin(''); }}>Cancel</button>
                                        </>
                                    ) : (
                                        <button className="gd-btn small" onClick={() => { setPinFor(p.name); setPin(''); }}>{p.has_pin ? 'Change PIN' : 'Set a PIN'}</button>
                                    ))}
                                </div>
                            );
                        })}
                    </div>
                    {!me.profiles.length && (
                        <div className="gd-note" style={{marginBottom: 12, maxWidth: 680}}>
                            There are no profiles yet: saves, favourites and play status are one set, shared by everyone, and games are played with the saves RetroArch already keeps.
                            Add a person below to keep theirs apart.
                        </div>
                    )}
                    <div className="gd-row" style={{marginTop: 14}}>
                        <input type="text" value={newName} maxLength={24} placeholder="New person's name" onChange={e => setNewName(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) add(); }} style={{...input, width: 200}} />
                        <button className="gd-btn small primary" disabled={!newName.trim()} onClick={add}>Add a profile</button>
                        <span className="gd-note">Makes their folders in saves and savestates. Letters, digits, - and _.</span>
                    </div>
                    {/* What becomes of the saves there are already: only asked when there are some */}
                    {shared && shared.beside_roms && (
                        <div className="gd-note" style={{marginTop: 8}}>
                            Saves and save states are kept beside the games here (Tools › Settings › Saves), so everyone shares them: a profile has its own favourites, play status and sign-in, but not saves of its own. For those, RetroArch has to keep saves in folders of their own, and that setting to say so.
                        </div>
                    )}
                    {shared && shared.saves + shared.states > 0 && newName.trim() && (
                        <div style={{marginTop: 10, padding: '10px 12px', borderRadius: 6, background: 'var(--bg-tertiary)', maxWidth: 680}}>
                            <div style={{fontSize: 13, fontWeight: 600, marginBottom: 6}}>
                                The {shared.saves} save{shared.saves === 1 ? '' : 's'} and {shared.states} save state{shared.states === 1 ? '' : 's'} there {shared.saves + shared.states === 1 ? 'is' : 'are'} already:
                            </div>
                            <label style={{display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer', fontSize: 13, marginBottom: 6}}>
                                <input type="radio" name="take-shared" style={{marginTop: 3}} checked={!takeShared} onChange={() => setTakeShared(false)} />
                                <span>Keep them shared<span className="gd-note" style={{display: 'block'}}>They stay where they are, for anyone. {newName.trim()} starts with none.</span></span>
                            </label>
                            <label style={{display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer', fontSize: 13}}>
                                <input type="radio" name="take-shared" style={{marginTop: 3}} checked={takeShared} onChange={() => setTakeShared(true)} />
                                <span>Move them to {newName.trim()}
                                    <span className="gd-note" style={{display: 'block'}}>
                                        They go into {newName.trim()}'s folders (saves/{newName.trim()}/…). RetroArch on your other devices only finds them there once it's set to use a folder per person: see the guide below first.
                                    </span>
                                </span>
                            </label>
                        </div>
                    )}
                    <div className="gd-note" style={{marginTop: 10, maxWidth: 680}}>
                        A profile's saves are kept in a folder of its own, so RetroArch has to be told to use it: <a href="https://github.com/DeltaGemini/retropie_profiles" target="_blank" rel="noopener noreferrer">RetroPie profiles</a> adds
                        a profile switcher to EmulationStation that does. docs/profiles.md, with RetroManager, goes through it.
                    </div>
                    <div className="gd-note" style={{marginTop: 10}}>
                        Forgotten the PIN? Put an empty file called <code>reset-login</code> in RetroManager's data folder: login switches itself off, and you can set a new one here.
                    </div>
                </div>
            )}
        </Modal>
    );
}
