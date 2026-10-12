/* Keep original observations; only the drawing is decimated to pixel envelopes. */
(function(root){
'use strict';
function lowerBound(values,x,after=false){
  let a=0,b=values.length;
  while(a<b){const m=(a+b)>>>1;if(values[m]<x||(after&&values[m]===x))a=m+1;else b=m;}
  return a;
}
function visiblePoints(profile,left,right,pixels){
  const {x,y}=profile,start=Math.max(0,lowerBound(x,left)-1),end=Math.min(x.length,lowerBound(x,right,true)+1);
  if(end-start<=pixels*4)return Array.from({length:end-start},(_,i)=>[x[start+i],y[start+i]]);
  const out=[],scale=pixels/(right-left);let bucket=null,indices=[];
  function flush(){
    if(!indices.length)return;
    let lo=indices[0],hi=lo;
    for(const i of indices){if(y[i]<y[lo])lo=i;if(y[i]>y[hi])hi=i;}
    [...new Set([indices[0],lo,hi,indices[indices.length-1]])].sort((a,b)=>a-b).forEach(i=>out.push([x[i],y[i]]));
  }
  for(let i=start;i<end;i++){
    const next=Math.floor((x[i]-left)*scale);
    if(next!==bucket){flush();indices=[];bucket=next;}indices.push(i);
  }
  flush();return out;
}
function nativeRuns(native){
  const runs=[];let current=null,group=null;
  native.x.forEach((x,i)=>{
    const y=native.y[i],next=native.group[i];
    if(y===null||!Number.isFinite(y)){current=null;group=next;return;}
    if(!current||group!==next){current={x:[],y:[]};runs.push(current);}
    current.x.push(x);current.y.push(y);group=next;
  });return runs;
}
function timeAt(native,distance){
  const end=lowerBound(native.x,distance,true),valid=v=>v!==null&&Number.isFinite(v);
  if(end&&native.x[end-1]===distance)return valid(native.time[end-1])?native.time[end-1]:null;
  if(!end||end===native.x.length)return null;
  const a=end-1,b=end,start=native.time[a],finish=native.time[b];
  if(native.group[a]!==native.group[b]||!valid(start)||!valid(finish)||finish<start)return null;
  return start+(distance-native.x[a])/(native.x[b]-native.x[a])*(finish-start);
}
function clamp(start,end,low,high){
  const span=Math.min(end-start,high-low);start=Math.max(low,Math.min(start,high-span));return[start,start+span];
}
class ProfilePlot{
  constructor(canvas,callbacks){
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.callbacks=callbacks;this.data=null;this.selection=null;this.pointers=new Map();
    new ResizeObserver(()=>this.draw()).observe(canvas);
    canvas.addEventListener('wheel',e=>{if(!this.data)return;e.preventDefault();this.zoom(e.deltaY<0?1.25:.8,this.position(e));},{passive:false});
    canvas.addEventListener('dblclick',()=>this.reset());
    canvas.addEventListener('pointerdown',e=>{
      if(!this.data||(e.pointerType==='mouse'&&e.button!==0))return;
      canvas.setPointerCapture(e.pointerId);this.pointers.set(e.pointerId,this.position(e));
      this.press=this.position(e);this.startView=this.view.slice();this.dragged=false;
      if(this.pointers.size===2){const p=[...this.pointers.values()];this.pinch=Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y);}
    });
    canvas.addEventListener('pointermove',e=>{
      if(!this.pointers.has(e.pointerId))return;
      const p=this.position(e);this.pointers.set(e.pointerId,p);
      if(this.pointers.size===2){
        const ps=[...this.pointers.values()],d=Math.hypot(ps[1].x-ps[0].x,ps[1].y-ps[0].y);
        if(this.pinch>0&&d>0)this.zoom(d/this.pinch,{x:(ps[0].x+ps[1].x)/2,y:(ps[0].y+ps[1].y)/2});
        this.pinch=d;this.dragged=true;return;
      }
      const dx=p.x-this.press.x,dy=p.y-this.press.y;
      if(Math.hypot(dx,dy)<4&&!this.dragged)return;
      this.dragged=true;
      const r=this.rect(),v=this.startView,b=this.bounds;
      this.view=[...clamp(v[0]-dx/r.w*(v[1]-v[0]),v[1]-dx/r.w*(v[1]-v[0]),b[0],b[1]),
                 ...clamp(v[2]+dy/r.h*(v[3]-v[2]),v[3]+dy/r.h*(v[3]-v[2]),b[2],b[3])];this.draw();
    });
    const finish=e=>{
      if(!this.pointers.has(e.pointerId))return;
      const p=this.position(e),select=!this.dragged&&this.pointers.size===1;this.pointers.delete(e.pointerId);
      if(select)this.selectAt(p);
      if(this.pointers.size===1){this.press=[...this.pointers.values()][0];this.startView=this.view.slice();this.dragged=true;}
    };
    canvas.addEventListener('pointerup',finish);
    canvas.addEventListener('pointercancel',e=>this.pointers.delete(e.pointerId));
    canvas.addEventListener('keydown',e=>{
      if(!this.data)return;
      if(['+','=','-','Home','ArrowLeft','ArrowRight','Enter'].includes(e.key))e.preventDefault();
      if(e.key==='+'||e.key==='=')this.zoom(1.5);
      if(e.key==='-')this.zoom(1/1.5);
      if(e.key==='Home')this.reset();
      if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
        const delta=(this.view[1]-this.view[0])*.1*(e.key==='ArrowLeft'?-1:1);
        this.view.splice(0,2,...clamp(this.view[0]+delta,this.view[1]+delta,this.bounds[0],this.bounds[1]));this.draw();
      }
      if(e.key==='Enter'){const r=this.rect();this.selectAt({x:r.x+r.w/2,y:r.y+r.h/2});}
    });
  }
  position(e){const r=this.canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
  rect(){return{x:62,y:20,w:Math.max(1,this.canvas.clientWidth-82),h:Math.max(1,this.canvas.clientHeight-96)};}
  setData(data,summary){
    this.data=data;this.selection=null;this.selectionRequest=(this.selectionRequest||0)+1;
    if(!data){this.bounds=this.view=null;this.draw();return;}
    this.runs=nativeRuns(data.native);let low=summary.altitude_min_m,high=summary.altitude_max_m;
    for(const p of this.runs)for(const y of p.y){low=Math.min(low,y);high=Math.max(high,y);}
    let margin=Math.max((high-low)*.12,5);
    if(![high-low,low-margin,high+margin,(high+margin)-(low-margin)].every(Number.isFinite)){
      this.runs=[];low=summary.altitude_min_m;high=summary.altitude_max_m;margin=Math.max((high-low)*.12,5);
    }
    this.bounds=[0,Math.max(summary.distance_m,1),low-margin,high+margin];this.reset();
  }
  reset(){if(this.bounds)this.view=this.bounds.slice();this.draw();}
  zoom(factor,position){
    if(!this.view)return;
    const r=this.rect(),p=position||{x:r.x+r.w/2,y:r.y+r.h/2},v=this.view,b=this.bounds;
    const fx=Math.max(0,Math.min(1,(p.x-r.x)/r.w)),fy=Math.max(0,Math.min(1,1-(p.y-r.y)/r.h));
    const sx=Math.max(1,Math.min(b[1]-b[0],(v[1]-v[0])/factor)),sy=Math.max(1,Math.min(b[3]-b[2],(v[3]-v[2])/factor));
    const ax=v[0]+fx*(v[1]-v[0]),ay=v[2]+fy*(v[3]-v[2]);
    this.view=[...clamp(ax-fx*sx,ax+(1-fx)*sx,b[0],b[1]),...clamp(ay-fy*sy,ay+(1-fy)*sy,b[2],b[3])];this.draw();
  }
  async selectAt(p){
    if(!this.view)return;
    const r=this.rect(),v=this.view.slice();
    if(p.x<r.x||p.x>r.x+r.w||p.y<r.y||p.y>r.y+r.h)return;
    const x=v[0]+(p.x-r.x)/r.w*(v[1]-v[0]),y=v[3]-(p.y-r.y)/r.h*(v[3]-v[2]);
    const token=this.selectionRequest=(this.selectionRequest||0)+1;
    try{const selected=await this.callbacks.select(x,y,v[0],v[1]);if(token!==this.selectionRequest)return;this.selection=selected;this.draw();}
    catch(error){this.callbacks.error(error);}
  }
  draw(){
    const canvas=this.canvas,ctx=this.ctx,dpr=window.devicePixelRatio||1,width=canvas.clientWidth,height=canvas.clientHeight;
    if(!width||!height)return;
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
    this.callbacks.changed(this);if(!this.data||!this.view)return;
    const r=this.rect(),v=this.view,num=this.callbacks.number,t=this.callbacks.t;
    const px=x=>r.x+(x-v[0])/(v[1]-v[0])*r.w,py=y=>r.y+r.h-(y-v[2])/(v[3]-v[2])*r.h;
    ctx.font='11px Noto, sans-serif';ctx.lineWidth=1;
    for(let i=0;i<=4;i++){
      const z=v[2]+i/4*(v[3]-v[2]),y=py(z);
      ctx.strokeStyle='#e8efea';ctx.beginPath();ctx.moveTo(r.x,y);ctx.lineTo(r.x+r.w,y);ctx.stroke();
      ctx.fillStyle='#62776d';ctx.textAlign='right';ctx.fillText(num(z)+' m',r.x-9,y+4);
    }
    const intervals=Math.max(2,Math.min(6,Math.floor(r.w/100)));
    for(let i=0;i<=intervals;i++){
      const x=v[0]+i/intervals*(v[1]-v[0]),at=px(x);
      ctx.strokeStyle='#e8efea';ctx.beginPath();ctx.moveTo(at,r.y);ctx.lineTo(at,r.y+r.h);ctx.stroke();
      ctx.textAlign='center';ctx.fillStyle='#62776d';ctx.fillText(num(x/1000,2),at,r.y+r.h+21);
      const time=timeAt(this.data.native,x);if(time!==null)ctx.fillText(this.callbacks.time(time,false),at,r.y+r.h+39);
    }
    ctx.fillStyle='#62776d';ctx.textAlign='center';
    ctx.fillText(t(this.data.native.time.some(x=>x!==null)?'Distance · Heure locale':'Distance · Heures GPX absentes.')+' (km)',r.x+r.w/2,height-8);
    ctx.save();ctx.beginPath();ctx.rect(r.x,r.y,r.w,r.h);ctx.clip();
    function line(profile,color,dashed){
      const points=visiblePoints(profile,v[0],v[1],r.w);
      ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=dashed?1.5:2.2;ctx.setLineDash(dashed?[5,4]:[]);ctx.beginPath();
      points.forEach(([x,y],i)=>i?ctx.lineTo(px(x),py(y)):ctx.moveTo(px(x),py(y)));ctx.stroke();
      if(points.length===1){ctx.beginPath();ctx.arc(px(points[0][0]),py(points[0][1]),2,0,Math.PI*2);ctx.fill();}
    }
    this.runs.forEach(p=>line(p,'#b86a22',true));this.data.terrain.forEach(p=>line(p,'#176c59',false));ctx.setLineDash([]);
    if(this.selection){
      const s=this.selection,x=px(s.distance);ctx.strokeStyle='#526d60';ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(x,r.y);ctx.lineTo(x,r.y+r.h);ctx.stroke();
      for(const[z,color]of[[s.terrain,'#176c59'],[s.gpx,'#b86a22']])if(z!==null){ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,py(z),4,0,Math.PI*2);ctx.fill();}
    }
    ctx.restore();
  }
}
const exported={ProfilePlot,lowerBound,visiblePoints,nativeRuns,timeAt,clamp};root.GpxChart=exported;
if(typeof module!=='undefined')module.exports=exported;
})(typeof window!=='undefined'?window:globalThis);
