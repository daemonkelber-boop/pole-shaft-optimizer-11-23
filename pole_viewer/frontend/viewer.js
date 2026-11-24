// Pole viewer -- three.js (r160, vendored), Streamlit custom component.
// Coordinates: ft. three.js axes map to PLS-POLE axes as
//   three +X = PLS +Y (transverse, azimuth 0)
//   three +Y = PLS +Z (up; height above ground line)
//   three +Z = PLS +X (longitudinal, azimuth 90)
// (a cyclic swap, so handedness is kept). Arms with azimuth 0 point along
// PLS +Y; clamps / brackets without arms sit on the +Y face.
import * as THREE from './three.module.min.js';
import { OrbitControls } from './OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from './CSS2DRenderer.js';

// ---------------- Streamlit component protocol (no npm lib) ----------------
function send(type, data) {
  window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data || {}), '*');
}
window.addEventListener('message', (ev) => {
  const d = ev.data;
  if (!d || d.type !== 'streamlit:render') return;
  try { render(d.args || {}); } catch (e) { showErr(e); }
});
send('streamlit:componentReady', { apiVersion: 1 });

function showErr(e) {
  const el = document.getElementById('err');
  el.style.display = 'flex';
  el.textContent = '3D viewer error: ' + (e && e.message ? e.message : e);
  console.error(e);
}

// ---------------- state ----------------
const S = { inited: false, token: null, pick: [], labels: [], showLabels: true,
            zoomGoal: 1, cursor: new THREE.Vector2(0, 0), dirty: true, tween: null,
            fitH: 100, midY: 50, sc: null };
const wrap = document.getElementById('wrap');
const view = document.getElementById('view');
const tip = document.getElementById('tip');
let renderer, labelR, scene, camera, controls, model;

// camera directions (from target toward camera), three.js coords
const VIEWS = {
  iso:   new THREE.Vector3(0.55, 0.30, 0.80).normalize(),   // like PLS-POLE's default 3D view
  trans: new THREE.Vector3(0, 0, 1),        // look along -X(PLS): transverse (Y) across the screen
  long:  new THREE.Vector3(-1, 0, 0),       // look along +Y(PLS): longitudinal (X) across the screen
  top:   new THREE.Vector3(0.0015, 1, 0).normalize(),
};
let gScene, gCam;
const DIST = 2000;

function init(sc) {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  view.appendChild(renderer.domElement);
  labelR = new CSS2DRenderer();
  labelR.domElement.style.position = 'absolute';
  labelR.domElement.style.top = '0';
  labelR.domElement.style.pointerEvents = 'none';
  view.appendChild(labelR.domElement);

  scene = new THREE.Scene();
  camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10000);
  scene.add(camera);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(1, 1.5, 2);
  camera.add(key);                       // light follows the view

  renderer.autoClear = false;
  buildGizmo();

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.rotateSpeed = 0.55;
  controls.panSpeed = 0.9;
  controls.enableZoom = false;           // smooth zoom handled below
  controls.screenSpacePanning = true;
  controls.addEventListener('change', () => { S.dirty = true; });

  // smooth wheel zoom toward the cursor
  renderer.domElement.addEventListener('wheel', (e) => {
    e.preventDefault();
    const k = parseFloat(document.getElementById('speed').value) || 0.5;
    const step = Math.exp(-Math.sign(e.deltaY) * Math.min(Math.abs(e.deltaY), 120) / 120 * 0.18 * k * 2);
    S.zoomGoal = clampZoom(S.zoomGoal * step);
    setCursor(e);
  }, { passive: false });
  renderer.domElement.addEventListener('pointermove', (e) => { setCursor(e); hover(e); });
  renderer.domElement.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
  renderer.domElement.addEventListener('dblclick', (e) => {
    const hit = raycast(e);
    if (hit) glideTo(hit.point.y, Math.max(camera.zoom * 2, 3), null, hit.point.x, hit.point.z);
  });

  document.getElementById('fit').onclick = () => fit(true);
  document.querySelectorAll('[data-v]').forEach((b) => {
    b.onclick = () => glideTo(controls.target.y, camera.zoom, b.dataset.v);
  });
  document.getElementById('zin').onclick = () => { S.cursor.set(0, 0); S.zoomGoal = clampZoom(S.zoomGoal * 1.5); };
  document.getElementById('zout').onclick = () => { S.cursor.set(0, 0); S.zoomGoal = clampZoom(S.zoomGoal / 1.5); };
  document.getElementById('focus').onchange = (e) => {
    const f = (S.sc.focus || [])[parseInt(e.target.value, 10)];
    if (!f) return;
    if (f.y === null) fit(true);
    else glideTo(f.y, Math.max(1, S.fitH / Math.max(f.span, 2) / 1.3), null,
                      f.span > 20 ? f.span * 0.25 : 0, 0);
  };
  document.getElementById('lbls').onclick = (e) => {
    S.showLabels = !S.showLabels;
    e.target.classList.toggle('on', S.showLabels);
    S.labels.forEach((l) => { l.visible = S.showLabels; });
    S.dirty = true;
  };
  document.getElementById('lbls').classList.add('on');
  new ResizeObserver(() => resize()).observe(wrap);
  S.inited = true;
  requestAnimationFrame(loop);
}

function clampZoom(z) { return Math.min(Math.max(z, 0.6), 80); }

function setCursor(e) {
  const r = renderer.domElement.getBoundingClientRect();
  S.cursor.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
}

function resize() {
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h);
  labelR.setSize(w, h);
  const a = w / h, H = S.fitH;
  camera.left = -H * a / 2; camera.right = H * a / 2; camera.top = H / 2; camera.bottom = -H / 2;
  camera.updateProjectionMatrix();
  S.dirty = true;
}

// ---------------- camera moves ----------------
function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

function glideTo(y, zoom, viewName, x = 0, z = 0) {
  const dir = viewName ? VIEWS[viewName] : camera.position.clone().sub(controls.target).normalize();
  S.tween = {
    t0: performance.now(), dur: 520,
    fromT: controls.target.clone(), toT: new THREE.Vector3(x, y, z),
    fromD: camera.position.clone().sub(controls.target).normalize(), toD: dir.clone(),
    fromZ: camera.zoom, toZ: clampZoom(zoom),
  };
  document.querySelectorAll('[data-v]').forEach((b) => b.classList.toggle('on', b.dataset.v === viewName));
}

function fit(animate) {
  if (animate) glideTo(S.midY, 1, 'iso');
  else {
    controls.target.set(0, S.midY, 0);
    camera.position.copy(VIEWS.iso.clone().multiplyScalar(DIST).add(controls.target));
    camera.zoom = 1; S.zoomGoal = 1; camera.updateProjectionMatrix();
    document.querySelectorAll('[data-v]').forEach((b) => b.classList.toggle('on', b.dataset.v === 'iso'));
  }
  document.getElementById('focus').value = '0';
}

function ndcWorld(v) { return new THREE.Vector3(v.x, v.y, 0).unproject(camera); }

function loop(now) {
  requestAnimationFrame(loop);
  if (S.tween) {
    const tw = S.tween, f = Math.min((now - tw.t0) / tw.dur, 1), e = ease(f);
    controls.target.lerpVectors(tw.fromT, tw.toT, e);
    const d = tw.fromD.clone().lerp(tw.toD, e).normalize();
    camera.position.copy(d.multiplyScalar(DIST).add(controls.target));
    camera.zoom = tw.fromZ + (tw.toZ - tw.fromZ) * e;
    S.zoomGoal = camera.zoom;
    camera.updateProjectionMatrix();
    camera.lookAt(controls.target);
    if (f >= 1) S.tween = null;
    S.dirty = true;
  } else if (Math.abs(S.zoomGoal - camera.zoom) > 1e-4 * S.zoomGoal) {
    const before = ndcWorld(S.cursor);
    camera.zoom += (S.zoomGoal - camera.zoom) * 0.2;
    if (Math.abs(S.zoomGoal - camera.zoom) < 1e-4 * S.zoomGoal) camera.zoom = S.zoomGoal;
    camera.updateProjectionMatrix();
    const shift = before.sub(ndcWorld(S.cursor));
    camera.position.add(shift); controls.target.add(shift);
    S.dirty = true;
  }
  if (controls.update()) S.dirty = true;
  if (S.dirty) {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setViewport(0, 0, w, h);
    renderer.setScissorTest(false);
    renderer.clear();
    renderer.render(scene, camera);
    labelR.render(scene, camera);
    // axis triad, bottom-left, follows the camera rotation
    const g = 104;
    gCam.position.copy(camera.position).sub(controls.target).normalize().multiplyScalar(5);
    gCam.up.copy(camera.up);
    gCam.lookAt(0, 0, 0);
    renderer.clearDepth();
    renderer.setScissorTest(true);
    renderer.setScissor(8, 26, g, g);
    renderer.setViewport(8, 26, g, g);
    renderer.render(gScene, gCam);
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, w, h);
    S.dirty = false;
  }
}

// ---------------- axis triad (PLS-POLE convention) ----------------
function textSprite(txt, color, scale) {
  const c = document.createElement('canvas');
  c.width = 128; c.height = 64;
  const x = c.getContext('2d');
  x.font = 'bold 40px Roboto, Arial, sans-serif';
  x.fillStyle = color; x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(txt, 64, 32);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false }));
  sp.scale.set(scale * 2, scale, 1);
  return sp;
}
function buildGizmo() {
  gScene = new THREE.Scene();
  gCam = new THREE.OrthographicCamera(-1.7, 1.7, 1.7, -1.7, 0.1, 20);
  const ax = [
    [new THREE.Vector3(0, 1, 0), 'Z', '#212121'],
    [new THREE.Vector3(0, 0, 1), 'X', '#c62828'],      // PLS +X longitudinal
    [new THREE.Vector3(1, 0, 0), 'Y', '#1565c0'],      // PLS +Y transverse
  ];
  for (const [d, n, col] of ax) {
    gScene.add(new THREE.ArrowHelper(d, new THREE.Vector3(0, 0, 0), 1.05, col, 0.3, 0.16));
    const sp = textSprite(n, col, 0.42);
    sp.position.copy(d.clone().multiplyScalar(1.4));
    gScene.add(sp);
  }
  const sub = textSprite('Long', '#c62828', 0.28); sub.position.set(0, -0.35, 1.45); gScene.add(sub);
  const sub2 = textSprite('Trans', '#1565c0', 0.28); sub2.position.set(1.45, -0.35, 0); gScene.add(sub2);
}

// ---------------- picking ----------------
const ray = new THREE.Raycaster();
function raycast(e) {
  setCursor(e);
  ray.setFromCamera(S.cursor, camera);
  const hits = ray.intersectObjects(S.pick, false);
  return hits.length ? hits[0] : null;
}
function hover(e) {
  if (e.buttons) { tip.style.display = 'none'; return; }
  const h = raycast(e);
  if (!h || !h.object.userData.info) { tip.style.display = 'none'; return; }
  tip.innerHTML = h.object.userData.info;
  const r = wrap.getBoundingClientRect();
  let x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
  tip.style.display = 'block';
  if (x + tip.offsetWidth > r.width - 4) x = e.clientX - r.left - tip.offsetWidth - 10;
  if (y + tip.offsetHeight > r.height - 4) y = e.clientY - r.top - tip.offsetHeight - 10;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}

// ---------------- geometry helpers ----------------
const COS15 = Math.cos(Math.PI / 12);
function rPole(d) { return d / 24 / COS15; }          // 12-sided circumradius (ft) from flat-to-flat (in)

function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial(Object.assign({ color, flatShading: true, roughness: 0.75,
    metalness: 0.15 }, opts));
}
function addPick(mesh, info) { if (info) { mesh.userData.info = info; S.pick.push(mesh); } return mesh; }

function frustum12(d0, d1, y0, y1, color, scale, opts, info, edgeColor) {
  const h = Math.max(y0 - y1, 0.01);
  const g = new THREE.CylinderGeometry(rPole(d0) * scale, rPole(d1) * scale, h, 12, 1, true, Math.PI / 12);
  const m = new THREE.Mesh(g, mat(color, Object.assign({ side: THREE.DoubleSide }, opts || {})));
  m.position.y = (y0 + y1) / 2;
  model.add(addPick(m, info));
  if (edgeColor) {
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(g, 1),
      new THREE.LineBasicMaterial({ color: edgeColor, transparent: true, opacity: 0.55 }));
    e.position.y = m.position.y;
    model.add(e);
  }
  return m;
}

function azDir(az) { const a = az * Math.PI / 180; return new THREE.Vector3(Math.cos(a), 0, Math.sin(a)); }

function member(p0, p1, d0, d1, sides, color, info) {
  const v = p1.clone().sub(p0), L = v.length();
  if (L < 1e-4) return;
  const c = 1 / Math.cos(Math.PI / sides);
  const g = new THREE.CylinderGeometry(d1 / 24 * c, d0 / 24 * c, L, sides, 1, false,
                                       sides === 4 ? Math.PI / 4 : Math.PI / sides);
  const m = new THREE.Mesh(g, mat(color));
  m.position.copy(p0.clone().add(p1).multiplyScalar(0.5));
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.normalize());
  model.add(addPick(m, info));
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(g, 20),
    new THREE.LineBasicMaterial({ color: S.sc.colors.edge, transparent: true, opacity: 0.5 }));
  e.position.copy(m.position); e.quaternion.copy(m.quaternion);
  model.add(e);
}

function label(text, pos, color, small, alignRight) {
  const div = document.createElement('div');
  div.className = 'lbl';
  div.textContent = text;
  div.style.color = color;
  if (small) div.style.fontSize = '10px';
  const o = new CSS2DObject(div);
  o.position.copy(pos);
  o.center.set(alignRight ? 1 : 0, 0.5);
  o.visible = S.showLabels;
  model.add(o);
  S.labels.push(o);
  return o;
}

// ---------------- build the model ----------------
function clearModel() {
  if (!model) return;
  model.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
    if (o.element && o.element.parentNode) o.element.parentNode.removeChild(o.element);
  });
  scene.remove(model);
}

function build(sc) {
  clearModel();
  model = new THREE.Group();
  scene.add(model);
  S.pick = []; S.labels = [];
  const C = sc.colors;

  for (const t of sc.tubes) frustum12(t.d0, t.d1, t.y0, t.y1, C.steel, 1, {}, t.info, C.edge);
  for (const l of sc.laps) frustum12(l.d0, l.d1, l.y0, l.y1, l.bad ? C.bad : C.lap, 1.03, {}, l.info);

  // clear zones (see-through sleeves)
  for (const s of sc.stations) {
    if (!s.zone) continue;
    frustum12(s.zone.d0, s.zone.d1, s.zone.y0, s.zone.y1, s.bad ? C.bad : C.zone, 1.38,
      { transparent: true, opacity: 0.2, depthWrite: false }, s.zone.info, s.bad ? C.bad : C.zone);
  }
  // elevation markers, bracket / vang bands, labels (+X face)
  for (const s of sc.stations) {
    const col = s.bad ? C.bad : C.primary;
    const mk = new THREE.Mesh(new THREE.OctahedronGeometry(0.45), mat(col, { flatShading: false }));
    mk.position.set(s.r * 1.04 + 0.3, s.y, 0);
    model.add(addPick(mk, s.info));
    if (s.band) {
      const bh = Math.max(s.band[0] - s.band[1], 0.02);
      const b = new THREE.Mesh(new THREE.BoxGeometry(0.35, bh, s.r * 1.2),
                               mat(s.bad ? C.bad : C.bracket, { transparent: true, opacity: 0.85 }));
      b.position.set(s.r + 0.2, (s.band[0] + s.band[1]) / 2, 0);
      model.add(addPick(b, s.info));
    }
    // elevation labels on the -X side (arms run along +X)
    label(s.tag, new THREE.Vector3(-s.r * 1.04 - 0.8, s.y, 0), col, false, true);
  }
  // arms and brackets
  for (const a of sc.arms) {
    const dir = azDir(a.az);
    const P = a.pts.map((p) => dir.clone().multiplyScalar(p[0]).add(new THREE.Vector3(0, p[1], 0)));
    for (let i = 0; i + 1 < P.length; i++) {
      member(P[i], P[i + 1], a.pts[i][2], a.pts[i + 1][2], a.sides, a.bracket ? C.bracket : C.arm, a.info);
    }
    if (!a.bracket && P.length) {
      const tipP = P[P.length - 1].clone().add(new THREE.Vector3(0, 1.2, 0));
      label(a.tag, tipP, C.text, true);
    }
  }
  for (const v of sc.vangs) {
    const p = azDir(v.az).multiplyScalar(v.h).add(new THREE.Vector3(0, v.y - 0.35, 0));
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 8), mat(C.primary, { flatShading: false }));
    m.position.copy(p);
    model.add(addPick(m, v.info));
  }
  // base plate
  if (sc.plate) {
    const t = sc.plate.t / 12, r = sc.plate.d / 24;
    const g = new THREE.CylinderGeometry(r, r, t, 64);
    const m = new THREE.Mesh(g, mat(C.plate));
    m.position.y = -t / 2;
    model.add(addPick(m, sc.plate.info));
  }
  // ground line square
  const gs = sc.pole.ground;
  const pts = [[-gs, -gs], [gs, -gs], [gs, gs], [-gs, gs], [-gs, -gs]].map(
    (q) => new THREE.Vector3(q[0], 0, q[1]));
  const gl = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineDashedMaterial({ color: C.muted, dashSize: 0.6, gapSize: 0.4 }));
  gl.computeLineDistances();
  model.add(gl);
  label('GL', new THREE.Vector3(gs + 0.5, 0, -gs), C.muted, true);
  // azimuth ring at GL (PLS-POLE: 0 = +Y transverse, 90 = +X longitudinal)
  const rr = gs * 1.25, ring = [];
  for (let i = 0; i <= 96; i++) {
    const a = i / 96 * Math.PI * 2;
    ring.push(new THREE.Vector3(rr * Math.cos(a), 0, rr * Math.sin(a)));
  }
  model.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring),
    new THREE.LineBasicMaterial({ color: C.muted, transparent: true, opacity: 0.6 })));
  for (let deg = 0; deg < 360; deg += 30) {
    const a = deg * Math.PI / 180, l = deg % 90 === 0 ? 0.16 : 0.08;
    const p0 = new THREE.Vector3(rr * Math.cos(a), 0, rr * Math.sin(a));
    const p1 = p0.clone().multiplyScalar(1 + l);
    model.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([p0, p1]),
      new THREE.LineBasicMaterial({ color: C.muted })));
    if (deg % 90 === 0) label(String(deg), p0.clone().multiplyScalar(1.32), C.muted, true);
  }
  const axL = (v, t, col) => {
    model.add(new THREE.ArrowHelper(v, new THREE.Vector3(0, 0, 0), rr * 1.15, col, rr * 0.12, rr * 0.06));
    label(t, v.clone().multiplyScalar(rr * 1.22), col, true);
  };
  axL(new THREE.Vector3(1, 0, 0), '+Y Trans', '#1565c0');
  axL(new THREE.Vector3(0, 0, 1), '+X Long', '#c62828');

  // focus list
  const sel = document.getElementById('focus');
  sel.innerHTML = '';
  (sc.focus || []).forEach((f, i) => {
    const o = document.createElement('option');
    o.value = String(i); o.textContent = f.label;
    sel.appendChild(o);
  });
  S.dirty = true;
}

function applyTheme(C) {
  const r = document.documentElement.style;
  r.setProperty('--surface', C.surface); r.setProperty('--border', C.border);
  r.setProperty('--text', C.text); r.setProperty('--muted', C.muted);
  r.setProperty('--primary', C.primary); r.setProperty('--label-bg', C.label_bg);
  wrap.style.background = C.bg;
}

function render(args) {
  const sc = args.scene;
  if (!sc) return;
  S.sc = sc;
  const H = args.height || 820;
  wrap.style.height = H + 'px';
  send('streamlit:setFrameHeight', { height: H });
  applyTheme(sc.colors);
  S.fitH = sc.pole.fit_h;
  S.midY = sc.pole.mid_y;
  if (!S.inited) init(sc);
  resize();
  build(sc);
  if (S.token !== sc.token) {             // new pole: frame it; same pole: keep the user's view
    S.token = sc.token;
    fit(false);
  }
}
