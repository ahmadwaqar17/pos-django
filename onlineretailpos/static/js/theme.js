/* ============================================================
   Modern POS theme — global interaction JS
   (spinner overlay, page-fade navigation, button loading)
   ============================================================ */
(function () {
    'use strict';

    var MIN_SPINNER_MS = 450;      // keep the overlay up at least this long (avoid flicker)

    /* ---- pure decision logic (unit-tested in theme.test.js) ----
       The overlay is only cleared by the `pageshow` event, which fires on a
       real document load. Intercepting a click that changes the page in place
       (in-page anchor, Bootstrap tab/collapse/dropdown/modal) would therefore
       leave the spinner on screen forever — those are never intercepted.
       Only clicks that will actually load a document qualify. */
    var IN_PAGE_ANCHOR = /^#/;
    var ABSOLUTE_URL = /^(https?:)?\/\//i;
    var OTHER_SCHEME = /^[a-z][a-z0-9+.\-]*:/i;   // javascript:, data:, mailto:, tel: …

    /* Which click targets get audible feedback? Every interactive element:
       buttons, links, Bootstrap toggles (tabs/dropdowns/modals/collapse — one
       click means one sound, the transition is only visual), option-style list
       items, and inline-handler elements (register grid cards). Opt out per
       element with data-no-click-sound. */
    function shouldPlayClickSound(target) {
        if (!target || !target.closest) return false;
        if (target.closest('[data-no-click-sound]')) return false;
        return !!target.closest(
            'button, a[href], .btn, [role="button"], [onclick], [data-toggle], .list-group-item-action'
        );
    }

    function shouldInterceptLink(href, opts) {
        opts = opts || {};
        if (!href || IN_PAGE_ANCHOR.test(href)) return false;   // same-document anchor
        if (opts.toggle) return false;                          // Bootstrap JS hook
        if (opts.target === '_blank' || opts.download) return false;
        return ABSOLUTE_URL.test(href) || !OTHER_SCHEME.test(href);
    }

    if (typeof module === 'object' && module.exports) {
        module.exports = { shouldInterceptLink: shouldInterceptLink, shouldPlayClickSound: shouldPlayClickSound };
        return;                         // Node (unit tests): no DOM wiring below
    }

    var overlay = null;
    var overlayText = null;
    var shownAt = 0;

    function buildOverlay() {
        overlay = document.getElementById('pos-loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'pos-loading-overlay';
            overlay.setAttribute('role', 'status');
            overlay.setAttribute('aria-live', 'polite');
            overlay.innerHTML =
                '<div class="pos-spinner"></div>' +
                '<div class="pos-overlay-text"></div>';
            document.body.appendChild(overlay);
        }
        overlayText = overlay.querySelector('.pos-overlay-text');
    }

    function showOverlay(text) {
        buildOverlay();
        overlayText.textContent = text || 'Loading…';
        shownAt = Date.now();
        overlay.classList.add('pos-visible');
    }

    function hideOverlaySoon() {
        if (!overlay) return;
        var elapsed = Date.now() - shownAt;
        var wait = Math.max(0, MIN_SPINNER_MS - elapsed);
        setTimeout(function () {
            overlay.classList.remove('pos-visible');
            restoreButtons();
        }, wait);
    }

    /* ---- button loading states ---- */
    function setBtnLoading(btn) {
        if (!btn || btn.classList.contains('pos-btn-loading')) return;
        btn.classList.add('pos-btn-loading');
    }

    function restoreButtons() {
        document.querySelectorAll('.pos-btn-loading').forEach(function (b) {
            b.classList.remove('pos-btn-loading');
        });
    }

    /* ---- navigation helper (used by templates' onclick / inline handlers) ----
       Independent guard: inline handlers may run alongside other events,
       so posGo manages its own double-fire protection. */
    window.posGo = function (url, text) {
        if (document.documentElement.getAttribute('data-pos-go') === '1') return false;
        document.documentElement.setAttribute('data-pos-go', '1');
        setTimeout(function () { document.documentElement.removeAttribute('data-pos-go'); }, 4000);
        showOverlay(text);
        if (window.location.href === url || window.location.pathname === url) {
            window.location.reload();
        } else {
            window.location.href = url;
        }
        return false;
    };

    /* ---- click sound (button / option press feedback) ----
       Browsers block audio until the user has interacted with the page; a click
       IS that interaction, so play() inside the handler works. The Audio
       element is created — and the file fetched — the moment the page loads.
       Creating it lazily on first click loses the race against posGo's instant
       navigation (the pending fetch is killed on unload), which is why the
       sound only ever played on the slow login POST. */
    function getClickAudio() {
        if (window.__posClickAudio) return window.__posClickAudio;
        var src = document.documentElement.getAttribute('data-click-sound-src');
        if (!src) return null;                  // feature disabled / no src configured
        try {
            var el = new Audio(src);
            el.preload = 'auto';
            el.volume = 0.85;
            el.load();                          // start buffering immediately
            window.__posClickAudio = el;
            return el;
        } catch (err) {
            return null;
        }
    }

    function playClickSound(target) {
        if (!shouldPlayClickSound(target)) return false;
        var el = getClickAudio();
        if (!el) return false;
        try {
            el.currentTime = 0;                 // restart if still ringing
            var p = el.play();
            if (p && p.catch) p.catch(function () { /* autoplay policy — ignore */ });
        } catch (err) { /* ignore */ }
        return true;
    }

    /* Fire on pointerdown (mouse/touch) for a head start over fast navigations;
       click covers keyboard activation. The click after a pointerdown is the
       same physical press — the timestamp window skips it, but every new press
       sounds again, however fast the operator works. */
    var pressSoundAt = 0;

    document.addEventListener('pointerdown', function (e) {
        if (e.button !== 0) return;
        if (playClickSound(e.target)) pressSoundAt = Date.now();
    }, true);

    document.addEventListener('click', function (e) {
        if (Date.now() - pressSoundAt < 500) return;   // same press — already sounded
        playClickSound(e.target);
    }, true);

    getClickAudio();   // warm the cache so the wav is buffered before the first click

    /* ---- link interception → overlay + fade ---- */
    document.addEventListener('click', function (e) {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        var a = e.target.closest('a[href]');
        if (!a) return;
        if (!shouldInterceptLink(a.getAttribute('href'), {
                toggle: a.hasAttribute('data-toggle'),
                target: a.getAttribute('target'),
                download: a.hasAttribute('download'),
            })) return;
        if (document.documentElement.getAttribute('data-pos-go') === '1') { e.preventDefault(); return; }
        e.preventDefault();
        showOverlay(a.getAttribute('data-loading-text'));
        document.documentElement.setAttribute('data-pos-go', '1');
        setTimeout(function () { document.documentElement.removeAttribute('data-pos-go'); }, 4000);
        window.location.href = a.getAttribute('href');
    }, true);

    /* ---- form submits → overlay + button spinner ----
       Forms with an inline onsubmit handler manage their own flow
       (they navigate via posGo or return false) — leave those alone. */
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || form.hasAttribute('data-no-loader')) return;
        if (form.hasAttribute('onsubmit')) return;
        if (document.documentElement.getAttribute('data-pos-go') === '1') { e.preventDefault(); return; }
        document.documentElement.setAttribute('data-pos-go', '1');
        setTimeout(function () { document.documentElement.removeAttribute('data-pos-go'); }, 4000);
        var submitter = e.submitter;
        var btn = submitter && submitter.tagName === 'BUTTON' ? submitter : form.querySelector('[type="submit"]');
        if (btn) setBtnLoading(btn);
        showOverlay(form.getAttribute('data-loading-text') || 'Working…');
    }, true);

    /* ---- safety net: a same-document change (hash / in-page tab) fires no
       page load, so nothing else would ever take the overlay back down. ---- */
    window.addEventListener('hashchange', function () {
        document.documentElement.removeAttribute('data-pos-go');
        hideOverlaySoon();
        restoreButtons();
    });

    /* ---- clear overlay when a new page lands (incl. back/forward bfcache) ---- */
    window.addEventListener('pageshow', function () {
        document.documentElement.removeAttribute('data-pos-go');
        hideOverlaySoon();
        restoreButtons();
        window.__posClickAudio = null;          // fresh document → re-read the src
        getClickAudio();                        // …and warm it right away
    });

    /* ---- Django messages: auto-dismiss ---- */
    var alerts = document.querySelectorAll('.pos-auto-alert');
    alerts.forEach(function (el) {
        setTimeout(function () {
            el.style.transition = 'opacity .4s ease, transform .4s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateY(-6px)';
            setTimeout(function () { el.remove(); }, 420);
        }, 4500);
    });
})();
