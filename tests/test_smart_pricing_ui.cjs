const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function setup({seeded=false,mode='standard',deferred=false,failure=null,malformed=false}={}) {
    const elements = {};
    class Element {
        constructor(value='',id='') { this.id=id; this.value=value; this.hidden=false; this.required=false; this.disabled=false; this.checked=false; this.textContent=''; this.listeners={}; this.children=[]; this.parentElement={hidden:false}; }
        addEventListener(type,fn) { (this.listeners[type] ||= []).push(fn); }
        async dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) await fn(event); return true; }
        setAttribute() {}
        focus() { this.focused=true; }
        contains(el) { return el && (el.id.startsWith('smart-') || el.id==='strategy'); }
        reportValidity() { return Number(this.value)>=0 && this.value!==''; }
        animate() { return {finished:Promise.resolve()}; }
        async click() { if (!this.disabled) for (const fn of this.listeners.click || []) await fn({type:'click'}); }
    }
    const ids=['smart-preview-net','smart-preview-net-note','smart-preview-total-net','smart-availability','smart-availability-title','smart-availability-copy','smart-availability-retry','smart-availability-manual','smart-pricing-panel','manual-pricing-controls','smart-pricing-enabled','smart-minimum','smart-pricing-enter','smart-pricing-exit','smart-pricing-use','smart-pricing-status','smart-description-title','smart-description-copy','sellForm','floor_price','spot_premium','price_per_coin','pricing_mode_static','pricing_mode_premium','smart-starting','smart-preview-token','smart-warning-acknowledged','smart-warning','smart-warning-continue','smart-warning-cancel','smart-preview-refresh','smart-preview','smart-starting-row','smart-market-message','smart-preview-strategy','smart-preview-premium','smart-premium-label','smart-preview-metal','smart-preview-minimum','smart-preview-price','smart-fair-row','smart-range-row','smart-preview-fair','smart-preview-range'];
    ids.forEach(id=>elements[id]=new Element('',id));
    ['smart-pricing-panel','smart-warning','smart-preview','smart-starting-row'].forEach(id=>elements[id].hidden=true);
    elements['smart-pricing-enabled'].value='0';elements['smart-warning-acknowledged'].value='0';
    elements['floor_price'].value='3000';elements['spot_premium'].value='20.00';
    elements.pricing_mode_static.value='static'; elements.pricing_mode_premium.value='premium_to_spot';elements.pricing_mode_static.checked=true;
    const radios=['fast','balanced','big'].map(value=>new Element(value,'strategy')); radios[1].checked=true;
    const document={getElementById:id=>elements[id],addEventListener:(type,fn)=>fn(),
        querySelector:selector=>selector.includes('smart_pricing_strategy') ? radios.find(r=>r.checked) : [elements.pricing_mode_static,elements.pricing_mode_premium].find(r=>r.checked),
        querySelectorAll:()=>radios};
    for (const radio of [elements.pricing_mode_static,elements.pricing_mode_premium]) radio.addEventListener('change',()=>{
        [elements.pricing_mode_static,elements.pricing_mode_premium].forEach(r=>r.checked=r===radio);
    });
    class FormData {
        constructor() { this.data=new Map([['smart_pricing_strategy',radios.find(r=>r.checked).value],['smart_minimum',elements['smart-minimum'].value],['smart_starting',elements['smart-starting'].value],['smart_warning_acknowledged',elements['smart-warning-acknowledged'].value]]); }
        entries() { return this.data.entries(); }
        delete(key) { this.data.delete(key); }
        set(key,value) { this.data.set(key,value); }
        get(key) { return this.data.get(key); }
    }
    const pending=[]; const events={};
    document.addEventListener=(type,fn)=>{ if(type==='DOMContentLoaded') fn(); else (events[type] ||= []).push(fn); };
    document.dispatchEvent=async event=>{for(const fn of events[event.type] || []) await fn(event);};
    const window={document,currentMode:mode,setItems:[]};
    function response(data) { return {ok:true,json:async()=>data}; }
    const fetch=async(url,{body})=>{
        if (failure) {const value=failure;failure=null;return {ok:false,json:async()=>value};}
        if (malformed) {malformed=false;return response({success:true,token:'bad',strategy:'balanced',initial_price_cents:null});}
        if (deferred) return new Promise(resolve=>pending.push(resolve));
        if (mode!=='standard' && body.get('smart_warning_acknowledged')!=='1') return response({success:true,warning_required:true});
        const strategy=body.get('smart_pricing_strategy'); const minimum=Math.round(Number(body.get('smart_minimum'))*100);
        if (seeded && body.get('smart_starting')==='') return response({success:true,seeded:true,needs_starting:true,confidence_label:'insufficient'});
        const premium=Math.max(minimum,seeded?Math.round(Number(body.get('smart_starting'))*100):({fast:16500,balanced:19000,big:22000})[strategy]);
        return response({success:true,token:'server-preview-token',strategy,minimum_cents:minimum,initial_premium_cents:premium,metal_value_cents:400000,initial_price_cents:400000+premium,quantity:1,seller_fee_cents:Math.round((400000+premium)*.05),estimated_net_cents:400000+premium-Math.round((400000+premium)*.05),estimated_total_net_cents:400000+premium-Math.round((400000+premium)*.05),seeded,confidence_label:seeded?'insufficient':'medium',fair_premium_cents:19000,range_lower_cents:16500,range_upper_cents:22000});
    };
    vm.runInNewContext(fs.readFileSync('static/js/smart_pricing.js','utf8'),{window,document,fetch,FormData,setTimeout:()=>1,clearTimeout:()=>{},matchMedia:()=>({matches:true}),Event:class {constructor(type) {this.type=type;}},getComputedStyle:()=>({display:'block'})});
    return {elements,radios,window,pending,response,document};
}
test('enter defaults to Balanced; preview precedes consent; exit restores manual pricing',async()=>{
    const {elements:e}=setup(); await e['smart-pricing-enter'].click();
    assert.equal(e['smart-pricing-panel'].hidden,false);assert.equal(e['manual-pricing-controls'].hidden,true);
    assert.equal(e['smart-description-title'].textContent,'Balance price and selling speed');
    assert.equal(e['smart-pricing-enabled'].value,'0');assert.equal(e['smart-preview-price'].textContent,'$4,190.00');
    assert.match(e['smart-preview-premium'].textContent,/190.00/);
    await e['smart-pricing-use'].click(); assert.equal(e['smart-pricing-enabled'].value,'1');assert.equal(e.spot_premium.value,'190.00');
    await e['smart-pricing-exit'].click();assert.equal(e['smart-pricing-panel'].hidden,true);assert.equal(e['manual-pricing-controls'].hidden,false);
    assert.equal(e['smart-pricing-enabled'].value,'0');assert.equal(e.pricing_mode_static.checked,true);assert.equal(e.floor_price.value,'3000');assert.equal(e.spot_premium.value,'20.00');
});
test('all strategies update explanations, initial premium and total from server',async()=>{
    const {elements:e,radios}=setup();await e['smart-pricing-enter'].click();
    for (const [index,title] of ['Prioritize a quicker sale','Balance price and selling speed','Prioritize a higher sale price'].entries()) {
        radios.forEach((r,n)=>r.checked=n===index);await radios[index].dispatchEvent({type:'change'});
        assert.equal(e['smart-description-title'].textContent,title);assert.ok(e['smart-description-copy'].textContent.length>40);
        assert.equal(e['smart-preview-price'].textContent,['$4,165.00','$4,190.00','$4,220.00'][index]);
    }
    assert.equal(radios.length,3);
});
test('unconfirmed Smart mode blocks submission',async()=>{
    const {elements:e}=setup();await e['smart-pricing-enter'].click();let prevented=false,stopped=false;
    await e.sellForm.dispatchEvent({type:'submit',preventDefault:()=>prevented=true,stopImmediatePropagation:()=>stopped=true});
    assert.ok(prevented && stopped);assert.match(e['smart-pricing-status'].textContent,/Use Smart Pricing/);
});
test('changing minimum invalidates consent and shows actual constrained target',async()=>{
    const {elements:e}=setup();await e['smart-pricing-enter'].click();await e['smart-pricing-use'].click();
    e['smart-minimum'].value='250.00';await e['smart-minimum'].dispatchEvent({type:'input'});
    assert.equal(e['smart-pricing-enabled'].value,'0');assert.equal(e['smart-preview-token'].value,'');assert.ok(e['smart-pricing-use'].disabled);
    await e['smart-preview-refresh'].click();assert.equal(e['smart-preview-price'].textContent,'$4,250.00');
    assert.equal(e['smart-preview-fair'].textContent,'+$190.00');
});
test('insufficient evidence offers manual pricing without asking for any premium',async()=>{
    const {elements:e}=setup({seeded:true});await e['smart-pricing-enter'].click();
    assert.equal(e['smart-starting-row'].hidden,true);assert.equal(e['smart-starting'].required,false);assert.ok(e['smart-pricing-use'].disabled);
    assert.equal(e['smart-availability-title'].textContent,'Not enough comparable market data');
    assert.match(e['smart-availability-copy'].textContent,/Fixed Price or Premium to Spot/);
    await e['smart-availability-manual'].click();assert.equal(e['manual-pricing-controls'].hidden,false);
});
for (const mode of ['set','isolated']) test(`${mode} warning requires Continue and can cancel into manual`,async()=>{
    const {elements:e}=setup({mode});await e['smart-pricing-enter'].click();
    assert.equal(e['smart-warning'].hidden,false);assert.equal(e['smart-pricing-panel'].hidden,true);assert.equal(e['smart-pricing-enabled'].value,'0');
    await e['smart-warning-cancel'].click();assert.equal(e['smart-warning'].hidden,true);assert.equal(e['manual-pricing-controls'].hidden,false);
    await e['smart-pricing-enter'].click();await e['smart-warning-continue'].click();
    assert.equal(e['smart-warning-acknowledged'].value,'1');assert.equal(e['smart-pricing-panel'].hidden,false);assert.equal(e['smart-pricing-enabled'].value,'0');
});
test('older preview response cannot replace a newer request or authorize activation',async()=>{
    const {elements:e,radios,pending,response}=setup({deferred:true});
    const enter=e['smart-pricing-enter'].click();await Promise.resolve();
    radios.forEach(r=>r.checked=r.value==='big');const change=radios[2].dispatchEvent({type:'change'});await Promise.resolve();
    const make=(premium,strategy)=>response({success:true,token:'signed',strategy,minimum_cents:0,initial_premium_cents:premium,metal_value_cents:400000,initial_price_cents:400000+premium,quantity:1,seller_fee_cents:Math.round((400000+premium)*.05),estimated_net_cents:400000+premium-Math.round((400000+premium)*.05),estimated_total_net_cents:400000+premium-Math.round((400000+premium)*.05),seeded:false,confidence_label:'medium',fair_premium_cents:19000,range_lower_cents:16500,range_upper_cents:22000});
    pending[1](make(22000,'big'));await change;pending[0](make(19000,'balanced'));await enter;
    assert.equal(e['smart-preview-price'].textContent,'$4,220.00');assert.equal(e['smart-preview-strategy'].textContent,'Sell Big');
});
test('product changes clear confirmed token immediately',async()=>{
    const {elements:e,window}=setup();await e['smart-pricing-enter'].click();await e['smart-pricing-use'].click();
    await e.sellForm.dispatchEvent({type:'change',target:{id:'weight'}});
    assert.equal(e['smart-preview-token'].value,'');assert.equal(e['smart-pricing-enabled'].value,'0');assert.equal(window.smartCurrentPreview,null);
});

test('spot outage offers friendly retry and manual exit; recovery requires consent',async()=>{
    const {elements:e}=setup({failure:{success:false,code:'SMART_SPOT_UNAVAILABLE',message:'provider database null NaN'}});
    await e['smart-pricing-enter'].click();
    assert.equal(e['smart-availability'].hidden,false);
    assert.equal(e['smart-availability-title'].textContent,'Current metal pricing is temporarily unavailable');
    assert.doesNotMatch(e['smart-availability-copy'].textContent,/provider|database|null|NaN/);
    assert.equal(e['smart-preview-token'].value,'');assert.ok(e['smart-pricing-use'].disabled);
    await e['smart-availability-retry'].click();
    assert.equal(e['smart-availability'].hidden,true);assert.equal(e['smart-preview-price'].textContent,'$4,190.00');
    assert.equal(e['smart-pricing-enabled'].value,'0');
    await e['smart-pricing-use'].click();assert.equal(e['smart-pricing-enabled'].value,'1');
    await e['smart-availability-manual'].click();assert.equal(e['manual-pricing-controls'].hidden,false);
});
test('changed publication preview regenerates exact price and clears prior consent',async()=>{
    const {elements:e,document}=setup();await e['smart-pricing-enter'].click();await e['smart-pricing-use'].click();
    await document.dispatchEvent({type:'metex:smart-preview-changed'});
    assert.equal(e['smart-pricing-enabled'].value,'0');assert.match(e['smart-pricing-status'].textContent,/Price updated/);
    assert.equal(e['smart-preview-price'].textContent,'$4,190.00');
});
test('malformed amounts never render null or NaN or allow confirmation',async()=>{
    const {elements:e}=setup({malformed:true});await e['smart-pricing-enter'].click();
    assert.ok(e['smart-pricing-use'].disabled);assert.equal(e['smart-preview'].hidden,true);
    assert.equal(e['smart-availability'].hidden,false);
    assert.doesNotMatch(e['smart-availability-copy'].textContent,/null|NaN|invalid preview/);
});

test('strategies display estimated seller proceeds after the actual platform fee',async()=>{
    const {elements:e,radios}=setup();await e['smart-pricing-enter'].click();
    for (const [index,net] of ['$3,956.75','$3,980.50','$4,009.00'].entries()) {
        radios.forEach((r,n)=>r.checked=n===index);await radios[index].dispatchEvent({type:'change'});
        assert.equal(e['smart-preview-net'].textContent,net);
        assert.match(e['smart-preview-net-note'].textContent,/after METEX’s 5% fee/);
        assert.equal(e['smart-preview-total-net'].hidden,true);
    }
});
