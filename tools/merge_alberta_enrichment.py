"""Merge reviewed profile/logo/business evidence into the shared OpenBand data."""
from tools.ingest_alberta import ROOT, read, write, now, page_url
from tools.build_site import slugify
from tools.collect_first_nation_logos import unverified_record

def merge():
    data = read(ROOT / 'data.json')
    by_id = {str(b['id']): b for b in data['bands']}
    enrichment = read(ROOT / 'alberta-enrichment.json')
    reviews = read(ROOT / 'manual_overrides/alberta-logo-reviews.json', {})
    contacts = read(ROOT / 'contacts-data.json')
    logos = read(ROOT / 'first-nation-logos.json')
    logo_report = read(ROOT / 'first-nation-logo-report.json')
    members = read(ROOT / 'member-counts.json')
    maps = read(ROOT / 'map-data.json')
    capital = read(ROOT / 'capital-data.json')
    for record in enrichment['nations']:
        band = by_id[str(record['id'])]
        if band['id'] == 477:
            band['name'] = 'Tthebatthie Denesųłiné Nation'
            band['officialName'] = band['name']
            band['aliases'] = ["Smith's Landing First Nation", 'Smiths Landing First Nation']
        aliases = {435: ['Blood Tribe', 'Kainai Nation'], 475: ['Wesley First Nation', 'Goodstoney First Nation'],
                   459: ['Whitefish Lake First Nation #459', 'Atikameg'], 438: ['Alexander First Nation'],
                   441: ['Paul First Nation'], 473: ['Bearspaw First Nation'], 433: ['Chiniki First Nation'],
                   442: ['Montana First Nation'], 444: ['Samson Cree Nation']}
        band['aliases'] = sorted(set(band.get('aliases', []) + aliases.get(band['id'], [])))
        if record.get('websiteVerified'):
            band['website'] = record['website']
            source = {'field': 'website', 'url': record['website'], 'retrievedAt': record['checkedAt']}
            band['sources'] = [s for s in band.get('sources', []) if s['field'] != 'website'] + [source]
        band['officialSiteResearch'] = {'checkedAt': record['checkedAt'], 'pages': record['researchPages'], 'errors': record['errors']}
        if record.get('relatedDisclosureSources'):
            band['relatedDisclosureSources'] = record['relatedDisclosureSources']
        if band['id'] in (433, 473, 475):
            band['identityNote'] = 'A distinct Stoney Nakoda Nation. ISC also lists Stoney Tribal Administration (471); its shared financial statements are not individual-Nation totals.'
            band['relatedDisclosureSources'] = [{'title': 'Stoney Tribal Administration shared disclosures', 'url': page_url('FederalFundingMain', 471), 'scope': 'Shared administration; not included in individual financial totals'}]
        logo = record['logo']
        if not (logo.get('sha256') and reviews.get(str(band['id']), {}).get('sha256') == logo['sha256']):
            reason = reviews.get(str(band['id']), {}).get('reason', 'No visually verified official logo available.')
            logo = unverified_record(band, record.get('website'), 'Official First Nation website', reason)
        logo.update({'nation_name': band['name'], 'slug': slugify(band['name'])})
        logos['logos'] = [r for r in logos['logos'] if str(r['nation_id']) != str(band['id'])] + [logo]
        logo_report = [r for r in logo_report if str(r['nation_id']) != str(band['id'])] + [{'nation_id': band['id'], 'nation_name': band['name'], 'status': logo['logo_status'], 'source': logo.get('logo_source'), 'reason': logo.get('verification_note')}]
        for key in ('logo_url', 'logo_source', 'logo_asset_source', 'logo_verified', 'logo_status'):
            band[key] = logo[key]
        contact = next((c for c in contacts['contacts'] if str(c['nation_id']) == str(band['id'])), None)
        if contact is None:
            contact = {'nation_id': band['id'], 'nation_name': band['name'], 'office_phone': None, 'office_email': None, 'mailing_address': None, 'source_url': band.get('website'), 'last_verified': now()[:10]}
            contacts['contacts'].append(contact)
        contact['nation_name'] = band['name']
        contact['website_url'] = band.get('website')
        contact['field_sources'] = {k: contact['source_url'] if contact.get(k) else None for k in ('office_phone', 'office_email', 'mailing_address')}
        contact['field_sources']['website_url'] = band.get('website')
        population = members['bands'].get(str(band['id']))
        if population:
            population['name'] = band['name']
            population['sourceYear'] = population.get('sourcePeriod')
            population['notes'] = 'Total registered population, not an on-reserve count. On-own-reserve population is stored separately.'
        location = next((c for c in maps['communities'] if str(c['id']) == str(band['id'])), None)
        if location:
            location['name'] = band['name']
        if str(band['id']) in capital.get('bands', {}):
            capital['bands'][str(band['id'])]['name'] = band['name']
        for filing in band.get('filings', []):
            filing.setdefault('nationId', band['id'])
    data['band_count'] = len(data['bands'])
    contacts['recordCount'] = len(contacts['contacts'])
    logos.update({'recordCount': len(logos['logos']), 'verifiedCount': sum(bool(r['logo_verified']) for r in logos['logos']), 'generated': now()[:10]})
    logos['unverifiedCount'] = logos['recordCount'] - logos['verifiedCount']
    maps['communityCount'] = len(maps['communities'])
    maps['missingLocations'] = [{'id': b['id'], 'name': b['name'], 'reason': 'Distinct location not verified; shared ISC coordinates are not copied'} for b in data['bands'] if not any(str(c['id']) == str(b['id']) for c in maps['communities'])]
    for filename, value in [('data.json', data), ('capital-data.json', capital), ('contacts-data.json', contacts), ('first-nation-logos.json', logos), ('first-nation-logo-report.json', logo_report), ('member-counts.json', members), ('map-data.json', maps)]:
        write(ROOT / filename, value)
    registry = read(ROOT / 'alberta-nations.json')
    for seed in registry['nations']:
        band = by_id[str(seed['id'])]
        for field in ('name', 'officialName', 'aliases', 'website', 'identityNote', 'relatedDisclosureSources'):
            if field in band:
                seed[field] = band[field]
    write(ROOT / 'alberta-nations.json', registry)
    enterprise = read(ROOT / 'community-enterprise.json')
    seeds = read(ROOT / 'alberta-businesses.json')['businesses']
    for business in seeds:
        sid = 'src-' + business['id']
        source = {'id': sid, 'title': business['name'] + ' ownership source', 'publisher': business['name'], 'url': business['sourceUrl'], 'publicationDate': None, 'lastVerified': now()[:10]}
        enterprise['sources'] = [s for s in enterprise['sources'] if s['id'] != sid] + [source]
        row = {'id': business['id'], 'name': business['name'], 'organizationType': 'Operating company', 'industry': business['industry'], 'description': business['description'], 'website': business['website'], 'sourceIds': [sid], 'verificationStatus': 'Verified', 'lastVerified': now()[:10], 'owningNationIds': business['nationIds'], 'operatingStatus': 'Publicly listed', 'financialInformation': None}
        enterprise['businesses'] = [b for b in enterprise['businesses'] if b['id'] != row['id']] + [row]
        for bid in business['nationIds']:
            band = by_id[str(bid)]
            oid = f'org-ab-nation-{bid}'
            if not any(o['id'] == oid for o in enterprise['organizations']):
                enterprise['organizations'].append({'id': oid, 'name': band['name'], 'organizationType': 'First Nation government', 'description': 'Nation owner of the separately sourced businesses listed below.', 'website': band.get('website'), 'sourceIds': [sid], 'verificationStatus': 'Verified', 'lastVerified': now()[:10]})
            interest = {'id': f'own-{bid}-{row["id"]}', 'ownerId': oid, 'businessId': row['id'], 'ownershipPercentage': business['ownershipPercentage'], 'ownershipType': business['ownershipType'], 'sourceIds': [sid], 'verificationStatus': 'Verified'}
            enterprise['ownershipInterests'] = [r for r in enterprise['ownershipInterests'] if r['id'] != interest['id']] + [interest]
            profile = next((p for p in enterprise['nationProfiles'] if str(p['bandId']) == str(bid)), None)
            if profile is None:
                profile = {'bandId': bid, 'primaryOrganizationId': oid, 'featuredBusinessIds': [], 'featuredProjectIds': [], 'industries': [], 'lastVerified': now()[:10], 'verificationStatus': 'Verified'}
                enterprise['nationProfiles'].append(profile)
            profile['featuredBusinessIds'] = sorted(set(profile['featuredBusinessIds'] + [row['id']]))
            profile['industries'] = sorted(set(profile['industries'] + [row['industry']]))
    for band in [b for b in data['bands'] if b['province'] == 'AB']:
        enterprise['coverage'] = [c for c in enterprise['coverage'] if str(c['bandId']) != str(band['id'])] + [{'bandId': band['id'], 'directOrganizationStatus': 'Verified' if any(str(p['bandId']) == str(band['id']) for p in enterprise['nationProfiles']) else 'Not verified', 'researchStatus': 'Official-site discovery attempted', 'checkedAt': now()}]
    write(ROOT / 'community-enterprise.json', enterprise)

if __name__ == '__main__':
    merge()
