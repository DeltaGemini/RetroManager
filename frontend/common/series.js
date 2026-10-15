// Works out which series (franchise) each game belongs to, from its name.
// Shared by the Timeline (series filter and lines) and the Bookcase (a shelf
// per franchise). Plain JavaScript, loaded after header.js:
//     const series = RM.series.assign(games);   // games need a `title`
// Each game gets `seriesKey` (or null); the result lists the series found.
(function () {
    const plain = (text) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

    // "Star Wars: Rogue Leader - …" -> "Star Wars"; sequel numbers come off
    // ("Castlevania II: …" -> "Castlevania"). Names without a colon join a series
    // they start with ("Pokémon Snap" -> Pokémon). Series need two or more games.
    const seriesPrefix = (name) => {
        const i = name.indexOf(': ');
        if (i < 1) return null;
        return name.slice(0, i).replace(/\s+(\d+|[IVX]+)$/, '').trim() || null;
    };
    function assignSeries(games) {
        const labels = {};
        games.forEach(g => {
            const prefix = seriesPrefix(g.title);
            if (!prefix) return;
            const key = plain(prefix);
            (labels[key] = labels[key] || {})[prefix] = ((labels[key] || {})[prefix] || 0) + 1;
            g.seriesKey = key;
        });
        const keys = Object.keys(labels).sort((a, b) => b.length - a.length);
        games.forEach(g => {
            if (g.seriesKey) return;
            const title = plain(g.title);
            const key = keys.find(k => title === k || title.startsWith(k + ' ') || title.startsWith(k + ':'));
            if (key) g.seriesKey = key;
        });
        const counts = {};
        games.forEach(g => { if (g.seriesKey) counts[g.seriesKey] = (counts[g.seriesKey] || 0) + 1; });
        const series = Object.keys(counts).filter(k => counts[k] >= 2).map(k => ({
            key: k,
            // The spelling most games use ("Pokémon" over "Pokemon")
            label: Object.entries(labels[k]).sort((a, b) => b[1] - a[1])[0][0],
            count: counts[k],
        })).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
        const valid = new Set(series.map(s => s.key));
        games.forEach(g => { if (!valid.has(g.seriesKey)) g.seriesKey = null; });
        return series;
    }

    window.RM = window.RM || {};
    window.RM.series = { plain, assign: assignSeries };
})();
