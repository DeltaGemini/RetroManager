// The site's language. Loaded in each page's <head>, after theme.js. English is
// the pages' own; any other language is a phrasebook: the interface's words
// (menus, buttons, headings, labels) are swapped for its own as the page draws
// them. Only text that is exactly a known phrase changes, so game names,
// descriptions and anything else you've written are left as they are; a part
// of a page can opt out with translate="no". The choice is remembered in this
// browser as retromanager.language.
//
// More languages can come from common/language-packs.js, loaded just before
// this: each pushes {key, label, lang, phrases, patterns, noCaps} onto
// window.RMLanguagePacks (noCaps: its capitals are letters of their own, so
// nothing is put in capitals while it's on).
(function () {
    const LANGUAGES = [
        { key: 'en', label: 'English', lang: 'en' },
        { key: 'cockney', label: 'Cockney', lang: 'en-GB' },
    ];

    // Whole phrases, as the page shows them (trimmed). Keys are English.
    const PHRASES = {
        cockney: {
            // Pages and header
            'Library': "Lib'ry", 'Console': 'Telly', 'Bookcase': 'Shelf', 'Timeline': 'Bygones',
            'Stats': 'Numbers', 'Add games': 'Bung In Games', 'Tools': 'Me Tools', 'Theme': 'Colours',
            'Profiles': "Who's Who", 'Language': 'Lingo', 'Colour theme': 'Colours', 'Open in Console': 'Open on the Telly',
            'Sign out': "'Op It", 'Sign in': 'Come In, Then', 'Settings': 'Gubbins', 'This phone': 'Me Dog and Bone',
            // Tools
            'Library health': "Is It Poorly?", 'Background scrape': 'Fetch the Lot', 'Media viewer': 'Pictures, Innit',
            'Play history': 'Wot You Played', 'Achievement overview': 'Gongs', 'Achievements': 'Gongs', 'Fill and media': "Fillin' an' Pictures", 'Library care': "Lookin' After the Lot", 'Playing': "'Avin' a Go", 'Setup': 'Sortin\' It Out', 'Missing in series': "Wot's Missin'",
            'Collections': 'Me Collections', 'ROM check': 'Check Me ROMs', 'Duplicates': 'Double Trouble',
            'Saves': 'Me Saves', 'Storage': 'The Lock-Up', 'Profiles and login': "Who's Who",
            // Buttons
            'Close': 'Shut It', 'Cancel': 'Leave It Out', 'Save': 'Stash It', 'Delete': 'Bin It', 'Delete all': 'Bin the Lot',
            'Play': "'Ave a Go", '▶ Play': "▶ 'Ave a Go", 'Scrape': 'Go Fetch', 'Scan': 'Give It a Once-Over', 'Edit': 'Fiddle With It',
            'Add': 'Bung In', 'Filters': 'Sort It Out', 'Back': 'Back Up, Guv', '‹ Back': '‹ Back Up, Guv', 'BACK': 'BACK UP, GUV',
            '‹ Games': '‹ Me Games', '‹ Systems': '‹ Me Machines', '‹ Home': '‹ Home Sweet Home', 'Compare': 'Weigh It Up',
            'Search': "'Ave a Butcher's", 'Apply': 'Do It', 'Yes': 'Too Right', 'No': 'Nah', 'OK': 'Sorted',
            'Select All Fields': 'Take the Lot', 'Deselect All': 'None of It', 'Clear them': 'Clear Off', 'Keep them': 'Keep Hold',
            'Pick all shown': "Grab Wot's Showin'", 'Tick all': 'Tick the Lot', 'Empty it': 'Clear It Out',
            'Show what\'s different': "Wot's Changed?", 'Put this copy back': 'Put It Back, Then', 'Delete it': 'Bin It',
            'Open': "'Ave a Look", 'Open Duplicates': 'Open Double Trouble', 'Find matches': 'Find a Match',
            'Download all (zip)': 'Take the Lot (zip)', 'Previous': 'Back One', 'Next ›': 'Next Up ›', '‹ Prev': '‹ Back One',
            // Console
            'Continue playing': "Carry On Playin'", 'Recently added': 'Fresh In', 'Installed': 'On the Dog and Bone',
            'Systems': 'Me Machines', 'Favourites': 'Me Faves', 'Surprise me': 'Go On, Surprise Me',
            'Console settings': 'Telly Gubbins', 'Sort': 'Sort', 'View': 'Look', 'Rows': 'Rows',
            'A game from any system': 'Any Old Game',
            // Play status
            '☆ Favourite': '☆ Proper Fave', '★ Favourite': '★ Proper Fave', 'Favourite': 'Proper Fave',
            '‣ Playing': "‣ On It", 'Playing': 'On It', '🕓 Backlog': "🕓 Gettin' Round To It", 'Backlog': "Gettin' Round To It",
            '✔ Finished': '✔ Done and Dusted', 'Finished': 'Done and Dusted', 'Collections ▾': 'Collections ▾',
            // Game details
            'Developer': 'Who Made It', 'Publisher': 'Who Flogged It', 'Released': 'Came Out', 'Genre': 'Wot Sort',
            'Players': "'Ow Many", 'Rating': 'Marks Out of Ten', 'Description': 'The Story', 'Series': 'The Lot of Em',
            'Manual': 'The Instructions', 'Achievements': 'Gongs', 'Media': 'Pictures', 'File': 'The File',
            // Library
            'Systems ': 'Me Machines', 'Sort: Name': 'Sort: Name', 'Search games  ( / )': "'Ave a Butcher's  ( / )",
            'Search games ( / )': "'Ave a Butcher's ( / )", 'Search systems and games': "'Ave a Butcher's...",
            'Select a game to view and edit metadata': 'Pick a Game, Any Game', 'Scrape...': 'Go Fetch...',
            'Add to a collection...': 'Bung It in a Collection...', 'Work on many games at once': 'Do a Load at Once',
            'Find a game...': "'Ave a Butcher's...", 'All systems': 'Every Machine', 'All games': 'Every Game',
            // Words that come and go
            'Loading...': "'Ang About...", 'Loading…': "'Ang About…", 'Measuring...': "Countin' Up...", 'Comparing…': "Weighin' Up…",
            'Checking every system...': "Checkin' Every Machine...", 'Nothing here.': "Nuffin' 'Ere.", 'No games here.': "Nuffin' 'Ere, Guv.",
            'No duplicates.': 'No Double Trouble.', 'Empty': 'Bare', 'Deleting…': "Binnin' It…",
            // Sorting and showing
            'Sort: Name': 'Sort: By Moniker', 'Sort: Most games': 'Sort: Most Games', 'Sort: Most missing metadata': 'Sort: Most Gaps',
            'Sort: Maker': "Sort: Who Made 'Em", 'Sort: Generation': 'Sort: How Old', 'Bulk ▾': 'Job Lot ▾',
            'Oldest first': "Old 'Uns First", 'Newest first': "New 'Uns First", 'File name': "Wot the File's Called", 'Name': 'Moniker',
            'Most games': 'Most Games', 'Most missing metadata': 'Most Gaps', 'Maker': "Who Made 'Em", 'Generation': 'How Old',
            'One row': 'One Row', 'Rows by generation': 'Rows by How Old', 'Rows by maker': "Rows by Who Made 'Em",
            'Sort the systems by': 'Sort the Machines By', 'Show the systems as': 'Show the Machines As',
            'System tiles show': 'Machine Tiles Show', 'Game tiles show': 'Game Tiles Show', 'Game tiles are': 'Game Tiles Are',
            'Drawn tiles': 'Drawn Ones', 'Switch theme pictures': 'Switch Pikchas', 'As wide as the picture': 'As Wide as the Pikcha',
            'A game without that picture shows another it has.': "No pikcha? It'll show summat else it's got.",
            // Kinds of picture
            'Picture:': 'Pikcha:', 'Mix': 'Mix-Up', '2D box': 'Flat Box', '3D box': 'Fat Box', 'Image': 'Pikcha', 'Screenshot': 'Snap',
            'Title screen': "Openin' Screen", 'Fan art': 'Fan Doodles', 'Logo': 'Logo', 'Box 2D': 'Flat Box', 'Box 3D': 'Fat Box',
            'Wheel': 'Logo', 'Spine': 'Spine', 'Cart / disc': 'Cart / Disc', 'Fanart': 'Fan Doodles',
            // Console's first screen
            'No profiles yet': "No One 'Ere Yet", 'Search every system': "'Ave a Butcher's Everywhere", 'Something to play': 'Summat to Play',
            'A game picked at random': 'Any Old Game', 'choose': 'pick', 'open': 'open up', 'nothing to show in it yet': "nuffin' in it yet",
        },
    };
    // Phrases with a number or name in them: [pattern, replacement]
    const PATTERNS = {
        cockney: [
            [/^GAMES \((\d+)\)$/, 'ME GAMES ($1)'],
            [/^Games \((\d+)\)$/, 'Me Games ($1)'],
            [/^(\d+) games?$/, '$1 games, guv'],
            [/^Scrape (\d*) ?picked$/, 'Go Fetch $1'],
            [/^Apply (\d+) games?$/, 'Do the $1, Then'],
            [/^Delete ticked \((.+)\)$/, 'Bin the Ticked Ones ($1)'],
            [/^Clear \((\d+)\)$/, 'Clear Off ($1)'],
        ],
    };

    (window.RMLanguagePacks || []).forEach(pack => {
        if (!pack || !pack.key || LANGUAGES.some(l => l.key === pack.key)) return;
        LANGUAGES.push({ key: pack.key, label: pack.label || pack.key, lang: pack.lang || pack.key, noCaps: !!pack.noCaps });
        PHRASES[pack.key] = pack.phrases || {};
        PATTERNS[pack.key] = pack.patterns || [];
    });

    const find = (key) => LANGUAGES.find(l => l.key === key) || LANGUAGES[0];
    const current = () => {
        try { return find(localStorage.getItem('retromanager.language')); } catch (e) { return LANGUAGES[0]; }
    };
    // Changing language draws the page again (the English words are the page's own)
    const set = (key) => {
        const language = find(key);
        try { localStorage.setItem('retromanager.language', language.key); } catch (e) {}
        if (language.key !== active.key) window.location.reload();
        return language;
    };

    const active = current();
    const phrases = PHRASES[active.key] || {};
    const patterns = PATTERNS[active.key] || [];
    const say = (text) => {
        const words = text.trim();
        if (!words) return null;
        let said = Object.prototype.hasOwnProperty.call(phrases, words) ? phrases[words] : null;
        if (said === null) {
            const rule = patterns.find(([pattern]) => pattern.test(words));
            if (rule) said = words.replace(rule[0], rule[1]);
        }
        if (said === null || said === words) return null;
        return text.replace(words, said);
    };
    const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE']);
    const skipped = (el) => !el || SKIP.has(el.tagName) || el.isContentEditable || !!el.closest('[translate="no"]');
    const ATTRIBUTES = ['placeholder', 'title', 'aria-label'];
    const translateNode = (node) => {
        if (node.nodeType === Node.TEXT_NODE) {
            if (skipped(node.parentElement)) return;
            const said = say(node.data);
            if (said !== null) node.data = said;
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE || skipped(node)) return;
        ATTRIBUTES.forEach(name => {
            const value = node.getAttribute(name);
            const said = value && say(value);
            if (said) node.setAttribute(name, said);
        });
        if (node.tagName === 'OPTION' || node.tagName === 'BUTTON' || node.childNodes.length) {
            const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
            for (let n = walker.nextNode(); n; n = walker.nextNode()) {
                if (n.nodeType === Node.TEXT_NODE) {
                    if (skipped(n.parentElement)) continue;
                    const said = say(n.data);
                    if (said !== null) n.data = said;
                } else if (!skipped(n)) {
                    ATTRIBUTES.forEach(name => {
                        const value = n.getAttribute(name);
                        const said = value && say(value);
                        if (said) n.setAttribute(name, said);
                    });
                }
            }
        }
    };

    if (active.key !== 'en') {
        document.documentElement.lang = active.lang;
        if (active.noCaps) document.documentElement.dataset.noCaps = '';
        const start = () => {
            translateNode(document.body);
            new MutationObserver(changes => {
                for (const change of changes) {
                    if (change.type === 'characterData') translateNode(change.target);
                    else if (change.type === 'attributes') translateNode(change.target);
                    else change.addedNodes.forEach(translateNode);
                }
            }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRIBUTES });
        };
        if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
    }

    window.RMLanguage = { LANGUAGES, current, set, say: (text) => say(text) ?? text };
})();
