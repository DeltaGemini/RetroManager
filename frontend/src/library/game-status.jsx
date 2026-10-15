// Play statuses, as the lists show them (a game's own status, star and collections
// are set in the Game Details panel: src/common/game-details.jsx).
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

const PLAY_STATUSES = [['playing', 'Playing', '▶'], ['backlog', 'Backlog', '🕓'], ['finished', 'Finished', '✔']];
const playStatusIcon = (status) => (PLAY_STATUSES.find(s => s[0] === status) || [])[2];
// The game list redraws when a game's status, star or collections change
const announceGameChange = () => window.dispatchEvent(new Event('retromanager:game-changed'));
