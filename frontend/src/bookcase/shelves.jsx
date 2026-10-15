// What each shelf holds: the shelf modes and sorting games onto shelves.
// Part of the Bookcase page (shelf.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// What each shelf holds
const SHELF_MODES = [
    { key: 'console', label: 'Shelves: Consoles' },
    { key: 'console-generation', label: 'Shelves: Consoles by generation' },
    { key: 'franchise', label: 'Shelves: Franchises' },
    { key: 'generation', label: 'Shelves: Generations' },
    { key: 'maker', label: 'Shelves: Manufacturers' },
    { key: 'status', label: 'Shelves: Play status' },
    { key: 'collection', label: 'Shelves: Collections' },
];
// Manufacturer shelves: the console makers, then computers, then the rest
const MAKER_ORDER = ['Nintendo', 'Sega', 'Sony', 'Atari', 'Computers', 'Other'];
const byText = (a, b) => a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true });

// Sorts games into shelves for a mode: [{id, label, system?, heading?, games}].
// `system` is set on a console's shelf (its picture goes on the label);
// `heading` is the group a console shelf sits under.
// Play-status shelves, in order; favourites get a shelf of their own
const STATUS_SHELVES = [['playing', 'Playing'], ['backlog', 'Backlog'], ['finished', 'Finished']];

function groupIntoShelves(games, mode, series, collections) {
    const shelves = {};
    const add = (id, shelf, game) => { (shelves[id] = shelves[id] || { id, ...shelf, games: [] }).games.push(game); };
    games.forEach(g => {
        if (mode === 'status') {
            // A game can stand on two of these: its status, and Favourites
            if (g.favorite) add('favourites', { label: 'Favourites', rank: 0 }, g);
            const at = STATUS_SHELVES.findIndex(([key]) => key === g.playStatus);
            if (at >= 0) add(`status:${g.playStatus}`, { label: STATUS_SHELVES[at][1], rank: at + 1 }, g);
        } else if (mode === 'collection') {
            (collections || []).forEach((c, at) => { if (c.games.includes(g.stateKey)) add(`collection:${c.id}`, { label: c.name, rank: at }, g); });
        } else if (mode === 'franchise') {
            const found = g.seriesKey && series[g.seriesKey];
            add(found ? `series:${g.seriesKey}` : 'other', found ? { label: found.label, rank: 0 } : { label: 'Other games', rank: 1 }, g);
        } else if (mode === 'generation') {
            const generation = RM.systems.generationGroup(g.system);
            add(`generation:${generation.rank}`, { label: generation.label, rank: generation.rank }, g);
        } else if (mode === 'maker') {
            const maker = RM.systems.makerOf(g.system);
            add(`maker:${maker}`, { label: maker, rank: MAKER_ORDER.indexOf(maker) }, g);
        } else {
            const generation = RM.systems.generationGroup(g.system);
            add(`system:${g.system}`, { label: g.fullName, system: g.system,
                rank: mode === 'console-generation' ? generation.rank : 0,
                heading: mode === 'console-generation' ? generation.label : null }, g);
        }
    });
    return Object.values(shelves).sort((a, b) => a.rank - b.rank || (mode === 'collection' ? 0 : byText(a.label, b.label)));
}
