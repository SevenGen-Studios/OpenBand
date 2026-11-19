"""Source-linked BC profile prerendering; no financial data is calculated."""
from datetime import date,datetime
from html import escape as esc
try:
 from tools.nation_name import nation_name_markup
except ModuleNotFoundError:
 from nation_name import nation_name_markup

def current_officials(band,today=None):
 today=today or date.today();rows=[]
 for p in band.get('leadership',{}).get('officials',[]):
  try:start=datetime.strptime(p['appointmentDate'],'%m/%d/%Y').date();end=datetime.strptime(p['expiryDate'],'%m/%d/%Y').date()
  except (ValueError,KeyError,TypeError):continue
  if start<=today<=end:rows.append(p)
 return rows

def profile_markup(band):
 pop=band.get('population') or {};measure=lambda v:f'{v:,}' if isinstance(v,int) else 'Not yet verified';rows=[('Official name',band['officialName']),('ISC band number',str(band['iscBandNumber']) if band.get('iscBandNumber') else 'No separate ISC band number assigned'),('Tribal council (ISC)',band.get('tribalCouncil') or 'Not verified'),('Registered population (ISC)',measure(pop.get('registeredMembers'))),('Registered on own reserve',measure(pop.get('onOwnReserve'))),('Registered off reserve',measure(pop.get('offReserve'))),('Population reference period',pop.get('sourcePeriod') or 'Not available'),('Administrative mailing address (ISC)',(band.get('contact') or {}).get('mailing_address') or 'Not yet verified')]
 out=f'<section class="nation-details"><h3>Government &amp; Community Profile</h3><p>{esc(band["entityType"].replace("_"," "))} · Identity verified {esc(band["verifiedAt"][:10])}</p>'
 if band.get('identityNote'):out+=f'<p class="note">{esc(band["identityNote"])}</p>'
 out+='<dl class="province-subtotals">'+''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in rows)+'</dl><p class="note">Registered population is not the full citizenship or resident population of a self-governing Nation. Reserve categories shown may not sum to the total. No population is copied from a related government.</p><h4>Treaties and agreements</h4>'
 agreements=band.get('treatyAgreements',[])
 out+=('<ul>'+''.join(f'<li>{esc(a["label"])} · {esc(a["kind"].replace("_"," "))} · {esc(a["status"])} · <a href="{esc(a["sourceUrl"],quote=True)}">Source</a></li>' for a in agreements)+'</ul>') if agreements else '<p>No treaty classification is verified. Missing information does not establish non-signatory status.</p>'
 if band.get('treatyNegotiation'):
  n=band['treatyNegotiation'];out+=f'<p>Treaty negotiations: {esc(n["statusText"])} · <a href="{esc(n["sourceUrl"],quote=True)}">Source</a>. Negotiation participation is not a completed treaty.</p>'
 if band.get('regionalAffiliations'):out+='<details><summary>Regional and treaty organizations</summary><ul>'+''.join(f'<li>{esc(a["name"])} · <a href="{esc(a["sourceUrl"],quote=True)}">Source</a></li>' for a in band['regionalAffiliations'])+'</ul></details>'
 if band.get('reserves'):out+=f'<details><summary>ISC-listed reserves ({len(band["reserves"])})</summary><ul>'+''.join(f'<li>{esc(r["name"])} · ISC reserve {esc(r["number"])}</li>' for r in band['reserves'])+'</ul></details>'
 if band.get('location'):out+=f'<p>Map point: {esc(band["location"]["locationType"])} · <a href="/browse/?province=BC">Browse BC communities</a>.</p>'
 else:out+='<p>No verified map location is indexed for this government.</p>'
 if band.get('website'):out+=f'<p><a href="{esc(band["website"],quote=True)}">Source-listed official government website</a></p>'
 out+='<p>'+ ' · '.join(f'<a href="{esc(s["url"],quote=True)}">{esc(s["field"])} source</a>' for s in band.get('sources',[]))+'</p></section>'
 officials=current_officials(band);source=band.get('leadership',{});out+='<section class="election-card"><h3>Elections &amp; Leadership</h3><p>'+esc(band.get('governanceSystem') or 'Governance system not yet verified')+'</p>'
 if officials:
  out+=f'<p>ISC-listed officeholders with terms covering today. Source checked {esc(source["retrievedAt"][:10])}. Appointment dates are not verified election dates.</p><ul>'+''.join(f'<li><strong>{esc(p["position"])} {esc(p["givenName"])} {esc(p["surname"])}</strong> · Appointment {esc(p["appointmentDate"])} · Term expiry {esc(p["expiryDate"])}</li>' for p in officials)+'</ul>'
 else:out+='<p>No term-verified current officeholders are indexed. This does not mean the government has no leadership.</p>'
 if source.get('sourceUrl'):out+=f'<p><a href="{esc(source["sourceUrl"],quote=True)}">ISC governance source</a></p>'
 return out+'</section>'
