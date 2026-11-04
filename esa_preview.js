const instances = new WeakMap();
let libraryPromise;
function loadAladin(url) {
  if (!libraryPromise) libraryPromise=import(url).then(async module=>{await module.default.init;return module.default;}).catch(error=>{libraryPromise=null;throw error;});
  return libraryPromise;
}
export default function(component) {
  const {parentElement:root,data,setStateValue}=component;
  const find=id=>root.querySelector('#'+id);
  let state=instances.get(root);
  if(!state){
    let crop=1;
    try{const saved=Number(sessionStorage.getItem('mw-astro-preview-crop'));if([1,.75,.5,.33].includes(saved))crop=saved;}catch(_){}
    state={viewer:null,pending:false,key:null,disposed:false,crop,viewSignature:null};instances.set(root,state);
  }
  state.data=data;state.setStateValue=setStateValue;
  const angle=find('angle'),frame=find('frame'),status=find('status'),retry=find('retry');
  angle.value=data.rotation;
  frame.setAttribute('x',300-data.width/2);frame.setAttribute('y',300-data.height/2);
  frame.setAttribute('width',data.width);frame.setAttribute('height',data.height);
  const labelX=300-data.width/2;
  find('dimensions').setAttribute('y',300+data.height/2+17);
  for(const id of ['frame-fov','frame-resolution','frame-scale'])find(id).setAttribute('x',labelX);
  find('frame-fov').textContent=`FOV: ${data.fov_width.toFixed(2)}° × ${data.fov_height.toFixed(2)}°`;
  find('frame-resolution').textContent=`Resolution: ${data.camera_width_px} × ${data.camera_height_px} pixels`;
  const scaleX=data.pixel_scale_width.toFixed(2),scaleY=data.pixel_scale_height.toFixed(2);
  find('frame-scale').textContent=`Scale: ${scaleX===scaleY?scaleX:scaleX+' × '+scaleY} arcsec/pixel`;
  const applyView=()=>{
    const current=state.data,factor=state.crop,cropped=factor!==1;
    const cropAngle=degrees=>2*Math.atan(Math.tan(degrees*Math.PI/360)*factor)*180/Math.PI;
    const field=cropped?cropAngle(current.fov_width):current.image_field;
    const rotation=cropped?(-Number(angle.value)||360):360;
    const box=find('sky-frame');
    box.style.aspectRatio=cropped?`${current.width} / ${current.height}`:'1';
    box.style.setProperty('--preview-aspect',cropped?current.width/current.height:1);
    box.classList.toggle('cropped',cropped);find('overlay').style.display=cropped?'none':'';
    find('crop').value=String(factor);
    const width=Math.floor(current.camera_width_px*factor),height=Math.floor(current.camera_height_px*factor);
    const cropField=cropped?` · FOV ${cropAngle(current.fov_width).toFixed(2)}° × ${cropAngle(current.fov_height).toFixed(2)}°`:'';
    find('crop-details').textContent=`${cropped?Math.round(factor*100)+'% of width and height retained':'Full frame'} · ${width} × ${height} pixels · ${(width*height/1e6).toFixed(1)} MP${cropField}`;
    find('large-details').textContent=find('crop-details').textContent;
    const signature=JSON.stringify([field,rotation,cropped,current.width/current.height]);
    if(state.viewer&&signature!==state.viewSignature){
      // Release the previous fixed scale before selecting the new crop scale.
      state.viewer.setFoVRange(.00001,360);
      state.viewer.setFoV(field);state.viewer.setRotation(rotation);
      state.viewer.setFoVRange(field,field);
      state.viewSignature=signature;
    }
  };
  const rotate=()=>{find('camera-frame').setAttribute('transform',`rotate(${-Number(angle.value)} 300 300)`);find('angle-value').textContent=angle.value;applyView();};
  angle.oninput=rotate;angle.onchange=()=>state.setStateValue('rotation',Number(angle.value));rotate();
  find('crop').onchange=()=>{
    const factor=Number(find('crop').value);
    if(![1,.75,.5,.33].includes(factor))return;
    state.crop=factor;
    try{sessionStorage.setItem('mw-astro-preview-crop',String(factor));}catch(_){}
    applyView();
  };
  const dialog=find('large-view'),home=find('preview-home');
  find('enlarge').onclick=()=>{
    if(dialog.open)return;
    // Move the existing viewer, retaining pan/crop and allowing higher-resolution tiles.
    home.style.height=find('sky-frame').getBoundingClientRect().height+'px';
    find('large-slot').appendChild(find('sky-frame'));
    dialog.showModal();
  };
  dialog.onclose=()=>{home.appendChild(find('sky-frame'));home.style.height='';};
  find('close-large').onclick=()=>dialog.close();
  const storageKey=()=>`mw-astro-esa-centre:${state.data.view_key}:${state.data.image_field}`;
  const publishCentre=()=>{
    const position=state.viewer.getRaDec();
    const value={view_key:state.data.view_key,ra:position[0],dec:position[1]};
    const stamp=JSON.stringify(value);
    if(stamp!==state.lastPublishedCentre){state.lastPublishedCentre=stamp;state.setStateValue('centre',value);}
  };
  const centre=()=>{
    const current=state.data;
    let position=[current.ra,current.dec];
    try{const saved=JSON.parse(sessionStorage.getItem(storageKey()));if(Array.isArray(saved)&&saved.length===2&&saved.every(Number.isFinite)&&saved[0]>=0&&saved[0]<360&&Math.abs(saved[1])<=90)position=saved;}catch(_){}
    state.viewer.gotoRaDec(...position);state.viewSignature=null;applyView();
    state.key=current.view_key;status.textContent='';retry.hidden=true;publishCentre();
  };
  const checkProvider=async()=>{
    const response=await fetch(state.data.survey+'/properties',{signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw new Error('ESA survey unavailable');
    if(!state.disposed){status.textContent='';retry.hidden=true;}
  };
  const failed=error=>{if(!state.disposed){status.textContent='ESA DSS2 colour preview could not load. Check your connection and retry.';retry.hidden=false;console.error('ESA DSS2 preview:',error);}};
  const initialise=async()=>{
    if(state.pending||state.disposed)return;
    if(state.viewer){if(state.key!==state.data.view_key)centre();return;}
    state.pending=true;status.textContent='Loading ESA DSS2 colour survey…';retry.hidden=true;
    try{
      const A=await loadAladin(state.data.module_url);
      if(state.disposed)return;
      const current=state.data;
      state.viewer=A.aladin(find('sky'),{survey:A.imageHiPS(current.survey,{name:'DSS2 colour (ESA)',imgFormat:'jpeg'}),target:`${current.ra} ${current.dec}`,fov:current.image_field,projection:'TAN',cooFrame:'ICRS',showReticle:false,showZoomControl:false,showFullscreenControl:false,showLayersControl:false,showGotoControl:false,showShareControl:false,showSimbadPointerControl:false,showFrame:false,showFov:false,showCooLocation:false,showProjectionControl:false,showContextMenu:false,showStatusBar:false});
      centre();
      state.viewer.on('positionChanged',()=>{try{sessionStorage.setItem(storageKey(),JSON.stringify(state.viewer.getRaDec()));}catch(_){} clearTimeout(state.centreTimer);state.centreTimer=setTimeout(publishCentre,250);});
      // Keep the image scale fixed so the sensor overlay remains geometrically correct.
      find('sky').addEventListener('wheel',event=>event.preventDefault(),{passive:false,capture:true});
      // Check the actual image provider separately from viewer initialisation.
      await checkProvider();
    }catch(error){failed(error);}
    finally{state.pending=false;}
  };
  find('centre').onclick=()=>{if(state.viewer){try{sessionStorage.removeItem(storageKey());}catch(_){}centre();}};
  retry.onclick=async()=>{
    if(!state.viewer){await initialise();return;}
    if(state.pending)return;
    state.pending=true;status.textContent='Loading ESA DSS2 colour survey…';retry.hidden=true;
    try{await checkProvider();state.viewer.setBaseImageLayer(state.data.survey);centre();}
    catch(error){failed(error);}finally{state.pending=false;}
  };
  initialise();
  return ()=>{clearTimeout(state.centreTimer);state.disposed=true;if(dialog.open)dialog.close();instances.delete(root);};
}
