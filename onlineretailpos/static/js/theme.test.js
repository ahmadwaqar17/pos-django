/* Executable contract for theme.js's link-interception guard.
   Run: node --test onlineretailpos/static/js/theme.test.js

   The overlay is dismissed by `pageshow`, which only fires on a real document
   load — so a click that changes the page in place must never be intercepted,
   or the spinner stays on screen forever (the reported "All Products Grid"
   tab hang). Every case below is a link shape that exists in this app. */
const test = require('node:test');
const assert = require('node:assert');

const { shouldInterceptLink, shouldPlayClickSound } = require('./theme.js');

const CASES = [
    // href,                 attrs,                    expected, why
    ['/register/',           {},                        true,  'relative path'],
    ['/cart/add/1001/1/',    {},                        true,  'relative path with segments'],
    ['https://example.com/', {},                        true,  'absolute http(s) URL'],
    ['//cdn.example.com/x',  {},                        true,  'protocol-relative URL'],

    ['#product-grid-pane',   { toggle: 'tab' },         false, 'Bootstrap tab (the tab-hang bug)'],
    ['#page-top',            {},                        false, 'scroll-to-top anchor'],
    ['#',                    {},                        false, 'bare hash'],
    ['',                     {},                        false, 'no href'],

    ['javascript:void(0)',   {},                        false, 'javascript: scheme'],
    ['mailto:store@shop.pk', {},                        false, 'mailto: scheme'],
    ['data:text/plain,hi',   {},                        false, 'data: scheme'],

    ['/register/',           { target: '_blank' },      false, 'opens a new tab'],
    ['/export.csv',          { download: true },        false, 'file download'],
];

test('only real document navigations are intercepted', () => {
    for (const [href, attrs, expected, why] of CASES) {
        assert.strictEqual(shouldInterceptLink(href, attrs), expected, `${href} — ${why}`);
    }
});

test('a missing attributes object does not intercept blindly', () => {
    assert.strictEqual(shouldInterceptLink('/register/'), true);
    assert.strictEqual(shouldInterceptLink(), false);
});

/* Minimal DOM stand-in: closest() walks the (mock) ancestor chain, where each
   entry is a selector token that node satisfies (innermost first). */
function fakeEl(chain) {
    return {
        closest(sel) {
            const tokens = sel.split(',').map((s) => s.trim());
            return chain.some((tok) => tokens.includes(tok)) ? sel : null;
        },
    };
}

test('clicks on buttons, links and option items play the sound', () => {
    assert.strictEqual(shouldPlayClickSound(fakeEl(['button'])), true, 'plain button');
    assert.strictEqual(shouldPlayClickSound(fakeEl(['a[href]', 'button'])), true, 'link');
    assert.strictEqual(shouldPlayClickSound(fakeEl(['.btn'])), true, 'bootstrap .btn');
    assert.strictEqual(
        shouldPlayClickSound(fakeEl(['.list-group-item-action', 'button'])),
        true,
        'option-style list item (register options)'
    );
    assert.strictEqual(shouldPlayClickSound(fakeEl(['[role="button"]'])), true, 'ARIA button');
    assert.strictEqual(
        shouldPlayClickSound(fakeEl(['[data-toggle="tab"]', 'a[href]'])),
        true,
        'Bootstrap tab/dropdown toggles click too (transition is only visual)'
    );
    assert.strictEqual(
        shouldPlayClickSound(fakeEl(['[onclick]', '.pos-grid-card'])),
        true,
        'inline-handler element (register grid card)'
    );
});

test('non-interactive and opted-out targets stay silent', () => {
    assert.strictEqual(shouldPlayClickSound(fakeEl(['p'])), false, 'paragraph text');
    assert.strictEqual(shouldPlayClickSound(fakeEl(['div'])), false, 'plain div');
    assert.strictEqual(shouldPlayClickSound(null), false, 'no target');
    assert.strictEqual(
        shouldPlayClickSound(fakeEl(['[data-no-click-sound]', 'button'])),
        false,
        'explicit opt-out attribute wins'
    );
});
