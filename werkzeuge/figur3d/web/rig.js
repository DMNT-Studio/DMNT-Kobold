// DMNT 9000 – 3D-Rig: Raute/Handschuhe/Schuhe aus dem Meshy-Modell, Arme/Beine als Schläuche.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';

const V = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const DEG = Math.PI / 180;
const GROUND = -0.952;               // Sohle im Modell

// ---------- deterministischer Zufall ----------
export function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
}

// ---------- Renderer / Szene ----------
export const W0 = 760, H0 = 720;
export const PX = 280;               // Pixel je Modelleinheit (fest für alle Animationen)
export const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, preserveDrawingBuffer: true});
renderer.setPixelRatio(1);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping;
document.body.appendChild(renderer.domElement);

export const scene = new THREE.Scene();
const hemi = new THREE.HemisphereLight(0xffffff, 0x50586a, 1.55); scene.add(hemi);
const key = new THREE.DirectionalLight(0xffffff, 2.1); key.position.set(2.5, 4, 5); scene.add(key);
const rim = new THREE.DirectionalLight(0x9fb8ff, 0.9); rim.position.set(-4, 2, -3); scene.add(rim);
const fill = new THREE.DirectionalLight(0xffffff, 0.45); fill.position.set(-3, 0.5, 4); scene.add(fill);

export const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 50);

// ---------- Figur ----------
export const root = new THREE.Group(); scene.add(root);          // Weltposition / Blickrichtung
export const figur = new THREE.Group(); root.add(figur);         // Modell, Boden = 0
figur.position.y = -GROUND;
export const koerper = new THREE.Group(); figur.add(koerper);     // Drehpunkt Hüfte
const teile = {};          // name -> {gruppe, mesh}
let P = null;              // parts.json
const R = {};              // Ruhe-Werte

const matArm = new THREE.MeshStandardMaterial({color: new THREE.Color().setRGB(11/255, 11/255, 12/255, THREE.SRGBColorSpace), roughness: 0.45, metalness: 0});
const matBein = new THREE.MeshStandardMaterial({color: new THREE.Color().setRGB(0.96, 0.965, 0.965, THREE.SRGBColorSpace), roughness: 0.3, metalness: 0});
const matHand = new THREE.MeshStandardMaterial({color: new THREE.Color().setRGB(112/255, 112/255, 114/255, THREE.SRGBColorSpace), roughness: 0.55, metalness: 0});

const ARM_R = 0.054, BEIN_R = 0.079;
const ARM_L = 0.44, BEIN_L = 0.54;

function teilGeometrie(geo, labels, wahl) {
  const idx = geo.index.array;
  const neu = [];
  for (let f = 0; f < labels.length; f++) if (wahl(f)) neu.push(idx[3*f], idx[3*f+1], idx[3*f+2]);
  const g = new THREE.BufferGeometry();
  for (const k of Object.keys(geo.attributes)) g.setAttribute(k, geo.attributes[k]);
  g.setIndex(neu);
  return g;
}

export async function laden() {
  const [gltf, lab, parts] = await Promise.all([
    new GLTFLoader().loadAsync('mascot.glb'),
    fetch('labels.bin').then(r => r.arrayBuffer()).then(b => new Uint8Array(b)),
    fetch('parts.json').then(r => r.json()),
  ]);
  P = parts;
  let orig; gltf.scene.traverse(o => { if (o.isMesh) orig = o; });
  const geo = orig.geometry, mat = orig.material;
  const pos = geo.attributes.position.array, idx = geo.index.array;
  const cy = (f) => (pos[3*idx[3*f]+1] + pos[3*idx[3*f+1]+1] + pos[3*idx[3*f+2]+1]) / 3;

  R.hip = new THREE.Vector3(0, -0.19, -0.066);
  koerper.position.copy(R.hip);
  const body = new THREE.Mesh(teilGeometrie(geo, lab, f => lab[f] === 0), mat);
  body.position.copy(R.hip).multiplyScalar(-1);
  koerper.add(body);
  teile.body = {mesh: body};

  for (const [n, k, anker] of [['hL', 1, 'gloveL'], ['hR', 2, 'gloveR'], ['fL', 3, 'shoeL'], ['fR', 4, 'shoeR']]) {
    const a = V(P[anker].top);
    const g = new THREE.Group(); g.position.copy(a); figur.add(g);
    if (k <= 2) {
      const grenze = a.y - 0.10;
      const stulpe = new THREE.Mesh(teilGeometrie(geo, lab, f => lab[f] === k && cy(f) > grenze), mat);
      const hand = new THREE.Mesh(teilGeometrie(geo, lab, f => lab[f] === k && cy(f) <= grenze), mat);
      stulpe.position.copy(a).multiplyScalar(-1); hand.position.copy(a).multiplyScalar(-1);
      g.add(stulpe, hand);
      const faust = faustBauen(k === 1 ? 1 : -1);
      g.add(faust.gruppe);
      teile[n] = {gruppe: g, hand, stulpe, faust, seite: k === 1 ? -1 : 1};
    } else {
      const m = new THREE.Mesh(teilGeometrie(geo, lab, f => lab[f] === k), mat);
      m.position.copy(a).multiplyScalar(-1); g.add(m);
      teile[n] = {gruppe: g, mesh: m, seite: k === 3 ? -1 : 1};
    }
    R[n] = {p: a.clone()};
  }
  // Schulter (im Körperraum, Modellkoordinaten) und Hüfte
  R.sL = new THREE.Vector3(-0.47, 0.272, -0.086); R.sR = new THREE.Vector3(0.47, 0.272, -0.086);
  // Hüfte genau auf der Achse der Original-Beine (dort ist die Öffnung in der Raute)
  for (const [n, leg] of [['bL', 'legL'], ['bR', 'legR']]) {
    const a = V(P[leg].top), b = V(P[leg].bot);
    const t = (-0.06 - a.y) / (b.y - a.y);
    R[n] = a.clone().lerp(b, t);
    R[n + 'dir'] = b.clone().sub(a).normalize();
  }
  for (const n of ['aL', 'aR', 'lL', 'lR']) {
    const m = new THREE.Mesh(new THREE.BufferGeometry(), n[0] === 'a' ? matArm : matBein);
    figur.add(m); teile[n] = {mesh: m};
  }
  requisitenBauen();
  return R;
}

// ---------- Faust mit Daumen (eigene Geometrie, Farbe wie Handschuh) ----------
function faustBauen(innen) {   // innen: Richtung zum Körper in x (+1 für linke Hand)
  const g = new THREE.Group();
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.13, 32, 20), matHand);
  ball.scale.set(1.0, 1.08, 0.95); ball.position.set(0, -0.2, 0.03); g.add(ball);
  for (let i = 0; i < 4; i++) {        // Fingerknöchel
    const k = new THREE.Mesh(new THREE.SphereGeometry(0.052, 20, 14), matHand);
    k.position.set((i - 1.5) * 0.058, -0.27 + Math.abs(i - 1.5) * 0.012, 0.115); g.add(k);
  }
  const daumen = new THREE.Group(); daumen.position.set(innen * 0.09, -0.15, 0.08); g.add(daumen);
  const d = new THREE.Mesh(new THREE.CapsuleGeometry(0.043, 0.09, 8, 16), matHand);
  d.position.y = 0.075; daumen.add(d);
  g.visible = false;
  return {gruppe: g, daumen};
}

// ---------- Schläuche ----------
function schlauch(P0, t0, P3, t3, B, L) {
  const ch = P3.clone().sub(P0); const d = ch.length(); const c = ch.clone().normalize();
  let sag = d < L ? Math.sqrt(Math.max(0, (L/2)**2 - (d/2)**2)) * 0.95 : 0;
  const bp = B.clone().sub(c.clone().multiplyScalar(B.dot(c)));
  if (bp.lengthSq() < 1e-6) bp.set(0, 0, 1); bp.normalize();
  const M = P0.clone().add(P3).multiplyScalar(0.5).add(bp.multiplyScalar(sag));
  const h1 = Math.max(0.05, P0.distanceTo(M) * 0.42), h2 = Math.max(0.05, M.distanceTo(P3) * 0.42);
  const k1 = new THREE.CubicBezierCurve3(P0, P0.clone().add(t0.clone().multiplyScalar(h1)), M.clone().sub(c.clone().multiplyScalar(h1 * 0.8)), M);
  const k2 = new THREE.CubicBezierCurve3(M, M.clone().add(c.clone().multiplyScalar(h2 * 0.8)), P3.clone().sub(t3.clone().multiplyScalar(h2)), P3);
  const pfad = new THREE.CurvePath(); pfad.add(k1); pfad.add(k2);
  return pfad;
}

// ---------- Requisiten ----------
export const req = {};
function radialTextur(stops) {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const x = c.getContext('2d'); const g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (const [o, col] of stops) g.addColorStop(o, col);
  x.fillStyle = g; x.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function noise3(x, y, z) {   // glatte Wertrauschfunktion
  const h = (i, j, k) => { let n = Math.sin(i * 127.1 + j * 311.7 + k * 74.7) * 43758.5453; return n - Math.floor(n); };
  const fx = Math.floor(x), fy = Math.floor(y), fz = Math.floor(z);
  const ux = x - fx, uy = y - fy, uz = z - fz; const s = (t) => t * t * (3 - 2 * t);
  let r = 0;
  for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) for (let k = 0; k < 2; k++)
    r += h(fx + i, fy + j, fz + k) * (i ? s(ux) : 1 - s(ux)) * (j ? s(uy) : 1 - s(uy)) * (k ? s(uz) : 1 - s(uz));
  return r;
}
function requisitenBauen() {
  // Transportbox (generisch, Sci-Fi): Metallgrau mit orangen Kanten
  const box = new THREE.Group();
  const kasten = new THREE.Mesh(new RoundedBoxGeometry(0.74, 0.46, 0.5, 4, 0.04),
    new THREE.MeshStandardMaterial({color: 0x5d6673, roughness: 0.5, metalness: 0.35}));
  box.add(kasten);
  const orange = new THREE.MeshStandardMaterial({color: 0xe89a2c, roughness: 0.45, metalness: 0.2});
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) {
    const k = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.52), orange); k.position.set(sx * 0.33, sy * 0.19, 0); box.add(k);
    const k2 = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.48, 0.1), orange); k2.position.set(sx * 0.33, 0, sy * 0.21); box.add(k2);
  }
  const rippe = new THREE.MeshStandardMaterial({color: 0x48505b, roughness: 0.55, metalness: 0.4});
  for (const y of [-0.08, 0.08]) { const r = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.035, 0.515), rippe); r.position.y = y; box.add(r); }
  const schild = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.11), new THREE.MeshStandardMaterial({color: 0xe8e8e0, roughness: 0.7}));
  schild.position.set(-0.1, 0, 0.252); box.add(schild);
  const streifen = new THREE.Mesh(new THREE.PlaneGeometry(0.16, 0.025), new THREE.MeshBasicMaterial({color: 0x222222}));
  streifen.position.set(-0.1, 0.02, 0.2525); box.add(streifen);
  const streifen2 = streifen.clone(); streifen2.scale.x = 0.6; streifen2.position.set(-0.13, -0.02, 0.2525); box.add(streifen2);
  for (const sx of [-1, 1]) {   // Griffmulden
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.06, 0.2), new THREE.MeshStandardMaterial({color: 0x1d2026, roughness: 0.8}));
    m.position.set(sx * 0.38, 0.06, 0); box.add(m);
  }
  box.visible = false; figur.add(box); req.box = box;

  // Mining-Pistole (generisch): Griff, Gehäuse, Emitter
  const pistole = new THREE.Group();
  const grau = new THREE.MeshStandardMaterial({color: 0x3a3f47, roughness: 0.5, metalness: 0.5});
  const hell = new THREE.MeshStandardMaterial({color: 0xd9dde2, roughness: 0.4, metalness: 0.3});
  const gelb = new THREE.MeshStandardMaterial({color: 0xf0a531, roughness: 0.4, metalness: 0.2});
  const griff = new THREE.Mesh(new RoundedBoxGeometry(0.08, 0.2, 0.1, 3, 0.02), grau); griff.position.set(0, -0.06, -0.02); griff.rotation.x = 0.25; pistole.add(griff);
  const gehaeuse = new THREE.Mesh(new RoundedBoxGeometry(0.13, 0.13, 0.36, 3, 0.03), gelb); gehaeuse.position.set(0, 0.07, 0.1); pistole.add(gehaeuse);
  const deckel = new THREE.Mesh(new RoundedBoxGeometry(0.135, 0.05, 0.22, 2, 0.015), hell); deckel.position.set(0, 0.145, 0.08); pistole.add(deckel);
  const akku = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.16, 16), grau); akku.rotation.x = Math.PI / 2; akku.position.set(0.075, 0.05, 0.03); pistole.add(akku);
  const lauf = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.12, 20), grau); lauf.rotation.x = Math.PI / 2; lauf.position.set(0, 0.07, 0.33); pistole.add(lauf);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.045, 0.012, 8, 24), new THREE.MeshStandardMaterial({color: 0xffc070, emissive: 0xff9020, emissiveIntensity: 0.4}));
  ring.position.set(0, 0.07, 0.39); pistole.add(ring); req.ring = ring;
  pistole.visible = false; scene.add(pistole); req.pistole = pistole;
  req.muendung = new THREE.Object3D(); req.muendung.position.set(0, 0.07, 0.4); pistole.add(req.muendung);

  // Stein mit Erz-Kristallen
  const stein = new THREE.Group();
  const sg = new THREE.IcosahedronGeometry(0.34, 3);
  const pa = sg.attributes.position; const cols = [];
  for (let i = 0; i < pa.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pa, i); const n = v.clone().normalize();
    const f = 1 + 0.32 * (noise3(n.x * 2.2 + 3, n.y * 2.2, n.z * 2.2) - 0.5) + 0.12 * (noise3(n.x * 6, n.y * 6 + 7, n.z * 6) - 0.5);
    v.copy(n.multiplyScalar(0.34 * f)); pa.setXYZ(i, v.x, v.y, v.z);
    const t = 0.55 + 0.45 * noise3(v.x * 9, v.y * 9, v.z * 9 + 2);
    cols.push(0.40 * t, 0.37 * t, 0.34 * t);
  }
  sg.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  sg.computeVertexNormals();
  const steinMat = new THREE.MeshStandardMaterial({vertexColors: true, roughness: 0.92, metalness: 0.05, flatShading: true});
  const sm = new THREE.Mesh(sg, steinMat); sm.scale.set(1.3, 0.82, 1.05); sm.position.y = 0.25; stein.add(sm);
  const kristall = new THREE.MeshStandardMaterial({color: 0x48d6c8, emissive: 0x1a8f86, emissiveIntensity: 0.35, roughness: 0.2, metalness: 0.1, flatShading: true});
  const kr = rng(7);
  req.kristalle = [];
  for (let i = 0; i < 6; i++) {
    const k = new THREE.Mesh(new THREE.OctahedronGeometry(0.05 + kr() * 0.04), kristall);
    const a = -0.9 + kr() * 2.2, e = 0.1 + kr() * 0.9;
    k.position.set(Math.cos(a) * 0.38 * Math.cos(e) * 1.2, 0.25 + Math.sin(e) * 0.26, Math.sin(a) * 0.3 * Math.cos(e) + 0.12);
    k.scale.set(0.7, 1.6, 0.7); k.rotation.set(kr() * 2, kr() * 3, kr() * 2); stein.add(k); req.kristalle.push(k);
  }
  stein.visible = false; scene.add(stein); req.stein = stein; req.steinMesh = sm;

  // Strahl, Glühen, Funken
  const strahlMat = new THREE.MeshBasicMaterial({color: 0xffa640, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false});
  const kernMat = new THREE.MeshBasicMaterial({color: 0xfff1c4, transparent: true, opacity: 1, depthWrite: false});
  req.strahl = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 16, 1, true), strahlMat);
  req.kern = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 12, 1, true), kernMat);
  scene.add(req.strahl, req.kern);
  const glowTex = radialTextur([[0, 'rgba(255,250,220,1)'], [0.25, 'rgba(255,190,90,0.9)'], [0.6, 'rgba(255,140,30,0.35)'], [1, 'rgba(255,120,0,0)']]);
  req.glowA = new THREE.Sprite(new THREE.SpriteMaterial({map: glowTex, transparent: true, depthWrite: false, depthTest: false}));
  req.glowB = req.glowA.clone(); req.glowB.material = req.glowA.material.clone();
  scene.add(req.glowA, req.glowB);
  req.funken = [];
  const fm = new THREE.MeshBasicMaterial({color: 0xffd27a});
  for (let i = 0; i < 14; i++) { const f = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.012, 1), fm); scene.add(f); req.funken.push(f); }
  req.brocken = [];
  for (let i = 0; i < 8; i++) {
    const b = new THREE.Mesh(new THREE.DodecahedronGeometry(0.07 + (i % 3) * 0.03), i % 3 === 0 ? kristall : new THREE.MeshStandardMaterial({color: 0x6a625a, roughness: 0.9, flatShading: true}));
    scene.add(b); req.brocken.push(b);
  }
  req.hitze = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), new THREE.MeshBasicMaterial({color: 0xffb060, transparent: true, opacity: 0.8, depthWrite: false}));
  scene.add(req.hitze);
  effekteAus();
}
function effekteAus() {
  for (const o of [req.strahl, req.kern, req.glowA, req.glowB, req.hitze, ...req.funken, ...req.brocken]) o.visible = false;
}

// ---------- Pose anwenden ----------
const e2q = (r) => new THREE.Quaternion().setFromEuler(new THREE.Euler((r?.[0] || 0) * DEG, (r?.[1] || 0) * DEG, (r?.[2] || 0) * DEG, 'YXZ'));

export function pose(p) {
  effekteAus();
  root.position.set(...(p.root?.p || [0, 0, 0]));
  root.rotation.set(0, (p.root?.yaw ?? 0) * DEG, 0);
  // Körper
  koerper.position.copy(R.hip).add(V(p.body?.p || [0, 0, 0]));
  koerper.quaternion.copy(e2q(p.body?.r));
  koerper.updateMatrix(); figur.updateMatrixWorld(true);
  const km = koerper.matrix;          // Körper -> Figur
  const kq = koerper.quaternion;
  // Hände / Füße
  for (const n of ['hL', 'hR', 'fL', 'fR']) {
    const t = teile[n], q = p[n] || {};
    const pos = V(q.p || [0, 0, 0]).add(R[n].p);
    let rot = e2q(q.r);
    if (n[0] === 'h' && p.haendeAmKoerper) {
      const rel = pos.clone().sub(R.hip);
      pos.copy(rel.applyQuaternion(kq).add(koerper.position));
      rot = kq.clone().multiply(rot);
    }
    t.gruppe.position.copy(pos); t.gruppe.quaternion.copy(rot);
    if (n[0] === 'h') {
      const faust = !!q.faust;
      t.hand.visible = !faust; t.faust.gruppe.visible = faust;
      t.faust.daumen.rotation.set(...(q.daumen || [0.9, 0, 0]).map((v) => v));
      t.faust.daumen.visible = q.daumenSichtbar !== false;
    }
  }
  figur.updateMatrixWorld(true);
  // Schläuche (im Figurraum)
  const ab = (g) => new THREE.Vector3(0, -1, 0).applyQuaternion(g.quaternion);
  for (const [n, s, h, rad, L, B] of [
    ['aL', R.sL, 'hL', ARM_R, ARM_L, new THREE.Vector3(-1, 0.1, -0.35)],
    ['aR', R.sR, 'hR', ARM_R, ARM_L, new THREE.Vector3(1, 0.1, -0.35)],
    ['lL', R.bL, 'fL', BEIN_R, BEIN_L, new THREE.Vector3(-0.15, 0, 1)],
    ['lR', R.bR, 'fR', BEIN_R, BEIN_L, new THREE.Vector3(0.15, 0, 1)]]) {
    const arm = n[0] === 'a';
    const P0 = s.clone().sub(R.hip).applyMatrix4(km);
    const t0 = (arm ? new THREE.Vector3(Math.sign(s.x), -0.35, 0).normalize() : (s === R.bL ? R.bLdir : R.bRdir).clone()).applyQuaternion(kq);
    const g = teile[h].gruppe;
    const t3 = ab(g);
    const P3 = g.position.clone().add(t3.clone().multiplyScalar(arm ? 0.035 : 0.03));
    const bend = (p.knick?.[n] ? V(p.knick[n]) : B).applyQuaternion(arm ? kq : new THREE.Quaternion());
    const pfad = schlauch(P0, t0, P3, t3, bend, (p.laenge?.[n] || 1) * L);
    teile[n].mesh.geometry.dispose();
    teile[n].mesh.geometry = new THREE.TubeGeometry(pfad, 64, rad, 16, false);
  }
  // Requisiten
  req.box.visible = !!p.box;
  if (p.box) {
    const bp = V(p.box.p || [0, -0.16, 0.5]).sub(R.hip).applyQuaternion(kq).add(koerper.position);
    req.box.position.copy(bp); req.box.quaternion.copy(kq.clone().multiply(e2q(p.box.r)));
  }
  req.pistole.visible = !!p.pistole;
  scene.updateMatrixWorld(true);
  if (p.pistole) {
    const hand = teile[p.pistole.hand || 'hR'].gruppe;
    req.pistole.position.set(0, -0.2, 0.03); req.pistole.quaternion.identity();
    hand.updateMatrixWorld(true);
    req.pistole.applyMatrix4(hand.matrixWorld);
    req.ring.material.emissiveIntensity = p.pistole.glut ?? 0.4;
  }
  req.stein.visible = !!p.stein;
  if (p.stein) {
    req.stein.position.set(...p.stein.p); req.stein.rotation.set(0, (p.stein.yaw || 0) * DEG, 0);
    req.stein.scale.setScalar(p.stein.s ?? 1);
    for (const k of req.kristalle) k.visible = p.stein.kristalle !== false;
  }
  scene.updateMatrixWorld(true);
  if (p.strahl) strahl(p.strahl);
  if (p.brocken) brocken(p.brocken);
  if (p.blitz) { req.glowB.visible = true; req.glowB.position.set(...p.blitz.p); req.glowB.scale.setScalar(p.blitz.s); }
}

function strahl(s) {
  const a = new THREE.Vector3(); req.muendung.getWorldPosition(a);
  const b = V(s.ziel);
  const d = b.clone().sub(a); const L = d.length();
  const mitte = a.clone().add(b).multiplyScalar(0.5);
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().normalize());
  for (const [m, r] of [[req.strahl, 0.035 * s.staerke], [req.kern, 0.012 * s.staerke]]) {
    m.visible = true; m.position.copy(mitte); m.quaternion.copy(q); m.scale.set(r, L, r);
  }
  req.glowA.visible = req.glowB.visible = true;
  req.glowA.position.copy(a); req.glowA.scale.setScalar(0.22 * s.staerke);
  req.glowB.position.copy(b); req.glowB.scale.setScalar(0.42 * s.staerke);
  req.hitze.visible = true; req.hitze.position.copy(b); req.hitze.scale.setScalar(0.06 + 0.05 * (s.hitze || 0));
  req.hitze.material.opacity = 0.35 + 0.5 * (s.hitze || 0);
  const r = rng(s.seed || 1);
  const n = Math.round(req.funken.length * (s.funken ?? 1));
  req.funken.forEach((f, i) => {
    if (i >= n) return;
    f.visible = true;
    const dir = new THREE.Vector3(-0.3 - r(), r() * 1.6 - 0.2, r() * 1.4 - 0.7).normalize();
    const weit = 0.08 + r() * 0.3, lang = 0.04 + r() * 0.09;
    f.position.copy(b).add(dir.clone().multiplyScalar(weit));
    f.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir); f.scale.set(1, 1, lang);
  });
}
function brocken(b) {
  const r = rng(b.seed || 3);
  req.brocken.forEach((m) => {
    m.visible = true;
    const dir = new THREE.Vector3(r() * 2 - 1, 0.6 + r(), r() * 2 - 1).normalize();
    const t = b.t;
    m.position.set(b.p[0] + dir.x * t * 1.1, b.p[1] + 0.25 + dir.y * t * 2.0 - 2.3 * t * t, b.p[2] + dir.z * t * 0.6);
    if (m.position.y < 0.06) m.position.y = 0.06;
    m.rotation.set(t * 7 * r(), t * 9 * r(), 0);
  });
}

// ---------- Kamera / Rendern ----------
export function kamera(x0, x1, y0, y1, pitch = 7) {
  cam.left = x0; cam.right = x1; cam.top = y1; cam.bottom = y0;
  const w = Math.round((x1 - x0) * PX), h = Math.round((y1 - y0) * PX);
  renderer.setSize(w, h, false);
  cam.position.set(0, 10 * Math.sin(pitch * DEG), 10 * Math.cos(pitch * DEG));
  cam.up.set(0, 1, 0);
  cam.lookAt(0, 0, 0);
  // Bildmitte so verschieben, dass y-Bereich in Welt-y stimmt (bei Neigung näherungsweise)
  cam.updateProjectionMatrix();
  return [w, h];
}

const idMats = new Map();
function idMat(farbe) {
  if (!idMats.has(farbe)) idMats.set(farbe, new THREE.ShaderMaterial({
    uniforms: {uid: {value: (farbe >> 16) / 255}},
    vertexShader: 'varying float vd; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vd = -mv.z; gl_Position = projectionMatrix * mv; }',
    fragmentShader: 'uniform float uid; varying float vd; void main(){ float t = clamp((vd - 6.0) / 8.0, 0.0, 1.0) * 65535.0; float hi = floor(t / 256.0); float lo = t - hi * 256.0; gl_FragColor = vec4(uid, hi / 255.0, lo / 255.0, 1.0); }',
    side: THREE.DoubleSide,
  }));
  return idMats.get(farbe);
}
export function rendern(mitId = true) {
  renderer.render(scene, cam);
  const bild = renderer.domElement.toDataURL('image/png');
  if (!mitId) return {bild};
  // ID-Durchgang für Innenlinien
  const tausch = [];
  const farbe = (o) => {
    if (o === teile.body?.mesh) return 0x100000;
    for (const n of ['hL', 'hR', 'fL', 'fR']) if (teile[n].gruppe === o.parent || teile[n].gruppe === o.parent?.parent || teile[n].gruppe === o.parent?.parent?.parent) return {hL: 0x200000, hR: 0x300000, fL: 0x400000, fR: 0x500000}[n];
    for (const n of ['aL', 'aR', 'lL', 'lR']) if (teile[n].mesh === o) return {aL: 0x600000, aR: 0x700000, lL: 0x800000, lR: 0x900000}[n];
    let x = o; while (x) { if (x === req.box) return 0xa00000; if (x === req.pistole) return 0xb00000; if (x === req.stein) return 0xc00000; x = x.parent; }
    return null;
  };
  scene.traverse((o) => {
    if (!o.isMesh && !o.isSprite) return;
    const f = farbe(o);
    tausch.push([o, o.material, o.visible]);
    if (f === null) o.visible = false; else o.material = idMat(f);
  });
  renderer.render(scene, cam);
  const id = renderer.domElement.toDataURL('image/png');
  for (const [o, m, v] of tausch) { o.material = m; o.visible = v; }
  return {bild, id};
}
