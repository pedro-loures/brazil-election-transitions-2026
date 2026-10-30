import assert from 'node:assert/strict';
import fs from 'node:fs';
import {graphFromMatrix,sankeyLayout,schematicLayout,ribbonPath,linePath,gainBreakdown} from '../web/flowcharts/flow-layout.mjs';

const matrix=[[2818,0,0,81],[0,3189,0,56],[13,292,57,94],[194,0,119,0],[478,0,6,1340]];
const graph=graphFromMatrix(matrix);
assert.deepEqual(graph.sources.map(n=>n.value),[2899,3245,456,313,1824]);
assert.deepEqual(graph.targets.map(n=>n.value),[3503,3481,182,1571]);
assert.equal(graph.total,8737);assert.equal(graph.links.length,13);
for(const layout of [sankeyLayout(matrix),schematicLayout(matrix)]){
  for(const n of [...layout.sources,...layout.targets]){
    assert(n.x>=0&&n.x+n.width<=layout.width);
    assert(n.y>=0&&n.y+n.height<=layout.height);
  }
  for(const link of layout.links){assert(!/NaN|Infinity/.test(ribbonPath(link)));assert(!/NaN|Infinity/.test(linePath(link)));}
}
const weighted=sankeyLayout(matrix);
for(const s of weighted.sources){
  const total=weighted.links.filter(l=>l.i===s.index).reduce((a,l)=>a+l.thickness,0);
  assert(Math.abs(total-s.height)<1e-8);
}
for(const t of weighted.targets){
  const total=weighted.links.filter(l=>l.j===t.index).reduce((a,l)=>a+l.thickness,0);
  assert(Math.abs(total-t.height)<1e-8);
}
const gains=gainBreakdown(matrix);
assert.equal(gains[0].gain,604);assert.equal(gains[1].gain,236);
for(const c of gains)assert.equal(c.parts.reduce((s,p)=>s+p.value,0),c.gain);
assert.throws(()=>graphFromMatrix([[0]]),/5 × 4/);
assert.throws(()=>graphFromMatrix(matrix.map((r,i)=>r.map((v,j)=>i===0&&j===0?-1:v))),/nonnegative/);
const dataDir=process.argv[2];
if(dataDir){
  const index=JSON.parse(fs.readFileSync(`${dataDir}/index.json`,'utf8'));
  assert.equal(index.length,5571);
  const lebon=JSON.parse(fs.readFileSync(`${dataDir}/municipalities/81914.json`,'utf8'));
  assert.equal(lebon.city.sections_analyzed,29);
  assert.notDeepEqual(lebon.models.full.matrix,matrix);
  const modeled=graphFromMatrix(lebon.models.full.matrix);
  modeled.sources.forEach(n=>assert(Math.abs(n.value-lebon.city[`analyzed_${n.key}_1`])<.001));
  modeled.targets.forEach(n=>assert(Math.abs(n.value-lebon.city[`analyzed_${n.key}_2`])<.001));
  const skipped=index.find(c=>c.model_status!=='ok');
  const skippedData=JSON.parse(fs.readFileSync(`${dataDir}/municipalities/${skipped.municipality_code}.json`,'utf8'));
  assert.deepEqual(skippedData.models,{});
}
console.log('Flow-layout checks passed: reference numbers, conserved ribbon thickness, gains, graph bounds, source separation');
