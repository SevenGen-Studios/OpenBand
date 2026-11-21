/* A continuous, directly draggable ring; province links retain native navigation. */
(() => {
  const hero = document.querySelector('.hero');
  if (!hero) return;
  const provinces = [
    {name:'Saskatchewan', code:'SK', path:'/saskatchewan/', flag:'/assets/flags/saskatchewan.svg'},
    {name:'Alberta', code:'AB', path:'/alberta/', flag:'/assets/flags/alberta.svg'},
    {name:'Manitoba',code:'MB',path:'/manitoba/',flag:'/assets/flags/manitoba.svg'}
  ];
  const scene = document.createElement('section');
  scene.className = 'province-carousel';
  scene.setAttribute('aria-label', 'Explore provinces');
  scene.setAttribute('aria-roledescription', 'carousel');
  scene.tabIndex = 0;
  scene.innerHTML = `<div class="province-ghost" aria-hidden="true">SASKATCHEWAN</div><div class="province-flags">${provinces.map((p,i)=>`<a class="province-flag-link ${i?'standby':'selected'}" href="${p.path}" aria-label="Open ${p.name} First Nations records"><img class="province-flag" src="${p.flag}" alt="${p.name} provincial flag" draggable="false"></a>`).join('')}</div><div class="province-carousel-bottom"><div><p class="province-carousel-kicker">FIRST NATIONS PUBLIC RECORDS</p><h1 class="province-carousel-name" aria-live="polite">Saskatchewan</h1><div class="province-carousel-controls"><button type="button" aria-label="Previous province"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M19 12H5m7 7-7-7 7-7"/></svg></button><button type="button" aria-label="Next province"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 12h14m-7-7 7 7-7 7"/></svg></button><span class="province-carousel-count">01 / ${String(provinces.length).padStart(2,'0')}</span></div></div><a class="province-enter" href="/saskatchewan/">Explore Saskatchewan <span aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9"/></svg></span></a></div>`;
  hero.append(scene);
  const flags = [...scene.querySelectorAll('.province-flag-link')];
  const flagArea = scene.querySelector('.province-flags');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const wrap = value => (value % provinces.length + provinces.length) % provinces.length;
  let position = 0, target = 0, index = -1, width = scene.clientWidth || window.innerWidth;
  let animation = 0, paint = 0, drag = null, suppressClickUntil = 0, drift = 22;
  function select(value) {
    const next = wrap(Math.round(value));
    if (next === index) return;
    index = next;
    const p = provinces[index];
    hero.dataset.previewProvince = p.code;
    scene.querySelector('.province-ghost').textContent = p.name.toUpperCase();
    scene.querySelector('.province-carousel-name').textContent = p.name;
    scene.querySelector('.province-carousel-count').textContent = `${String(index+1).padStart(2,'0')} / ${String(provinces.length).padStart(2,'0')}`;
    const link = scene.querySelector('.province-enter');
    link.href = p.path;
    link.innerHTML = `Explore ${p.name} <span aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9"/></svg></span>`;
    flags.forEach((flag,i) => {
      flag.classList.toggle('selected', i === index);
      flag.classList.toggle('standby', i !== index);
      flag.tabIndex = i === index ? 0 : -1;
      flag.setAttribute('aria-hidden', String(i !== index));
    });
  }
  function render() {
    flags.forEach((flag,i) => {
      const angle = (i-position) * Math.PI * 2 / provinces.length;
      const depth = Math.cos(angle), side = Math.sin(angle), front = (depth+1)/2;
      flag.style.transform = `translate3d(calc(-50% + ${side*width*.6}px), calc(-50% + ${(1-depth)*drift}px), ${(depth-1)*100}px) scale(${.42+.58*front}) rotate(${-6*front+side*10}deg)`;
      flag.style.opacity = String(Math.max(0, (depth+.6)/1.6));
    });
  }
  function stop() {
    cancelAnimationFrame(animation);
    cancelAnimationFrame(paint);
    animation = paint = 0;
  }
  function animateTo(value) {
    stop();
    target = value;
    select(target);
    scene.classList.remove('is-dragging');
    if (motion.matches || Math.abs(target-position) < .001) {
      position = target = wrap(target);
      scene.classList.remove('is-moving');
      render();
      return;
    }
    const from = position, began = performance.now();
    const duration = Math.min(420, 260 + Math.abs(target-from)*60);
    scene.classList.add('is-moving');
    function tick(now) {
      const progress = Math.min(1, (now-began)/duration);
      position = from + (target-from)*(1-Math.pow(1-progress,4));
      render();
      if (progress < 1) animation = requestAnimationFrame(tick);
      else {
        animation = 0;
        position = target = wrap(target);
        scene.classList.remove('is-moving');
      }
    }
    animation = requestAnimationFrame(tick);
  }
  function navigate(direction) {
    drag = null;
    animateTo((animation ? target : Math.round(position)) + direction);
  }
  scene.querySelectorAll('button').forEach((button,i) => button.addEventListener('click', () => navigate(i ? 1 : -1)));
  scene.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      navigate(event.key === 'ArrowRight' ? 1 : -1);
    }
  });
  scene.addEventListener('pointerdown', event => {
    if (event.isPrimary === false || (event.button != null && event.button !== 0) || event.target.closest('button, .province-enter')) return;
    stop();
    width = scene.clientWidth || window.innerWidth;
    drag = {id:event.pointerId, x:event.clientX, y:event.clientY, lastX:event.clientX, time:performance.now(), velocity:0, position, active:false};
  });
  scene.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX-drag.x, dy = event.clientY-drag.y;
    if (!drag.active) {
      if (Math.abs(dy) > 8 && Math.abs(dy) > Math.abs(dx)) { drag = null; animateTo(Math.round(position)); return; }
      if (Math.abs(dx) < 6 || Math.abs(dx) < Math.abs(dy)*1.1) return;
      drag.active = true;
      scene.setPointerCapture(event.pointerId);
      scene.classList.add('is-moving', 'is-dragging');
    }
    event.preventDefault();
    const now = performance.now();
    drag.velocity = (event.clientX-drag.lastX)/Math.max(1,now-drag.time);
    drag.lastX = event.clientX;
    drag.time = now;
    position = drag.position-dx/Math.max(180,width*.95);
    select(position);
    if (!paint) paint = requestAnimationFrame(() => { paint = 0; render(); });
  }, {passive:false});
  function release(event, cancelled = false) {
    if (!drag || (event.pointerId != null && event.pointerId !== drag.id)) return;
    const gesture = drag;
    drag = null;
    if (scene.hasPointerCapture(gesture.id)) scene.releasePointerCapture(gesture.id);
    const dx = event.clientX-gesture.x, dy = event.clientY-gesture.y;
    const horizontal = Math.abs(dx) > Math.abs(dy)*1.1;
    const flick = performance.now()-gesture.time < 100 && Math.abs(gesture.velocity) > .35 && Math.abs(dx) > 12;
    const commit = !cancelled && horizontal && (Math.abs(dx) > Math.max(28,width*.14) || flick);
    if (gesture.active || commit) suppressClickUntil = performance.now()+350;
    let destination = cancelled ? Math.round(gesture.position) : Math.round(position);
    if (commit && destination === Math.round(gesture.position)) destination += dx < 0 ? 1 : -1;
    animateTo(destination);
  }
  scene.addEventListener('pointerup', event => release(event));
  scene.addEventListener('pointercancel', event => release(event,true));
  window.addEventListener('pointerup', event => release(event), {passive:true});
  window.addEventListener('pointercancel', event => release(event,true), {passive:true});
  scene.addEventListener('lostpointercapture', event => { if (drag && event.target === scene && !scene.hasPointerCapture(event.pointerId)) release(event,true); });
  scene.addEventListener('dragstart', event => event.preventDefault());
  scene.addEventListener('click', event => {
    if (event.detail !== 0 && performance.now() < suppressClickUntil) { event.preventDefault(); event.stopPropagation(); }
  }, true);
  function resize() {
    width = scene.clientWidth || window.innerWidth;
    // A rotated 2:1 flag needs extra height and width; reserve it before painting.
    const fit = Math.max(0,Math.min(820,width*(width<=700?.86:.62),flagArea.clientHeight/0.68,(width-24)/1.05));
    drift=Math.min(22,flagArea.clientHeight*.03);
    flagArea.style.setProperty('--flag-width',`${fit}px`);
    render();
  }
  if (typeof ResizeObserver !== 'undefined') { const observer=new ResizeObserver(resize);observer.observe(scene);observer.observe(flagArea); }
  else window.addEventListener('resize',resize,{passive:true});
  motion.addEventListener('change', () => { if (motion.matches) { const gesture = drag; drag = null; if (gesture && scene.hasPointerCapture(gesture.id)) scene.releasePointerCapture(gesture.id); animateTo(Math.round(target)); } });
  select(0);
  resize();
})();
