'use strict';
(() => {
  const status = document.getElementById('operationsStatus');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  async function api(path, method = 'GET', data) {
    const response = await fetch(path, {method, headers: {'Content-Type':'application/json','X-CSRFToken':csrf || ''}, body:data === undefined ? undefined : JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Operation failed');
    return result;
  }
  function text(parent, tag, value) { const node=document.createElement(tag); node.textContent=value; parent.append(node); return node; }
  async function load() {
    try {
      const [ops, settings, health]=await Promise.all([api('/admin/api/flow-operations'),api('/admin/api/flow-controls'),api('/admin/api/flow-health')]);
      document.getElementById('flowHealth').replaceChildren();
      text(document.getElementById('flowHealth'),'p',health.worker_recent ? 'Worker heartbeat is recent.' : 'Worker heartbeat is missing or stale.');
      text(document.getElementById('flowHealth'),'p',`${health.unbalanced_journals} unbalanced journals; ${Object.values(health.pending_reviews).reduce((a,b)=>a+b,0)} reviews or retries.`);
      for (const id of ['controls','shipments','reviews']) document.getElementById(id).replaceChildren();
      for (const [key,value] of Object.entries(settings.controls)) {
        const label=text(document.getElementById('controls'),'label', key.replaceAll('_',' ')+' ');
        label.style.display='block'; const checkbox=document.createElement('input'); checkbox.type='checkbox'; checkbox.checked=value; label.append(checkbox);
        checkbox.addEventListener('change',async()=>{ checkbox.disabled=true; try {await api('/admin/api/flow-controls','PUT',{[key]:checkbox.checked}); status.textContent='Control saved';} catch(e) { checkbox.checked=value; status.textContent=e.message;} finally {checkbox.disabled=false;} });
      }
      for (const ship of ops.shipments) {
        const card=text(document.getElementById('shipments'),'article',''); card.style.cssText='padding:1rem;border:1px solid #ccc;margin:1rem 0;overflow-wrap:anywhere';
        text(card,'h3',ship.id); text(card,'p',`${ship.state} · ${ship.carrier || 'No carrier'} · ${ship.tracking_number || 'No tracking'}`);
        const input=document.createElement('input'); input.placeholder='Carrier evidence reference'; input.setAttribute('aria-label','Carrier evidence reference'); input.style.maxWidth='100%'; card.append(input);
        const confirmLabel=text(card,'label',' Carrier acceptance and destination verified '); const checked=document.createElement('input'); checked.type='checkbox'; confirmLabel.append(checked);
        text(card,'p',`Required insured merchandise value: $${(ship.insured_value_required_cents/100).toFixed(2)}. Tracking due: ${ship.tracking_due_at || 'Not authorized'}`);
        const policy=document.createElement('input'); policy.placeholder='Insurance policy number'; policy.setAttribute('aria-label','Insurance policy number'); card.append(policy);
        const premium=document.createElement('input'); premium.type='number'; premium.min='0'; premium.step='0.01'; premium.placeholder='Premium in dollars'; premium.setAttribute('aria-label','Premium in dollars'); card.append(premium);
        const insuredLabel=text(card,'label',' Applicable contents and value coverage verified '); const coverage=document.createElement('input'); coverage.type='checkbox'; insuredLabel.append(coverage);
        const signatureLabel=text(card,'label',' Signature service required '); const signature=document.createElement('input'); signature.type='checkbox'; signatureLabel.append(signature);
        const record=text(card,'button','Record insurance evidence'); record.type='button';
        record.addEventListener('click',async()=>{
          const cost=Math.round(Number(premium.value)*100);
          if (!policy.value.trim() || !input.value.trim() || !coverage.checked || premium.value.trim()==='' || !Number.isSafeInteger(cost) || cost<0) { status.textContent='Verified coverage, policy, premium and evidence reference are required'; return; }
          record.disabled=true;
          try {await api(`/admin/api/flow-shipments/${encodeURIComponent(ship.id)}/insurance`,'POST',{policy_number:policy.value.trim(),insured_value_cents:ship.insured_value_required_cents,premium_cents:cost,evidence:{reference:input.value.trim(),covered:true,signature_required:signature.checked}});status.textContent='Insurance evidence recorded';}
          catch(e){status.textContent=e.message;} finally{record.disabled=false;}
        });
        const authorize=text(card,'button','Authorize shipment'); authorize.type='button';
        authorize.addEventListener('click',async()=>{authorize.disabled=true;try{await api(`/admin/api/flow-shipments/${encodeURIComponent(ship.id)}/authorize`,'POST',{});status.textContent='Shipment authorization recorded';await load();}catch(e){status.textContent=e.message;authorize.disabled=false;}});
        for (const [label,path,payload] of [['Confirm tracking','carrier-confirmation',{}],['Confirm delivery','carrier-event',{state:'DELIVERED'}]]) {
          const button=text(card,'button',label); button.type='button'; button.addEventListener('click',async()=>{
            if (!input.value.trim() || !checked.checked) {status.textContent='Evidence and carrier verification are required';return;}
            button.disabled=true;
            try {await api(`/admin/api/flow-shipments/${encodeURIComponent(ship.id)}/${path}`,'POST',{...payload,evidence:{reference:input.value.trim(),carrier_confirmed:true,destination_matches:true}}); status.textContent='Carrier event saved';await load();}
            catch(e){status.textContent=e.message;button.disabled=false;}
          });
        }
      }
      for (const review of ops.reviews) text(document.getElementById('reviews'),'p',`${review.reason}: ${review.scope_type} ${review.scope_id}`);
    } catch(e){status.textContent=e.message;}
  }
  load();
})();
