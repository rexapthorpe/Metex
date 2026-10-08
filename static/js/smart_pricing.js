/* Optional dollar-premium management; pricing requests remain server-owned. */
(function (root) {
    const descriptions = {
        fast: ['Competitive price for a quicker sale', ''],
        balanced: ['Balance price and selling speed', ''],
        big: ['Aim higher; allow more time to sell', '']
    };
    if (typeof module !== 'undefined') module.exports = { descriptions };
    if (!root.document) return;
    document.addEventListener('DOMContentLoaded', () => {
        const panel = document.getElementById('smart-pricing-panel');
        if (!panel) return;
        const manual = document.getElementById('manual-pricing-controls');
        const flag = document.getElementById('smart-pricing-enabled');
        const minimum = document.getElementById('smart-minimum');
        const enter = document.getElementById('smart-pricing-enter');
        const status = document.getElementById('smart-pricing-status');
        let previousMode = 'static';
        let oldFloor = '';
        let oldPremium = '';
        let switching = false;
        let requestVersion = 0;
        let timer;
        let quote = null;
        const form = document.getElementById('sellForm');
        const starting = document.getElementById('smart-starting');
        const token = document.getElementById('smart-preview-token');
        const acknowledged = document.getElementById('smart-warning-acknowledged');
        const warning = document.getElementById('smart-warning');
        const use = document.getElementById('smart-pricing-use');
        const preview = document.getElementById('smart-preview');
        const availability = document.getElementById('smart-availability');
        const unavailableCopy = 'A fresh spot quote could not be retrieved. Try again, or choose a manual Fixed Price.';
        const money = cents => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(cents / 100);
        const label = value => ({fast:'Sell Fast',balanced:'Balanced',big:'Sell Big'})[value];
        function invalidate() {
            requestVersion++;
            quote = null; root.smartCurrentPreview = null; token.value = ''; flag.value = '0'; use.disabled = true;
            const summary=document.getElementById('summaryPrice');
            if (summary && !panel.hidden) summary.textContent='Calculating…';
        }
        function payload() {
            const data = new FormData(form);
            // Preview is metadata-only: photos remain in the existing publish flow.
            for (const [key,value] of [...data.entries()]) if (typeof value !== 'string') data.delete(key);
            if (root.currentMode === 'set') {
                data.set('is_set','1');
                data.set('set_items_json', JSON.stringify(root.setItems || []));
            }
            return data;
        }
        function showWarning() {
            invalidate(); warning.hidden = false;
            document.getElementById('smart-warning-continue').focus();
        }
        async function refresh() {
            invalidate();
            if (root.currentMode !== 'set' && ['metal','product_line','product_type','weight','purity','mint','year','finish','series_variant'].some(id => { const field=document.getElementById(id); return field && !field.value.trim(); })) {
                warning.hidden=true; preview.hidden=true; availability.hidden=true;
                status.textContent='Complete the item specifications above to see your price.'; return;
            }
            const version = requestVersion;
            preview.hidden = true; availability.hidden = true;
            status.textContent = 'Loading the current pricing preview…';
            try {
                const response = await fetch('/sell/smart-pricing-preview', {method:'POST',body:payload()});
                const data = await response.json();
                if (version !== requestVersion || panel.hidden) return;
                if (!response.ok || !data.success) {
                    availability.hidden=false;
                    document.getElementById('smart-availability-title').textContent=data.code === 'SMART_SPOT_UNAVAILABLE' ? 'Current metal pricing is temporarily unavailable' : 'Pricing preview is temporarily unavailable';
                    document.getElementById('smart-availability-copy').textContent=data.code === 'SMART_SPOT_UNAVAILABLE' ? unavailableCopy : 'Please check your product details and try again shortly, or use manual pricing.';
                    status.textContent=''; return;
                }
                if (data.warning_required && acknowledged.value !== '1') { showWarning(); status.textContent = ''; return; }
                const seeded = !!data.seeded;
                const row = document.getElementById('smart-starting-row');
                row.hidden = true; starting.required = false;
                document.getElementById('smart-market-message').textContent = seeded
                    ? 'Not enough comparable market data. METEX does not currently have enough comparable sales/listing data to confidently recommend a starting premium for this item.'
                    : `Pricing confidence: ${data.confidence_label === 'high' ? 'High' : data.confidence_label === 'medium' ? 'Medium' : 'Low — pricing data is limited'}.`;
                if (data.needs_starting) {
                    document.getElementById('smart-market-message').textContent='';
                    availability.hidden=false;
                    document.getElementById('smart-availability-title').textContent='Not enough comparable market data';
                    document.getElementById('smart-availability-copy').textContent='METEX does not yet have enough comparable sales or listings to recommend a reliable price for this item. Return to manual pricing to choose Fixed Price or Premium to Spot.';
                    status.textContent=''; return;
                }
                const amounts=['initial_premium_cents','metal_value_cents','minimum_cents','initial_price_cents','estimated_net_cents','estimated_total_net_cents','seller_fee_cents',...(seeded?[]:['fair_premium_cents','range_lower_cents','range_upper_cents'])];
                if (!data.token || amounts.some(key => !Number.isSafeInteger(data[key])) || !['fast','balanced','big'].includes(data.strategy)) throw new Error('invalid preview');
                quote = data; root.smartCurrentPreview = data; token.value = data.token;
                preview.hidden = false;
                document.getElementById('smart-preview-strategy').textContent = label(data.strategy);
                document.getElementById('smart-preview-premium').textContent = `+${money(data.initial_premium_cents)} over spot`;
                document.getElementById('smart-premium-label').textContent = seeded ? 'Starting premium selected by you' : 'Initial Premium';
                document.getElementById('smart-preview-metal').textContent = money(data.metal_value_cents);
                document.getElementById('smart-preview-minimum').textContent = `+${money(data.minimum_cents)} over spot`;
                document.getElementById('smart-preview-price').textContent = money(data.initial_price_cents);
                document.getElementById('smart-preview-net').textContent = money(data.estimated_net_cents);
                document.getElementById('smart-preview-net-note').textContent = `Per ${root.currentMode === 'set' ? 'set' : 'item'}, after METEX’s 5% fee (${money(data.seller_fee_cents)}); shipping costs excluded.`;
                const totalNet=document.getElementById('smart-preview-total-net');
                totalNet.hidden=data.quantity<=1;
                totalNet.textContent=data.quantity>1 ? `If all ${data.quantity} sell at this price: ${money(data.estimated_total_net_cents)} after METEX’s fee, before shipping.` : '';
                document.getElementById('smart-fair-row').hidden = seeded;
                document.getElementById('smart-range-row').hidden = seeded;
                if (!seeded) {
                    document.getElementById('smart-preview-fair').textContent = `+${money(data.fair_premium_cents)}`;
                    document.getElementById('smart-preview-range').textContent = `+${money(data.range_lower_cents)} – +${money(data.range_upper_cents)}`;
                }
                const rangePrice=document.getElementById('smart-market-range-price');
                const midpoint=document.getElementById('smart-market-midpoint');
                if (rangePrice) rangePrice.textContent=seeded ? 'Unavailable' : `${money(data.metal_value_cents+data.range_lower_cents)} – ${money(data.metal_value_cents+data.range_upper_cents)}`;
                if (midpoint) midpoint.textContent=seeded ? 'Unavailable' : money(data.metal_value_cents+data.fair_premium_cents);
                use.disabled=false;
                flag.value='1';
                const premium=document.getElementById('spot_premium');
                premium.value=(data.initial_premium_cents/100).toFixed(2);
                premium.dispatchEvent(new Event('input',{bubbles:true}));
                status.textContent='';
            } catch (error) {
                if (version === requestVersion) {
                    availability.hidden=false;
                    document.getElementById('smart-availability-title').textContent='Pricing preview is temporarily unavailable';
                    document.getElementById('smart-availability-copy').textContent='Please try again shortly or use manual pricing.';
                    status.textContent='';
                }
            }
        }
        function schedule() {
            invalidate(); clearTimeout(timer);
            if (!panel.hidden) { preview.hidden = true; status.textContent = 'Updating pricing preview…'; timer = setTimeout(refresh,180); }
        }
        const describe = () => {
            const strategy = document.querySelector('[name="smart_pricing_strategy"]:checked').value;
            document.getElementById('smart-description-title').textContent = descriptions[strategy][0];
            document.getElementById('smart-description-copy').textContent = descriptions[strategy][1];
            const selector=document.getElementById('smart-strategies');
            if (selector) selector.setAttribute('data-strategy',strategy);
        };
        async function switchMode(enabled, focus = true) {
            if (switching) return;
            switching = true;
            const outgoing = enabled ? manual : panel;
            // The manual wrapper uses display:contents; animate its visible child controls.
            const animated = [outgoing];
            const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (motion) await Promise.all(animated.map(el => el.animate([{opacity:1,transform:'translateX(0)'},{opacity:0,transform:'translateX(-100%)'}], {duration:140}).finished.catch(() => {})));
            outgoing.hidden = true;
            (enabled ? panel : manual).hidden = false;
            enter.parentElement.hidden = enabled;
            if (enabled) {
                previousMode = document.querySelector('[name="pricing_mode"]:checked').value;
                oldFloor = document.getElementById('floor_price').value;
                oldPremium = document.getElementById('spot_premium').value;
                document.getElementById('pricing_mode_premium').checked = true;
                document.getElementById('pricing_mode_premium').dispatchEvent(new Event('change', {bubbles:true}));
                document.getElementById('floor_price').value = '0.01';
                ['spot_premium','floor_price','price_per_coin'].forEach(id => document.getElementById(id).required = false);
                flag.value = '0'; // Only a valid signed preview enables Smart Pricing.
                minimum.required = false;
                if (!minimum.value) minimum.value = '0.00';
                describe();
            } else {
                invalidate(); warning.hidden = true; acknowledged.value='0'; starting.required = false; minimum.required = false; status.textContent = ''; preview.hidden = true;
                document.getElementById('floor_price').value = oldFloor;
                document.getElementById('spot_premium').value = oldPremium;
                const radio = document.getElementById(previousMode === 'static' ? 'pricing_mode_static' : 'pricing_mode_premium');
                radio.checked = true; radio.dispatchEvent(new Event('change', {bubbles:true}));
            }
            if (motion) {
                const incoming = [enabled ? panel : manual];
                await Promise.all(incoming.map(el => el.animate([{opacity:0,transform:'translateX(100%)'},{opacity:1,transform:'translateX(0)'}],{duration:200}).finished.catch(() => {})));
            }
            switching = false;
            if (focus) (enabled ? document.querySelector('[name="smart_pricing_strategy"]:checked') : enter).focus();
            if (enabled) await refresh();
        }
        enter.addEventListener('click', () => {
            if (root.currentMode === 'set' || root.currentMode === 'isolated') showWarning();
            else return switchMode(true);
        });
        document.getElementById('smart-warning-continue').addEventListener('click', async () => {
            acknowledged.value='1'; warning.hidden=true;
            if (panel.hidden) await switchMode(true); else await refresh();
        });
        document.getElementById('smart-warning-cancel').addEventListener('click', async () => {
            warning.hidden=true; acknowledged.value='0';
            if (!panel.hidden) await switchMode(false); else { invalidate(); enter.focus(); }
        });
        document.getElementById('smart-preview-refresh').addEventListener('click', refresh);
        document.getElementById('smart-availability-retry').addEventListener('click', refresh);
        document.getElementById('smart-availability-manual').addEventListener('click', () => switchMode(false));
        document.addEventListener('metex:smart-preview-changed', async () => {
            if (panel.hidden) return;
            await refresh();
            if (quote) status.textContent='Price updated. Review the new price before publishing.';
        });
        document.getElementById('smart-pricing-exit').addEventListener('click', () => switchMode(false));
        const pricingBox=document.getElementById('pricing-box');
        let swipeStart=null;
        if (pricingBox) {
            pricingBox.addEventListener('pointerdown', event => {
                swipeStart=event.pointerType==='touch' && !event.target.closest('input,button,label,textarea,select,a')
                    ? {x:event.clientX,y:event.clientY} : null;
            });
            pricingBox.addEventListener('pointercancel', () => { swipeStart=null; });
            pricingBox.addEventListener('pointerup', event => {
                if (!swipeStart) return;
                const dx=event.clientX-swipeStart.x,dy=event.clientY-swipeStart.y; swipeStart=null;
                if (Math.abs(dx)<70 || Math.abs(dx)<Math.abs(dy)*2 || switching) return;
                if (dx>0 && (!panel.hidden || !warning.hidden)) { warning.hidden=true; switchMode(false); }
                else if (dx<0 && panel.hidden) enter.click();
            });
        }
        document.querySelectorAll('[name="smart_pricing_strategy"]').forEach(input => input.addEventListener('change', () => {describe(); return refresh();}));
        minimum.addEventListener('input', schedule);
        starting.addEventListener('input', schedule);
        form.addEventListener('input', event => {
            if (!panel.hidden && !panel.contains(event.target) && !['spot_premium','floor_price','pricing_mode_premium','pricing_mode_static'].includes(event.target?.id)) { acknowledged.value='0'; schedule(); }
        });
        form.addEventListener('change', event => {
            if (!panel.hidden && !panel.contains(event.target) && !['spot_premium','floor_price','pricing_mode_premium','pricing_mode_static'].includes(event.target?.id)) { acknowledged.value='0'; schedule(); }
        });
        document.addEventListener('metex:set-items-changed', () => {
            if (!panel.hidden) { acknowledged.value='0'; schedule(); }
        });
        const infoToggle=document.getElementById('smart-info-toggle');
        if (infoToggle) infoToggle.addEventListener('click', () => {
            const info=document.getElementById('smart-info');
            const open=infoToggle.getAttribute('aria-expanded')!=='true';
            infoToggle.setAttribute('aria-expanded',String(open));
            info.setAttribute('aria-hidden',String(!open));
            info.setAttribute('data-open',String(open));
            info.firstElementChild.inert=!open;
        });
        // Block publishing an unconfirmed exploratory mode; no hidden manual fallback.
        document.getElementById('sellForm').addEventListener('submit', event => {
            if (!panel.hidden && flag.value !== '1') { event.preventDefault(); event.stopImmediatePropagation(); status.textContent = 'Wait for a valid Smart Pricing quote, or price manually.'; }
        }, true);
        const smart = root.sellPrefillData?.smart_pricing;
        if (smart?.enabled) {
            minimum.value = (smart.minimum_cents / 100).toFixed(2);
            document.querySelector(`[name="smart_pricing_strategy"][value="${smart.strategy}"]`).checked = true;
            starting.value = ''; // New activations require market evidence; no seller premium entry.
            if (root.sellPrefillData.isolated_type) showWarning(); else switchMode(true);
        } else if (!root.sellEditMode && document.getElementById('pricing-box')) {
            switchMode(true, false);
        }
    });
})(typeof window === 'undefined' ? globalThis : window);
