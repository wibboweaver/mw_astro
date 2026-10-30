/* Pure interval calculations, shared by the browser and regression tests. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Observation = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  function select(points, timestamp, first, last) {
    if (!Number.isFinite(timestamp) || timestamp < first || timestamp > last) return points.slice();
    // A third click begins a fresh two-click interval.
    return points.length === 2 ? [timestamp] : [...points, timestamp];
  }
  function summary(points, exposureSeconds, pointerTime=null) {
    if (!Number.isFinite(exposureSeconds) || exposureSeconds <= 0) throw new Error('Exposure must be positive.');
    if (points.length === 1 && Number.isFinite(pointerTime)) points = [points[0], Math.round(pointerTime/1000)*1000];
    if (points.length !== 2) return null;
    const seconds = Math.round(Math.abs(points[1] - points[0]) / 1000);
    return {seconds, images: Math.floor(seconds / exposureSeconds)};
  }
  function duration(seconds) {
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = Math.floor(seconds % 60);
    return [h,m,s].map(v => String(v).padStart(2,'0')).join(':');
  }
  function restore(raw, first, last) {
    try {
      const values = JSON.parse(raw);
      return Array.isArray(values) && values.length <= 2 && values.every(v => Number.isFinite(v) && v >= first && v <= last) ? values : [];
    } catch (_) { return []; }
  }
  return {select, summary, duration, restore};
});
