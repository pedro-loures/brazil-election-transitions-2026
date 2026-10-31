const $=id=>document.getElementById(id),names=['Lula','Flávio','Other candidates','Blank/null','Abstention'];
function options(id,values){$(id).replaceChildren(...values.map(([value,label])=>{const o=document.createElement('option');o.value=value;o.textContent=label;return o}));}
const fmt=(x,d=2)=>x===null||x===undefined||!Number.isFinite(Number(x))?'Unavailable':Number(x).toFixed(d);
options('city',DATA.cities.map(c=>[c.municipality_code,`${c.municipality} / ${c.uf} · bin ${c.population_bin}`]));
options('origin',names.map((n,i)=>[i,n]));$('origin').value='4';
options('destination',[0,1,3,4].map((i,k)=>[k,names[i]]));
options('family',DATA.families.map(f=>[f,f]));
const subsets=DATA.families.map((_,i)=>DATA.families.filter((_,j)=>i!==j));subsets.push(DATA.families);
options('subset',subsets.map(c=>[c.join('|'),c.join(' + ')]));$('subset').value=DATA.families.join('|');
const key=r=>[r.municipality_code,r.support,r.unit,r.origin,r.destination].join('|');
const agreement=new Map(DATA.agreement.map(r=>[key(r),r]));
const flows=new Map(DATA.flows.map(r=>[key(r)+'|'+r.family,r]));
const resampling=new Map(DATA.resampling.map(r=>[key(r)+'|'+r.family,r]));
const prior=new Map(DATA.prior.map(r=>[key(r)+'|'+r.family,r]));
const bootstrap=new Map(DATA.bootstrap.map(r=>[key(r)+'|'+r.families.join('|'),r]));
function row(code,unit=0){return{municipality_code:Number(code),support:$('support').value,unit:Number(unit),origin:Number($('origin').value),destination:Number($('destination').value)};}
function value(code,unit=0){const k=key(row(code,unit)),f=flows.get(k+'|'+$('family').value);switch($('metric').value){case'range':return agreement.get(k)?.range_rate_pp;case'agreement':return agreement.get(k)?.agreeing_models;case'bootstrap':{const v=bootstrap.get(k+'|'+$('subset').value)?.diagnostic_ok_agreement_fraction;return v==null?null:v*100;}case'sd':return resampling.get(k+'|'+$('family').value)?.rate_sd_pp;case'prior':{const p=prior.get(k+'|'+$('family').value);return p?.all_diagnostic_ok?p.shift_electorate_pp:null;}case'width':return f?.width_rate_pp;case'estimate':return f?.origin_voters>0?100*f.estimate/f.origin_voters:null;}}
function colour(v,max){return v===null||v===undefined||!Number.isFinite(v)?'#cfd8e2':`hsl(${215-190*Math.min(1,Math.max(0,v/max))} 65% 58%)`;}
function units(){const old=$('unit').value,code=Number($('city').value),support=$('support').value;const ids=DATA.locations.filter(r=>r.municipality_code===code&&r.support===support).map(r=>r.unit);options('unit',ids.map(i=>[i,i]));if(ids.includes(Number(old)))$('unit').value=old;}
const ns='http://www.w3.org/2000/svg';function element(tag,attrs){const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;}
let current=[];
function render(){if(!DATA.cities.length){$('notice').textContent='No completed observed fits yet. Execution is still pending.';return;}
const code=Number($('city').value),unit=Number($('unit').value),support=$('support').value,c=DATA.cities.find(c=>c.municipality_code===code),k=key(row(code,unit)),a=agreement.get(k),svg=$('map');svg.replaceChildren();current=[];
const max=({range:30,agreement:4,bootstrap:100,sd:20,prior:5,width:100,estimate:100})[$('metric').value];
if(support==='municipality'){
 const project=([lon,lat])=>[(lon+75)*17,(6-lat)*19];
 for(const feature of DATA.geometry.features){const polygons=feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.coordinates;
 const d=polygons.map(p=>p.map(r=>r.map((v,i)=>(i?'L':'M')+project(v).join(',')).join(' ')+'Z').join(' ')).join(' ');
 const n=Number(feature.properties.key),v=value(n),path=element('path',{d,fill:colour(v,max),'fill-rule':'evenodd'});svg.append(path);
 const loc=DATA.locations.find(r=>r.municipality_code===n&&r.support==='municipality');if(loc){const[x,y]=project([loc.longitude,loc.latitude]),p=element('circle',{cx:x,cy:y,r:6,fill:colour(v,max)});p.onclick=()=>{$('city').value=String(n);units();render();};svg.append(p);}current.push({municipality_code:n,value:v??null});}
}else{
 const locations=DATA.locations.filter(r=>r.municipality_code===code&&r.support===support),xs=locations.map(r=>r.longitude),ys=locations.map(r=>r.latitude),x0=Math.min(...xs),y0=Math.min(...ys),dx=Math.max(.001,Math.max(...xs)-x0),dy=Math.max(.001,Math.max(...ys)-y0);
 for(const r of locations){const v=value(code,r.unit),p=element('circle',{cx:40+720*(r.longitude-x0)/dx,cy:760-720*(r.latitude-y0)/dy,r:r.unit===unit?7:4,fill:colour(v,max)});p.onclick=()=>{$('unit').value=String(r.unit);render();};svg.append(p);current.push({...r,value:v??null});}}
$('legend').textContent=`${$('metric').selectedOptions[0].textContent}. Colour range 0–${max}; gray means unavailable. Agreement counts do not certify accuracy.`;
$('selected').textContent=`${c.municipality} / ${c.uf} · ${support} ${unit}`;
const b=bootstrap.get(k+'|'+$('subset').value);
$('detail').textContent=[`Agreeing families: ${a?.maximum_subsets?.map(c=>c.join(' + ')).join(' OR ')||'Unavailable / unsupported origin'}`,
`Available: ${a?.available_models?.join(', ')||'none'}. Unavailable: ${a?.unavailable_models?.join(', ')||'none'}.`,
`Passing computational diagnostics: ${a?.diagnostic_ok_families?.join(', ')||'none'}.`,
`Across-model rate range: ${fmt(a?.range_rate_pp)} pp. Count range: ${fmt(a?.range_voters)} voters.`,
`Completed paired resamples: ${fmt(b?.completed_paired_cases,0)}. Agreement among diagnostically valid fits: ${fmt(b?.diagnostic_ok_agreement_fraction==null?null:b.diagnostic_ok_agreement_fraction*100)}%.`,
'Independent validation: incomplete. Resampling ranges are sensitivity summaries, not calibrated confidence intervals.'].join('\n');
const table=document.createElement('table'),head=table.insertRow();['Model','Rate (%)','95% posterior interval (%)','Computation','Resampling SD (pp)'].forEach(t=>{const th=document.createElement('th');th.textContent=t;head.append(th)});
for(const family of DATA.families){const f=flows.get(k+'|'+family),r=resampling.get(k+'|'+family),tr=table.insertRow(),n=f?.origin_voters;[family,n>0?fmt(100*f.estimate/n):'Unavailable',n>0?`${fmt(100*f.low/n)}–${fmt(100*f.high/n)}`:'Unavailable',f?.status||'Unavailable',fmt(r?.rate_sd_pp)].forEach(t=>tr.insertCell().textContent=t);}$('table').replaceChildren(table);
}
$('notice').textContent=`${DATA.decision.completed_fit_attempts} completed fit attempts. Decision: insufficient evidence. Frozen source hashes unchanged: ${DATA.decision.sources_unchanged}.`;
const sim=document.createElement('table');const h=sim.insertRow();['Phase','Bin','Scenario','Independent datasets','Datasets with eligible consensus','Fraction wrong among selected cells'].forEach(t=>{const th=document.createElement('th');th.textContent=t;h.append(th)});
for(const s of DATA.simulation){const tr=sim.insertRow();[s.phase,s.population_bin,s.scenario,s.independent_datasets,s.datasets_with_eligible_consensus,s.conditional_wrong_fraction.mean==null?'Unavailable':fmt(s.conditional_wrong_fraction.mean*100)+'%'].forEach(t=>tr.insertCell().textContent=t);}$('simulation').replaceChildren(sim);
for(const id of ['origin','destination','family','unit','metric','subset'])$(id).onchange=render;
for(const id of ['city','support'])$(id).onchange=()=>{units();render();};
$('export').onclick=()=>{const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify({selection:Object.fromEntries(['city','origin','destination','family','support','unit','metric','subset'].map(k=>[k,$(k).value])),values:current},null,2)],{type:'application/json'}));a.href=url;a.download='model-agreement-view.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};units();render();
