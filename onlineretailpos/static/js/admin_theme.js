/* Admin colour theme: Light / Dark / System.
   The choice is saved per browser; "System" follows the OS setting live.
   An inline script in templates/admin/base_site.html applies the theme
   before first paint; this file adds the switcher to the top bar. */
(function () {
    var KEY = 'admin-theme';
    var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    var CHOICES = [
        { value: 'light', label: 'Light', icon: 'fa-sun' },
        { value: 'dark', label: 'Dark', icon: 'fa-moon' },
        { value: 'system', label: 'System', icon: 'fa-desktop' },
    ];

    function getPref() {
        try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; }
    }
    function resolve(pref) {
        if (pref === 'system') return media && media.matches ? 'dark' : 'light';
        return pref;
    }
    function apply(pref) {
        document.documentElement.setAttribute('data-theme', resolve(pref));
        document.documentElement.setAttribute('data-theme-pref', pref);
        updateMenu(pref);
    }
    function setPref(pref) {
        try { localStorage.setItem(KEY, pref); } catch (e) { /* private mode: apply for this page only */ }
        apply(pref);
    }

    var toggleIcon = null;
    function updateMenu(pref) {
        if (!toggleIcon) return;
        var current = CHOICES.filter(function (c) { return c.value === pref; })[0] || CHOICES[2];
        toggleIcon.className = 'fas ' + current.icon;
        document.querySelectorAll('.theme-switch [data-theme-choice]').forEach(function (el) {
            el.classList.toggle('active-choice', el.getAttribute('data-theme-choice') === pref);
        });
    }

    function buildSwitcher() {
        var nav = document.querySelector('.main-header .navbar-nav.ml-auto');
        if (!nav || nav.querySelector('.theme-switch')) return;
        var li = document.createElement('li');
        li.className = 'nav-item dropdown theme-switch';
        li.innerHTML =
            '<a class="nav-link" data-toggle="dropdown" href="#" title="Theme" aria-label="Change theme">' +
            '<i class="fas fa-desktop"></i></a>' +
            '<div class="dropdown-menu dropdown-menu-right">' +
            '<span class="dropdown-header">Theme</span>' +
            CHOICES.map(function (c) {
                return '<a href="#" class="dropdown-item" data-theme-choice="' + c.value + '">' +
                    '<i class="fas ' + c.icon + ' fa-fw"></i> ' + c.label + '<i class="fas fa-check"></i></a>';
            }).join('') +
            '</div>';
        nav.insertBefore(li, nav.firstChild);
        toggleIcon = li.querySelector('.nav-link i');
        li.addEventListener('click', function (e) {
            var item = e.target.closest('[data-theme-choice]');
            if (!item) return;
            e.preventDefault();
            setPref(item.getAttribute('data-theme-choice'));
        });
    }

    if (media) {
        var onChange = function () { if (getPref() === 'system') apply('system'); };
        media.addEventListener ? media.addEventListener('change', onChange) : media.addListener(onChange);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { buildSwitcher(); apply(getPref()); });
    } else {
        buildSwitcher(); apply(getPref());
    }
})();
