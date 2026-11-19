"""Static counterpart of assets/nation-name.js, using only the database field."""
import html
import re


def band_number(band):
    value = str(band.get('iscBandNumber', ''))
    return value.zfill(3) if re.fullmatch(r'\d{1,3}', value) and int(value) > 0 else ''


def nation_name_markup(band):
    name = html.escape(str(band.get('name', '')), quote=True)
    value = band_number(band)
    suffix = f'<span class="nation-band-number" aria-label="ISC band number {value}">{value}</span>' if value else ''
    return f'<span class="nation-name">{name}{suffix}</span>'


def identity_source_url(band):
    number = band_number(band)
    if number:
        return f'https://services.sac-isc.gc.ca/fnp/main/Search/FederalFundingMain.aspx?BAND_NUMBER={int(number)}&lang=eng'
    return next((source['url'] for source in band.get('sources', []) if source.get('field') == 'identity'), 'https://www.fsin.ca/sask-fn-listings')
