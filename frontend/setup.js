// The first-run setup page (setup.html): where saves go, ScreenScraper, and who can change things.
// Plain JavaScript, loaded where its <script> tag is in the page, so it runs just where it did inline.

// The first-run steps (backend/routes/setup.py): where the library is, a
// ScreenScraper account or none, and on to the library. Finishing or
// skipping notes that it's been done, so it isn't shown again.
const $ = (id) => document.getElementById(id);
const el = (tag, props, ...children) => { const node = Object.assign(document.createElement(tag), props || {}); children.forEach(c => node.append(c)); return node; };
let state = null, saved = false, signedIn = null;

const show = (step) => {
    const order = ['folders', 'scraper', 'login', 'done'];
    order.forEach(name => { $(name).hidden = name !== step; });
    document.querySelectorAll('ol.steps li').forEach(li => {
        li.classList.toggle('on', li.dataset.step === step);
        li.classList.toggle('past', order.indexOf(li.dataset.step) < order.indexOf(step));
    });
    window.scrollTo(0, 0);
};
document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => show(button.dataset.go)));

const look = async () => {
    $('library-summary').textContent = 'Looking at the folders…';
    try {
        state = await (await fetch('/api/setup')).json();
    } catch (e) {
        $('library-summary').textContent = `Couldn't reach RetroManager: ${e.message}`;
        return;
    }
    const { library, folders } = state;
    $('library-summary').textContent = library.games
        ? `RetroManager can see ${library.games} file${library.games === 1 ? '' : 's'} in ${library.systems} system folder${library.systems === 1 ? '' : 's'}.`
        : 'There are no games here yet, which is as it should be for a new library: you can add them in a moment.';
    const list = $('folder-list');
    list.replaceChildren();
    folders.forEach(folder => {
        const good = folder.exists && (folder.writable || !folder.written);
        list.append(el('tr', null,
            el('td', null, el('b', { textContent: folder.label }), el('div', { className: 'quiet', textContent: folder.holds })),
            el('td', { className: `state ${good ? 'ok' : 'not'}`, textContent: !folder.exists ? 'Not there' : good ? 'Ready' : "Can't be written to" })));
    });
    const where = state.on_host || 'RetroGames';
    $('where').replaceChildren('On this machine the library is in ', el('code', { textContent: where }),
        where.startsWith('.') ? ' beside docker-compose.yml' : '', '. Games go in its ', el('code', { textContent: 'roms' }),
        ' folder, one folder per system (', el('code', { textContent: 'roms/snes' }), ', ', el('code', { textContent: 'roms/gba' }),
        '…). To use folders you already have somewhere else, see "Paths" in the documentation (docs/setup.md): it is one line in a file, and the only thing that can’t be set from here.');
    // Where saves are kept: as set, else as the files found suggest
    const { location, beside_roms: beside, in_folders: separate } = state.saves;
    const many = (n) => (n >= 500 ? 'over 500' : String(n));
    const suggested = beside > separate ? 'roms' : 'folders';
    $('saves-found').textContent = beside || separate
        ? `Found ${many(separate)} save file${separate === 1 ? '' : 's'} in the saves folders and ${many(beside)} beside the games, so ${suggested === 'roms' ? 'beside the games' : 'folders of their own'} looks right.`
        : 'No saves yet. Choose the way your RetroArch is set up (if you’re not sure, the first: it’s what RetroArch does unless told otherwise).';
    const chosen = beside || separate ? (location === 'roms' || suggested === 'roms' ? 'roms' : 'folders') : location;
    document.querySelectorAll('input[name="save-location"]').forEach(input => { input.checked = input.value === chosen; });
    const bad = folders.filter(f => !f.exists || (f.written && !f.writable));
    $('folder-problem').hidden = !bad.length;
    if (bad.length) {
        $('folder-problem').textContent = `${bad.map(f => f.label).join(', ')}: ${bad.length === 1 ? "this folder isn't" : "these folders aren't"} usable yet. `
            + 'On the machine running RetroManager, make sure the folder exists and that the user Docker runs as may write to it, then press Look again. You can go on without, but what needs that folder will fail.';
    }
};
$('look-again').addEventListener('click', look);
// On to ScreenScraper, with where saves are kept said first if it isn't as it was
$('folders-next').addEventListener('click', async () => {
    const picked = (document.querySelector('input[name="save-location"]:checked') || {}).value;
    $('folders-message').textContent = '';
    if (picked && state && picked !== state.saves.location) {
        try {
            const d = await (await fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values: { save_location: picked } }) })).json();
            if (!d.success) throw new Error(d.error || 'it wasn’t saved');
            state.saves.location = picked;
        } catch (e) {
            $('folders-message').textContent = `Couldn't save where saves are kept: ${e.message}`;
            return;
        }
    }
    show('scraper');
});

const finish = async () => {
    try { await fetch('/api/setup/done', { method: 'POST' }); } catch (e) {}
};
const toDone = () => {
    $('done-summary').textContent = (saved
        ? 'ScreenScraper is set up. The first scrape will tell you if it doesn’t accept the details.'
        : 'You skipped ScreenScraper. Add it whenever you like in Tools › Settings.')
        + (signedIn ? ` Login is on, and this device is signed in as ${signedIn}.`
            : ' Login is off: anyone on your network can change the library until you turn it on in Tools › Profiles and login.');
    finish();
    show('done');
};
// ScreenScraper done with (or skipped): on to who can change things
let shared = 0;
const toLogin = async () => {
    try {
        const d = await (await fetch('/api/accounts/shared-saves')).json();
        shared = d.success && !d.beside_roms ? d.saves + d.states : 0;
    } catch (e) { shared = 0; }
    $('take-label').hidden = !shared;
    show('login');
};
$('skip-keys').addEventListener('click', toLogin);
$('skip-login').addEventListener('click', toDone);
$('turn-on').addEventListener('click', async () => {
    const form = Object.fromEntries(new FormData($('admin')));
    const name = String(form.name || '').trim(), pin = String(form.pin || '');
    $('login-message').textContent = '';
    if (!name) { $('login-message').textContent = 'Say your name: it’s what you pick when you open RetroManager.'; return; }
    if (!/^\d{4,8}$/.test(pin)) { $('login-message').textContent = 'A PIN is 4 to 8 digits.'; return; }
    if (pin !== String(form.again || '')) { $('login-message').textContent = 'The two PINs aren’t the same.'; return; }
    const call = async (url, method, body) => {
        const d = await (await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
        if (!d.success) throw new Error(d.error || 'that didn’t work');
        return d;
    };
    $('turn-on').disabled = true;
    try {
        await call('/api/accounts/people', 'POST', { name, take_shared: !!shared && !!form.take });
        await call('/api/accounts/profile', 'PUT', { name, role: 'admin', pin });
        await call('/api/accounts/enabled', 'PUT', { enabled: true, profile: name, pin });
        signedIn = name;
        toDone();
    } catch (e) {
        $('login-message').textContent = `Login isn't on: ${e.message}`;
    }
    $('turn-on').disabled = false;
});
$('save-keys').addEventListener('click', async () => {
    const values = Object.fromEntries([...new FormData($('keys'))].map(([key, value]) => [key, String(value).trim()]).filter(([, value]) => value));
    $('message').textContent = '';
    if (!values.screenscraper_login || !values.screenscraper_password) {
        $('message').textContent = 'ScreenScraper needs the developer ID and password. Without them, press Skip for now.';
        return;
    }
    $('save-keys').disabled = true;
    try {
        const d = await (await fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values }) })).json();
        if (!d.success) throw new Error(d.error || 'they weren’t saved');
        saved = true;
        toLogin();
    } catch (e) {
        $('message').textContent = `Couldn't save them: ${e.message}`;
    }
    $('save-keys').disabled = false;
});
$('finish').addEventListener('click', () => { window.location.replace('/'); });

show('folders');
look();
