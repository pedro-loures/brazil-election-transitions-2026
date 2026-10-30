// Smoke test the generated offline report without external browser dependencies.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const payload = html.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/)[1];
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const data = JSON.parse(payload);
assert(data.cities.length > 0);
const elements = new Map();
const element = name => {
  if (!elements.has(name)) elements.set(name, {value:name === '#sort'?'municipality':'', textContent:'', innerHTML:'', scrollIntoView(){}});
  return elements.get(name);
};
const context = {document:{getElementById:()=>({textContent:payload}), querySelector:element, querySelectorAll:()=>[]}};
vm.createContext(context);
vm.runInContext(script, context);
assert(element('#table').innerHTML.includes('Municipality'));
element('#search').value='lebon';
element('#search').oninput();
assert(element('#count').textContent.startsWith('1 municipalities'));
assert(element('#table').innerHTML.includes('LEBON RÉGIS'));
vm.runInContext('detail(filtered[0])', context);
assert(element('#detail').innerHTML.includes('Observed counts'));
assert(element('#detail').innerHTML.includes('Model estimates'));
assert(element('#detail').innerHTML.includes('Bootstrap'));
console.log(`Report smoke test passed: ${data.cities.length} municipalities, search and detail rendering`);
