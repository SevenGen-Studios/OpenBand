/* One display contract for official ISC band numbers; never infer from route IDs. */
(function(root){
  'use strict';
  const escape=value=>String(value??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  function number(band){const value=String(band?.iscBandNumber??'');return /^\d{1,3}$/.test(value)&&Number(value)>0?value.padStart(3,'0'):''}
  function text(band){const value=number(band);return String(band?.name||'')+(value?' '+value:'')}
  function markup(band,query=''){
    let name=escape(band?.name||'');
    if(query){const pattern=String(query).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');name=String(band?.name||'').split(new RegExp(`(${pattern})`,'gi')).map((part,index)=>index%2?`<strong>${escape(part)}</strong>`:escape(part)).join('')}
    const value=number(band);
    return `<span class="nation-name">${name}${value?`<span class="nation-band-number" aria-label="ISC band number ${value}">${value}</span>`:''}</span>`;
  }
  root.OpenBandNationName={number,text,markup};
  if(typeof module!=='undefined')module.exports=root.OpenBandNationName;
})(typeof window!=='undefined'?window:globalThis);
