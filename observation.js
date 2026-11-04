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
  function interpolate(times, values, timestamp) {
    if (!times || !values || times.length !== values.length || !times.length) return null;
    const t=Math.max(times[0],Math.min(times[times.length-1],timestamp));
    let i=0;while(i<times.length-2&&times[i+1]<t)i++;
    if (times.length===1) return Number.isFinite(values[0])?values[0]:null;
    const a=values[i],b=values[i+1];
    if (!Number.isFinite(a)||!Number.isFinite(b)) return null;
    return a+(b-a)*(t-times[i])/(times[i+1]-times[i]);
  }
  function moonPhase(angle){
    if(!Number.isFinite(angle))return {icon:'○',name:'Moon phase unavailable'};
    const index=Math.floor((((angle%360)+360)%360+22.5)/45)%8;
    return {icon:['🌑','🌒','🌓','🌔','🌕','🌖','🌗','🌘'][index],name:['New Moon','Waxing crescent','First quarter','Waxing gibbous','Full Moon','Waning gibbous','Last quarter','Waning crescent'][index]};
  }
  function moonRating(separation,altitude,illumination,intervals,timestamp,enabled){
    if(!enabled||![separation,altitude,illumination].every(Number.isFinite))return 'Unknown';
    const interval=(intervals||[]).find(p=>timestamp>=p.start&&timestamp<p.end);
    return interval?.level==='strong'?'High impact':interval?'Moderate impact':'Low impact';
  }
  return {select, summary, duration, restore, interpolate, moonPhase, moonRating};
});
