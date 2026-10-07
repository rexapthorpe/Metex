const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function wizard(hasMethod) {
  const controls = {
    'bm-back': {style:{}}, 'bm-continue': {style:{}, disabled:false}, 'bm-submit': {style:{}},
    'selected-pm-id': {value:hasMethod ? 'pm_test' : ''}
  };
  if (!hasMethod) controls['bm-no-card-block'] = {};
  const window = {};
  vm.runInNewContext(fs.readFileSync('static/js/modals/bid_modal_steps.js','utf8'), {
    window, document: {getElementById:id=>controls[id] || null, querySelectorAll:()=>[]}, console
  });
  return {window, controls};
}
test('missing payment disables Continue at payment step; Back restores navigation', async()=>{
  const {window,controls}=wizard(false);
  await window.bmGoToStep(4);
  assert.equal(controls['bm-continue'].disabled,true);
  await window.bmGoToStep(3);
  assert.equal(controls['bm-continue'].disabled,false);
});
test('selected payment enables Continue, but empty selection blocks it',async()=>{
  const {window,controls}=wizard(true);
  await window.bmGoToStep(4);
  assert.equal(controls['bm-continue'].disabled,false);
  controls['selected-pm-id'].value='';
  await window.bmGoToStep(4);
  assert.equal(controls['bm-continue'].disabled,true);
});
