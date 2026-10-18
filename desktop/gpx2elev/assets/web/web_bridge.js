'use strict';
async function request(route,payload) {
  const response=await fetch('/api/'+route,payload===undefined?{cache:'no-store'}:{
    method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  let data;
  try{data=await response.json();}catch(_){throw new Error('Le serveur local est indisponible.');}
  if(!response.ok||data.error)throw new Error(data.error||'Le serveur local est indisponible.');
  return data;
}
window.api={
  init:()=>request('init'),state:()=>request('state'),result:()=>request('result'),
  obstacles:cfg=>request('obstacles',cfg),
  upload:cfg=>request('upload',cfg),recalculate:cfg=>request('recalculate',cfg),
  cancel:()=>request('cancel',{}),clearCache:()=>request('clear-cache',{confirm:true}),quit:()=>request('quit',{}),
  export:kind=>request('export?kind='+encodeURIComponent(kind)),
  select:(x,y,left,right)=>request('select?'+new URLSearchParams({x,y,left,right}))
};
