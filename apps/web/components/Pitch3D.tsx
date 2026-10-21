"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import Pitch, { type Arrow, type PitchProps } from "./Pitch";

/**
 * 3D replay of the same frames the 2D board draws: a broadcast camera above the touchline, simple
 * player figures in team colours and the ball at its real height. It takes exactly the 2D props, so
 * playback, scrubbing and every overlay keep working from one timeline.
 *
 * World mapping: pitch x (0-105 m) -> X, pitch y (0-68 m) -> Z, ball height -> Y. The camera sits on
 * the y = 68 touchline, so left/right match the 2D board.
 */

const L = 105;
const W = 68;
const S = 1.5; // figures are drawn larger than life so they read from the broadcast distance
const v3 = (x: number, y: number, h = 0) => new THREE.Vector3(x - L / 2, h, y - W / 2);

const ARROW_COLOR: Record<Arrow["kind"], string> = {
  actual: "#f8fafc", selected: "#d4ee8f", alternative: "#cfe2b4", defense: "#f97316", recommended: "#34d399",
};

function pitchTexture(): THREE.CanvasTexture {
  const px = 20; // pixels per metre
  const c = document.createElement("canvas");
  c.width = (L + 8) * px;
  c.height = (W + 8) * px;
  const g = c.getContext("2d")!;
  g.fillStyle = "#0e3523";
  g.fillRect(0, 0, c.width, c.height);
  g.translate(4 * px, 4 * px);
  for (let i = 0; i < 10; i++) {
    g.fillStyle = i % 2 ? "#123f2a" : "#164730";
    g.fillRect(i * 10.5 * px, 0, 10.5 * px, W * px);
  }
  g.strokeStyle = "rgba(255,255,255,0.78)";
  g.lineWidth = 0.14 * px;
  const rect = (x: number, y: number, w: number, h: number) => g.strokeRect(x * px, y * px, w * px, h * px);
  const circle = (x: number, y: number, r: number, a0 = 0, a1 = Math.PI * 2) => {
    g.beginPath();
    g.arc(x * px, y * px, r * px, a0, a1);
    g.stroke();
  };
  rect(0, 0, L, W);
  g.beginPath();
  g.moveTo((L / 2) * px, 0);
  g.lineTo((L / 2) * px, W * px);
  g.stroke();
  circle(L / 2, W / 2, 9.15);
  rect(0, (W - 40.32) / 2, 16.5, 40.32);
  rect(L - 16.5, (W - 40.32) / 2, 16.5, 40.32);
  rect(0, (W - 18.32) / 2, 5.5, 18.32);
  rect(L - 5.5, (W - 18.32) / 2, 5.5, 18.32);
  const arc = Math.acos(5.5 / 9.15);
  circle(11, W / 2, 9.15, -arc, arc);
  circle(L - 11, W / 2, 9.15, Math.PI - arc, Math.PI + arc);
  g.fillStyle = "rgba(255,255,255,0.8)";
  for (const [x, y] of [[L / 2, W / 2], [11, W / 2], [L - 11, W / 2]]) {
    g.beginPath();
    g.arc(x * px, y * px, 0.3 * px, 0, Math.PI * 2);
    g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function numberSprite(n: number, fill: string, ink: string, gk: boolean): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = c.height = 96;
  const g = c.getContext("2d")!;
  g.beginPath();
  g.arc(48, 48, 40, 0, Math.PI * 2);
  g.fillStyle = fill;
  g.fill();
  g.lineWidth = 7;
  g.strokeStyle = gk ? "#f8fafc" : "#020617";
  g.stroke();
  g.fillStyle = ink;
  g.font = "800 44px Inter, ui-sans-serif, system-ui, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(String(n), 48, 51);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  sp.scale.set(1.5, 1.5, 1);
  sp.renderOrder = 10;
  return sp;
}

function groundRing(r0: number, r1: number, color: string, opacity = 1): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.RingGeometry(r0, r1, 48),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
  m.rotation.x = -Math.PI / 2;
  m.position.y = 0.04;
  return m;
}

/** Flat strip on the grass between two pitch points, optionally dashed. */
function groundStrip(from: [number, number], to: [number, number], width: number, color: string, dash?: [number, number], opacity = 1, h = 0.06): THREE.Group {
  const grp = new THREE.Group();
  const a = v3(from[0], from[1], h);
  const b = v3(to[0], to[1], h);
  const len = a.distanceTo(b);
  if (len < 0.01) return grp;
  const dir = b.clone().sub(a).normalize();
  const ang = Math.atan2(dir.x, dir.z);
  const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, side: THREE.DoubleSide });
  const pieces: [number, number][] = [];
  if (dash) for (let s = 0; s < len; s += dash[0] + dash[1]) pieces.push([s, Math.min(len, s + dash[0])]);
  else pieces.push([0, len]);
  for (const [s0, s1] of pieces) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(width, s1 - s0), mat);
    // Lay the plane on the grass (X -90 deg), then turn it to face the strip direction about Y.
    m.rotation.set(-Math.PI / 2, ang, 0, "YXZ");
    m.position.copy(a.clone().addScaledVector(dir, (s0 + s1) / 2));
    grp.add(m);
  }
  return grp;
}

function arrowMesh(a: Arrow): { group: THREE.Group; hit: THREE.Mesh | undefined; labelAt: THREE.Vector3 } {
  const color = ARROW_COLOR[a.kind];
  const dash: [number, number] | undefined = a.kind === "actual" ? [1.4, 0.9] : a.kind === "alternative" ? [0.8, 0.7]
    : a.kind === "defense" ? [1, 0.6] : undefined;
  const width = a.kind === "selected" ? 0.75 : 0.5;
  const group = new THREE.Group();
  const [x1, y1] = a.from;
  const [x2, y2] = a.to;
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const head: [number, number] = [x2 - Math.cos(ang) * 2.2, y2 - Math.sin(ang) * 2.2];
  group.add(groundStrip([x1, y1], head, width, color, dash, a.kind === "alternative" ? 0.85 : 1));
  const tri = new THREE.Shape();
  const lx = head[0] + Math.cos(ang + Math.PI / 2) * 1.1;
  const ly = head[1] + Math.sin(ang + Math.PI / 2) * 1.1;
  const rx = head[0] + Math.cos(ang - Math.PI / 2) * 1.1;
  const ry = head[1] + Math.sin(ang - Math.PI / 2) * 1.1;
  // Shape lives in XY; rotating -90 deg about X maps shape y onto world -Z, so feed -z.
  tri.moveTo(x2 - L / 2, -(y2 - W / 2));
  tri.lineTo(lx - L / 2, -(ly - W / 2));
  tri.lineTo(rx - L / 2, -(ry - W / 2));
  const headMesh = new THREE.Mesh(new THREE.ShapeGeometry(tri),
    new THREE.MeshBasicMaterial({ color, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
  headMesh.rotation.x = -Math.PI / 2;
  headMesh.position.y = 0.07;
  group.add(headMesh);
  const hitGroup = groundStrip([x1, y1], [x2, y2], 3.2, "#000000", undefined, 0, 0.05);
  const hit = hitGroup.children[0] as THREE.Mesh | undefined;
  if (hit) hit.userData.arrowId = a.id;
  group.add(hitGroup);
  const side = ((a.rank ?? 1) % 2 === 0 ? 1 : -1) * (1.2 + (a.rank ?? 1) * 0.35);
  const mx = x1 + (x2 - x1) * 0.62 + Math.cos(ang + Math.PI / 2) * side;
  const my = y1 + (y2 - y1) * 0.62 + Math.sin(ang + Math.PI / 2) * side;
  return { group, hit, labelAt: v3(mx, my, 0.3) };
}

interface PlayerRig {
  group: THREE.Group;
  body: THREE.Mesh;
  hl: THREE.Mesh;
  sel: THREE.Mesh;
  last: THREE.Vector3 | null;
}

function disposeTree(o: THREE.Object3D) {
  o.traverse((c) => {
    const m = c as THREE.Mesh;
    m.geometry?.dispose();
    const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
    for (const mat of mats) {
      (mat as THREE.MeshBasicMaterial).map?.dispose();
      mat.dispose();
    }
  });
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function Pitch3D(p: PitchProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const labelsEl = useRef<HTMLDivElement>(null);
  const props = useRef(p);
  props.current = p;
  const [ok, setOk] = useState(true);
  // Imperative handles shared between the setup effect and the per-prop effects.
  const world = useRef<{
    scene: THREE.Scene; camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer;
    players: Map<string, PlayerRig>; ball: THREE.Mesh; ballShadow: THREE.Mesh; overlays: THREE.Group;
    border: THREE.LineLoop; hits: THREE.Mesh[]; labels: { el: HTMLElement; at: THREE.Vector3 }[];
  } | null>(null);

  // Scene, camera, pitch and player figures: built once per match.
  useEffect(() => {
    const host = wrap.current;
    if (!host) return;
    if (!webglAvailable()) {
      setOk(false);
      return;
    }
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor("#040906");
    renderer.domElement.className = "block h-full w-full";
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog("#040906", 95, 190);
    const camera = new THREE.PerspectiveCamera(34, 1, 1, 400);
    camera.position.set(0, 58, 78);

    scene.add(new THREE.HemisphereLight("#dff3d6", "#0b1a10", 1.1));
    const sun = new THREE.DirectionalLight("#ffffff", 1.6);
    sun.position.set(-30, 70, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -62, right: 62, top: 45, bottom: -45, near: 10, far: 200 });
    sun.shadow.bias = -0.0005;
    scene.add(sun);

    const apron = new THREE.Mesh(new THREE.PlaneGeometry(L + 40, W + 30), new THREE.MeshStandardMaterial({ color: "#0a2419", roughness: 1 }));
    apron.rotation.x = -Math.PI / 2;
    apron.position.y = -0.02;
    apron.receiveShadow = true;
    scene.add(apron);
    const pitch = new THREE.Mesh(new THREE.PlaneGeometry(L + 8, W + 8), new THREE.MeshStandardMaterial({ map: pitchTexture(), roughness: 0.95 }));
    pitch.rotation.x = -Math.PI / 2;
    pitch.receiveShadow = true;
    pitch.userData.pitch = true;
    scene.add(pitch);

    // Goals: posts, crossbar and a faint net.
    const postMat = new THREE.MeshStandardMaterial({ color: "#f8fafc", roughness: 0.4 });
    const netMat = new THREE.MeshBasicMaterial({ color: "#e2e8f0", transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false });
    for (const gx of [0, L]) {
      const out = gx === 0 ? -1 : 1;
      for (const z of [-3.66, 3.66]) {
        const post = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 2.44, 10), postMat);
        post.position.copy(v3(gx, W / 2 + z, 1.22));
        post.castShadow = true;
        scene.add(post);
      }
      const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 7.32, 10), postMat);
      bar.rotation.x = Math.PI / 2;
      bar.position.copy(v3(gx, W / 2, 2.44));
      bar.castShadow = true;
      scene.add(bar);
      const net = new THREE.Mesh(new THREE.BoxGeometry(1.8, 2.44, 7.32), netMat);
      net.position.copy(v3(gx + out * 0.9, W / 2, 1.22));
      scene.add(net);
    }

    const border = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints([v3(-2.6, -2.6, 0.05), v3(L + 2.6, -2.6, 0.05), v3(L + 2.6, W + 2.6, 0.05), v3(-2.6, W + 2.6, 0.05)]),
      new THREE.LineBasicMaterial({ color: "#d4ee8f", transparent: true, opacity: 0.9 }));
    scene.add(border);

    // Players: shorts, shirt, head, number badge and two ground rings (highlight, selectable).
    const { match } = props.current;
    const players = new Map<string, PlayerRig>();
    const legGeo = new THREE.CylinderGeometry(0.26 * S, 0.22 * S, 0.8 * S, 12);
    const torsoGeo = new THREE.CapsuleGeometry(0.3 * S, 0.55 * S, 4, 12);
    const headGeo = new THREE.SphereGeometry(0.2 * S, 16, 12);
    const headMat = new THREE.MeshStandardMaterial({ color: "#e7dccf", roughness: 0.8 });
    for (const pl of match.players) {
      const isHome = pl.team_id === match.home.team_id;
      const team = isHome ? match.home : match.away;
      const shirt = new THREE.MeshStandardMaterial({ color: pl.role === "GK" ? "#f8fafc" : team.color_primary, roughness: 0.6 });
      const shorts = new THREE.MeshStandardMaterial({ color: team.color_secondary || "#0f172a", roughness: 0.7 });
      const group = new THREE.Group();
      const legs = new THREE.Mesh(legGeo, shorts);
      legs.position.y = 0.4 * S;
      const body = new THREE.Mesh(torsoGeo, shirt);
      body.position.y = 1.15 * S;
      const head = new THREE.Mesh(headGeo, headMat);
      head.position.y = 1.72 * S;
      for (const m of [legs, body, head]) {
        m.castShadow = true;
        m.userData.playerId = pl.player_id;
      }
      const badge = numberSprite(pl.shirt_number, team.color_primary, isHome ? "#04263b" : "#2a1704", pl.role === "GK");
      badge.position.y = 2.55 * S;
      const hl = groundRing(1.5, 1.85, "#f8fafc", 0.9);
      const sel = groundRing(1.9, 2.15, "#34d399", 0.9);
      group.add(legs, body, head, badge, hl, sel);
      group.visible = false;
      scene.add(group);
      players.set(pl.player_id, { group, body, hl, sel, last: null });
    }

    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.42, 20, 14), new THREE.MeshStandardMaterial({ color: "#f8fafc", roughness: 0.35, emissive: "#334155", emissiveIntensity: 0.2 }));
    ball.castShadow = true;
    scene.add(ball);
    const ballShadow = new THREE.Mesh(new THREE.CircleGeometry(0.5, 20), new THREE.MeshBasicMaterial({ color: "#000000", transparent: true, opacity: 0.45, depthWrite: false }));
    ballShadow.rotation.x = -Math.PI / 2;
    ballShadow.position.y = 0.03;
    scene.add(ballShadow);

    const overlays = new THREE.Group();
    scene.add(overlays);
    world.current = { scene, camera, renderer, players, ball, ballShadow, overlays, border, hits: [], labels: [] };

    const resize = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // Pull the camera back on narrow screens so both goals stay in view.
      camera.fov = w / h < 1.2 ? 46 : 34;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();

    const look = new THREE.Vector3(0, 0, 3);
    const camPos = camera.position.clone();
    let raf = 0;
    let lastT = performance.now();
    const tick = (now: number) => {
      // Time-based easing: the camera settles in about a second whatever the frame rate.
      const k = 1 - Math.exp(-Math.min(0.25, (now - lastT) / 1000) * 4);
      lastT = now;
      const f = props.current.frame;
      const hlId = props.current.highlightId;
      const selectable = new Set(props.current.selectableIds ?? []);
      if (f) {
        for (const [id, rig] of players) {
          const pos = f.players[id];
          rig.group.visible = !!pos;
          if (!pos) continue;
          const at = v3(pos[0], pos[1]);
          // Face the direction of travel; keep the last heading while standing still.
          if (rig.last && at.distanceToSquared(rig.last) > 0.0004) rig.group.rotation.y = Math.atan2(at.x - rig.last.x, at.z - rig.last.z);
          rig.last = at.clone();
          rig.group.position.copy(at);
          rig.hl.visible = id === hlId || id === f.possessor_id;
          rig.sel.visible = selectable.has(id);
        }
        ball.position.copy(v3(f.ball[0], f.ball[1], 0.42 + Math.max(0, f.ball[2])));
        ballShadow.position.set(ball.position.x, 0.03, ball.position.z);
        const sc = Math.max(0.35, 1 - f.ball[2] * 0.12);
        ballShadow.scale.set(sc, sc, sc);
        // Broadcast follow: drift along the touchline with the ball, never far enough to lose shape.
        const tx = THREE.MathUtils.clamp((f.ball[0] - L / 2) * 0.45, -20, 20);
        camPos.x += (tx - camPos.x) * k;
        look.x += (tx - look.x) * k;
      }
      camera.position.copy(camPos);
      camera.lookAt(look);
      renderer.render(scene, camera);
      const w = host.clientWidth;
      const h = host.clientHeight;
      for (const lb of world.current?.labels ?? []) {
        const q = lb.at.clone().project(camera);
        lb.el.style.transform = `translate(${((q.x + 1) / 2) * w}px, ${((1 - q.y) / 2) * h}px) translate(-50%, -100%)`;
        lb.el.style.visibility = q.z < 1 ? "visible" : "hidden";
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    // Picking: players (when selectable), then arrows, then the grass.
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    type Pick = { player: string } | { arrow: string } | { point: [number, number] } | null;
    const pick = (ev: PointerEvent): Pick => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const cur = props.current;
      const sel = new Set(cur.selectableIds ?? []);
      if (sel.size && cur.onPlayerClick) {
        const bodies = [...players.entries()].filter(([id, rg]) => sel.has(id) && rg.group.visible).flatMap(([, rg]) => rg.group.children);
        const hit = ray.intersectObjects(bodies, false).find((h) => h.object.userData.playerId);
        if (hit) return { player: hit.object.userData.playerId as string };
        // Figures are small from the broadcast camera: a click on the grass picks the nearest selectable teammate.
        const ground = ray.intersectObject(pitch, false)[0];
        if (ground) {
          let best: [string, number] | null = null;
          for (const id of sel) {
            const rg = players.get(id);
            if (!rg?.group.visible) continue;
            const d = rg.group.position.distanceTo(new THREE.Vector3(ground.point.x, 0, ground.point.z));
            if (d < 3.5 && (!best || d < best[1])) best = [id, d];
          }
          if (best) return { player: best[0] };
        }
      }
      if (cur.onArrowClick && world.current?.hits.length) {
        const hit = ray.intersectObjects(world.current.hits, false)[0];
        if (hit) return { arrow: hit.object.userData.arrowId as string };
      }
      if (cur.onPitchClick) {
        const hit = ray.intersectObject(pitch, false)[0];
        if (hit) {
          const x = hit.point.x + L / 2;
          const y = hit.point.z + W / 2;
          if (x >= 0 && x <= L && y >= 0 && y <= W) return { point: [x, y] };
        }
      }
      return null;
    };
    const onClick = (ev: PointerEvent) => {
      const r = pick(ev);
      if (!r) return;
      if ("player" in r) props.current.onPlayerClick?.(r.player);
      else if ("arrow" in r) props.current.onArrowClick?.(r.arrow);
      else props.current.onPitchClick?.(r.point[0], r.point[1]);
    };
    const onMove = (ev: PointerEvent) => {
      const r = pick(ev);
      renderer.domElement.style.cursor = r ? ("point" in r ? "crosshair" : "pointer") : "default";
    };
    renderer.domElement.addEventListener("click", onClick as EventListener);
    // Development-only hook for end-to-end tests: where a player stands on screen, relative to the canvas.
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __pitch3d?: unknown }).__pitch3d = {
        screenOf(id: string): [number, number] | null {
          const rig = players.get(id);
          if (!rig?.group.visible) return null;
          const q = rig.body.getWorldPosition(new THREE.Vector3()).project(camera);
          return [((q.x + 1) / 2) * host.clientWidth, ((1 - q.y) / 2) * host.clientHeight];
        },
      };
    }
    renderer.domElement.addEventListener("pointermove", onMove);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("click", onClick as EventListener);
      renderer.domElement.removeEventListener("pointermove", onMove);
      disposeTree(scene);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      world.current = null;
    };
  }, [p.match]);

  // Overlays (arrows, trails, lanes, rings, marker, tint) are rebuilt only when they change.
  const overlayKey = JSON.stringify([p.arrows, p.trail?.length, p.ghostTrail?.length, p.rings, p.lanes, p.marker, p.tint, p.dimmed]);
  useEffect(() => {
    const wd = world.current;
    const host = labelsEl.current;
    if (!wd || !host) return;
    for (const c of [...wd.overlays.children]) {
      wd.overlays.remove(c);
      disposeTree(c);
    }
    host.replaceChildren();
    wd.hits = [];
    wd.labels = [];
    const cur = props.current;
    const tint = cur.tint === "simulated" ? "#d4ee8f" : cur.tint === "snapshot" ? "#cfe2b4" : null;
    wd.border.visible = !!tint;
    if (tint) (wd.border.material as THREE.LineBasicMaterial).color.set(tint);
    const line = (pts: [number, number][], color: string, opacity: number, h = 0.08) => {
      const geo = new THREE.BufferGeometry().setFromPoints(pts.map(([x, y]) => v3(x, y, h)));
      return new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
    };
    if (cur.ghostTrail && cur.ghostTrail.length > 1) wd.overlays.add(line(cur.ghostTrail, "#f8fafc", 0.35));
    if (cur.trail && cur.trail.length > 1) {
      for (let i = 1; i < cur.trail.length; i++) wd.overlays.add(groundStrip(cur.trail[i - 1], cur.trail[i], 0.45, "#8fca7c", undefined, 0.9, 0.07));
    }
    for (const ln of cur.lanes ?? []) {
      wd.overlays.add(groundStrip(ln.from, ln.to, 0.3, ln.quality > 0.7 ? "#22c55e" : ln.quality > 0.4 ? "#eab308" : "#ef4444", [0.5, 0.5], 0.6, 0.05));
    }
    for (const r of cur.rings ?? []) {
      const ring = groundRing(r.r - 0.15, r.r, "#ef4444", 0.6);
      ring.position.copy(v3(r.x, r.y, 0.04));
      wd.overlays.add(ring);
      const disc = new THREE.Mesh(new THREE.CircleGeometry(r.r, 48), new THREE.MeshBasicMaterial({ color: "#ef4444", transparent: true, opacity: 0.07, depthWrite: false }));
      disc.rotation.x = -Math.PI / 2;
      disc.position.copy(v3(r.x, r.y, 0.035));
      wd.overlays.add(disc);
    }
    for (const a of cur.arrows ?? []) {
      const { group, hit, labelAt } = arrowMesh(a);
      wd.overlays.add(group);
      if (hit) wd.hits.push(hit);
      const el = document.createElement("span");
      const color = ARROW_COLOR[a.kind];
      el.className = "pointer-events-none absolute left-0 top-0 whitespace-nowrap border bg-slate-950/85 px-1.5 py-0.5 text-[11px] font-semibold shadow-lg";
      el.style.borderColor = color;
      el.style.color = color;
      el.textContent = `${a.rank != null ? `${a.rank}. ` : ""}${a.label}`;
      host.append(el);
      wd.labels.push({ el, at: labelAt });
    }
    if (cur.marker) {
      const c = cur.marker.ok ? "#34d399" : "#ef4444";
      const ring = groundRing(1.3, 1.65, c);
      ring.position.copy(v3(cur.marker.x, cur.marker.y, 0.05));
      wd.overlays.add(ring);
    }
    const dim = cur.dimmed ? 0.55 : 1;
    for (const rig of wd.players.values()) {
      rig.group.traverse((o) => {
        const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
        if (m && o !== rig.hl && o !== rig.sel) {
          m.transparent = dim < 1;
          m.opacity = dim;
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, p.match]);

  if (!ok) {
    return (
      <div className="relative">
        <Pitch {...p} />
        <p className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-slate-950/85 px-2 py-1 text-[11px] text-slate-300">3D needs WebGL; showing the 2D board.</p>
      </div>
    );
  }
  return (
    <div ref={wrap} className="relative aspect-[111/74] w-full overflow-hidden" role="img" aria-label={`${p.ariaLabel} (3D replay)`}
      data-testid="pitch-3d">
      <div ref={labelsEl} className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden />
    </div>
  );
}
