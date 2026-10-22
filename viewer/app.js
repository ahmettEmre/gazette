/* Gazette reader. No server: data is loaded as data/*.js scripts, so it works from file://. */
(() => {
  'use strict';

  // Only what the page needs before the first edition exists; everything else comes from data/site.js.
  const FALLBACK = {
    empty_title: 'No editions yet',
    empty_body: 'Open Claude Code in this folder and type /gazette-setup, then /gazette.',
    error_title: 'Something went wrong',
    error_edition: 'Could not load the edition file: {file}',
    hype: ['', '', '', '', '', ''],
  };
  const TIERS = ['official', 'press', 'community'];
  const TOP = 'top';

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const store = {
    get(k, d) { try { const v = localStorage.getItem('gazette.' + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('gazette.' + k, JSON.stringify(v)); } catch (e) { /* private window */ } },
  };

  const S = {
    site: { labels: {}, sections: [], lang: 'en', locale: 'en', brand: 'Gazette' },
    index: null, editions: {}, current: null, view: 'edition', pending: null,
    tiers: new Set(TIERS), unread: false, q: '',
    read: store.get('read', {}), saved: store.get('saved', {}), focus: -1,
  };

  // ---------------------------------------------------------------- helpers
  const t = (key, vars) => {
    const s = S.site.labels[key] ?? FALLBACK[key] ?? key;
    return vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : s;
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '#');
  function rich(s) {
    // Plain text + `code` + **bold**; a blank line separates paragraphs.
    let h = esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    if (S.q) h = highlight(h, S.q);
    return h.split(/\n{2,}/).map((p) => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
  }
  function highlight(html, q) {
    const rx = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return html.split(/(<[^>]+>)/).map((part) => (part.startsWith('<') ? part : part.replace(rx, '<mark>$1</mark>'))).join('');
  }
  const plain = (s) => (S.q ? highlight(esc(s), S.q) : esc(s));
  // One-line fields: `code` and **bold**, no paragraphs.
  const inline = (s) => {
    const h = esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    return S.q ? highlight(h, S.q) : h;
  };
  const lower = (s) => s.toLocaleLowerCase(S.site.lang);

  const fmtDate = (iso, opts) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleString(S.site.locale, opts); };
  const longDate = (iso) => fmtDate(iso, { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  const shortDate = (iso) => fmtDate(iso, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  let rtf;
  function ago(iso) {
    const d = new Date(iso); if (isNaN(d)) return '';
    rtf = rtf || new Intl.RelativeTimeFormat(S.site.lang, { numeric: 'auto' });
    const m = Math.round((d - Date.now()) / 60000);
    if (Math.abs(m) < 60) return rtf.format(m, 'minute');
    const h = Math.round(m / 60); if (Math.abs(h) < 36) return rtf.format(h, 'hour');
    const dd = Math.round(h / 24); if (Math.abs(dd) < 14) return rtf.format(dd, 'day');
    return fmtDate(iso, { day: 'numeric', month: 'short', year: 'numeric' });
  }
  function daysLeft(iso) {
    const d = new Date(iso); if (isNaN(d)) return null;
    const end = new Date(d); end.setHours(23, 59, 59, 999);
    return Math.ceil((end - Date.now()) / 86400000) - 1;
  }

  let toastTimer;
  function toast(msg) {
    const el = $('#toast'); el.textContent = msg; el.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
      ta.remove(); return ok;
    }
  }

  // ---------------------------------------------------------------- data loading
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `${src}?v=${Date.now()}`; s.onload = () => { s.remove(); resolve(); };
      s.onerror = () => { s.remove(); reject(new Error(src)); };
      document.head.appendChild(s);
    });
  }
  window.__gazetteSite = (site) => { S.site = { ...S.site, ...site }; };
  window.__gazetteIndex = (idx) => { S.index = idx; };
  window.__gazetteEdition = (ed) => { S.editions[ed.id] = ed; };

  function applyLabels() {
    document.documentElement.lang = S.site.lang;
    document.title = S.site.brand;
    $('#brandName').textContent = S.site.brand;
    $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    $$('[data-i18n-html]').forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    $$('[data-i18n-label]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nLabel)); });
    $$('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); el.setAttribute('aria-label', el.placeholder); });
  }
  const sectionsOf = (ed) => (ed.sections && ed.sections.length ? ed.sections : S.site.sections);

  async function openEdition(id, itemId) {
    S.view = 'edition'; S.pending = id;
    if (!S.editions[id]) {
      try { await loadScript(`data/editions/${id}.js`); } catch (e) { renderError(t('error_edition', { file: `data/editions/${id}.js` })); return; }
    }
    if (S.pending !== id) return;
    S.current = id; S.focus = -1;
    history.replaceState(null, '', `#${id}${itemId ? '/' + itemId : ''}`);
    render();
    if (itemId) {
      const el = document.getElementById(`i-${itemId}`);
      if (el) { el.classList.add('is-open'); el.scrollIntoView({ block: 'start' }); setFocus(cards().indexOf(el), false); }
    } else { window.scrollTo(0, 0); }
  }

  // ---------------------------------------------------------------- filter
  function matches(it) {
    if (!S.tiers.has(it.tier)) return false;
    if (S.unread && S.read[it.uid]) return false;
    if (S.q) {
      const hay = [it.title, it.original_title, it.what, it.why_you, it.take, ...(it.tags || []),
        ...(it.sources || []).map((s) => s.name), ...(it.terms || []).map((x) => x.term)].join(' ');
      if (!lower(hay).includes(lower(S.q))) return false;
    }
    return true;
  }

  // ---------------------------------------------------------------- drawing
  function card(it) {
    const read = !!S.read[it.uid], saved = !!S.saved[it.uid], breaking = it.section === TOP;
    const imp = [1, 2, 3, 4, 5].map((n) => `<i class="${n <= it.importance ? 'on' : ''}"></i>`).join('');
    const hype = [1, 2, 3, 4, 5].map((n) => `<i class="${n <= it.hype ? 'on' : ''}"></i>`).join('');
    const hypeName = (t('hype') || [])[it.hype] || '';
    const names = [...new Set((it.sources || []).map((s) => s.name))].join(', ');
    let deadline = '';
    if (it.deadline) {
      const left = daysLeft(it.deadline);
      const when = fmtDate(it.deadline, { day: 'numeric', month: 'short' });
      deadline = left === null ? '' : left < 0
        ? `<span class="badge deadline is-past">${esc(t('deadline_past', { date: when }))}</span>`
        : `<span class="badge deadline">${esc(left === 0 ? t('deadline_today', { date: when }) : t('deadline_left', { date: when, days: left }))}</span>`;
    }
    const terms = (it.terms || []).length ? `<div class="terms">${it.terms.map((x, n) =>
      `<button class="term-chip" data-action="term" data-n="${n}" aria-expanded="false">${plain(x.term)}</button>`).join('')}</div>` : '';
    return `
<article class="card${breaking ? ' breaking' : ''}${read ? ' is-read' : ''}" id="i-${esc(it.id)}" data-uid="${esc(it.uid)}">
  <div class="meta">
    <span class="badge tier-${esc(it.tier)}">${esc(t('tier_' + it.tier))}</span>
    ${it.verified ? '' : `<span class="badge unverified" title="${esc(t('unverified_hint'))}">${esc(t('unverified'))}</span>`}
    ${deadline}
    <span>${esc(names)}</span>
    ${it.published ? `<span title="${esc(longDate(it.published))}">${esc(ago(it.published))}</span>` : ''}
    <span class="importance" title="${esc(t('importance', { n: it.importance }))}" aria-label="${esc(t('importance', { n: it.importance }))}">${imp}</span>
  </div>
  <h3 class="title"><button data-action="expand">${plain(it.title)}</button></h3>
  <div class="body">
    ${it.original_title && it.original_title !== it.title ? `<p class="orig">${plain(it.original_title)}</p>` : ''}
    <div class="what">${rich(it.what)}</div>
    <div class="for-you"><span class="label">${esc(t('for_you'))}</span>${inline(it.why_you)}</div>
    <div class="take"><span class="label">${esc(t('take'))}</span>${inline(it.take)}</div>
    ${terms}
    <div class="foot">
      <span class="hype" title="${esc(t('hype_label'))}: ${esc(hypeName)}">${esc(t('hype_label'))} <span class="hype-bars h${it.hype}">${hype}</span> ${esc(hypeName)}</span>
      ${(it.tags || []).length ? `<span class="tags">${it.tags.map((x) => `<span class="tag">#${plain(x)}</span>`).join('')}</span>` : ''}
      <span class="sources">${(it.sources || []).map((s) =>
        `<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer" data-action="source">${esc(s.name)} ↗</a>`).join('')}</span>
      <span class="actions">
        <button class="act read${read ? ' on' : ''}" data-action="read">${esc(read ? t('read_on') : t('read'))}</button>
        <button class="act save${saved ? ' on' : ''}" data-action="save">${esc(saved ? t('saved_on') : t('save'))}</button>
        <button class="act ask" data-action="ask" title="${esc(t('ask_hint'))}">${esc(t('ask'))}</button>
      </span>
    </div>
  </div>
</article>`;
  }

  function sectionHtml(sec, items) {
    return `<section class="section${sec.id === TOP ? ' is-breaking' : ''}" id="s-${esc(sec.id)}">
  <div class="section-head"><h2>${esc(sec.title)}</h2><span class="count">${items.length}</span></div>
  ${sec.desc ? `<p class="section-desc">${esc(sec.desc)}</p>` : ''}
  ${items.map(card).join('')}
</section>`;
  }

  function lessonsHtml(list) {
    if (!list || !list.length) return '';
    return `<section class="section" id="s-lessons">
  <div class="section-head"><h2>${esc(t('lessons'))}</h2><span class="count">${list.length}</span></div>
  <p class="section-desc">${esc(t('lessons_desc'))}</p>
  ${list.map((l) => `
  <article class="lesson">
    <p class="lesson-meta">${esc(l.track_title || l.track)} · ${esc(t('lesson_of', { n: l.n, total: l.total || '?' }))}</p>
    <h3>${plain(l.title)}</h3>
    <div class="lesson-body">${rich(l.body)}</div>
    ${(l.key_points || []).length ? `<div class="key-points"><span class="label">${esc(t('key_points'))}</span><ul>${l.key_points.map((p) => `<li>${inline(p)}</li>`).join('')}</ul></div>` : ''}
    ${l.example ? `<div class="example"><span class="label">${esc(t('example'))}</span>${rich(l.example)}</div>` : ''}
    ${(l.sources || []).length ? `<p class="lesson-sources">${l.sources.map((s) =>
      `<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.name)} ↗</a>`).join('')}</p>` : ''}
  </article>`).join('')}
</section>`;
  }

  function conceptsHtml(list) {
    if (!list || !list.length) return '';
    return `<section class="section" id="s-concepts">
  <div class="section-head"><h2>${esc(t('concepts'))}</h2><span class="count">${list.length}</span></div>
  <p class="section-desc">${esc(t('concepts_desc'))}</p>
  <div class="concepts">${list.map((c) => `
    <article class="concept">
      <h3>${plain(c.term)}</h3>
      <p class="short">${plain(c.short)}</p>
      <details><summary>${esc(t('read_more'))}</summary>
        <div class="long">${rich(c.long)}</div>
        ${c.example ? `<div class="example"><span class="label">${esc(t('example'))}</span>${rich(c.example)}</div>` : ''}
      </details>
    </article>`).join('')}</div>
</section>`;
  }

  function render() {
    renderArchive();
    $('#savedLink').classList.toggle('is-active', S.view === 'saved');
    $('#savedCount').textContent = Object.keys(S.saved).length;
    if (S.view === 'saved') return renderSaved();
    const ed = S.editions[S.current];
    if (!ed) return;
    const secs = sectionsOf(ed);
    const pos = S.index.editions.findIndex((e) => e.id === ed.id);
    $('#editionLabel').textContent = longDate(ed.created);
    $('[data-action="prev"]').disabled = pos >= S.index.editions.length - 1;
    $('[data-action="next"]').disabled = pos <= 0;

    const visible = ed.items.filter(matches);
    const bySec = Object.fromEntries(secs.map((s) => [s.id, []]));
    visible.forEach((it) => (bySec[it.section] || (bySec[it.section] = [])).push(it));
    const total = ed.items.length, done = ed.items.filter((it) => S.read[it.uid]).length;
    const stats = ed.stats || {};
    const extras = !S.q && !S.unread;

    $('#main').innerHTML = `
<header class="masthead">
  <p class="kicker">${esc(longDate(ed.created))}${pos === 0 ? ' · ' + esc(t('latest')) : ''}</p>
  <h1 class="headline">${plain(ed.headline)}</h1>
  <div class="big-picture"><span class="label">${esc(t('big_picture'))}</span>${rich(ed.big_picture)}</div>
  <div class="ed-stats">
    <span class="progress"><span class="progress-bar"><span style="width:${total ? (done / total) * 100 : 0}%"></span></span>${esc(t('progress', { done, total }))}</span>
    ${stats.candidates ? `<span>${esc(t('scanned', { candidates: stats.candidates, sources: stats.sources_ok ?? '?' }))}</span>` : ''}
    ${done < total ? `<button class="text-btn" data-action="read-all">${esc(t('mark_all_read'))}</button>` : ''}
  </div>
</header>
${secs.filter((s) => bySec[s.id].length).map((s) => sectionHtml(s, bySec[s.id])).join('')}
${visible.length ? '' : `<p class="no-match">${esc(t('no_match'))}</p>`}
${extras ? lessonsHtml(ed.lessons) : ''}
${extras ? conceptsHtml(ed.concepts) : ''}`;

    const nav = (id, label, n, hot) => `<li><a href="#s-${esc(id)}" data-action="jump" data-target="s-${esc(id)}"${hot ? ' class="hot"' : ''}>${esc(label)}<span class="count">${n}</span></a></li>`;
    $('#sectionNav').innerHTML = secs.map((s) => (bySec[s.id].length ? nav(s.id, s.nav || s.title, bySec[s.id].length, s.id === TOP) : '')).join('')
      + (extras && (ed.lessons || []).length ? nav('lessons', t('lessons'), ed.lessons.length) : '')
      + (extras && (ed.concepts || []).length ? nav('concepts', t('concepts'), ed.concepts.length) : '');
    observeSections();
  }

  function renderSaved() {
    const items = Object.values(S.saved).sort((a, b) => (b.savedAt || '').localeCompare(a.savedAt || '')).map((x) => x.item).filter(matches);
    $('#editionLabel').textContent = t('saved_title');
    $('#sectionNav').innerHTML = '';
    $('#main').innerHTML = `
<header class="masthead"><p class="kicker">${esc(t('saved_kicker'))}</p><h1 class="headline">${esc(t('saved_title'))}</h1>
  <div class="ed-stats"><span>${esc(t('n_stories', { n: items.length }))}</span><button class="text-btn" data-action="latest">${esc(t('back_latest'))}</button></div></header>
${items.length ? `<section class="section">${items.map(card).join('')}</section>` : `<p class="no-match">${esc(t('saved_empty'))}</p>`}`;
  }

  function renderArchive() {
    if (!S.index) return;
    $('#archive').innerHTML = S.index.editions.slice(0, 40).map((e) => `
<li><button data-action="edition" data-id="${esc(e.id)}" class="${e.id === S.current && S.view === 'edition' ? 'is-current' : ''}">
  <span class="a-date">${esc(shortDate(e.created))} · ${esc(t('n_stories', { n: e.n }))}</span>
  <span class="a-head">${esc(e.headline)}</span>
</button></li>`).join('');
  }

  function renderEmpty() {
    $('#editionLabel').textContent = '—';
    $('#main').innerHTML = `<div class="empty"><h1>${esc(t('empty_title'))}</h1><p>${esc(t('empty_body'))}</p></div>`;
  }
  function renderError(msg) {
    $('#main').innerHTML = `<div class="empty"><h1>${esc(t('error_title'))}</h1><p>${esc(msg)}</p></div>`;
  }

  // ---------------------------------------------------------------- active section
  let io;
  function observeSections() {
    if (io) io.disconnect();
    io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        $$('#sectionNav a').forEach((a) => a.classList.toggle('is-active', a.dataset.target === en.target.id));
      });
    }, { rootMargin: '-70px 0px -70% 0px' });
    $$('.section[id]').forEach((s) => io.observe(s));
  }

  // ---------------------------------------------------------------- state changes
  function itemByUid(uid) {
    for (const ed of Object.values(S.editions)) { const it = ed.items.find((x) => x.uid === uid); if (it) return it; }
    return S.saved[uid] && S.saved[uid].item;
  }
  function setRead(uid, on) {
    if (on) S.read[uid] = Date.now(); else delete S.read[uid];
    store.set('read', S.read);
  }
  function refreshCard(el) {
    const it = itemByUid(el.dataset.uid); if (!it) return;
    const open = el.classList.contains('is-open'), focused = el.classList.contains('is-focused');
    const tmp = document.createElement('div'); tmp.innerHTML = card(it).trim();
    const fresh = tmp.firstElementChild;
    if (open) fresh.classList.add('is-open'); if (focused) fresh.classList.add('is-focused');
    el.replaceWith(fresh);
    updateProgress();
    return fresh;
  }
  function updateProgress() {
    const ed = S.editions[S.current]; if (!ed || S.view !== 'edition') return;
    const total = ed.items.length, done = ed.items.filter((it) => S.read[it.uid]).length;
    const bar = $('.progress-bar span'); if (bar) bar.style.width = `${(done / total) * 100}%`;
    const p = $('.progress'); if (p && p.lastChild) p.lastChild.textContent = t('progress', { done, total });
  }
  function toggleRead(el) {
    const uid = el.dataset.uid, on = !S.read[uid];
    setRead(uid, on);
    el.classList.remove('is-open');
    return refreshCard(el);
  }
  function toggleSave(el) {
    const uid = el.dataset.uid;
    if (S.saved[uid]) delete S.saved[uid]; else S.saved[uid] = { item: itemByUid(uid), savedAt: new Date().toISOString() };
    store.set('saved', S.saved);
    $('#savedCount').textContent = Object.keys(S.saved).length;
    toast(S.saved[uid] ? t('toast_saved') : t('toast_unsaved'));
    return refreshCard(el);
  }
  async function ask(el) {
    const cmd = `/gazette explain ${el.dataset.uid}`;
    toast((await copy(cmd)) ? t('copied', { cmd }) : t('copy_failed', { cmd }));
  }

  // ---------------------------------------------------------------- keyboard focus
  const cards = () => $$('#main .card');
  function setFocus(n, smooth = true) {
    const list = cards(); if (!list.length) return;
    S.focus = Math.max(0, Math.min(list.length - 1, n));
    list.forEach((c, i) => c.classList.toggle('is-focused', i === S.focus));
    list[S.focus].scrollIntoView({ block: 'nearest', behavior: smooth ? 'smooth' : 'auto' });
  }
  const focused = () => cards()[S.focus];

  // ---------------------------------------------------------------- events
  document.addEventListener('click', (e) => {
    const el0 = e.target.closest('[data-action]'); if (!el0) return;
    const el = el0.closest('.card');
    switch (el0.dataset.action) {
      case 'read': toggleRead(el); break;
      case 'save': toggleSave(el); break;
      case 'ask': ask(el); break;
      case 'expand': if (el.classList.contains('is-read')) el.classList.toggle('is-open'); break;
      case 'source': if (!S.read[el.dataset.uid]) { setRead(el.dataset.uid, true); setTimeout(() => refreshCard(el), 0); } break;
      case 'term': {
        const it = itemByUid(el.dataset.uid), term = it.terms[+el0.dataset.n];
        const box = el0.parentElement, open = el0.getAttribute('aria-expanded') === 'true';
        $$('.term-def', box).forEach((d) => d.remove());
        $$('.term-chip', box).forEach((c) => c.setAttribute('aria-expanded', 'false'));
        if (!open) {
          el0.setAttribute('aria-expanded', 'true');
          const d = document.createElement('div'); d.className = 'term-def';
          d.innerHTML = `<b>${esc(term.term)}</b> — ${esc(term.explain)}`;
          box.appendChild(d);
        }
        break;
      }
      case 'read-all': {
        const ed = S.editions[S.current]; ed.items.forEach((it) => { S.read[it.uid] = S.read[it.uid] || Date.now(); });
        store.set('read', S.read); render(); break;
      }
      case 'jump': e.preventDefault(); document.getElementById(el0.dataset.target)?.scrollIntoView({ block: 'start' }); document.body.classList.remove('menu-open'); break;
      case 'edition': openEdition(el0.dataset.id); document.body.classList.remove('menu-open'); break;
      case 'prev': case 'next': {
        const list = S.index.editions, pos = list.findIndex((x) => x.id === S.current);
        const nxt = list[pos + (el0.dataset.action === 'prev' ? 1 : -1)]; if (nxt) openEdition(nxt.id); break;
      }
      case 'latest': e.preventDefault(); if (S.index && S.index.editions.length) openEdition(S.index.editions[0].id); break;
      case 'saved': S.view = 'saved'; render(); window.scrollTo(0, 0); document.body.classList.remove('menu-open'); break;
      case 'menu': document.body.classList.toggle('menu-open'); break;
      case 'theme': {
        const root = document.documentElement;
        const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
        root.dataset.theme = dark ? 'light' : 'dark'; store.set('theme', root.dataset.theme); break;
      }
      default:
    }
  });

  $('#filters').addEventListener('change', (e) => {
    const el = e.target;
    if (el.dataset.tier) { if (el.checked) S.tiers.add(el.dataset.tier); else S.tiers.delete(el.dataset.tier); }
    if (el.id === 'unreadOnly') S.unread = el.checked;
    render();
  });
  let qTimer;
  $('#search').addEventListener('input', (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { S.q = e.target.value.trim(); S.focus = -1; render(); }, 120);
  });

  document.addEventListener('keydown', (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (e.key === 'Escape') {
      if (typing) { document.activeElement.blur(); if (S.q) { $('#search').value = ''; S.q = ''; render(); } }
      document.body.classList.remove('menu-open'); return;
    }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    const el = focused();
    switch (e.key) {
      case '/': e.preventDefault(); $('#search').focus(); break;
      case 'j': setFocus(S.focus + 1); break;
      case 'k': setFocus(S.focus - 1); break;
      case 'r': if (el) { const f = toggleRead(el); if (f) setFocus(cards().indexOf(f) + (S.read[f.dataset.uid] ? 1 : 0)); } break;
      case 's': if (el) toggleSave(el); break;
      case 'c': if (el) ask(el); break;
      case 'o': if (el) { const a = $('.sources a', el); if (a) { window.open(a.href, '_blank', 'noopener'); setRead(el.dataset.uid, true); refreshCard(el); } } break;
      default:
    }
  });

  // ---------------------------------------------------------------- start
  (async function init() {
    // Forget read marks older than 180 days.
    const cutoff = Date.now() - 180 * 86400000;
    Object.keys(S.read).forEach((k) => { if (S.read[k] < cutoff) delete S.read[k]; });
    store.set('read', S.read);
    try { await loadScript('data/site.js'); } catch (e) { /* not set up yet: English fallback */ }
    applyLabels();
    try { await loadScript('data/index.js'); } catch (e) { renderEmpty(); return; }
    if (!S.index || !S.index.editions.length) { renderEmpty(); return; }
    const [hashEd, hashItem] = decodeURIComponent(location.hash.slice(1)).split('/');
    const target = S.index.editions.find((x) => x.id === hashEd) ? hashEd : S.index.editions[0].id;
    openEdition(target, target === hashEd ? hashItem : undefined);
  })();
})();
