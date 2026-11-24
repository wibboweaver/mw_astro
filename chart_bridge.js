// Keep the iframe and its click markers alive across unchanged Streamlit reruns.
const instances = new WeakMap();
export default function(component) {
  const {parentElement, data, setStateValue, setTriggerValue} = component;
  const frame = parentElement.querySelector('iframe');
  let state = instances.get(frame);
  if (!state) {
    state = {html: null, setStateValue, setTriggerValue, interval: null};
    state.receive = event => {
      if (event.source !== frame.contentWindow) return;
      if (event.data?.type === 'mw-astro-clear-objects') {
        state.setTriggerValue('clear_objects', true);
        return;
      }
      if (event.data?.type !== 'mw-astro-interval') return;
      const value = JSON.stringify(event.data.points);
      if (value === state.interval) return;
      state.interval = value;
      state.setStateValue('interval', event.data.points);
    };
    window.addEventListener('message', state.receive);
    instances.set(frame, state);
  }
  state.setStateValue = setStateValue;
  state.setTriggerValue = setTriggerValue;
  if (state.html !== data.html) {
    state.html = data.html;
    frame.srcdoc = data.html;
  }
  return () => {
    window.removeEventListener('message', state.receive);
    instances.delete(frame);
  };
}
