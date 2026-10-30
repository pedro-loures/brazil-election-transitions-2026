// Geographic selection uses observed totals, independently of transition models.
const NS='http://www.w3.org/2000/svg',W=960,H=760;
const fmt=n=>Number(n).toLocaleString('en-US'),signed=n=>(n>0?'+':'')+fmt(n);
const $=id=>document.getElementById(id);
const project=([lon,lat])=>[lon,-Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))*180/Math.PI];
const rings=geometry=>geometry.type==='Polygon'?geometry.coordinates:geometry.coordinates.flat();
const LOG_SOFTENING=1.55;

export function marginChange(p){return (p.a_2-p.a_1)-(p.b_2-p.b_1);}
export function colorFraction(value,maximum,scale='log'){
  if(!maximum)return 0;
  const magnitude=Math.min(maximum,Math.abs(value));
  return scale==='log'?(Math.log1p(magnitude)/Math.log1p(maximum))**LOG_SOFTENING:magnitude/maximum;
}
export function legendValue(fraction,maximum,scale='log'){
  return Math.sign(fraction)*(scale==='log'?Math.expm1(Math.abs(fraction)**(1/LOG_SOFTENING)*Math.log1p(maximum)):Math.abs(fraction)*maximum);
}
export function gainLabel(difference){
  if(!difference)return 'Equal gains';
  return `${difference>0?'Lula':'Flávio'} +${fmt(Math.abs(difference))}`;
}
export function colorFor(value,maximum,scale='log'){
  const t=colorFraction(value,maximum,scale);
  const end=value<0?[112,149,181]:[193,112,126],neutral=[245,242,234];
  return '#'+neutral.map((v,i)=>Math.round(v+(end[i]-v)*t).toString(16).padStart(2,'0')).join('');
}

export class ElectionMap{
  constructor(onSelect){
    this.onSelect=onSelect;this.level='state';this.filter='';this.selected=null;this.data=new Map();
    this.scale='log';
    this.transform={x:0,y:0,k:1};this.svg=$('election-map');this.group=$('map-areas');this.token=0;
    this.svg.addEventListener('pointerdown',e=>{
      if(e.button!==0)return;
      this.drag={x:e.clientX,y:e.clientY,tx:this.transform.x,ty:this.transform.y,moved:false,id:e.pointerId};
    });
    this.svg.addEventListener('pointermove',e=>{
      if(!this.drag)return;
      const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;
      if(Math.hypot(dx,dy)>5){this.drag.moved=true;this.svg.setPointerCapture(e.pointerId);}
      if(this.drag.moved){const scale=W/this.svg.getBoundingClientRect().width;
        this.transform.x=this.drag.tx+dx*scale;this.transform.y=this.drag.ty+dy*scale;this.applyTransform();}
    });
    this.svg.addEventListener('pointerup',()=>{
      this.suppressClick=!!this.drag?.moved;this.drag=null;setTimeout(()=>{this.suppressClick=false;},0);
    });
    this.svg.addEventListener('pointercancel',()=>{this.drag=null;});
    this.svg.addEventListener('wheel',e=>{
      // Ordinary scrolling still moves the page; Ctrl/trackpad pinch zooms the map.
      if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();
      const point=this.svg.createSVGPoint();point.x=e.clientX;point.y=e.clientY;
      const local=point.matrixTransform(this.svg.getScreenCTM().inverse());
      this.zoom(Math.exp(-e.deltaY*.005),local.x,local.y);
    },{passive:false});
    $('map-level').addEventListener('change',()=>{this.setLevel($('map-level').value);});
    $('map-scale').addEventListener('change',()=>{this.scale=$('map-scale').value;this.recolor();});
    $('map-filter').addEventListener('change',()=>{this.filter=$('map-filter').value;this.render();});
    $('map-zoom-in').addEventListener('click',()=>this.zoom(1.7));
    $('map-zoom-out').addEventListener('click',()=>this.zoom(1/1.7));
    $('map-reset').addEventListener('click',()=>{this.transform={x:0,y:0,k:1};this.applyTransform();});
    $('map-selected').addEventListener('click',()=>this.zoomSelection());
    $('map-country').addEventListener('click',()=>this.onSelect('country','BR'));
  }
  load(level){
    if(!this.data.has(level)){
      this.data.set(level,fetch(new URL(`data/maps/${level}.geojson`,import.meta.url)).then(r=>{
        if(!r.ok)throw Error('Geographic boundaries could not be loaded.');return r.json();
      }).catch(e=>{this.data.delete(level);throw e;}));
    }
    return this.data.get(level);
  }
  async setLevel(level){
    this.level=level;$('map-level').value=level;$('map-filter-field').hidden=level!=='municipality';
    const token=++this.token;$('map-status').textContent='Loading geographic boundaries…';
    try{
      const [data,states,regions]=await Promise.all([this.load(level),this.load('state'),this.load('region')]);
      if(token!==this.token)return;
      this.features=data.features;
      this.outlines={state:states.features,region:regions.features};
      if(!$('map-filter').options.length){
        const choices=[{key:'',name:'All Brazil'},...states.features.map(f=>f.properties).sort((a,b)=>a.name.localeCompare(b.name))];
        $('map-filter').replaceChildren(...choices.map(p=>{const option=document.createElement('option');option.value=p.key;option.textContent=p.name;return option;}));
        $('map-filter').value=this.filter;
      }
      if(token!==this.token)return;this.render();
    }catch(e){if(token===this.token)$('map-status').textContent=e.message;}
  }
  render(){
    const visible=this.features.filter(f=>this.level!=='municipality'||!this.filter||f.properties.uf===this.filter);
    if(!visible.length)return;
    const allPoints=visible.flatMap(f=>rings(f.geometry).flatMap(r=>r.map(project)));
    const xs=allPoints.map(p=>p[0]),ys=allPoints.map(p=>p[1]);
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    for(let i=0;i<xs.length;i++){minX=Math.min(minX,xs[i]);maxX=Math.max(maxX,xs[i]);minY=Math.min(minY,ys[i]);maxY=Math.max(maxY,ys[i]);}
    const s=Math.min((W-70)/(maxX-minX),(H-50)/(maxY-minY));
    const ox=(W-(maxX-minX)*s)/2,oy=(H-(maxY-minY)*s)/2;
    const point=p=>{const [x,y]=project(p);return [(x-minX)*s+ox,(y-minY)*s+oy];};
    const maximum=Math.max(...visible.map(f=>Math.abs(f.properties.margin_change)),1);
    this.maximum=maximum;this.visible=visible;this.svg.dataset.level=this.level;
    this.group.replaceChildren();this.paths=new Map();
    const pathData=points=>points.map(r=>'M'+r.map(([x,y])=>`${x.toFixed(3)},${y.toFixed(3)}`).join('L')+'Z').join('');
    for(const feature of visible){
      const p=feature.properties,path=document.createElementNS(NS,'path');
      const points=rings(feature.geometry).map(r=>r.map(point));
      path.setAttribute('d',pathData(points));
      path.setAttribute('fill',colorFor(p.margin_change,maximum,this.scale));path.setAttribute('fill-rule','evenodd');
      path.setAttribute('class','map-area');path.setAttribute('role','button');path.setAttribute('tabindex','0');
      path.setAttribute('aria-label',`${p.name}: ${gainLabel(p.margin_change)} vote gain advantage. Lula change ${signed(p.delta_a)}, Flávio change ${signed(p.delta_b)}. Select flowchart.`);
      path.dataset.key=p.key;path.dataset.delta=p.margin_change;
      const title=document.createElementNS(NS,'title');title.textContent=`${p.name}\n${gainLabel(p.margin_change)} · gain advantage\nLula change ${signed(p.delta_a)}\nFlávio change ${signed(p.delta_b)}`;path.append(title);
      path.addEventListener('pointerenter',()=>{if(!this.drag?.moved)this.describe(p,true);});
      path.addEventListener('focus',()=>this.describe(p,true));
      path.addEventListener('pointerleave',()=>this.describeSelected());
      path.addEventListener('blur',()=>this.describeSelected());
      const select=()=>{this.selected={level:this.level,key:p.key};this.highlight();this.describe(p);this.onSelect(this.level,p.key);};
      path.addEventListener('click',()=>{if(!this.suppressClick)select();});
      path.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});
      this.group.append(path);this.paths.set(p.key,{path,properties:p,points:points.flat()});
    }
    this.outlineGroup=document.createElementNS(NS,'g');this.outlineGroup.setAttribute('aria-hidden','true');
    this.outlineGroup.setAttribute('class','map-outlines');
    for(const level of ['state','region'])for(const feature of this.outlines[level]){
      if(level==='state'&&this.level==='municipality'&&this.filter&&feature.properties.key!==this.filter)continue;
      const path=document.createElementNS(NS,'path');
      path.setAttribute('d',pathData(rings(feature.geometry).map(r=>r.map(point))));
      path.setAttribute('class',`map-boundary map-boundary-${level}`);this.outlineGroup.append(path);
    }
    this.group.append(this.outlineGroup);
    this.transform={x:0,y:0,k:1};this.applyTransform();this.highlight();this.describeSelected();
    this.recolor();
  }
  recolor(){
    if(!this.paths)return;
    for(const {path,properties:p} of this.paths.values())path.setAttribute('fill',colorFor(p.margin_change,this.maximum,this.scale));
    $('map-legend-ticks').replaceChildren(...[-1,-.5,0,.5,1].map(t=>{
      const span=document.createElement('span'),votes=Math.round(legendValue(t,this.maximum,this.scale));
      span.textContent=t===0?'Equal':'+'+fmt(Math.abs(votes));
      span.title=t===0?'Both candidates had the same vote change':gainLabel(votes)+' votes of gain advantage';return span;
    }));
    $('map-scale-note').textContent=this.scale==='log'?'Gain advantage in votes · soft logarithmic intensity · equal gains stay neutral':'Gain advantage in votes · linear intensity · equal gains stay neutral';
    $('map-status').textContent=`${fmt(this.visible.length)} ${this.level==='state'?'states / UF':this.level==='region'?'regions':'municipalities'} · full observed results · ${this.scale==='log'?'soft logarithmic':'linear'} color range for displayed areas`;
  }
  describe(p,hover=false){
    $('map-area-name').textContent=p.name;
    $('map-delta-lula').textContent=signed(p.delta_a);$('map-delta-flavio').textContent=signed(p.delta_b);
    $('map-margin-change').textContent=gainLabel(p.margin_change);
    const preview=hover&&!(this.selected?.level===this.level&&this.selected.key===p.key);
    $('map-selection-note').textContent=preview?'Preview · click or press Enter to open its flowchart':'Selected area · flowchart below';
  }
  describeSelected(){
    const entry=this.selected?.level===this.level?this.paths?.get(this.selected.key):null;
    if(entry){this.describe(entry.properties);return;}
    $('map-area-name').textContent='Choose an area';
    for(const id of ['map-delta-lula','map-delta-flavio','map-margin-change'])$(id).textContent='—';
    $('map-selection-note').textContent='Click a colored area to open its flowchart.';
  }
  highlight(){
    if(!this.paths)return;
    for(const [key,{path}] of this.paths){const selected=this.selected?.level===this.level&&key===this.selected.key;
      path.classList.toggle('is-selected',selected);path.setAttribute('aria-pressed',String(selected));}
    const entry=this.selected?.level===this.level?this.paths.get(this.selected.key):null;
    if(entry)this.group.insertBefore(entry.path,this.outlineGroup);
    $('map-selected').disabled=!entry;
  }
  async sync(level,key){
    this.selected={level,key:String(key)};
    if(!this.features||(level!=='country'&&level!==this.level))await this.setLevel(level==='country'?'state':level);
    else{this.highlight();this.describeSelected();}
  }
  applyTransform(){const {x,y,k}=this.transform;this.group.setAttribute('transform',`translate(${x} ${y}) scale(${k})`);}
  zoom(factor,cx=W/2,cy=H/2){
    const old=this.transform,k=Math.max(1,Math.min(120,old.k*factor)),ratio=k/old.k;
    this.transform={x:cx-(cx-old.x)*ratio,y:cy-(cy-old.y)*ratio,k};this.applyTransform();
  }
  zoomSelection(){
    const entry=this.selected?.level===this.level?this.paths.get(this.selected.key):null;if(!entry)return;
    const xs=entry.points.map(p=>p[0]),ys=entry.points.map(p=>p[1]);
    const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
    const k=Math.max(1,Math.min(120,Math.min((W-90)/Math.max(1,x1-x0),(H-90)/Math.max(1,y1-y0))));
    this.transform={x:W/2-(x0+x1)/2*k,y:H/2-(y0+y1)/2*k,k};this.applyTransform();
  }
}
