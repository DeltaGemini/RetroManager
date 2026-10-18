// Builds the frontend for the container image (run by the Dockerfile; nothing
// in the repository changes). The pages in frontend/ load React from a CDN and
// compile their JSX in the browser, which is handy for development but slow,
// and breaks when the internet is down. This:
//   - copies React and ReactDOM into frontend/vendor/ and points each page at them
//   - compiles each page's JSX (a <script type="text/babel"> block, or the
//     frontend/src/ files it loads) to plain JavaScript, all of a page's in one
//     file, frontend/js/<page>.js, and removes the in-browser compiler
//   - adds ?v=<its contents' stamp> to the page's own scripts and stylesheets,
//     so the browser can keep them until they change (backend/routes/pages.py)
//   - writes a gzipped copy beside every script, stylesheet and SVG, sent to
//     browsers that take it
// Usage: node build_frontend.js <frontend dir>
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const zlib = require('zlib');
const babel = require('@babel/core');

const root = path.resolve(process.argv[2] || 'frontend');
const vendorDir = path.join(root, 'vendor');
const jsDir = path.join(root, 'js');
fs.mkdirSync(vendorDir, { recursive: true });
fs.mkdirSync(jsDir, { recursive: true });

const stamp = (text) => crypto.createHash('sha1').update(text).digest('hex').slice(0, 10);

// CDN script -> the file it's replaced with (null: removed)
// (the pages name an exact version, for development; the image's is the Dockerfile's)
const VENDOR = [
    [/<script[^>]*src="https:\/\/unpkg\.com\/react@18[\d.]*\/umd\/react\.production\.min\.js"[^>]*><\/script>/, 'react/umd/react.production.min.js', 'react.production.min.js'],
    [/<script[^>]*src="https:\/\/unpkg\.com\/react-dom@18[\d.]*\/umd\/react-dom\.production\.min\.js"[^>]*><\/script>/, 'react-dom/umd/react-dom.production.min.js', 'react-dom.production.min.js'],
    [/[ \t]*<script[^>]*src="https:\/\/cdn\.jsdelivr\.net\/npm\/@babel\/standalone@7[\d.]*\/babel\.min\.js"[^>]*><\/script>\n?/, null, null],
];
// The app's pages (old copies left in frontend/ aren't built or served)
const PAGES = ['index.html', 'console.html', 'shelf.html', 'timeline.html', 'stats.html', 'import.html'];
const INLINE_JSX = /<script type="text\/babel">([\s\S]*?)<\/script>/g;
const JSX_FILE = /<script type="text\/babel" src="\/src\/([^"]+)\.jsx"><\/script>/g;

const compile = (jsx, filename) => babel.transformSync(jsx, {
    presets: [['@babel/preset-react', { runtime: 'classic' }]],
    filename, babelrc: false, configFile: false, compact: false, comments: false,
}).code;

let built = 0;
for (const file of PAGES) {
    const source = fs.readFileSync(path.join(root, file), 'utf8');
    const page = path.basename(file, '.html').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
    let html = source;

    for (const [pattern, modulePath, name] of VENDOR) {
        if (!pattern.test(html)) throw new Error(`${file}: expected script tag not found (${pattern})`);
        if (modulePath) {
            const code = fs.readFileSync(path.join(__dirname, 'node_modules', modulePath));
            fs.writeFileSync(path.join(vendorDir, name), code);
            html = html.replace(pattern, `<script src="/vendor/${name}?v=${stamp(code)}"></script>`);
        } else {
            html = html.replace(pattern, '');
        }
    }

    // A page's JSX, in the order it's loaded, as one script where the first was. They sit together at
    // the end of each page, and share one global scope as separate scripts did (a name declared twice
    // would stop the page: checked below)
    let blocks = 0;
    const parts = [];
    const BLOCK = new RegExp(`[ \\t]*(?:${JSX_FILE.source}|${INLINE_JSX.source})\\n?`, 'g');
    html = html.replace(BLOCK, (whole, name, jsx) => {
        blocks += 1;
        const label = name ? `${name}.jsx` : `${file} (its own script)`;
        parts.push(`// ---- ${label} ----\n` + compile(name ? fs.readFileSync(path.join(root, 'src', `${name}.jsx`), 'utf8') : jsx, label));
        return blocks === 1 ? '\u0000BUNDLE\u0000' : '';
    });
    if (blocks) {
        const code = parts.join('\n');
        new Function(code);   // throws on a name declared in two of the files, as the browser would
        fs.writeFileSync(path.join(jsDir, `${page}.js`), code);
        html = html.replace('\u0000BUNDLE\u0000', `    <script src="/js/${page}.js?v=${stamp(code)}"></script>\n`);
    }
    // The page's own scripts and stylesheets, stamped
    html = html.replace(/(<(?:script|link)\b[^>]*?\b(?:src|href)=")(\/[^"?#]+\.(?:js|css))(")/g, (whole, before, url, after) => {
        const local = path.join(root, url);
        return fs.existsSync(local) ? `${before}${url}?v=${stamp(fs.readFileSync(local))}${after}` : whole;
    });
    if (!blocks) throw new Error(`${file}: no JSX block found`);
    if (html.includes('text/babel') || html.includes('unpkg.com') || html.includes('jsdelivr')) {
        throw new Error(`${file}: still loads something from a CDN or needs the in-browser compiler`);
    }
    fs.writeFileSync(path.join(root, file), html);
    built += 1;
    console.log(`built ${file}: ${blocks} script(s)`);
}
if (!built) throw new Error('No pages were built');

// Gzipped copies, for browsers that take them (most of the size is text)
let zipped = 0;
const zipAll = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) { if (!['node_modules', 'src'].includes(entry.name)) zipAll(full); continue; }
        if (!/\.(js|css|svg|html|json|webmanifest)$/.test(entry.name)) continue;
        const data = fs.readFileSync(full);
        if (data.length < 1024) continue;
        fs.writeFileSync(`${full}.gz`, zlib.gzipSync(data, { level: 9 }));
        zipped += 1;
    }
};
zipAll(root);
console.log(`gzipped ${zipped} files`);
