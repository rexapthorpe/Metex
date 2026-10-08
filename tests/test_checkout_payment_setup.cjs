const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function checkout(responses) {
  const nodes = new Map();
  const context = vm.createContext({
    console: { log() {}, error() {} },
    window: { stripePublishableKey: 'pk_test_fixture' },
    document: {
      addEventListener() {},
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, { value: '', style: {}, textContent: '' });
        return nodes.get(id);
      },
    },
    Stripe: () => ({}),
    fetch: async () => {
      const next = responses.shift();
      if (next instanceof Error) throw next;
      return { ok: next.status === 200, json: async () => next.body };
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/checkout_page.js'), 'utf8'), context);
  vm.runInContext("_selectedSavedPmId = 'pm_test_saved';", context);
  return { context, nodes, run: code => vm.runInContext(code, context) };
}

test('saved card cannot advance after policy rejection; setup can retry', async () => {
  const c = checkout([
    { status: 503, body: { error_code: 'POLICY_CONFIGURATION_REQUIRED', error: 'Required policy configuration is not approved: ups_coverage_and_claim_policy' } },
    { status: 200, body: { clientSecret: 'test_secret', paymentIntentId: 'pi_test' } },
  ]);
  await c.run('initStripeElements()');
  assert.equal(c.run('validatePaymentForm()'), false);
  assert.match(c.nodes.get('payment-element-error').textContent, /shipping coverage/);
  await c.run('initStripeElements()');
  assert.equal(c.run('validatePaymentForm()'), true);
  assert.equal(c.nodes.get('payment-element-error').style.display, 'none');
});

test('tax failure is explained and blocks review', async () => {
  const c = checkout([{ status: 503, body: { error: 'Tax could not be verified.' } }]);
  await c.run('initStripeElements()');
  assert.equal(c.run('validatePaymentForm()'), false);
  assert.equal(c.nodes.get('payment-element-error').textContent, 'Tax could not be verified.');
});

test('network failure permits another setup attempt', async () => {
  const c = checkout([new Error('Network unavailable'),
    { status: 200, body: { clientSecret: 'test_secret', paymentIntentId: 'pi_test' } }]);
  await c.run('initStripeElements()');
  assert.equal(c.run('validatePaymentForm()'), false);
  await c.run('initStripeElements()');
  assert.equal(c.run('validatePaymentForm()'), true);
});
