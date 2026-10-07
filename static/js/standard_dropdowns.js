/* Shared rounded menus keep native selects as the authoritative form values. */
(() => {
  const menus = new WeakMap();
  function enhance(select) {
    if (menus.has(select) || select.multiple || select.size > 1 || select.hidden || select.id === 'bid-pricing-mode') return;
    const wrapper = document.createElement('div'); wrapper.className='metex-select';
    const menu=document.createElement('details'); menu.className='metex-dropdown';
    const trigger=document.createElement('summary');
    const options=document.createElement('div'); options.className='metex-dropdown-options';
    select.before(wrapper); wrapper.append(select,menu); menu.append(trigger,options);
    select.classList.add('metex-native-select');
    select.setAttribute('aria-hidden','true'); select.tabIndex=-1;
    if(select.classList.contains('bm-select--state')) wrapper.classList.add('metex-state-select');
    const label=select.labels?.[0]?.textContent.trim() || select.getAttribute('aria-label') || select.name || select.options[select.selectedIndex]?.textContent || 'Select an option';
    trigger.setAttribute('aria-label',label);
    function sync() {
      wrapper.hidden=select.hidden || select.style.display==='none';
      trigger.textContent=select.selectedOptions[0]?.textContent || 'Choose an option';
      trigger.setAttribute('aria-disabled',String(select.disabled));
      options.replaceChildren();
      for (const option of select.options) {
        const button=document.createElement('button'); button.type='button'; button.textContent=option.textContent;
        button.disabled=select.disabled || option.disabled || option.parentElement.disabled;
        button.classList.toggle('selected',option.selected);
        button.addEventListener('click',()=>{
          select.value=option.value;
          select.dispatchEvent(new Event('input',{bubbles:true}));
          select.dispatchEvent(new Event('change',{bubbles:true}));
          menu.open=false; sync(); trigger.focus();
        });
        options.append(button);
      }
    }
    if (options.showPopover) {
      options.setAttribute('popover','manual');
      menu.addEventListener('toggle',()=>{
        if(!menu.open) { if(options.matches(':popover-open')) options.hidePopover(); return; }
        options.showPopover();
        const r=trigger.getBoundingClientRect();
        const height=Math.min(260,options.scrollHeight);
        options.style.width=r.width+'px'; options.style.left=r.left+'px';
        options.style.top=(innerHeight-r.bottom>height+12 ? r.bottom+6 : Math.max(8,r.top-height-6))+'px';
      });
    }
    menus.set(select,{sync,menu}); sync();
    select.addEventListener('change',sync);
    select.addEventListener('focus',()=>trigger.focus());
    select.addEventListener('invalid',()=>{ trigger.focus(); trigger.setAttribute('aria-invalid','true'); });
    trigger.addEventListener('click',event=>{ if(select.disabled) event.preventDefault(); else sync(); });
    menu.addEventListener('keydown',event=>{
      if(event.key==='Escape') { menu.open=false; trigger.focus(); }
      if(event.key==='ArrowDown' || event.key==='ArrowUp') {
        event.preventDefault(); menu.open=true;
        const buttons=[...options.querySelectorAll('button:not(:disabled)')];
        const index=buttons.indexOf(document.activeElement);
        buttons[(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();
      }
    });
    select.form?.addEventListener('reset',()=>setTimeout(sync,0));
  }
  const scan=()=>document.querySelectorAll('select').forEach(enhance);
  new MutationObserver(records=>{
    for(const record of records) {
      const select=record.target.closest?.('select');
      if(select && menus.has(select)) menus.get(select).sync();
    }
    scan();
  }).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','hidden','style','selected']});
  document.addEventListener('click',event=>document.querySelectorAll('.metex-dropdown[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;}));
  scan();
})();
