// Keep the iframe and its click markers alive across unchanged Streamlit reruns.
const instances = new WeakMap();
export default function(component) {
  const {parentElement, data, setStateValue} = component;
  const frame = parentElement.querySelector('iframe');
  let state = instances.get(frame);
  if (!state) {
    state = {html: null, setStateValue, interval: null};
    state.receive = event => {
      if (event.source !== frame.contentWindow || event.data?.type !== 'mw-astro-interval') return;
      const value = JSON.stringify(event.data.points);
      if (value === state.interval) return;
      state.interval = value;
      state.setStateValue('interval', event.data.points);
    };
    window.addEventListener('message', state.receive);
    instances.set(frame, state);
  }
  state.setStateValue = setStateValue;
  if (state.html !== data.html) {
    state.html = data.html;
    frame.srcdoc = data.html;
  }
  return () => {
    window.removeEventListener('message', state.receive);
    instances.delete(frame);
  };
}
