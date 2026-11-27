// Prepara la cartella www dell'app: la pagina del telefono del sito (site/telefono.html, jpeg_prog.js) e il Web Bluetooth per Android (src/entry.js + ble-shim.js, con esbuild).
//   node scripts/build-www.js
const fs = require('fs');
const path = require('path');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '..');
const site = path.resolve(root, '..', 'site');
const www = path.join(root, 'www');
fs.rmSync(www, { recursive: true, force: true });
fs.mkdirSync(www, { recursive: true });

let html = fs.readFileSync(path.join(site, 'telefono.html'), 'utf8');
if (!html.includes('<script src="jpeg_prog.js"></script>')) throw new Error('telefono.html: manca il tag di jpeg_prog.js');
html = html.replace('<script src="jpeg_prog.js"></script>', '<script src="shim.js"></script>\n<script src="jpeg_prog.js"></script>');   // il Bluetooth deve esserci prima della pagina
html = html.split('href="firmware-v3.html"').join('href="https://iu5hju.github.io/VoLoRa-v3/firmware-v3.html"');       // fuori dall'app questa pagina non c'e'
fs.writeFileSync(path.join(www, 'index.html'), html);
fs.copyFileSync(path.join(site, 'jpeg_prog.js'), path.join(www, 'jpeg_prog.js'));
esbuild.buildSync({ entryPoints: [path.join(root, 'src', 'entry.js')], bundle: true, format: 'iife', minify: false, outfile: path.join(www, 'shim.js'), logLevel: 'warning' });
console.log('www pronta: ' + fs.readdirSync(www).map(f => f + ' ' + fs.statSync(path.join(www, f)).size).join(', '));
