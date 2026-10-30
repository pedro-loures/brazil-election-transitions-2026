const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const file=process.argv[2],html=fs.readFileSync(file,'utf8');
assert(Buffer.byteLength(html)<1_000_000);
assert(!/<!doctype|<html|<head>|<body>/i.test(html));
const data=html.match(/<script type="application\/json" id="bm-data">([\s\S]*?)<\/script>/)[1];
const rows=JSON.parse(data);assert.equal(rows.length,5571);
const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]));
class Element {
  constructor(tag){this.tagName=tag;this.value='';this.textContent='';this.children=[];this.events={};this.attributes={};}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  addEventListener(name,callback){this.events[name]=callback;}
  setAttribute(key,value){this.attributes[key]=value;}
}
const elements=new Map([...ids].map(id=>[id,new Element('div')]));
elements.get('bm-data').textContent=data;
const root=elements.get('brazil-municipalities-view');
root.querySelector=selector=>{assert(ids.has(selector.slice(1)),selector);return elements.get(selector.slice(1));};
const saves=[];
const window={openai:{setWidgetState:state=>{saves.push(state);return Promise.resolve();}},addEventListener(){}};
const document={getElementById:id=>{assert(ids.has(id));return elements.get(id);},createElement:tag=>new Element(tag)};
const context={document,window,console};vm.createContext(context);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];assert.equal(scripts.length,1);
vm.runInContext(scripts[0][1],context);
assert.equal(elements.get('bm-name').textContent,'LEBON RÉGIS · SC');
assert(elements.get('bm-gains').textContent.includes('+604'));
assert(elements.get('bm-coverage').textContent.includes('29/30'));
assert.equal(saves.length,0,'Do not save state on load');
const query=elements.get('bm-search');query.value='sao paulo';query.events.input();
const city=rows.find(r=>r[2]==='SÃO PAULO'&&r[0]==='SP');assert(city);
const picker=elements.get('bm-city');assert(picker.children.some(o=>o.textContent==='SÃO PAULO · SP'));
picker.value=String(city[1]);picker.events.change();
assert.equal(elements.get('bm-name').textContent,'SÃO PAULO · SP');
assert.equal(saves.at(-1).modelContent.municipality_code,city[1]);
const noModel=rows.find(r=>!r[19]);assert(noModel);picker.value=String(noModel[1]);picker.events.change();
assert(elements.get('bm-model-scope').textContent.includes('Insufficient'));
assert.equal(elements.get('bm-model-table').children.length,0);
console.log(`Inline report passed: ${rows.length} municipalities, ${Buffer.byteLength(html)} bytes, search/selection/state/model fallback`);
