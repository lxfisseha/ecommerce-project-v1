document.body.addEventListener('htmx:configRequest', (event) => {
    event.detail.headers['X-CSRF-Token'] = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
});

document.body.addEventListener('htmx:beforeOnLoad', function (evt) {
    if (evt.detail.xhr.status >= 400) {
        evt.detail.shouldSwap = true;
        evt.detail.target = htmx.find("#auth-container") || evt.detail.target;
    }
});

// --- Progress bar ---
(function () {
    const bar = document.getElementById('progress-bar');
    if (!bar) return;
    let timers = [];

    function clearTimers() {
        timers.forEach(clearTimeout);
        timers = [];
    }

    function start() {
        clearTimers();
        bar.style.width = '0%';
        bar.classList.remove('complete');
        bar.classList.add('active');
        // Force reflow so the transition restarts from 0
        void bar.offsetWidth;
        timers.push(setTimeout(() => { bar.style.width = '60%'; }, 10));
        timers.push(setTimeout(() => { bar.style.width = '85%'; }, 1500));
        timers.push(setTimeout(() => { bar.style.width = '92%'; }, 4000));
    }

    function complete() {
        clearTimers();
        bar.style.width = '100%';
        bar.classList.add('complete');
        timers.push(setTimeout(() => {
            bar.classList.remove('active', 'complete');
            bar.style.width = '0%';
        }, 400));
    }

    // Regular link clicks
    document.addEventListener('click', function (e) {
        const link = e.target.closest('a[href]');
        if (!link) return;
        // Skip htmx-handled, anchor-only, blank-target, download links
        if (link.hasAttribute('hx-get') || link.hasAttribute('hx-post')) return;
        if (link.target === '_blank' || link.hasAttribute('download')) return;
        const href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        start();
    });

    // htmx navigation
    document.addEventListener('htmx:beforeRequest', function (e) {
        if (e.detail.verb === 'get') start();
    });
    document.addEventListener('htmx:afterRequest', function () { complete(); });
    document.addEventListener('htmx:loadError', function () { complete(); });

    // Page load
    window.addEventListener('load', complete);
})();
