'use strict';
const $=id=>document.getElementById(id);
let language='fr',catalog={},patterns=[],currentState=null,currentResult=null,revision=-1,sending=false,optionsDirty=false,updateState=null;
function t(text){
  if(language==='fr')return text;
  if(Object.prototype.hasOwnProperty.call(catalog,text))return catalog[text];
  for(const[expression,replacement,indices]of patterns)text=text.replace(expression,(...args)=>replacement.replace(/\{(\d+)\}/g,(_,n)=>args[1+indices.indexOf(Number(n))]));
  for(const[fr,en]of Object.entries(catalog).filter(([fr])=>!/\{\d+\}/.test(fr)).sort((a,b)=>b[0].length-a[0].length))text=text.split(fr).join(en);
  return text;
}
function number(value,decimals=0){return Number(value).toLocaleString(language==='fr'?'fr-FR':'en-GB',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});}
// Signe seulement pour une valeur affichée non nulle : « 0 m », jamais « −0 m ».
function signedMetres(sign,value){const text=number(value);return(/^[-−]?0$/.test(text)?'0':sign+text)+' m';}
function size(value){
  if(value>=1048576)return number(value/1048576,1)+' '+t('Mio');
  if(value>=1024)return number(value/1024,1)+' '+t('Kio');
  return number(value)+' '+t('octets');
}
function clock(value,full=true){
  if(value===null)return'—';
  return new Date(value*1000).toLocaleString(language==='fr'?'fr-FR':'en-GB',full
    ?{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}:{hour:'2-digit',minute:'2-digit'});
}
function notify(error){$('notice').querySelector('span').textContent=t(error.message||String(error));$('notice').hidden=false;}
const plot=new GpxChart.ProfilePlot($('chart'),{t,number,time:clock,select:window.api.select,error:notify,changed:updatePlotControls});
function applyLanguage(){
  document.querySelectorAll('[data-i18n]').forEach(el=>{if(!el.dataset.original)el.dataset.original=el.textContent;el.textContent=t(el.dataset.original);});
  $('dropzone').setAttribute('aria-label',t('Choisir ou déposer un GPX'));
  $('chart').setAttribute('aria-label',t("Profils d'altitude : terrain lissé et mesures GPX"));
  document.querySelectorAll('[aria-label="Fermer"],[aria-label="Close"]').forEach(el=>el.setAttribute('aria-label',t('Fermer')));
  if(currentState)render(currentState);renderUpdate();plot.draw();
}
document.addEventListener('nico579-langue',event=>{language=event.detail.code;applyLanguage();});
function updatePlotControls(){
  const has=!!plot.data;['zoom-in','zoom-out','fullscreen'].forEach(id=>$(id).disabled=!has);
  $('reset').disabled=!has||plot.view.every((x,i)=>Math.abs(x-plot.bounds[i])<1e-8);
  $('chart-empty').hidden=has;
  const full=!!document.fullscreenElement||$('plot-panel').classList.contains('expanded');
  $('fullscreen').textContent=t(full?'Quitter le plein écran':'Plein écran');
  const s=plot.selection;
  $('selection').textContent=s
    ?t('Distance : {0} km').replace('{0}',number(s.distance/1000,3))+' · '+t('Heure locale : ')+clock(s.time)
      +' · '+t('Terrain lissé : {0} m').replace('{0}',s.terrain===null?'—':number(s.terrain,1))
      +' · '+t(s.interpolated?'GPX interpolé : {0} m':'Mesure GPX : {0} m').replace('{0}',s.gpx===null?'—':number(s.gpx,1))
    :t('Touchez la courbe pour lire les valeurs.');
}
function gainText(gain){return gain?'D+ '+number(gain.Dplus_m)+' m / D− '+number(gain.Dmoins_m)+' m':t('altitudes absentes ou incomplètes');}
function render(state){
  const busy=state.busy||sending;
  ['import','model','online'].forEach(id=>$(id).disabled=busy);$('recalculate').disabled=busy||!state.has_input;
  $('clear-cache').disabled=busy||!Object.values(state.cache).some(x=>x>0)||!!state.cache_error;
  $('cancel').hidden=state.phase!=='calculate'||!state.busy;$('cancel').disabled=state.message==='Annulation en cours…';
  if(!optionsDirty){$('online').checked=state.online;$('model').value=state.model||'';}
  const progress=$('progress');progress.hidden=!state.busy;
  if(state.total>0){progress.max=state.total;progress.value=state.completed;}else progress.removeAttribute('value');
  $('status').textContent=t(state.message);$('filename').textContent=state.filename||t('Déposez un fichier GPX ici');$('input-note').hidden=!!state.filename;
  $('cache').textContent=state.cache_error?t(state.cache_error):size(state.cache.profiles+state.cache.tiles)+' · '+t('Profils')+' '+size(state.cache.profiles)+' · '+t('Tuiles')+' '+size(state.cache.tiles);
  const available=currentResult&&state.has_result,summary=available?currentResult.summary:null;
  $('export-summary').disabled=!available;$('export-profile').disabled=!available;
  if(!summary){
    $('up').textContent='— m';$('down').textContent='— m';$('length').textContent='— km';
    $('source').textContent=t(state.phase==='error'?'Aucun profil complet disponible':'Source : sélection automatique selon la couverture');
    $('comparison').textContent=t(state.busy?'Calcul en cours…':"Altitudes GPX : les sommes brutes et filtrées seront affichées après le calcul.");
    $('range').textContent=t('Profil lissé · pas 5 m · gaussienne σ = 20 m · hystérésis 2 m');
    $('details').hidden=state.phase!=='error';$('details').textContent=t(state.message);
  }else{
    $('up').textContent=signedMetres('+',summary.terrain.Dplus_m);$('down').textContent=signedMetres('−',summary.terrain.Dmoins_m);
    $('length').textContent=number(summary.distance_m/1000,2)+' km';$('filename').textContent=summary.fichier;
    $('source').textContent=t('Source : ')+summary.modele+(summary.depuis_cache?t(' · profil en cache'):'');
    $('range').textContent=t('Terrain lissé')+' '+number(summary.altitude_min_m)+'–'+number(summary.altitude_max_m)+' m · '+t('pas 5 m · σ = 20 m · hystérésis 2 m');
    $('comparison').textContent=t('Somme brute des variations : ')+gainText(summary.gpx_somme_brute)+'\n'+t('GPX rééchantillonné et filtré : ')+gainText(summary.gpx_filtre);
    const messages=[];
    if(summary.avertissement_cache)messages.push(t("Le profil n'a pas pu être enregistré dans le cache. Le résultat reste disponible, mais son utilisation hors connexion n'est pas assurée."));
    if(summary.replis.length)messages.push(t('Repli entre modèles :')+'\n'+summary.replis.map(r=>r.modele+' : '+t(r.raison)).join('\n'));
    if(state.phase==='error')messages.push(t(state.message));$('details').textContent=messages.join('\n\n');$('details').hidden=!messages.length;
    if(state.phase==='done'&&state.message==='Calcul terminé')$('status').textContent=t('Calcul terminé')+' · '+number(summary.points_origine)+' '+t('points GPX')+' · '+number(summary.positions_5m)+' '+t('positions à 5 m');
  }
}
async function refresh(){
  const state=await window.api.state();currentState=state;
  if(state.revision!==revision){const result=await window.api.result();revision=result.revision;currentResult=result.summary?result:null;plot.setData(result.chart,result.summary);}
  render(state);
}
const options=()=>({online:$('online').checked,model:$('model').value||null});
async function upload(file){
  if(!file||sending||!currentState||currentState.busy)return;
  if(!/\.gpx$/i.test(file.name))return notify(new Error("Ce fichier n'est pas un GPX."));
  if(file.size>20*1024*1024)return notify(new Error('Le GPX dépasse 20 Mo.'));
  sending=true;render(currentState);
  try{
    const content=await new Promise((resolve,reject)=>{
      const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Lecture du GPX impossible.'));reader.readAsDataURL(file);
    });
    await window.api.upload({name:file.name,content,...options()});optionsDirty=false;$('notice').hidden=true;
  }catch(error){notify(error);}
  finally{sending=false;$('file').value='';await refresh().catch(notify);}
}
$('import').onclick=()=>$('file').click();$('file').onchange=e=>upload(e.target.files[0]);
$('dropzone').onclick=()=>{if(currentState&&!currentState.busy)$('file').click();};
$('dropzone').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('dropzone').click();}};
document.addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('Files')){e.preventDefault();$('dropzone').classList.add('dragover');}});
document.addEventListener('dragleave',e=>{if(!e.relatedTarget)$('dropzone').classList.remove('dragover');});
document.addEventListener('drop',e=>{e.preventDefault();$('dropzone').classList.remove('dragover');upload([...e.dataTransfer.files].find(f=>/\.gpx$/i.test(f.name))||e.dataTransfer.files[0]);});
['model','online'].forEach(id=>$(id).onchange=()=>{optionsDirty=true;});
$('recalculate').onclick=async()=>{try{await window.api.recalculate(options());optionsDirty=false;await refresh();}catch(error){notify(error);}};
$('cancel').onclick=async()=>{try{await window.api.cancel();await refresh();}catch(error){notify(error);}};
$('zoom-in').onclick=()=>plot.zoom(2);$('zoom-out').onclick=()=>plot.zoom(.5);$('reset').onclick=()=>plot.reset();
$('fullscreen').onclick=async()=>{
  const panel=$('plot-panel');
  if(document.fullscreenElement)await document.exitFullscreen();
  else if(panel.classList.contains('expanded'))panel.classList.remove('expanded');
  else{try{await panel.requestFullscreen();}catch(_){panel.classList.add('expanded');}}
  plot.draw();
};
document.addEventListener('fullscreenchange',()=>plot.draw());
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('plot-panel').classList.remove('expanded');plot.draw();}});
async function download(kind){
  try{
    const exported=await window.api.export(kind),blob=new Blob([exported.content],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=exported.name;document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){notify(error);}
}
$('export-summary').onclick=()=>download('summary');$('export-profile').onclick=()=>download('profile');
$('about').onclick=()=>$('about-dialog').showModal();$('notice').querySelector('button').onclick=()=>$('notice').hidden=true;
function confirmAction(title,text,action){
  const dialog=$('confirm-dialog');$('confirm-title').textContent=t(title);$('confirm-text').textContent=t(text);$('confirm-action').textContent=t(action);
  dialog.returnValue='cancel';dialog.showModal();
  return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true}));
}
$('clear-cache').onclick=async()=>{
  if(!await confirmAction('Vider le cache ?','Les altitudes devront être téléchargées à nouveau. Le GPX, les réglages et le résultat affiché sont conservés.','Vider le cache'))return;
  try{await window.api.clearCache();await refresh();}catch(error){notify(error);}
};
$('quit').onclick=async()=>{
  if(!await confirmAction("Arrêter l'application ?",'Le calcul en cours sera annulé. Vous pourrez relancer gpx2elev depuis son raccourci.','Arrêter'))return;
  try{await window.api.quit();$('status').textContent=t('Application arrêtée. Vous pouvez fermer cet onglet.');stopped=true;}catch(error){notify(error);}
};
function renderUpdate(){
  $('installed-version').textContent=t('Version installée : {0}').replace('{0}',$('version').textContent);
  if(!updateState)return;
  const s=updateState;$('update-status').textContent=t(s.message);
  if(s.release&&s.phase==='available')$('update-status').textContent=t('Version {0} disponible · {1} Mio').replace('{0}',s.release.version).replace('{1}',number(s.release.size/1048576,1));
  $('update-notes').textContent=s.release?.notes||'';$('update-notes').hidden=!s.release?.notes;
  $('update-check').disabled=s.busy||s.phase==='installing';
  $('update-action').hidden=!(s.release&&!s.busy&&(s.phase==='available'||s.phase==='ready'));
  $('update-action').textContent=t(s.prepared==='install'?'Installer et redémarrer':s.prepared==='folder'?'Ouvrir le dossier':s.can_install?'Télécharger et installer':'Télécharger');
  $('update-cancel').hidden=!s.busy;$('update-progress').hidden=!s.busy;
  if(s.total){$('update-progress').max=s.total;$('update-progress').value=s.completed;}else $('update-progress').removeAttribute('value');
  const version=s.advertised_version||s.release?.version;$('new-version').hidden=!version;
  if(version)$('new-version').querySelector('span').textContent=t('Version {0} disponible').replace('{0}',version);
}
async function checkUpdate(){try{await window.api.updateCheck();updateState=await window.api.updateState();renderUpdate();}catch(error){notify(error);}}
async function openUpdates(){if(!$('update-dialog').open)$('update-dialog').showModal();await checkUpdate();}
$('updates').onclick=openUpdates;$('show-new-version').onclick=openUpdates;$('update-close').onclick=()=>$('update-dialog').close();
$('update-check').onclick=checkUpdate;$('update-cancel').onclick=async()=>{try{await window.api.updateCancel();}catch(error){notify(error);}};
$('update-action').onclick=async()=>{
  try{
    if(updateState.prepared==='folder')await window.api.updateFolder();
    else if(updateState.prepared==='install'){
      if(await confirmAction('Installer et redémarrer',"Mise à jour vérifiée. L'application va se fermer puis redémarrer.",'Installer et redémarrer'))await window.api.updateInstall();
    }else await window.api.updateDownload();
    updateState=await window.api.updateState();renderUpdate();
  }catch(error){notify(error);}
};
let stopped=false,failures=0;
async function poll(){
  if(stopped)return;
  try{await refresh();updateState=await window.api.updateState();renderUpdate();failures=0;}
  catch(error){failures++;if(failures>2)$('status').textContent=t('Le serveur local est indisponible. Relancez gpx2elev.');}
  setTimeout(poll,currentState?.busy||updateState?.busy?350:1200);
}
(async()=>{
  try{
    const init=await window.api.init();catalog=init.translations;$('version').textContent=init.version;
    patterns=Object.entries(catalog).filter(([fr])=>/\{\d+\}/.test(fr)).map(([fr,en])=>{
      const indices=[...fr.matchAll(/\{(\d+)\}/g)].map(m=>Number(m[1]));
      const expression=fr.split(/(\{\d+\})/).map(part=>/\{\d+\}/.test(part)?'(.+?)':part.replace(/[.*+?^{}()|[\]\\$]/g,'\\$&')).join('');
      return[new RegExp(expression,'g'),en,indices];
    });
    init.models.forEach(model=>{$('model').add(new Option(model.label,model.id));});
    language=window.nico579Langue?.code()||init.language||(navigator.language.startsWith('fr')?'fr':'en');
    applyLanguage();await refresh();poll();if(new URLSearchParams(location.search).get('updates'))openUpdates();
  }catch(error){notify(error);$('status').textContent=t('Le serveur local est indisponible. Relancez gpx2elev.');}
})();
