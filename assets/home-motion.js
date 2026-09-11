/* Decorative motion stays separate from profile, financial and routing logic. */
(() => {
  'use strict';
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

  function pauseButton(label, onChange) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'motion-toggle';
    let paused = false;
    const setPaused = value => {
      paused = value;
      button.setAttribute('aria-pressed', String(paused));
      button.setAttribute('aria-label', `${paused ? 'Resume' : 'Pause'} ${label}`);
      button.title = button.getAttribute('aria-label');
      onChange(paused);
    };
    button.addEventListener('click', () => setPaused(!paused));
    setPaused(false);
    return {button, setPaused};
  }

  const hero = document.querySelector('.hero');
  if (hero) {
    let paused = false;
    let visible = false;
    const layer = document.createElement('div');
    layer.className = 'hero-feathers';
    layer.setAttribute('aria-hidden', 'true');
    // Fixed lanes and staggered starts keep the background sparse and predictable.
    const feathers = [
      [5, 84, 28, -9, .45], [22, 66, 34, -24, .3],
      [47, 58, 31, -4, .18], [77, 90, 30, -19, .4], [91, 70, 26, -13, .38]
    ];
    for (const [left, size, duration, delay, opacity] of feathers) {
      const feather = document.createElement('span');
      feather.className = 'hero-feather';
      feather.style.cssText = `--left:${left}%;--size:${size}px;--duration:${duration}s;--delay:${delay}s;--opacity:${opacity}`;
      const artwork = document.createElement('img');
      artwork.src = '/assets/hero-feathers.webp';
      artwork.alt = '';
      artwork.width = artwork.height = 625;
      artwork.decoding = 'async';
      artwork.draggable = false;
      feather.append(artwork);
      layer.append(feather);
    }
    hero.prepend(layer);
    const syncHero = () => {
      hero.dataset.motionActive = String(visible && !paused && !document.hidden && !reducedMotion.matches);
    };
    const control = pauseButton('background animation', value => { paused = value; syncHero(); });
    control.button.classList.add('hero-motion-toggle');
    hero.append(control.button);
    new ResizeObserver(() => hero.style.setProperty('--fall-distance', `${hero.offsetHeight + 220}px`)).observe(hero);
    new IntersectionObserver(entries => { visible = entries[0].isIntersecting; syncHero(); }).observe(hero);
    document.addEventListener('visibilitychange', syncHero);
    reducedMotion.addEventListener('change', syncHero);
  }

  const list = document.getElementById('recentList');
  const heading = document.querySelector('#recentSection .section-head');
  if (!list || !heading) return;
  let group = null;
  let period = 0;
  let position = 0;
  let frame = 0;
  let previousTime = null;
  let visible = false;
  let paused = false;
  let hovered = false;
  let focused = false;
  const canMove = () => group && period > 0 && visible && !paused && !hovered && !focused && !document.hidden && !reducedMotion.matches;

  function tick(time) {
    frame = 0;
    if (!canMove()) return;
    const elapsed = previousTime === null ? 0 : Math.min(time - previousTime, 64);
    previousTime = time;
    position = (position + elapsed * .028) % period;
    list.scrollLeft = position;
    frame = requestAnimationFrame(tick);
  }

  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    previousTime = null;
    position = list.scrollLeft;
    if (canMove()) frame = requestAnimationFrame(tick);
  }

  const control = pauseButton('recent updates scrolling', value => { paused = value; sync(); });
  control.button.hidden = true;
  heading.append(control.button);

  function sizeLoop() {
    if (!group || !group.isConnected) return;
    list.querySelectorAll('[data-motion-clone]').forEach(node => node.remove());
    period = group.getBoundingClientRect().width;
    control.button.hidden = reducedMotion.matches || group.children.length < 2;
    if (!reducedMotion.matches && period > 0 && group.children.length > 1) {
      // Repeat enough copies to fill even ultrawide screens. Only originals enter the tab order.
      const copies = Math.ceil(list.clientWidth / period) + 1;
      for (let i = 0; i < copies; i++) {
        const clone = group.cloneNode(true);
        clone.dataset.motionClone = '';
        clone.setAttribute('aria-hidden', 'true');
        clone.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
        clone.querySelectorAll('button,a,input,select,textarea,[tabindex]').forEach(node => node.tabIndex = -1);
        clone.querySelectorAll('.recent-btn').forEach((button, index) => {
          button.addEventListener('click', () => group.querySelectorAll('.recent-btn')[index]?.click());
        });
        list.append(clone);
      }
      list.scrollLeft %= period;
    } else {
      period = 0;
    }
    sync();
  }

  function enhance() {
    if (group?.isConnected) return;
    const items = [...list.children].filter(node => node.classList.contains('recent-item'));
    if (!items.length) { group = null; period = 0; control.button.hidden = true; sync(); return; }
    group = document.createElement('div');
    group.className = 'recent-motion-group';
    group.append(...items);
    list.append(group);
    list.classList.add('recent-motion');
    sizeLoop();
  }

  new MutationObserver(enhance).observe(list, {childList:true});
  new ResizeObserver(sizeLoop).observe(list);
  new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); }).observe(list);
  list.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') { hovered = true; sync(); } });
  list.addEventListener('pointerleave', () => { hovered = false; sync(); });
  list.addEventListener('pointerdown', event => { if (event.pointerType !== 'mouse') control.setPaused(true); });
  list.addEventListener('focusin', event => {
    focused = true;
    if (event.target.matches(':focus-visible')) {
      event.target.closest('.recent-item')?.scrollIntoView({block:'nearest', inline:'nearest', behavior:'instant'});
    }
    sync();
  });
  list.addEventListener('focusout', () => queueMicrotask(() => { focused = list.contains(document.activeElement); sync(); }));
  document.addEventListener('visibilitychange', sync);
  reducedMotion.addEventListener('change', sizeLoop);
  enhance();
})();
