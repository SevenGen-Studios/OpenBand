/* The gateway previews provinces; entering one retains the existing routing. */
(() => {
  const hero = document.querySelector('.hero');
  if (!hero) return;
  const provinces = [
    {name:'Saskatchewan', code:'SK', path:'/saskatchewan/', flag:'https://upload.wikimedia.org/wikipedia/commons/b/bb/Flag_of_Saskatchewan.svg'},
    {name:'Alberta', code:'AB', path:'/alberta/', flag:'https://upload.wikimedia.org/wikipedia/commons/f/f5/Flag_of_Alberta.svg'}
  ];
  const scene = document.createElement('section');
  scene.className = 'province-carousel';
  scene.setAttribute('aria-label', 'Explore provinces');
  scene.setAttribute('aria-roledescription', 'carousel');
  scene.tabIndex = 0;
  scene.innerHTML = `<div class="province-ghost" aria-hidden="true">SASKATCHEWAN</div><div class="province-flags">${provinces.map((p,i)=>`<a class="province-flag-link ${i?'standby':'selected'}" href="${p.path}" aria-label="Open ${p.name} First Nations records"><img class="province-flag" src="${p.flag}" alt="${p.name} provincial flag" draggable="false"></a>`).join('')}</div><div class="province-carousel-bottom"><div><p class="province-carousel-kicker">FIRST NATIONS PUBLIC RECORDS</p><h1 class="province-carousel-name" aria-live="polite">Saskatchewan</h1><div class="province-carousel-controls"><button type="button" aria-label="Previous province"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M19 12H5m7 7-7-7 7-7"/></svg></button><button type="button" aria-label="Next province"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 12h14m-7-7 7 7-7 7"/></svg></button><span class="province-carousel-count">01 / 02</span></div></div><a class="province-enter" href="/saskatchewan/">Explore Saskatchewan <span aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9"/></svg></span></a></div>`;
  hero.append(scene);
  let index = 0, locked = false, start = null;
  function navigate(direction) {
    if (locked) return;
    locked = true;
    index = (index + direction + provinces.length) % provinces.length;
    const p = provinces[index];
    hero.dataset.previewProvince = p.code;
    scene.querySelector('.province-ghost').textContent = p.name.toUpperCase();
    scene.querySelector('.province-carousel-name').textContent = p.name;
    scene.querySelector('.province-carousel-count').textContent = `0${index+1} / 02`;
    const link = scene.querySelector('.province-enter');
    link.href = p.path;
    link.innerHTML = `Explore ${p.name} <span aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9"/></svg></span>`;
    scene.querySelectorAll('.province-flag-link').forEach((flag,i)=>{flag.classList.toggle('selected',i===index);flag.classList.toggle('standby',i!==index)});
    setTimeout(()=>{locked=false},650);
  }
  scene.querySelectorAll('button').forEach((button,i)=>button.addEventListener('click',()=>navigate(i?1:-1)));
  scene.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();navigate(event.key==='ArrowRight'?1:-1)}});
  scene.addEventListener('pointerdown',event=>{if(event.target.closest('a,button'))return;start={x:event.clientX,y:event.clientY};scene.setPointerCapture(event.pointerId)});
  scene.addEventListener('pointerup',event=>{if(!start)return;const dx=event.clientX-start.x,dy=event.clientY-start.y;start=null;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy))navigate(dx<0?1:-1)});
  scene.addEventListener('pointercancel',()=>{start=null});
})();
