(function(){
  "use strict";
  const container=document.getElementById("operationsStatus"),escape=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll('"',"&quot;");
  const definitions=[
    {label:"News pipeline",url:"/news-coverage-report.json",metrics:[["Published articles","articlesAfter"],["Awaiting review","manualReviewCount"],["Source failures","sourceFailureCount"]]},
    {label:"Jobs pipeline",url:"/jobs-coverage-report.json",metrics:[["Verified active listings","verifiedActiveListings"],["Pending verification","pendingVerification"],["Sources checked","sourcesChecked"]]},
    {label:"Events pipeline",url:"/events-coverage-report.json",metrics:[["Published records","after"],["Review queue","reviewCount"]]}
  ];
  async function refresh(){
    document.getElementById("operationsRefresh").disabled=true;
    container.setAttribute("aria-busy","true");
    const cards=await Promise.all(definitions.map(async item=>{try{const response=await fetch(item.url,{cache:"no-store",signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error(`HTTP ${response.status}`);const data=await response.json(),date=new Date(data.generated),valid=Number.isFinite(date.getTime()),stale=!valid||Date.now()-date.getTime()>172800000;return `<article class="portal-card"><span class="portal-status">${stale?"Needs freshness review":"Updated within 48 hours"}</span><h3>${item.label}</h3><p>${valid?date.toLocaleString("en-CA",{timeZone:"America/Regina"}):"No generation timestamp"} · Saskatchewan time</p>${item.metrics.map(([label,key])=>`<p><strong>${Number.isFinite(data[key])?data[key].toLocaleString("en-CA"):"Unavailable"}</strong> ${label}</p>`).join("")}<a href="${item.url}">Inspect source report</a></article>`}catch(error){return `<article class="portal-card"><span class="portal-status">Unavailable</span><h3>${item.label}</h3><p>Report could not be checked: ${escape(error.message)}</p></article>`}}));
    container.innerHTML=cards.join("");container.setAttribute("aria-busy","false");
    const config=window.OPENBAND_ANALYTICS_CONFIG||{},health=document.getElementById("analyticsServiceStatus");
    try{if(!config.apiEndpoint)throw new Error("endpoint not configured");const url=new URL(config.apiEndpoint);url.pathname="/health";url.search="";const response=await fetch(url,{cache:"no-store",signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error(`HTTP ${response.status}`);const data=await response.json();if(data.status!=="ok")throw new Error("unexpected response");health.textContent=`Analytics API responded at ${new Date().toLocaleTimeString("en-CA",{timeZone:"America/Regina"})}. Tracking ${config.enabled?"enabled":"disabled"}; GA4 ${config.gaMeasurementId?"configured":"not configured"}. Open the private dashboard to verify event collection.`}catch(error){health.textContent=`Analytics API could not be verified: ${error.message}.`}
    document.getElementById("operationsRefresh").disabled=false;
  }
  document.getElementById("operationsRefresh").addEventListener("click",refresh);void refresh();
})();
