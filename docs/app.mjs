import {ORIGINS,DESTINATIONS,LABELS,graphFromMatrix,sankeyLayout,schematicLayout,ribbonPath,linePath,curvePoint,gainBreakdown} from './flow-layout.mjs';
import {ElectionMap} from './map.mjs';

const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
const colors={a:'var(--a)',b:'var(--b)',other:'var(--other)',invalid:'var(--invalid)',abstention:'var(--abstention)'};
const softColors={a:'var(--a-soft)',b:'var(--b-soft)',other:'var(--other-soft)',invalid:'var(--invalid-soft)',abstention:'var(--abstention-soft)'};
const fmt=(value,digits=0)=>value==null?'—':Number(value).toLocaleString('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits});
const signed=value=>(value>0?'+':'')+fmt(value);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalize=value=>String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const query=new URLSearchParams(location.hash.slice(1));
const state={source:query.get('source')==='municipality'?'municipality':'thread',
  city:query.get('city')||'81914',model:query.get('model')==='no_cross'?'no_cross':'full',
  level:['state','region','country'].includes(query.get('level'))?query.get('level'):'municipality',
  stateCode:query.get('state')||'MG',region:query.get('region')||'northeast',
  view:query.get('view')==='schematic'?'schematic':'sankey',minimum:0,retained:true,values:query.get('view')==='schematic',pinned:null};
let index=[],aggregateIndex=[],reference=null,current=null,matrix=null,graph=null,request=0,drawnLinks=[];
const cache=new Map();
const electionMap=new ElectionMap((level,key)=>{
  state.source='municipality';state.level=level;
  if(level==='municipality'){state.city=key;fillCities();}
  else if(level==='state')state.stateCode=key;
  else if(level==='region')state.region=key;
  loadCurrent();
});

function displayCity(){return current?{...current.city,...current.models[state.model]?.coverage}:null;}

function fillGeography(){
  $('aggregate-level').value=state.level;
  const municipal=state.level==='municipality';
  $('city-search-field').hidden=!municipal;$('city-options-field').hidden=!municipal;
  $('aggregate-field').hidden=municipal||state.level==='country';
  if(state.level==='state'||state.level==='region'){
    const choices=aggregateIndex.filter(item=>item.level===state.level).sort((a,b)=>a.label.localeCompare(b.label));
    const key=state.level==='state'?'stateCode':'region';
    if(!choices.some(item=>item.key===state[key]))state[key]=choices[0]?.key;
    $('aggregate-options-label').textContent=state.level==='state'?'State / UF':'Region';
    $('aggregate-options').replaceChildren(...choices.map(item=>{
      const option=document.createElement('option');option.value=item.key;
      option.textContent=item.level==='state'?`${item.label} · ${item.key}`:item.label;
      option.selected=item.key===state[key];return option;
    }));
  }
}

function element(tag,attrs={},parent=null,text=null){
  const node=document.createElementNS(NS,tag);
  Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,String(v)));
  if(text!==null)node.textContent=text;if(parent)parent.append(node);return node;
}

function updateHash(){
  const q=new URLSearchParams({source:state.source,city:String(state.city),level:state.level,
    state:state.stateCode,region:state.region,model:state.model,view:state.view});
  history.replaceState(null,'','#'+q.toString());
}

async function json(path){
  const response=await fetch(new URL(path,import.meta.url));
  if(!response.ok)throw Error(`Could not load ${path} (${response.status})`);
  return response.json();
}

function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);$('status').setAttribute('role',error?'alert':'status');}

function fillCities(){
  const term=normalize($('city-search').value.trim());
  const matches=index.filter(c=>normalize(`${c.municipality} ${c.uf} ${c.municipality_code}`).includes(term));
  const shown=matches.slice(0,120),selected=index.find(c=>String(c.municipality_code)===String(state.city));
  if(selected&&!shown.includes(selected))shown.unshift(selected);
  $('city-options').replaceChildren(...shown.map(c=>{
    const option=document.createElement('option');option.value=String(c.municipality_code);
    option.textContent=`${c.municipality} · ${c.uf}`;option.selected=String(c.municipality_code)===String(state.city);return option;
  }));
  if(state.source==='municipality')status(`${fmt(matches.length)} matching municipalities. Select a name to update the diagrams.`);
}

async function loadCurrent(){
  const token=++request;state.pinned=null;
  $('source-thread').setAttribute('aria-selected',String(state.source==='thread'));
  $('source-municipality').setAttribute('aria-selected',String(state.source==='municipality'));
  $('municipality-controls').hidden=state.source!=='municipality';
  fillGeography();
  $('model').value=state.model;
  status('Loading selected results…');
  try{
    if(state.source==='municipality'){
      const key=state.level==='municipality'?String(state.city):state.level==='state'?`state-${state.stateCode}`:
        state.level==='region'?`region-${state.region}`:'country-BR';
      const path=state.level==='municipality'?`data/municipalities/${encodeURIComponent(key)}.json`:`data/aggregates/${encodeURIComponent(key)}.json`;
      if(!cache.has(key))cache.set(key,json(path).catch(error=>{cache.delete(key);throw error;}));
      const loaded=await cache.get(key);if(token!==request)return;current=loaded;
    }else current=null;
    if(token!==request)return;
    matrix=state.source==='thread'?reference.matrix:current.models[state.model]?.matrix??null;
    graph=matrix?graphFromMatrix(matrix):null;
    renderSummary();renderChart();renderTotals();renderGains();resetInspector();updateHash();
    if(state.source==='municipality')electionMap.sync(state.level,state.level==='municipality'?state.city:state.level==='state'?state.stateCode:state.level==='region'?state.region:'BR');
    status(state.source==='thread'?'Screenshot reference · original thread estimates':current.aggregate?
      'Geographic aggregate · sum of municipal model estimates · overseas voting excluded':
      `${fmt(index.length)} municipalities available · all observed totals reconcile with TSE summaries`);
  }catch(error){if(token===request)status(error.message,true);}
}

function renderSummary(){
  if(state.source==='thread'){
    $('city-title').textContent='Lebon Régis, SC';
    $('source-label').textContent='ORIGINAL THREAD · SCREENSHOT REFERENCE';
    $('scope').textContent='Estimated flows transcribed from posts 5–7 · 8,737 eligible voters';
    $('coverage').textContent='30 / 30 sections\nThread snapshot';
    $('provenance').textContent='These are the original thread’s estimated numbers, reproduced from your screenshots. They are not our fitted results. The thread’s estimator was not fully specified.';
    $('fit-note').textContent='Reference: 2,818 retained Lula voters, 3,189 retained Flávio voters, and 1,340 repeated abstainers. Individual transitions are estimates.';
  }else{
    const c=displayCity(),aggregate=current.aggregate;
    $('city-title').textContent=aggregate?aggregate.label:`${c.municipality}, ${c.uf}`;
    const prefix=aggregate?aggregate.level.toUpperCase():'MUNICIPALITY';
    $('source-label').textContent=prefix+(state.model==='full'?' · FULL TRANSITION MODEL':' · NO FINALIST SWITCHING');
    $('scope').textContent=aggregate?`Sum of ${fmt(c.municipalities_modeled??0)} municipal models · matched, validated sections only`:
      `TSE ${c.municipality_code} · Diagrams use matched, validated sections only`;
    $('coverage').textContent=(aggregate?`${fmt(c.municipalities_modeled??0)} / ${fmt(aggregate.municipalities_total)} municipalities\n`:'')+
      `${fmt(c.sections_analyzed)} / ${fmt(c.sections_union)} sections\n${fmt(c.electorate_coverage==null?null:c.electorate_coverage*100,1)}% of electorate`;
    $('provenance').textContent=matrix?
      (aggregate?'Flows are summed from the available municipality models, not refitted at this geographic level. Unmodeled municipalities and excluded sections are absent from the diagram. Full observed geographic totals appear below. Aggregate uncertainty intervals have not been computed.':
      'Our reconstruction uses a documented common-transition model. Flows describe the analyzed sections, not the excluded sections. Full observed municipality totals appear below.'):
      'Observed municipality totals are available. No flow matrix was assigned for this selection; the page does not invent voter transitions.';
    const fit=state.model==='full'?'full':'no_cross';
    $('fit-note').textContent=aggregate?'Sum of independently fitted municipal models. No single aggregate fit or aggregate bootstrap interval is reported.':matrix?`Section fit RMSE: ${fmt(c[fit+'_rmse_votes'],2)} votes. `+
      (fit==='full'?`${fmt(c.bootstrap_successful)} / ${fmt(c.bootstrap_requested)} successful resamples.`:'Sensitivity model: switching between finalists is prohibited.'):
      `Model status: ${state.model==='full'?c.model_status:c.no_cross_status??c.model_status}.`;
  }
}

function bindFlow(node,link){
  node.dataset.link=link.id;
  node.addEventListener('pointerenter',()=>{if(!state.pinned)inspect(link);});
  node.addEventListener('pointerleave',()=>{if(!state.pinned)resetInspector();});
  node.addEventListener('focus',()=>{if(!state.pinned)inspect(link);});
  node.addEventListener('blur',()=>{if(!state.pinned)resetInspector();});
  const choose=()=>{
    state.pinned=state.pinned===link.id?null:link.id;
    if(state.pinned)inspect(link);else resetInspector();
  };
  node.addEventListener('click',choose);
  node.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose();}});
}

function labelPositions(layout,links){
  const placed=[],labels=[];
  for(const link of [...links].sort((a,b)=>b.value-a.value)){
    const text=link.retained?`${fmt(link.value)} retained`:fmt(link.value);
    const boxWidth=text.length*7.3+16,boxHeight=23;
    const positions=link.retained?[.5,.35,.65]:[.38,.62,.26,.74,.5,.18,.82];
    let chosen=null;
    for(const t of positions){
      const point=curvePoint({...link,y0:link.y0+(state.view==='sankey'?link.thickness/2:0),y1:link.y1+(state.view==='sankey'?link.thickness/2:0)},t);
      for(const offset of [0,-17,17,-31,31]){
        const box={x:point.x-boxWidth/2,y:point.y-11+offset,width:boxWidth,height:boxHeight};
        const overlaps=placed.some(p=>box.x<p.x+p.width+5&&box.x+box.width+5>p.x&&box.y<p.y+p.height+5&&box.y+box.height+5>p.y);
        if(!overlaps&&box.x>250&&box.x+box.width<layout.width-250&&box.y>8&&box.y+box.height<layout.height-8){chosen={...box,text,id:link.id};break;}
      }
      if(chosen)break;
    }
    if(chosen){placed.push(chosen);labels.push(chosen);}
  }
  return labels;
}

function renderChart(){
  const svg=$('flow-chart');svg.replaceChildren();drawnLinks=[];
  $('view-sankey').setAttribute('aria-selected',String(state.view==='sankey'));
  $('view-schematic').setAttribute('aria-selected',String(state.view==='schematic'));
  $('show-values').checked=state.values;
  $('empty-chart').hidden=!!matrix;
  $('flow-chart').hidden=!matrix;
  $('download-svg').disabled=!matrix;
  if(!matrix){$('empty-chart').textContent='A flowchart is unavailable for this municipality/model. See its observed totals below.';return;}
  const layout=state.view==='sankey'?sankeyLayout(matrix):schematicLayout(matrix);
  svg.setAttribute('viewBox',`0 0 ${layout.width} ${layout.height}`);
  const title=element('title',{id:'chart-title'},svg,`${$('city-title').textContent}: ${state.view==='sankey'?'proportional voter flows':'labeled transition arrows'}`);
  element('desc',{id:'chart-description'},svg,'Estimated transitions between five first-round groups and four runoff groups. Values are model estimates, not observed individual votes.');
  const defs=element('defs',{},svg);
  if(state.view==='schematic')ORIGINS.forEach(key=>{
    const marker=element('marker',{id:`arrow-${key}`,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto'},defs);
    element('path',{d:'M0 0L10 5L0 10Z',fill:colors[key]},marker);
  });
  const paths=element('g',{'aria-label':'Estimated flows'},svg);
  drawnLinks=layout.links.filter(l=>l.value>=Math.max(.5,state.minimum)&&(state.retained||!l.retained));
  [...drawnLinks].sort((a,b)=>b.value-a.value).forEach(link=>{
    const label=`${LABELS[link.source]} to ${LABELS[link.target]}: approximately ${fmt(link.value)} voters`;
    const attrs=state.view==='sankey'?{d:ribbonPath(link),fill:colors[link.source],opacity:link.retained?.22:.5,class:'flow-ribbon'}:
      {d:linePath(link),fill:'none',stroke:colors[link.source],'stroke-width':link.retained?3:2.5,
        'stroke-dasharray':link.target==='abstention'?'7 5':'none','marker-end':`url(#arrow-${link.source})`,opacity:.75,class:'flow-line'};
    const path=element('path',{...attrs,role:'button',tabindex:0,'aria-label':label},paths);
    element('title',{},path,label);bindFlow(path,link);
    if(state.view==='schematic'||link.thickness<10){
      const hit=element('path',{d:state.view==='sankey'?linePath({...link,y0:link.y0+link.thickness/2,y1:link.y1+link.thickness/2}):linePath(link),class:'flow-hit','aria-hidden':'true'},paths);
      bindFlow(hit,link);
    }
  });
  if(state.values){
    const labels=element('g',{'aria-hidden':'true'},svg);
    for(const pos of labelPositions(layout,drawnLinks)){
      element('rect',{x:pos.x,y:pos.y,width:pos.width,height:pos.height,rx:4,class:'flow-number-bg'},labels);
      element('text',{x:pos.x+pos.width/2,y:pos.y+16,'text-anchor':'middle',class:'flow-number'},labels,pos.text);
    }
  }
  for(const [side,nodes] of [['source',layout.sources],['target',layout.targets]]){
    // Keep labels legible for tiny groups without changing proportional node sizes.
    const labelCenters=nodes.map(n=>n.y+n.height/2);
    for(let i=0;i<labelCenters.length;i++)labelCenters[i]=Math.max(labelCenters[i],i?labelCenters[i-1]+46:34);
    for(let i=labelCenters.length-1;i>=0;i--)labelCenters[i]=Math.min(labelCenters[i],i<labelCenters.length-1?labelCenters[i+1]-46:layout.height-30);
    nodes.forEach((node,nodeIndex)=>{
      const group=element('g',{'data-node':`${side}-${node.key}`},svg);
      if(state.view==='sankey'){
        element('rect',{x:node.x,y:node.y,width:node.width,height:Math.max(.75,node.height),fill:colors[node.key],rx:1},group);
        const x=side==='source'?node.x-15:node.x+node.width+15;
        const anchor=side==='source'?'end':'start',center=labelCenters[nodeIndex];
        if(Math.abs(center-node.y-node.height/2)>3)element('line',{x1:side==='source'?node.x-2:node.x+node.width+2,
          y1:node.y+node.height/2,x2:side==='source'?x+3:x-3,y2:center,stroke:'var(--line)','stroke-width':1},group);
        element('text',{x,y:center-3,'text-anchor':anchor,class:'node-label'},group,LABELS[node.key]);
        element('text',{x,y:center+20,'text-anchor':anchor,class:'node-count'},group,`${fmt(node.value)} voters`);
      }else{
        element('rect',{x:node.x,y:node.y,width:node.width,height:node.height,rx:8,fill:softColors[node.key]},group);
        const x=node.x+node.width/2;
        element('text',{x,y:node.y+27,'text-anchor':'middle',class:'node-label'},group,LABELS[node.key]);
        element('text',{x,y:node.y+49,'text-anchor':'middle',class:'node-count'},group,`${fmt(node.value)} voters`);
      }
    });
  }
  $('diagram-note').textContent=(state.view==='sankey'?'Ribbon thickness is proportional to estimated voters.':'Schematic view: arrow widths are not proportional.')+
    (state.minimum>0?` Flows below ${fmt(state.minimum)} hidden.`:' Flows below 0.5 voter omitted.');
  if(state.pinned){const link=drawnLinks.find(l=>l.id===state.pinned);if(link)inspect(link);else{state.pinned=null;resetInspector();}}
}

function highlight(id){
  $('flow-chart').querySelectorAll('[data-link]').forEach(node=>{
    node.classList.toggle('is-dimmed',!!id&&node.dataset.link!==id);
    node.classList.toggle('is-active',node.dataset.link===id);
  });
}

function inspect(link){
  highlight(link.id);
  $('flow-title').textContent=`${LABELS[link.source]} → ${LABELS[link.target]}`;
  $('flow-value').textContent=fmt(link.value,link.value<10?1:0);
  $('flow-unit').textContent=state.source==='thread'?'voters in thread estimate':current.aggregate?'estimated voters · summed municipal models':'estimated voters · analyzed sections';
  const source=graph.sources[link.i].value,target=graph.targets[link.j].value;
  let details=`<dl><dt>Share of first-round group</dt><dd>${fmt(100*link.value/source,1)}%</dd><dt>Share of runoff destination</dt><dd>${fmt(100*link.value/target,1)}%</dd>`;
  if(state.source==='municipality'){
    const fitted=current.models[state.model];
    if(fitted.low&&fitted.high)details+=`<dt>Section-bootstrap range · 2.5–97.5%</dt><dd>${fmt(fitted.low[link.i][link.j])} – ${fmt(fitted.high[link.i][link.j])} voters</dd>`;
    else details+='<dt>Bootstrap range</dt><dd>'+(current.aggregate?'Not computed for this aggregate; municipal quantiles cannot be added':'Not estimated for this sensitivity model')+'</dd>';
  }else details+='<dt>Uncertainty</dt><dd>No per-flow ranges supplied in the screenshots</dd>';
  details+=`<dt>Interpretation</dt><dd>${link.retained?'Stayed in the same category':'Changed voting category'}; inferred movement</dd></dl>`;
  $('flow-details').innerHTML=details;$('clear-selection').hidden=!state.pinned;
}

function resetInspector(){
  if(state.pinned){const link=drawnLinks.find(l=>l.id===state.pinned);if(link){inspect(link);return;}}
  highlight(null);$('flow-title').textContent='Choose a flow';$('flow-value').textContent='—';
  $('flow-unit').textContent='estimated voters';$('flow-details').textContent='Select a ribbon or arrow to see its source, destination, and estimated size.';
  $('clear-selection').hidden=true;
}

function renderTotals(){
  const c=displayCity();
  const area=state.source==='thread'||!current?.aggregate?'municipality':current.aggregate.level==='country'?'domestic electorate':current.aggregate.level;
  $('observed-round-one').textContent=`Round 1 · full ${area}`;
  $('observed-round-two').textContent=`Runoff · full ${area}`;
  const src=graph?.sources.map(n=>n.value)??Array(5).fill(null),dst=graph?.targets.map(n=>n.value)??Array(4).fill(null);
  const full1=state.source==='thread'?reference.origins:[c.a_1,c.b_1,c.other_1,c.invalid_1,c.abstention_1];
  const full2=state.source==='thread'?reference.destinations:[c.a_2,c.b_2,c.invalid_2,c.abstention_2];
  const mapping=[0,1,null,2,3];
  $('totals-body').innerHTML=ORIGINS.map((key,i)=>{
    const j=mapping[i];return `<tr><td>${esc(LABELS[key])}</td><td>${fmt(full1[i])}</td><td>${fmt(j===null?0:full2[j])}</td><td>${fmt(src[i])}</td><td>${fmt(j===null?(graph?0:null):dst[j])}</td></tr>`;
  }).join('')+`<tr><td>Total electorate</td><td>${fmt(full1.reduce((a,b)=>a+b,0))}</td><td>${fmt(full2.reduce((a,b)=>a+b,0))}</td><td>${fmt(graph?.total)}</td><td>${fmt(graph?.total)}</td></tr>`;
}

function renderGains(){
  const host=$('gain-charts');host.replaceChildren();
  $('gain-scope').textContent=state.source==='thread'?'Thread estimates · all 30 sections':current.aggregate?'Sum of municipality estimates · covered sections only':'Our estimates · analyzed sections only';
  if(!matrix){host.textContent='No flow decomposition is available for this municipality/model.';return;}
  const parts=gainBreakdown(matrix),values=parts.flatMap(c=>c.parts.map(p=>p.value));
  const min=Math.min(0,...values),max=Math.max(1,...values),span=max-min;
  const low=min-span*.05,high=max+span*.05;
  parts.forEach(candidate=>{
    const container=document.createElement('div');container.className='gain-chart';
    const heading=document.createElement('h3');heading.innerHTML=`${esc(LABELS[candidate.key])}<span>${signed(candidate.gain)} votes</span>`;container.append(heading);
    host.append(container);
    const width=Math.max(260,container.getBoundingClientRect().width);
    const svg=element('svg',{viewBox:`0 0 ${width} 300`,role:'img','aria-label':`${LABELS[candidate.key]}: estimated contributions to the net gain`});
    const start=12,end=width-85,scale=value=>start+(value-low)/(high-low)*(end-start);
    candidate.parts.forEach((part,i)=>{
      const y=28+i*48;
      element('text',{x:12,y,class:'chart-label'},svg,part.label);
      element('rect',{x:Math.min(scale(0),scale(part.value)),y:y+10,width:Math.max(.5,Math.abs(scale(part.value)-scale(0))),height:15,rx:2,
        fill:part.value>=0?colors[candidate.key]:'var(--other)'},svg);
      element('text',{x:width-4,y:y+23,'text-anchor':'end',class:'chart-value'},svg,signed(part.value));
    });
    element('line',{x1:scale(0),x2:scale(0),y1:34,y2:254,class:'chart-axis'},svg);
    element('text',{x:12,y:287,class:'chart-tick'},svg,'Estimated voters · rounded');
    container.append(svg);
  });
}

function downloadSvg(){
  const original=$('flow-chart'),copy=original.cloneNode(true);
  const originals=[original,...original.querySelectorAll('*')],copies=[copy,...copy.querySelectorAll('*')];
  originals.forEach((node,i)=>{
    const computed=getComputedStyle(node);
    const keys=['fill','stroke','stroke-width','stroke-dasharray','opacity','font-family','font-size','font-weight','text-anchor'];
    keys.forEach(key=>copies[i].style.setProperty(key,computed.getPropertyValue(key)));
  });
  copy.setAttribute('xmlns',NS);copy.setAttribute('width','1100');copy.setAttribute('height','640');
  copy.style.background=getComputedStyle(document.documentElement).getPropertyValue('--surface').trim();
  const blob=new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;
  const identifier=current?.aggregate?`${current.aggregate.level}-${current.aggregate.key}`:state.city;
  a.download=`${state.source==='thread'?'thread-reference':identifier}-${state.view}.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

$('source-thread').addEventListener('click',()=>{state.source='thread';loadCurrent();});
$('source-municipality').addEventListener('click',()=>{state.source='municipality';fillCities();loadCurrent();});
$('city-search').addEventListener('input',fillCities);
$('city-options').addEventListener('change',()=>{state.city=$('city-options').value;loadCurrent();});
$('model').addEventListener('change',()=>{state.model=$('model').value;loadCurrent();});
$('aggregate-level').addEventListener('change',()=>{state.level=$('aggregate-level').value;loadCurrent();});
$('aggregate-options').addEventListener('change',()=>{
  if(state.level==='state')state.stateCode=$('aggregate-options').value;
  else if(state.level==='region')state.region=$('aggregate-options').value;
  loadCurrent();
});
for(const view of ['sankey','schematic'])$('view-'+view).addEventListener('click',()=>{state.view=view;state.values=view==='schematic';renderChart();updateHash();});
$('show-retained').addEventListener('change',()=>{state.retained=$('show-retained').checked;renderChart();});
$('show-values').addEventListener('change',()=>{state.values=$('show-values').checked;renderChart();});
$('minimum-flow').addEventListener('input',()=>{state.minimum=Math.max(0,Number($('minimum-flow').value)||0);renderChart();});
$('clear-selection').addEventListener('click',()=>{state.pinned=null;resetInspector();});
$('download-svg').addEventListener('click',downloadSvg);
let previousGainWidth=0;
if(typeof ResizeObserver==='function')new ResizeObserver(entries=>{
  const width=entries[0].contentRect.width;
  if(Math.abs(width-previousGainWidth)>1){previousGainWidth=width;if(matrix)renderGains();}
}).observe($('gain-charts'));

try{
  [index,reference,aggregateIndex]=await Promise.all([json('data/index.json'),json('data/thread-reference.json'),json('data/aggregates/index.json')]);
  index.sort((a,b)=>a.municipality.localeCompare(b.municipality)||a.uf.localeCompare(b.uf));
  if(!index.some(c=>String(c.municipality_code)===String(state.city)))state.city='81914';
  fillCities();await loadCurrent();
  if(state.source==='thread')electionMap.setLevel('state');
}catch(error){status(`Unable to load the report: ${error.message}. Open this page through the local HTTP server.`,true);}
