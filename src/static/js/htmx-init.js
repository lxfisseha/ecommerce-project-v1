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
    let started = false;
    let resubmitting = false;

    function clearTimers() {
        timers.forEach(clearTimeout);
        timers = [];
    }

    function start() {
        started = true;
        clearTimers();
        bar.style.width = '0%';
        bar.classList.remove('complete');
        bar.classList.add('active');
        // Force reflow so the transition restarts from 0
        void bar.offsetWidth;
        bar.style.width = '30%';
        timers.push(setTimeout(() => { bar.style.width = '60%'; }, 200));
        timers.push(setTimeout(() => { bar.style.width = '85%'; }, 1000));
        timers.push(setTimeout(() => { bar.style.width = '92%'; }, 3000));
    }

    function complete() {
        clearTimers();
        bar.style.width = '100%';
        bar.classList.add('complete');
        timers.push(setTimeout(() => {
            bar.classList.remove('active', 'complete');
            bar.style.width = '0%';
            started = false;
        }, 400));
    }

    // Paint the bar, then run the action. Double rAF guarantees the browser
    // paints the bar before we leave the page.
    function afterPaint(fn) {
        requestAnimationFrame(() => requestAnimationFrame(fn));
    }

    function isSamePage(href) {
        return href === location.pathname + location.search || href === location.href;
    }

    function isLeftClick(e) {
        return e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
    }

    // Regular link clicks -> intercept, show bar, then navigate
    document.addEventListener('click', function (e) {
        const a = e.target.closest('a[href]');
        if (!a || !isLeftClick(e)) return;
        if (a.hasAttribute('hx-get') || a.hasAttribute('hx-post')) return;
        if (a.target === '_blank' || a.hasAttribute('download')) return;
        const href = a.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (isSamePage(href)) return;
        e.preventDefault();
        start();
        afterPaint(() => { window.location.href = a.href; });
    });

    // Plain form submits (Explore, checkout, logout, product forms) -> intercept and submit
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (form.hasAttribute('hx-post') || form.hasAttribute('hx-get')) return;
        if (resubmitting) { resubmitting = false; return; }
        if (!form.checkValidity()) return;
        e.preventDefault();
        start();
        afterPaint(() => {
            resubmitting = true;
            form.requestSubmit();
        });
    });

    // Buttons/elements that navigate via onclick -> best-effort start
    document.addEventListener('click', function (e) {
        const el = e.target.closest('button[onclick], [onclick]');
        if (!el) return;
        if (el.closest('a[href]')) return;
        if (el.hasAttribute('hx-get') || el.hasAttribute('hx-post')) return;
        const onclick = el.getAttribute('onclick') || '';
        if (!onclick.includes('location')) return;
        start();
    });

    // htmx navigation
    document.addEventListener('htmx:beforeRequest', function (e) {
        if (e.detail.verb === 'get') start();
    });
    document.addEventListener('htmx:afterRequest', function () { complete(); });
    document.addEventListener('htmx:loadError', function () { complete(); });

    // Back/forward navigation
    window.addEventListener('popstate', start);

    // Fallback for JS-initiated navigation not caught above
    window.addEventListener('beforeunload', function () {
        if (!started) start();
    });

    // Page load
    window.addEventListener('load', complete);
})();
