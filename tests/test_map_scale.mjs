import assert from 'node:assert/strict';
import {colorFraction,colorFor,legendValue,marginChange,gainLabel} from '../web/flowcharts/map.mjs';

assert.equal(marginChange({a_1:2899,a_2:3503,b_1:3245,b_2:3481}),368);
for(const scale of ['linear','log']){
  assert.equal(colorFraction(0,1e6,scale),0);
  assert.equal(colorFraction(1e6,1e6,scale),1);
  assert.equal(colorFraction(-1e6,1e6,scale),1);
  assert.equal(colorFor(0,1e6,scale),'#f5f2ea');
  for(const votes of [-1e6,-1000,-1,0,1,1000,1e6]){
    const fraction=Math.sign(votes)*colorFraction(votes,1e6,scale);
    assert.ok(Math.abs(legendValue(fraction,1e6,scale)-votes)<1e-6,'Legend must invert the color scale');
  }
}
assert.ok(colorFraction(1000,1e6,'log')>.3,'Smaller municipalities must remain visible against the largest city');
assert.ok(colorFraction(1000,1e6,'log')<.4,'Soft logarithmic coloring must temper the previous high contrast');
assert.ok(colorFraction(1000,1e6,'linear')<.01);
assert.equal(colorFor(1e6,1e6),'#c1707e');
assert.equal(colorFor(-1e6,1e6),'#7095b5');
assert.equal(gainLabel(368),'Lula +368');
assert.equal(gainLabel(-368),'Flávio +368');
assert.equal(gainLabel(0),'Equal gains');
assert.equal(colorFraction(0,0),0);
console.log('Map scale checks passed: zero, direction, log contrast, and exact legend inversion');
