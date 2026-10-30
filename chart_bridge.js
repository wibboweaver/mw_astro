export default function(component) {
  const {parentElement, data, setStateValue} = component;
  const frame = parentElement.querySelector('iframe');
  const receive = event => {
    if (event.source !== frame.contentWindow || event.data?.type !== 'mw-astro-interval') return;
    setStateValue('interval', event.data.points);
  };
  window.addEventListener('message', receive);
  frame.srcdoc = data.html;
  return () => window.removeEventListener('message', receive);
}
