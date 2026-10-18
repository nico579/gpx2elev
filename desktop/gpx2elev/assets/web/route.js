/* Offline route drawing. Distances always follow original GPX order. */
(function(root){
'use strict';
const COLOURS={route:'#3476ba',blocked:'#c73535',uncertain:'#b66b0b'};
function longitudeDelta(lon,origin){return((lon-origin+540)%360)-180;}
function projectRoute(route){
  if(!route||!Array.isArray(route.segments))return null;
  const first=route.segments.flatMap(s=>s.slice(0,1)).find(p=>Array.isArray(p)&&p.length>=3&&p.every(Number.isFinite));
  if(!first)return null;
  const lat0=first[0],lon0=first[1],cos=Math.max(.000001,Math.cos(lat0*Math.PI/180)),metres=6371008.8*Math.PI/180;
  const project=(lat,lon)=>[longitudeDelta(lon,lon0)*metres*cos,(lat-lat0)*metres];
  const bounds=[Infinity,-Infinity,Infinity,-Infinity];
  const segments=route.segments.map(segment=>segment.filter(p=>Array.isArray(p)&&p.length>=3&&p.every(Number.isFinite)).map(p=>{
    const xy=project(p[0],p[1]);bounds[0]=Math.min(bounds[0],xy[0]);bounds[1]=Math.max(bounds[1],xy[0]);
    bounds[2]=Math.min(bounds[2],xy[1]);bounds[3]=Math.max(bounds[3],xy[1]);return[xy[0],xy[1],p[2]];
  }));
  return{segments,bounds,project,length:Math.max(0,Number(route.length_m)||0)};
}
function lowerDistance(points,distance){
  let low=0,high=points.length;
  while(low<high){const mid=(low+high)>>>1;if(points[mid][2]<distance)low=mid+1;else high=mid;}
  return low;
}
function clipSpan(points,start,end){
  if(!points||points.length<2||!Number.isFinite(start)||!Number.isFinite(end)||end<start)return[];
  const out=[];
  for(let i=Math.max(1,lowerDistance(points,start));i<points.length&&points[i-1][2]<=end;i++){
    const a=points[i-1],b=points[i],length=b[2]-a[2];
    if(length<=0||b[2]<start||a[2]>end)continue;
    const at=d=>{const f=(d-a[2])/length;return[a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1]),d];};
    const left=at(Math.max(start,a[2])),right=at(Math.min(end,b[2]));
    if(!out.length)out.push(left);out.push(right);
  }
  return out;
}
function orderedEvents(events,length,reverse){
  return(events||[]).filter(e=>e&&(e.status==='blocked'||e.status==='uncertain')&&Number.isFinite(e.route_distance_m)).map(e=>({
    ...e,distance_m:Math.max(0,reverse?length-e.route_distance_m:e.route_distance_m)
  })).sort((a,b)=>a.distance_m-b.distance_m||a.segment-b.segment);
}
function endpoints(segments,reverse){
  const present=segments.filter(s=>s.length);
  if(!present.length)return null;
  const first=present[0][0],last=present[present.length-1].at(-1);
  return reverse?[last,first]:[first,last];
}
class RouteMap{
  constructor(canvas,callbacks){
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.callbacks=callbacks;
    this.data=null;this.events=[];this.reverse=false;this.selected=-1;this.zoomLevel=1;this.pointers=new Map();
    new ResizeObserver(()=>this.draw()).observe(canvas);
    canvas.addEventListener('wheel',e=>{if(!this.data)return;e.preventDefault();this.zoom(e.deltaY<0?1.25:.8,this.position(e));},{passive:false});
    canvas.addEventListener('dblclick',()=>this.reset());
    canvas.addEventListener('pointerdown',e=>{
      if(!this.data||(e.pointerType==='mouse'&&e.button!==0))return;
      canvas.setPointerCapture(e.pointerId);this.pointers.set(e.pointerId,this.position(e));this.dragged=false;this.press=this.position(e);
      if(this.pointers.size===2)this.dragged=true;
    });
    canvas.addEventListener('pointermove',e=>{
      if(!this.pointers.has(e.pointerId))return;
      const before=[...this.pointers.values()],previous=this.pointers.get(e.pointerId),p=this.position(e);
      this.pointers.set(e.pointerId,p);
      if(this.pointers.size===2){
        const after=[...this.pointers.values()],oldDistance=Math.hypot(before[0].x-before[1].x,before[0].y-before[1].y);
        const distance=Math.hypot(after[0].x-after[1].x,after[0].y-after[1].y);
        if(oldDistance>0&&distance>0)this.zoom(distance/oldDistance,{x:(after[0].x+after[1].x)/2,y:(after[0].y+after[1].y)/2});
        this.dragged=true;return;
      }
      if(!this.dragged&&Math.hypot(p.x-this.press.x,p.y-this.press.y)<4)return;
      const dx=p.x-previous.x,dy=p.y-previous.y;
      if(Math.hypot(dx,dy)>0){this.center[0]-=dx/this.scale();this.center[1]+=dy/this.scale();this.dragged=true;this.draw();}
    });
    canvas.addEventListener('pointerup',e=>{
      if(!this.pointers.has(e.pointerId))return;
      const click=!this.dragged&&this.pointers.size===1;this.pointers.delete(e.pointerId);
      if(click)this.selectAt(this.position(e));
    });
    canvas.addEventListener('pointercancel',e=>this.pointers.delete(e.pointerId));
    canvas.addEventListener('keydown',e=>{
      if(!this.data)return;
      if(['+','=','-','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))e.preventDefault();
      if(e.key==='+'||e.key==='=')this.zoom(1.5);else if(e.key==='-')this.zoom(1/1.5);else if(e.key==='Home')this.reset();
      else if(e.key.startsWith('Arrow')){
        const d=60/this.scale();if(e.key==='ArrowLeft')this.center[0]-=d;if(e.key==='ArrowRight')this.center[0]+=d;
        if(e.key==='ArrowUp')this.center[1]+=d;if(e.key==='ArrowDown')this.center[1]-=d;this.draw();
      }
    });
  }
  position(e){const r=this.canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
  scale(){
    if(!this.data)return 1;const b=this.data.bounds;
    return Math.min(Math.max(1,this.canvas.clientWidth-100)/Math.max(50,b[1]-b[0]),Math.max(1,this.canvas.clientHeight-100)/Math.max(50,b[3]-b[2]))*this.zoomLevel;
  }
  pixel(p){const scale=this.scale();return[this.canvas.clientWidth/2+(p[0]-this.center[0])*scale,this.canvas.clientHeight/2-(p[1]-this.center[1])*scale];}
  setData(route){this.data=projectRoute(route);this.events=[];this.spans=[];this.selected=-1;this.reset();}
  setReport(report){
    this.reverse=!!report.reverse;this.events=orderedEvents(report.events,this.data?.length||0,this.reverse);
    this.spans=this.events.map(e=>clipSpan(this.data?.segments[e.segment],e.start_m,e.end_m));this.selected=-1;this.draw();
  }
  reset(){
    this.zoomLevel=1;
    if(this.data){const b=this.data.bounds;this.center=[(b[0]+b[1])/2,(b[2]+b[3])/2];}
    this.draw();
  }
  zoom(factor,position){
    if(!this.data)return;
    const p=position||{x:this.canvas.clientWidth/2,y:this.canvas.clientHeight/2},oldScale=this.scale();
    const x=p.x-this.canvas.clientWidth/2,y=p.y-this.canvas.clientHeight/2;
    this.zoomLevel=Math.max(1,Math.min(2000,this.zoomLevel*factor));
    this.center[0]+=x/oldScale-x/this.scale();this.center[1]-=y/oldScale-y/this.scale();this.draw();
  }
  eventPoint(event){
    if(Number.isFinite(event.lat)&&Number.isFinite(event.lon))return this.data.project(event.lat,event.lon);
    return clipSpan(this.data.segments[event.segment],event.route_distance_m,event.route_distance_m)[0]||null;
  }
  select(index,focus=false){
    if(!this.events[index]||!this.data)return;
    this.selected=index;
    if(focus){const p=this.eventPoint(this.events[index]);if(p){this.center=p.slice(0,2);this.zoomLevel=Math.max(4,this.zoomLevel);}}
    this.draw();this.callbacks.select(index);
  }
  selectAt(position){
    let best=-1,distance=20;
    this.events.forEach((e,i)=>{const p=this.eventPoint(e);if(!p)return;const xy=this.pixel(p),d=Math.hypot(xy[0]-position.x,xy[1]-position.y);if(d<=distance){best=i;distance=d;}});
    if(best>=0)this.select(best);
  }
  draw(){
    const ctx=this.ctx,canvas=this.canvas,width=canvas.clientWidth,height=canvas.clientHeight,dpr=root.devicePixelRatio||1;
    if(!width||!height)return;
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
    ctx.fillStyle='#f6f9fc';ctx.fillRect(0,0,width,height);this.callbacks.changed();
    if(!this.data)return;
    const t=this.callbacks.t;
    const line=(points,color,lineWidth)=>{
      if(!points.length)return;
      ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();
      let last=null;
      points.forEach((point,i)=>{const p=this.pixel(point);if(!last){ctx.moveTo(...p);last=p;}else if(i===points.length-1||Math.hypot(p[0]-last[0],p[1]-last[1])>=.7){ctx.lineTo(...p);last=p;}});
      ctx.stroke();
    };
    ctx.save();ctx.beginPath();ctx.rect(0,0,width,height);ctx.clip();
    this.data.segments.forEach(s=>line(s,COLOURS.route,3));
    // Red remains visible if a blocked passage and a warning share the same place.
    for(const status of['uncertain','blocked'])this.events.forEach((event,i)=>{if(event.status===status)line(this.spans[i],COLOURS[status],7);});
    ctx.strokeStyle='#235887';ctx.lineWidth=1.8;
    this.data.segments.forEach(points=>{
      let spacing=60;
      for(let i=1;i<points.length;i++){
        const a=this.pixel(points[i-1]),b=this.pixel(points[i]),dx=b[0]-a[0],dy=b[1]-a[1],distance=Math.hypot(dx,dy);
        if(!distance)continue;
        // Avoid work proportional to huge off-screen edges at high zoom.
        const count=Math.floor((distance-spacing)/120)+1;
        if(count>0){
          for(let k=0;k<count;k++){
            const along=spacing+k*120,x=a[0]+dx*along/distance,y=a[1]+dy*along/distance;
            if(x<8||x>width-8||y<8||y>height-8)continue;
            const sign=this.reverse?-1:1,ux=dx/distance*sign,uy=dy/distance*sign;
            ctx.beginPath();ctx.moveTo(x-ux*6-uy*4,y-uy*6+ux*4);ctx.lineTo(x+ux*3,y+uy*3);ctx.lineTo(x-ux*6+uy*4,y-uy*6-ux*4);ctx.stroke();
          }
          spacing+=count*120;
        }
        spacing-=distance;
      }
    });
    const ends=endpoints(this.data.segments,this.reverse);
    if(ends){
      const overlapping=Math.hypot(...this.pixel(ends[0]).map((v,i)=>v-this.pixel(ends[1])[i]))<28;
      ends.forEach((point,i)=>{
        const p=this.pixel(point);ctx.fillStyle=i?'#203c33':'#fff';ctx.strokeStyle='#203c33';ctx.lineWidth=2;
        ctx.beginPath();ctx.arc(p[0],p[1],6,0,Math.PI*2);ctx.fill();ctx.stroke();
        const text=t(i?'Arrivée':'Départ');ctx.font='bold 11px Noto, sans-serif';ctx.textAlign='center';
        const y=p[1]+(i&&overlapping?24:-14),tw=ctx.measureText(text).width;
        ctx.fillStyle='#ffffffed';ctx.fillRect(p[0]-tw/2-4,y-12,tw+8,17);ctx.fillStyle='#203c33';ctx.fillText(text,p[0],y);
      });
    }
    this.events.forEach((event,i)=>{
      const point=this.eventPoint(event);if(!point)return;const p=this.pixel(point);
      if(p[0]<-20||p[0]>width+20||p[1]<-20||p[1]>height+20)return;
      ctx.fillStyle=COLOURS[event.status];ctx.strokeStyle=this.selected===i?'#172f48':'#fff';ctx.lineWidth=this.selected===i?3:2;
      ctx.beginPath();ctx.arc(p[0],p[1],12,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.font='bold 11px Noto, sans-serif';ctx.textAlign='center';ctx.fillStyle='#fff';ctx.fillText(String(i+1),p[0],p[1]+4);
    });
    ctx.restore();
    ctx.fillStyle='#ffffffed';ctx.fillRect(width-43,8,35,48);ctx.fillStyle='#425c71';ctx.font='bold 11px Noto, sans-serif';ctx.textAlign='center';ctx.fillText('N',width-26,23);
    ctx.beginPath();ctx.moveTo(width-26,29);ctx.lineTo(width-31,45);ctx.lineTo(width-26,41);ctx.lineTo(width-21,45);ctx.closePath();ctx.fill();
    const target=80/this.scale(),power=10**Math.floor(Math.log10(target)),units=[1,2,5,10].filter(v=>v*power<=target).at(-1)||1;
    const metres=units*power,pixels=metres*this.scale(),label=metres>=1000?this.callbacks.number(metres/1000,metres<10000?1:0)+' km':this.callbacks.number(metres)+' m';
    ctx.fillStyle='#ffffffed';ctx.fillRect(8,height-43,pixels+18,35);ctx.strokeStyle='#425c71';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(16,height-22);ctx.lineTo(16,height-16);ctx.lineTo(16+pixels,height-16);ctx.lineTo(16+pixels,height-22);ctx.stroke();
    ctx.fillStyle='#425c71';ctx.font='10px Noto, sans-serif';ctx.textAlign='left';ctx.fillText(label,16,height-26);
  }
}
const exported={RouteMap,projectRoute,clipSpan,orderedEvents,endpoints};root.GpxRoute=exported;
if(typeof module!=='undefined')module.exports=exported;
})(typeof window!=='undefined'?window:globalThis);
