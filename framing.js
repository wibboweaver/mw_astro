export default function(component) {
  const {parentElement: root, data, setStateValue} = component;
  const find = id => root.querySelector('#' + id);
  const angle = find('angle'), frame = find('frame'), canvas = find('canvas'), survey = find('survey');
  const storageKey = `mw-astro-pan:${data.view_key}:${data.image_field}`;
  let pan = {x: 0, y: 0};
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey));
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) pan = saved;
  } catch (_) { /* Framing still works when browser storage is unavailable. */ }
  const limit = value => Math.max(-300, Math.min(300, value));
  pan = {x: limit(pan.x), y: limit(pan.y)};
  const save = () => {try {sessionStorage.setItem(storageKey, JSON.stringify(pan));} catch (_) {}};
  survey.setAttribute('href', data.image);
  frame.setAttribute('x', 300 - data.width / 2);
  frame.setAttribute('y', 300 - data.height / 2);
  frame.setAttribute('width', data.width);
  frame.setAttribute('height', data.height);
  angle.value = data.rotation;
  find('dimensions').textContent = `Camera field: ${data.fov_width.toFixed(2)}° × ${data.fov_height.toFixed(2)}° · ${data.camera_width_px} × ${data.camera_height_px} pixels`;
  function draw() {
    frame.setAttribute('transform', `rotate(${-Number(angle.value)} 300 300)`);
    survey.setAttribute('transform', `translate(${pan.x} ${pan.y})`);
    find('angle-value').textContent = angle.value;
  }
  let drag = null;
  // Map screen coordinates through SVG's inverse matrix: works at every responsive size.
  function point(event) {
    const matrix = canvas.getScreenCTM();
    if (!matrix) return null;
    return new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
  }
  canvas.onpointerdown = event => {
    if (event.button !== 0 || drag) return;
    const position = point(event);
    if (!position) return;
    drag = {id: event.pointerId, x: position.x, y: position.y, initial: {...pan}};
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add('dragging');
    event.preventDefault();
  };
  canvas.onpointermove = event => {
    if (!drag || event.pointerId !== drag.id) return;
    const position = point(event);
    if (!position) return;
    pan = {x: limit(drag.initial.x + position.x - drag.x), y: limit(drag.initial.y + position.y - drag.y)};
    draw();
  };
  const finish = event => {
    if (!drag || event.pointerId !== drag.id) return;
    const id = drag.id;
    drag = null;
    if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
    canvas.classList.remove('dragging');
    save();
  };
  canvas.onpointerup = canvas.onpointercancel = canvas.onlostpointercapture = finish;
  // Rotate locally during input; only the committed angle goes to the server.
  angle.oninput = draw;
  angle.onchange = () => {save(); setStateValue('rotation', Number(angle.value));};
  find('centre').onclick = () => {pan = {x:0, y:0}; save(); draw();};
  draw();
  return () => {
    angle.oninput = angle.onchange = null;
    find('centre').onclick = null;
    canvas.onpointerdown = canvas.onpointermove = canvas.onpointerup = canvas.onpointercancel = canvas.onlostpointercapture = null;
  };
}
