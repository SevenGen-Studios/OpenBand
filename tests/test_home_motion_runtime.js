const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/home-motion.js','utf8');
function harness(mobile=true,season){
 const media={},observers=[],timers=new Map(),frames=new Map();let id=0;
 class Node{
  constructor(cls=''){this.className=cls;this.children=[];this.events={};this.dataset={};this.attrs={};this.style={setProperty(){}};this.isConnected=true;this.scrollLeft=0;this.clientWidth=400;this.offsetHeight=380;this.hidden=false;this.classList={contains:c=>this.className.split(' ').includes(c),add:c=>this.className+=' '+c};}
  addEventListener(k,fn){(this.events[k]??=[]).push(fn)}
  emit(k,e={}){for(const fn of this.events[k]||[])fn(e)}
  setAttribute(k,v){this.attrs[k]=v} getAttribute(k){return this.attrs[k]}
  removeAttribute(k){delete this.attrs[k]} append(...nodes){for(const n of nodes){if(n.parent)n.parent.children=n.parent.children.filter(x=>x!==n);n.parent=this;this.children.push(n)}}
  prepend(n){this.children.unshift(n)} remove(){this.parent.children=this.parent.children.filter(x=>x!==this)}
  getBoundingClientRect(){return {width:600}} cloneNode(){return new Node(this.className)}
  querySelectorAll(sel){if(sel==='[data-motion-clone]')return this.children.filter(c=>'motionClone'in c.dataset);return []}
  contains(n){return n===this||this.children.some(c=>c.contains(n))}
  matches(){return !!this.keyboardFocus} closest(){return null}
 }
 const hero=new Node(),list=new Node(),heading=new Node(),win=new Node();list.append(new Node('recent-item'),new Node('recent-item'));
 const doc=new Node();doc.documentElement={dataset:{heroSeason:season}};doc.activeElement=null;doc.hidden=false;doc.querySelector=s=>s==='.hero'?hero:heading;doc.getElementById=()=>list;doc.createElement=()=>new Node();
 const context={document:doc,window:win,matchMedia:q=>media[q]??=(Object.assign(new Node(),{matches:q.includes('max-width')?mobile:false})),ResizeObserver:class{observe(){}},IntersectionObserver:class{constructor(cb){this.cb=cb;observers.push(this)}observe(){}},MutationObserver:class{observe(){}},requestAnimationFrame:fn=>{frames.set(++id,fn);return id},cancelAnimationFrame:i=>frames.delete(i),setTimeout:fn=>{timers.set(++id,fn);return id},clearTimeout:i=>timers.delete(i),queueMicrotask:fn=>fn()};
 vm.runInNewContext(source,context);observers.forEach(o=>o.cb([{isIntersecting:true}]));
 return {hero,list,heading,media,doc,win,frames,flush(){const work=[...timers.values()];timers.clear();work.forEach(fn=>fn())},Node};
}
const h=harness();assert.equal(h.hero.children[0].dataset.season,'winter');assert.equal(h.hero.children[0].children.length,5);assert.equal(h.hero.children[0].children[0].children[0].src,'/assets/hero-snowflake.svg');
assert.ok(h.frames.size);h.list.emit('pointerdown',{pointerType:'touch'});assert.equal(h.frames.size,0);
h.win.emit('pointerup');h.flush();assert.equal(h.frames.size,1,'swipe resumes automatically');assert.equal(h.heading.children[0].getAttribute('aria-pressed'),'false');
// A tap-induced focus must not latch the mobile strip; keyboard focus must pause it.
const button=new h.Node();h.list.append(button);h.doc.activeElement=button;h.list.emit('focusin',{target:button});assert.equal(h.frames.size,1);
button.keyboardFocus=true;h.list.emit('focusin',{target:button});assert.equal(h.frames.size,0);h.doc.activeElement=null;h.list.emit('focusout');assert.equal(h.frames.size,1);
h.list.emit('pointerdown',{pointerType:'touch'});h.win.emit('pointercancel');h.flush();assert.equal(h.frames.size,1);
h.doc.hidden=true;h.doc.emit('visibilitychange');assert.equal(h.frames.size,0);h.doc.hidden=false;h.doc.emit('visibilitychange');assert.equal(h.frames.size,1);
const reduced=h.media['(prefers-reduced-motion: reduce)'];reduced.matches=true;reduced.emit('change');assert.equal(h.frames.size,0);assert.equal(h.hero.dataset.motionActive,'false');
const desktop=harness(false,'spring');assert.equal(desktop.hero.children[0].children[0].children[0].src,'/assets/hero-feathers.webp');desktop.heading.children[0].emit('click');assert.equal(desktop.frames.size,0);desktop.heading.children[0].emit('click');assert.equal(desktop.frames.size,1);
console.log('Home motion runtime: winter/spring, touch release/cancel, focus, visibility, reduced motion and desktop controls passed');
