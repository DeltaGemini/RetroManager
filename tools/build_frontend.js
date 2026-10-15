// Builds the frontend for the container image (run by the Dockerfile; nothing
// in the repository changes). The pages in frontend/ load React from a CDN and
// compile their JSX in the browser, which is handy for development but slow,
// and breaks when the internet is down. This:
//   - copies React and ReactDOM into frontend/vendor/ and points each page at them
//   - compiles each page's JSX (a <script type="text/babel"> block, or the
//     frontend/src/ files it loads) to plain JavaScript in frontend/js/ and
//     removes the in-browser compiler
// Usage: node build_frontend.js <frontend dir>
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const babel = require('@babel/core');

const root = path.resolve(process.argv[2] || 'frontend');
const vendorDir = path.join(root, 'vendor');
const jsDir = path.join(root, 'js');
fs.mkdirSync(vendorDir, { recursive: true });
fs.mkdirSync(jsDir, { recursive: true });

const stamp = (text) => crypto.createHash('sha1').update(text).digest('hex').slice(0, 10);

// CDN script -> the file it's replaced with (null: removed)
const VENDOR = [
    [/<script[^>]*src="https:\/\/unpkg\.com\/react@18\/umd\/react\.production\.min\.js"[^>]*><\/script>/, 'react/umd/react.production.min.js', 'react.production.min.js'],
    [/<script[^>]*src="https:\/\/unpkg\.com\/react-dom@18\/umd\/react-dom\.production\.min\.js"[^>]*><\/script>/, 'react-dom/umd/react-dom.production.min.js', 'react-dom.production.min.js'],
    [/[ \t]*<script[^>]*src="https:\/\/cdn\.jsdelivr\.net\/npm\/@babel\/standalone@7\/babel\.min\.js"[^>]*><\/script>\n?/, null, null],
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

    let blocks = 0;
    html = html.replace(JSX_FILE, (_, name) => {
        blocks += 1;
        const code = compile(fs.readFileSync(path.join(root, 'src', `${name}.jsx`), 'utf8'), `${name}.jsx`);
        fs.mkdirSync(path.dirname(path.join(jsDir, `${name}.js`)), { recursive: true });
        fs.writeFileSync(path.join(jsDir, `${name}.js`), code);
        return `<script src="/js/${name}.js?v=${stamp(code)}"></script>`;
    });
    html = html.replace(INLINE_JSX, (_, jsx) => {
        blocks += 1;
        const name = `${page}.js`;
        const code = compile(jsx, file);
        fs.writeFileSync(path.join(jsDir, name), code);
        return `<script src="/js/${name}?v=${stamp(code)}"></script>`;
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
