// The sign-in page (login.html): who's playing, and their password where they have one.
// Plain JavaScript, loaded where its <script> tag is in the page, so it runs just where it did inline.

// The "Who's playing?" screen: a tile per profile. A player's signs in at
// a tap; an admin's asks for their PIN. ?next= is where to go afterwards,
// ?profile= goes straight to that profile (switching to an admin).
const params = new URLSearchParams(window.location.search);
// Only ever back to a page of this site
const next = (() => { const n = params.get('next') || '/'; return n.startsWith('/') && !n.startsWith('//') && !n.startsWith('/login') ? n : '/'; })();
const $ = (id) => document.getElementById(id);
let chosen = null;

const signIn = async (name, pin) => {
    $('message').textContent = '';
    try {
        const res = await fetch('/api/accounts/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile: name, pin }) });
        const d = await res.json();
        if (d.success) { window.location.replace(next); return; }
        $('message').textContent = pin === undefined && d.pin_needed ? '' : (d.error || "That didn't work");
    } catch (e) { $('message').textContent = `Couldn't reach RetroManager: ${e.message}`; }
    $('pin').value = '';
    $('pin').focus();
};
const askPin = (profile) => {
    chosen = profile;
    document.querySelectorAll('.person').forEach(el => { el.hidden = el.dataset.name !== profile.name; el.classList.toggle('chosen', el.dataset.name === profile.name); });
    $('heading').textContent = `Hello, ${profile.name}`;
    $('pin-label').textContent = `${profile.name}'s PIN`;
    $('pin-form').hidden = false;
    $('pin').focus();
};
$('pin-form').addEventListener('submit', (e) => { e.preventDefault(); if (chosen && $('pin').value) signIn(chosen.name, $('pin').value); });
$('pin-back').addEventListener('click', () => {
    chosen = null;
    $('pin-form').hidden = true;
    $('message').textContent = '';
    $('heading').textContent = "Who's playing?";
    document.querySelectorAll('.person').forEach(el => { el.hidden = false; el.classList.remove('chosen'); });
});

RM.me.then(me => {
    if (!me.enabled) { window.location.replace(next); return; }
    me.profiles.forEach(profile => {
        const look = RM.avatar(profile);
        const tile = Object.assign(document.createElement('button'), { className: 'person', type: 'button' });
        tile.dataset.name = profile.name;
        tile.setAttribute('role', 'listitem');
        const face = tile.appendChild(Object.assign(document.createElement('span'), { className: 'face' }));
        if (look.photo) face.appendChild(Object.assign(document.createElement('img'), { src: look.photo, alt: '' }));
        else { face.textContent = look.initial; face.style.background = look.colour; }
        tile.appendChild(Object.assign(document.createElement('span'), { className: 'name', textContent: profile.name }));
        if (profile.role === 'admin') tile.appendChild(Object.assign(document.createElement('span'), { className: 'role', textContent: 'Admin · PIN' }));
        tile.addEventListener('click', () => (profile.role === 'admin' ? askPin(profile) : signIn(profile.name)));
        $('people').appendChild(tile);
    });
    const wanted = me.profiles.find(p => p.name === params.get('profile'));
    if (wanted && wanted.role === 'admin') askPin(wanted);
});
