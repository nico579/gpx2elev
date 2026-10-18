'use strict';
const assert=require('node:assert/strict');
const {RouteMap,projectRoute,clipSpan,orderedEvents,endpoints}=require('../gpx2elev/assets/web/route.js');
const route={length_m:300,segments:[[[48,2,0],[48,2.002,200]],[[48.001,2.003,200],[48.002,2.003,300]]]};
const projected=projectRoute(route);
assert.equal(projected.segments.length,2);
assert.equal(projected.segments[1][0][2],200); // Gaps never add a fictitious joining edge.
assert(projected.segments[0][1][0]>projected.segments[0][0][0]);
assert(projected.segments[1][1][1]>projected.segments[1][0][1]); // North is up.
const sparse=[[0,0,0],[100,0,100],[100,100,200]];
assert.deepEqual(clipSpan(sparse,25,75),[[25,0,25],[75,0,75]]);
assert.deepEqual(clipSpan(sparse,75,125),[[75,0,75],[100,0,100],[100,25,125]]);
assert.deepEqual(clipSpan(sparse,-25,25),[[0,0,0],[25,0,25]]);
assert.deepEqual(clipSpan(sparse,175,225),[[100,75,175],[100,100,200]]);
assert.deepEqual(clipSpan(sparse,250,275),[]);
assert.deepEqual(clipSpan(sparse,75,25),[]);
assert.deepEqual(clipSpan([[0,0,0],[0,0,0],[100,0,100]],25,75),[[25,0,25],[75,0,75]]);
const events=[
  {status:'blocked',route_distance_m:50,segment:0,label:'A',start_m:25,end_m:75},
  {status:'uncertain',route_distance_m:275,segment:1,label:'B',start_m:250,end_m:300},
  {status:'passable',route_distance_m:150,segment:0,label:'C'}
];
assert.deepEqual(orderedEvents(events,300,false).map(e=>[e.label,e.distance_m]),[['A',50],['B',275]]);
const reversed=orderedEvents(events,300,true);
assert.deepEqual(reversed.map(e=>[e.label,e.distance_m]),[['B',25],['A',250]]);
assert.equal(reversed[1].start_m,25); // Reversal changes travel order, never the normal-order geometry.
assert.equal(events[0].distance_m,undefined); // Reports are not mutated.
assert.deepEqual(endpoints(projected.segments,true),endpoints(projected.segments,false).reverse());
const dateline=projectRoute({length_m:100,segments:[[[0,179.999,0],[0,-179.999,100]]]});
assert(dateline.bounds[1]-dateline.bounds[0]<300);
assert.equal(projectRoute(null),null);
assert.equal(projectRoute({segments:[[]]}),null);

// Exercise rendering and updates without a browser: no network or DOM library is needed.
global.ResizeObserver=class{observe(){}};
const handlers={};
const ctx=new Proxy({measureText:text=>({width:text.length*6})},{get:(obj,key)=>obj[key]||(()=>{})});
const canvas={clientWidth:800,clientHeight:400,getContext:()=>ctx,addEventListener:(key,fn)=>{handlers[key]=fn;},getBoundingClientRect:()=>({left:0,top:0}),setPointerCapture(){}};
let selected=null;
const map=new RouteMap(canvas,{t:s=>s,number:x=>String(x),changed(){},select:i=>{selected=i;}});
map.setData(route);map.zoom(3);map.center[0]+=30;
const view=map.center.slice();
map.setReport({events,reverse:true});
assert.equal(map.zoomLevel,3);
assert.deepEqual(map.center,view); // A report poll must preserve the user's view.
assert.equal(map.events[0].label,'B');
assert.equal(map.spans[0].length,2); // The second segment alone supplies this span.
map.select(0,true);assert.equal(selected,0);assert(map.zoomLevel>=4);
const press=map.pixel(map.eventPoint(map.events[0]));
handlers.pointerdown({pointerId:1,pointerType:'mouse',button:0,clientX:press[0],clientY:press[1]});
handlers.pointermove({pointerId:1,clientX:press[0]+1,clientY:press[1]+1});
selected=null;
handlers.pointerup({pointerId:1,clientX:press[0]+1,clientY:press[1]+1});
assert.equal(selected,0); // Small pointer jitter must still select a marker.
map.setData(null);assert.equal(map.data,null);assert.deepEqual(map.events,[]);
console.log('Route spans, GPX gaps, travel reversal, dateline, redraw stability and selection: OK');
