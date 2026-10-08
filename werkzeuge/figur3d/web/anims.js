// Animationen des DMNT 9000 (3D) – je 8 Bilder. Koordinaten: Figurraum (Blick +z, Boden y = 0 der Figur).
// Hände/Füße: p = Versatz zur Ruhelage, r = Drehung in Grad (Reihenfolge YXZ).
const PI = Math.PI;
const S = 0.377;                 // Sohle unter dem Knöchel
const FERSE = -0.18, SPITZE = 0.43;
const YAW = 50;                  // Dreiviertelansicht nach rechts
const K_STD = [-1.36, 1.36, -0.15, 2.42];
const K_MINE = [-1.36, 2.3, -0.38, 2.42];

const glatt = (t) => t * t * (3 - 2 * t);
const lerp = (a, b, t) => a + (b - a) * t;
const lerpV = (a, b, t) => a.map((v, i) => lerp(v, b[i], t));

// Fuß anheben, damit Ferse/Spitze bei Kippung nicht im Boden stecken
function fussHub(rxGrad) {
  const t = rxGrad * PI / 180;
  const y = (z) => -S * Math.cos(t) - z * Math.sin(t);
  return Math.max(0, -S - Math.min(y(FERSE), y(SPITZE)));
}

// Schrittzyklus: Phase 0..1 → {z, y, rx}
function schritt(ph, A, H) {
  ph = ((ph % 1) + 1) % 1;
  if (ph < 0.5) {
    const s = ph / 0.5;
    const rx = s < 0.15 ? lerp(-14, 0, s / 0.15) : (s > 0.7 ? lerp(0, 22, (s - 0.7) / 0.3) : 0);
    return {z: A * (1 - 2 * s), y: fussHub(rx), rx};
  }
  const s = (ph - 0.5) / 0.5;
  const rx = lerp(22, -14, glatt(s));
  return {z: -A + 2 * A * glatt(s), y: H * Math.sin(PI * s) + fussHub(rx) * (1 - Math.sin(PI * s)), rx};
}

function gehen(i, n, o = {}) {
  const t = i / n;
  const A = o.A ?? 0.2, H = o.H ?? 0.13;
  const l = schritt(t, A, H), r = schritt(t + 0.5, A, H);
  const bob = (o.bob ?? 0.028) * -Math.cos(4 * PI * t) + (o.bob ?? 0.028);
  const arm = o.arm ?? 0.85;
  const p = {
    root: {yaw: o.yaw ?? YAW},
    body: {p: [0, bob - (o.tief ?? 0), 0], r: [o.lean ?? 4, 5 * Math.sin(2 * PI * t), 3 * Math.sin(2 * PI * t)]},
    fL: {p: [0, l.y, l.z], r: [l.rx, 0, 0]},
    fR: {p: [0, r.y, r.z], r: [r.rx, 0, 0]},
    hL: {p: [0.02, 0.05 * Math.abs(r.z) / A + bob * 0.5, r.z * arm], r: [-35 * r.z / A, 0, -4]},
    hR: {p: [-0.02, 0.05 * Math.abs(l.z) / A + bob * 0.5, l.z * arm], r: [-35 * l.z / A, 0, 4]},
  };
  return p;
}

// Weltpunkt aus Figurraum (Drehung um y)
function welt(x, y, z, yaw = YAW) {
  const a = yaw * PI / 180;
  return [x * Math.cos(a) + z * Math.sin(a), y, -x * Math.sin(a) + z * Math.cos(a)];
}

const DAUMEN_HOCH = [1.57, 0, 0];

export const ANIM = {
  test_vorne: {n: 1, kamera: K_STD, pose: () => ({root: {yaw: 0}})},
  test_34: {n: 1, kamera: K_STD, pose: () => ({root: {yaw: YAW}})},

  // --- Grundlage ---
  stehen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, s = Math.sin(2 * PI * t), c = Math.cos(2 * PI * t);
    return {root: {yaw: YAW},
      body: {p: [0, 0.012 * s, 0], r: [1.5 * s, 2 * c, 1.2 * c]},
      hL: {p: [0.005 * c, 0.012 * s + 0.004, 0.01 * s], r: [-4 * s, 0, -2 * c]},
      hR: {p: [-0.005 * c, 0.012 * s + 0.004, -0.01 * s], r: [4 * s, 0, 2 * c]}};
  }},

  gehen: {n: 8, kamera: K_STD, pose: (i, n) => gehen(i, n)},

  rennen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const p = gehen(i, n, {A: 0.25, H: 0.2, bob: 0.045, lean: 10, arm: 0.9});
    const t = i / n;
    p.hL.faust = p.hR.faust = true;
    p.hL.p[1] += 0.1; p.hR.p[1] += 0.1;
    p.hL.p[2] += 0.05; p.hR.p[2] += 0.05;
    p.body.p[1] += 0.03 * Math.abs(Math.sin(2 * PI * t));
    return p;
  }},

  // --- Karton/Transportbox schleppen ---
  tragen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const p = gehen(i, n, {A: 0.15, H: 0.1, bob: 0.036, lean: -6, arm: 0});
    const t = i / n;
    p.body.r = [-6 + 1.5 * Math.cos(4 * PI * t), 3 * Math.sin(2 * PI * t), 2.5 * Math.sin(2 * PI * t)];
    p.haendeAmKoerper = true;
    p.hL = {p: [0.13, 0.03, 0.43], r: [0, -8, 6]};
    p.hR = {p: [-0.13, 0.03, 0.43], r: [0, 8, -6]};
    p.box = {p: [0, -0.21, 0.52], r: [0, 0, 0]};
    return p;
  }},

  // --- Mining-Pistole auf Stein ---
  minen: {n: 8, kamera: K_MINE, pose: (i, n) => {
    const t = i / n;
    const st = [1.0, 0.82, 1.12, 0.9, 1.05, 0.86, 1.1, 0.95][i];
    const ziel = welt(0.02, 0.4, 1.66);
    return {root: {yaw: YAW},
      body: {p: [0, -0.02 + 0.006 * Math.sin(4 * PI * t), -0.01 * st], r: [2, -6, 0]},
      fL: {p: [-0.03, 0, 0.14], r: [0, -8, 0]},
      fR: {p: [0.04, 0, -0.12], r: [0, 10, 0]},
      hR: {p: [-0.14, 0.1 + 0.006 * Math.sin(8 * PI * t), 0.5 - 0.012 * st], r: [32, 0, 0], faust: true, daumen: [0.5, 0, 0]},
      hL: {p: [0.06, 0.02, 0.08], r: [-10, 0, -10], faust: true, daumen: [0.9, 0, 0]},
      pistole: {hand: 'hR', glut: 1.4 + 0.4 * st},
      stein: {p: welt(0, 0, 2.08), yaw: 20, s: 1.12},
      strahl: {ziel, staerke: st, hitze: 0.6 + 0.4 * Math.sin(2 * PI * t) ** 2, seed: 11 + i * 7, funken: 0.7 + 0.3 * st},
    };
  }},

  // --- Ausdrücke ---
  freuen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n;
    const hop = Math.max(0, Math.sin(2 * PI * t)) * 0.12;
    const hock = Math.max(0, -Math.sin(2 * PI * t)) * 0.05;
    return {root: {yaw: 30},
      body: {p: [0, hop - hock, 0], r: [-3, 0, 4 * Math.sin(2 * PI * t)]},
      fL: {p: [0, hop * 0.9, 0], r: [hop * 60, 0, 0]}, fR: {p: [0, hop * 0.9, 0], r: [hop * 60, 0, 0]},
      haendeAmKoerper: true,
      hL: {p: [0.06, 0.3 + 0.03 * Math.sin(4 * PI * t), 0.28], r: [-90, 0, -10], faust: true, daumen: DAUMEN_HOCH},
      hR: {p: [-0.06, 0.3 + 0.03 * Math.sin(4 * PI * t + 1), 0.28], r: [-90, 0, 10], faust: true, daumen: DAUMEN_HOCH},
    };
  }},

  unzufrieden: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, s = Math.sin(2 * PI * t);
    return {root: {yaw: 30},
      body: {p: [0, -0.03, 0], r: [9, 5 * s, 3 * s]},
      haendeAmKoerper: true,
      hL: {p: [-0.06, 0.1 + 0.02 * Math.sin(4 * PI * t), 0.3], r: [90, 0, 180], faust: true, daumen: DAUMEN_HOCH},
      hR: {p: [0.06, 0.1 + 0.02 * Math.sin(4 * PI * t + 1), 0.3], r: [90, 0, 180], faust: true, daumen: DAUMEN_HOCH},
    };
  }},

  // --- Sitzen / Schlafen ---
  sitzen: {n: 8, kamera: K_STD, pose: (i, n) => sitz(i / n, 0)},
  schlafen: {n: 8, kamera: K_STD, pose: (i, n) => sitz(i / n, 1)},

  // --- Physik / Sockel ---
  fallen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, s = Math.sin(2 * PI * t), c = Math.cos(2 * PI * t);
    return {root: {yaw: 30},
      body: {p: [0, 0.05, 0], r: [-8, 6 * s, 7 * s]},
      hL: {p: [-0.12 + 0.05 * c, 0.6 + 0.08 * s, 0.05 * s], r: [-20 * s, 0, -150 + 25 * c], faust: false},
      hR: {p: [0.12 - 0.05 * c, 0.6 - 0.08 * s, -0.05 * s], r: [20 * s, 0, 150 - 25 * c]},
      fL: {p: [0, 0.14 + 0.06 * s, 0.1 * c], r: [35 + 15 * s, 0, 0]},
      fR: {p: [0, 0.14 - 0.06 * s, -0.1 * c], r: [35 - 15 * s, 0, 0]}};
  }},
  gezogen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, s = Math.sin(2 * PI * t), c = Math.cos(2 * PI * t);
    return {root: {yaw: 25},
      body: {p: [0, 0.12, 0], r: [-4, 4 * s, 7 * s]},
      hL: {p: [-0.02 - 0.06 * s, -0.12, 0.05 * c], r: [10 * c, 0, -10 * s]},
      hR: {p: [0.02 - 0.06 * s, -0.12, -0.05 * c], r: [-10 * c, 0, -10 * s]},
      fL: {p: [-0.05 * s, 0.05, 0.08 * c], r: [42 + 8 * c, 0, -5 * s]},
      fR: {p: [-0.05 * s, 0.05, -0.08 * c], r: [42 - 8 * c, 0, -5 * s]}};
  }},
  springen: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, s = Math.sin(2 * PI * t);
    return {root: {yaw: YAW},
      body: {p: [0, 0.16, 0], r: [-6 + 3 * s, 0, 3 * s]},
      hL: {p: [-0.14, 0.52 + 0.04 * s, 0.05], r: [0, 0, -140]},
      hR: {p: [0.14, 0.52 - 0.04 * s, 0.05], r: [0, 0, 140]},
      fL: {p: [0, 0.3 + 0.03 * s, -0.08], r: [40, 0, 0]},
      fR: {p: [0, 0.24 - 0.03 * s, 0.1], r: [20, 0, 0]}};
  }},
  schweben: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, s = Math.sin(2 * PI * t), c = Math.cos(2 * PI * t);
    return {root: {yaw: 30},
      body: {p: [0, 0.1 + 0.02 * s, 0], r: [-3, 4 * c, 3 * s]},
      hL: {p: [-0.26, 0.3 + 0.05 * s, 0], r: [0, 0, -80 + 10 * s]},
      hR: {p: [0.26, 0.3 - 0.05 * s, 0], r: [0, 0, 80 + 10 * s]},
      fL: {p: [0, 0.08 + 0.03 * c, 0.04 * s], r: [30 + 8 * s, 0, 0]},
      fR: {p: [0, 0.08 - 0.03 * c, -0.04 * s], r: [30 - 8 * s, 0, 0]}};
  }},

  // --- Regeln ---
  anschauen: {n: 8, kamera: K_STD, pose: (i, n) => {   // Winken zum Nutzer
    const t = i / n, s = Math.sin(2 * PI * t);
    return {root: {yaw: 15},
      body: {p: [0, 0.01 * Math.abs(s), 0], r: [0, 0, -3 + 2 * s]},
      haendeAmKoerper: true,
      hR: {p: [0.12, 0.6, 0.12], r: [0, 0, 165 + 25 * s]},
      hL: {p: [0.01, 0.005 * s, 0.02], r: [0, 0, -3]}};
  }},
  sprechen: {n: 8, kamera: K_STD, pose: (i, n) => sprechen(i / n, 35)},
  sprechen_vorne: {n: 8, kamera: K_STD, pose: (i, n) => sprechen(i / n, 0)},
  erschrecken: {n: 8, kamera: K_STD, pose: (i, n) => {
    const t = i / n, z = (i % 2 ? 1 : -1);
    const auf = Math.min(1, i / 2);
    return {root: {yaw: 35},
      body: {p: [0.008 * z, 0.06 * auf, -0.07 * auf], r: [-12 * auf, 0, 2.5 * z]},
      haendeAmKoerper: true,
      hL: {p: [0.02, 0.42 * auf, 0.2 * auf], r: [-60 * auf, 0, -40 * auf + 6 * z]},
      hR: {p: [-0.02, 0.42 * auf, 0.2 * auf], r: [-60 * auf, 0, 40 * auf - 6 * z]},
      fL: {p: [0, 0.1 * auf, -0.04], r: [-15 * auf, 0, 0]},
      fR: {p: [0, 0, 0.02], r: [0, 0, 0]}};
  }},
  zuschauen: {n: 8, kamera: K_STD, pose: (i, n) => {   // Hände hinterm Rücken, wippt
    const t = i / n, s = Math.sin(2 * PI * t);
    const w = 6 * s;
    return {root: {yaw: 20},
      body: {p: [0, fussHub(w) * 0.6 + 0.005, 0.01 * s], r: [w * 0.4, 0, 0]},
      haendeAmKoerper: true,
      hL: {p: [0.2, 0.06, -0.38], r: [0, -60, -15]},
      hR: {p: [-0.2, 0.06, -0.38], r: [0, 60, 15]},
      fL: {p: [0, fussHub(w), 0], r: [w, 0, 0]}, fR: {p: [0, fussHub(w), 0], r: [w, 0, 0]}};
  }},
  musik: {n: 8, kamera: K_STD, pose: (i, n) => {   // im Takt nicken, Fuß tippt, schnippt
    const t = i / n, b = Math.abs(Math.sin(2 * PI * t));      // zwei Schläge je Umlauf
    const tipp = i % 4 < 2 ? -22 : 0;
    return {root: {yaw: 40},
      body: {p: [0, -0.03 * b, 0], r: [7 * b, 6 * Math.sin(PI * t * 2), 3 * Math.sin(2 * PI * t)]},
      haendeAmKoerper: true,
      hL: {p: [0.03, 0.2 - 0.05 * b, 0.12], r: [-40, 0, -10], faust: true, daumen: [1.0, 0, 0]},
      hR: {p: [-0.03, 0.2 - 0.05 * (1 - b), 0.12], r: [-40, 0, 10], faust: true, daumen: [1.0, 0, 0]},
      fR: {p: [0, fussHub(tipp), 0], r: [tipp, 0, 0]}};
  }},

  // --- Overlay-Zusätze: Mining-Ablauf ---
  minen_start: {n: 8, kamera: K_MINE, pose: (i, n) => {
    const k = glatt(i / (n - 1));
    const p = ANIM.minen.pose(0, 8);
    delete p.strahl;
    p.hR.p = lerpV([0, 0, 0], p.hR.p, k); p.hR.r = lerpV([0, 0, 0], p.hR.r, k);
    p.body.r = lerpV([0, 0, 0], p.body.r, k);
    p.fL.p = lerpV([0, 0, 0], p.fL.p, k); p.fR.p = lerpV([0, 0, 0], p.fR.p, k);
    p.pistole.glut = 0.3 + k;
    p.stein.s = 1.12 * glatt(Math.min(1, i / 3));      // Stein erscheint (wird "gescannt")
    return p;
  }},
  minen_ende: {n: 8, kamera: K_MINE, pose: (i, n) => {
    const p = ANIM.minen.pose(0, 8);
    delete p.strahl;
    const k = glatt(i / (n - 1));
    p.hR.p = lerpV(p.hR.p, [0, 0, 0], k); p.hR.r = lerpV(p.hR.r, [0, 0, 0], k);
    if (i >= 5) { p.hR = {p: [-0.04, 0.32, 0.2], r: [-90, 0, 10], faust: true, daumen: DAUMEN_HOCH}; p.haendeAmKoerper = true; }
    if (i < 1) { p.stein.s = 1.12; p.blitz = {p: welt(0.02, 0.4, 1.66), s: 0.5}; }
    else { delete p.stein; p.brocken = {p: welt(0, 0, 2.08), t: Math.min(1, (i - 0.5) / 5), seed: 5}; if (i === 1) p.blitz = {p: welt(0, 0.3, 2.08), s: 1.1}; }
    p.pistole = i >= 5 ? undefined : {hand: 'hR', glut: 0.4};
    return p;
  }},
};

function sitz(t, schlaf) {
  const s = Math.sin(2 * PI * t);
  const vor = schlaf ? 14 : -6;
  return {root: {yaw: 40},
    body: {p: [0, -0.53 + 0.008 * s, -0.04], r: [vor + 1.5 * s, schlaf ? 0 : 3 * s, schlaf ? 4 : 0]},
    fL: {p: [-0.04, fussHub(-28), 0.44], r: [-28, -8, 0]},
    fR: {p: [0.04, fussHub(-28), 0.44], r: [-28, 8, 0]},
    hL: {p: [-0.06, -0.43 + 0.004 * s, schlaf ? 0.1 : -0.02], r: [schlaf ? 20 : 0, 0, -25]},
    hR: {p: [0.06, -0.43 + 0.004 * s, schlaf ? 0.1 : -0.02], r: [schlaf ? 20 : 0, 0, 25]}};
}

function sprechen(t, yaw) {
  const s = Math.sin(2 * PI * t), s2 = Math.sin(4 * PI * t + 0.8);
  return {root: {yaw},
    body: {p: [0, 0.008 * Math.abs(s2), 0], r: [2 * s2, 4 * s, 2 * s]},
    haendeAmKoerper: true,
    hL: {p: [0.06, 0.2 + 0.1 * Math.max(0, s), 0.22], r: [-45 - 20 * Math.max(0, s), 0, -25]},
    hR: {p: [-0.06, 0.2 + 0.1 * Math.max(0, -s), 0.22], r: [-45 - 20 * Math.max(0, -s), 0, 25]}};
}
ANIM.portraet = {n: 1, kamera: [-1.36, 1.36, -0.15, 2.42], pose: () => ({root: {yaw: 22}})};
