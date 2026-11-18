// Set preview for the dashboard (web/src/components/SetPreview.vue): one set seen through the wide camera, with
// two grey stand-ins on the stage for scale. Not used by renders. One WebGL renderer is shared by every preview
// (browsers cap live contexts); the picture is copied into the caller's 2D canvas.
import * as THREE from "three";
import { setLibrary } from "./library.js";
import { buildSet } from "./world.js";

let gl = null;
const grey = new THREE.MeshBasicMaterial({ color: 0x9a948a });
const standIn = (x) => {
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 1.1), grey);
  body.position.set(x, 0.55, 0);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.22), grey);
  head.position.set(x, 1.35, 0);
  return new THREE.Group().add(body, head);
};

function dispose(o) {
  o.traverse((m) => {
    if (!m.isMesh) return;
    m.geometry.dispose();
    if (m.material !== grey) { m.material.map?.dispose(); m.material.dispose(); }
  });
}

/** draw set `name` (built-in, or one of `custom`) into a 2D canvas; throws the builder's error (stage clearance) */
export function previewSet(out, name, custom) {
  const { width: w, height: h } = out;
  gl ??= new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  gl.setSize(w, h, false);
  const camera = new THREE.PerspectiveCamera(50, w / h, 0.05, 100); // main.js ANGLES.wide
  camera.position.set(0, 1.5, 6.5);
  camera.lookAt(0, 1.35, 0);
  const scene = new THREE.Scene();
  try {
    setLibrary({ sets: custom || [] });
    const set = buildSet(name, "preview");
    scene.add(set, standIn(-0.9), standIn(0.9));
    scene.background = set.userData.background;
    scene.fog = set.userData.fog || null;
    gl.render(scene, camera);
    const g = out.getContext("2d");
    g.clearRect(0, 0, w, h);
    g.drawImage(gl.domElement, 0, 0, w, h);
  } finally {
    dispose(scene);
  }
}
