// Rendert Animationen aus web/anims.js nach render/<name>/NN.png (+ _id.png für die Innenlinien).
// Aufruf: node render.mjs stehen gehen ...   (ohne Namen: alle)
// Modell: MODELL=<pfad.glb>, Standard ../../quellen/dmnt9000_3d/modell/dmnt9000.glb
import {chromium} from 'playwright';
import http from 'http'; import fs from 'fs'; import path from 'path'; import {fileURLToPath} from 'url';
const hier = path.dirname(fileURLToPath(import.meta.url));
const web = path.join(hier, 'web');
const modell = process.env.MODELL || path.join(hier, '..', '..', 'quellen', 'dmnt9000_3d', 'modell', 'dmnt9000.glb');
if (!fs.existsSync(modell)) { console.error('Modell fehlt: ' + modell); process.exit(1); }
const typen = {'.html': 'text/html', '.js': 'text/javascript', '.glb': 'model/gltf-binary', '.json': 'application/json'};
const port = +(process.env.PORT || 8766);
const srv = http.createServer((q, s) => {
  const url = decodeURIComponent(q.url.split('?')[0]);
  let p = url.startsWith('/node_modules/') ? path.join(hier, url) : url === '/mascot.glb' ? modell : path.join(web, url);
  fs.readFile(p, (e, b) => {
    if (e) { s.writeHead(404); s.end(); return; }
    s.writeHead(200, {'Content-Type': typen[path.extname(p)] || 'application/octet-stream', 'Cache-Control': 'no-store'}); s.end(b);
  });
}).listen(port);
const opt = {args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']};
if (process.env.CHROMIUM) opt.executablePath = process.env.CHROMIUM;
const b = await chromium.launch(opt);
const pg = await b.newPage();
pg.on('pageerror', (e) => console.log('Fehler:', e.message));
await pg.goto(`http://localhost:${port}/rig.html`);
await pg.waitForFunction('window.ready', null, {timeout: 300000});
let namen = process.argv.slice(2);
if (!namen.length) namen = await pg.evaluate(() => Object.keys(window.ANIM).filter((n) => !n.startsWith('test')));
for (const n of namen) {
  const r = await pg.evaluate((n) => window.renderAnim(n), n);
  const ziel = path.join(hier, 'render', n); fs.mkdirSync(ziel, {recursive: true});
  r.frames.forEach((f, i) => {
    const nr = String(i).padStart(2, '0');
    fs.writeFileSync(path.join(ziel, nr + '.png'), Buffer.from(f.bild.split(',')[1], 'base64'));
    if (f.id) fs.writeFileSync(path.join(ziel, nr + '_id.png'), Buffer.from(f.id.split(',')[1], 'base64'));
  });
  console.log(n, `${r.w}x${r.h}`, r.frames.length);
}
await b.close(); srv.close();
