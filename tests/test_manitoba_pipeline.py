import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import ingest_alberta as engine
from tools.ingest_manitoba import merge_band,safe_write,ROOT,SOURCE_CACHE
from tools.manitoba_baseline import verify

class ManitobaPipelineTests(unittest.TestCase):
    def test_verified_roster_and_non_signatories(self):
        roster=json.loads((ROOT/'manitoba-nations.json').read_text())['nations']
        self.assertEqual(len(roster),63)
        self.assertEqual(len({n['iscBandNumber'] for n in roster}),63)
        self.assertTrue(all(n['province']=='MB' and n['id']==n['iscBandNumber'] for n in roster))
        self.assertEqual(sum(bool(n['treaty']) for n in roster),58)
        self.assertEqual(sum(n['treatyVerificationStatus']=='non_signatory' for n in roster),5)
        self.assertTrue(all(-103<n['location']['longitude']<-88 and 48<n['location']['latitude']<61 for n in roster))

    def test_protected_records_unchanged(self):
        verify(json.loads((SOURCE_CACHE/'protected-baseline.json').read_text()))

    def test_reject_cross_province_collision(self):
        data={'bands':[{'id':261,'province':'SK','name':'Protected'}]}
        before=copy.deepcopy(data)
        with self.assertRaises(ValueError):merge_band(data,{'id':261,'iscBandNumber':261,'province':'MB','name':'Incoming'})
        self.assertEqual(data,before)

    def test_discovery_error_keeps_parsed_source_and_profile(self):
        filing={'href':'https://example.test/source.pdf','year':'2024-2025','people':[{'name':'Source person'}],'verificationStatus':'automated_validated'}
        data={'bands':[{'id':261,'iscBandNumber':261,'province':'MB','name':'Nation','website':'https://nation.test','filings':[filing]}]}
        merged=merge_band(data,{'id':261,'iscBandNumber':261,'province':'MB','name':'Nation','website':None,'sourceErrors':[{'kind':'filings','error':'timeout'}]})
        self.assertEqual(merged['filings'],[filing]);self.assertEqual(merged['website'],'https://nation.test')
        self.assertEqual(merged['discoveryStatus'],'error')

    def test_rerun_does_not_duplicate_or_erase_extraction(self):
        data={'bands':[]};seed={'id':261,'iscBandNumber':261,'province':'MB','name':'Nation','filings':[{'href':'https://example.test/a.pdf','people':[{'name':'Verified'}],'parse_status':'parsed'}]}
        merge_band(data,seed)
        seed['filings'][0]={'href':'https://example.test/a.pdf','people':[],'parse_status':'pending'}
        merge_band(data,seed)
        self.assertEqual(len(data['bands']),1);self.assertEqual(data['bands'][0]['filings'][0]['parse_status'],'parsed')

    def test_failed_capital_retry_preserves_validated_result(self):
        data={'bands':[{'id':261,'iscBandNumber':261,'name':'Nation','province':'MB','filings':[{'href':'https://example.test/a.pdf','posted':True,'year':'2024-2025','docType':'Audited consolidated financial statements','parse_status':'parsed','verificationStatus':'automated_validated'}]}]}
        capital={'bands':{'261':{'years':{'2024-2025':{'publishable':True,'parseStatus':'parsed','totalRevenue':123}}}}}
        before=copy.deepcopy(capital);writes={}
        with patch.object(engine,'PROVINCE','MB'),patch.object(engine,'read',side_effect=lambda p:data if Path(p).name=='data.json' else capital),patch.object(engine,'write',side_effect=lambda p,v:writes.update({Path(p).name:copy.deepcopy(v)})),patch.object(engine,'bounded_parse',return_value=('261','https://example.test/a.pdf',{'parse_status':'error','warnings':['timeout']},None)):
            engine.parse_documents(limit=1,workers=1,reparse=True)
        self.assertEqual(writes['capital-data.json'],before)
        self.assertEqual(writes['data.json']['bands'][0]['filings'][0]['verificationStatus'],'automated_validated')

    def test_wrong_document_identity_withheld(self):
        self.assertTrue(engine.document_identity(['Other Nation March 31, 2025'],{'name':'Brokenhead Ojibway Nation'}, {'year':'2024-2025'}))

    def test_safe_write_rejects_protected_mutation_before_write(self):
        data=json.loads((ROOT/'data.json').read_text());data['bands'][0]['name']='Wrong'
        before=(ROOT/'data.json').read_bytes()
        with self.assertRaises(ValueError):safe_write(ROOT/'data.json',data)
        self.assertEqual((ROOT/'data.json').read_bytes(),before)

    def test_identified_provincial_revenue_is_source_labelled(self):
        from tools.capital_parser import identified_revenue_fields
        fields=identified_revenue_fields([{'label':'Manitoba Health','amount':30},{'label':'Indigenous Services Canada','amount':100},{'label':'Unclassified contribution','amount':70}])
        self.assertEqual(fields['manitobaGovernmentRevenue'],30)
        self.assertIsNone(fields['albertaGovernmentRevenue'])
        self.assertEqual(fields['governmentRevenue'],130)
        self.assertIsNone(fields['ownSourceRevenue'])

    def test_concurrent_writer_is_rejected(self):
        from tools.ingest_manitoba import dataset_lock
        with dataset_lock():
            with self.assertRaises(RuntimeError):
                with dataset_lock():pass

    def test_roster_refresh_preserves_verified_aliases_sources_and_listing(self):
        data={'bands':[{'id':261,'iscBandNumber':261,'province':'MB','name':'Nation','aliases':['Verified historic name'],'sources':[{'field':'population','url':'https://example.test/population'}],'discoveryStatus':'checked','filings':[]}]}
        seed={'id':261,'iscBandNumber':261,'province':'MB','name':'Nation','aliases':['New source spelling'],'sources':[{'field':'identity','url':'https://example.test/identity'}]}
        merged=merge_band(data,seed)
        self.assertEqual(merged['discoveryStatus'],'checked')
        self.assertEqual(merged['aliases'],['New source spelling','Verified historic name'])
        self.assertEqual(len(merged['sources']),2)

    def test_new_alias_confirms_previously_unmatched_cover(self):
        filing={'year':'2024-2025'}
        text=['Sagkeeng First Nation\nMarch 31, 2025']
        self.assertTrue(engine.document_identity(text,{'name':'Fort Alexander','aliases':[]},filing))
        self.assertEqual(engine.document_identity(text,{'name':'Fort Alexander','aliases':['Sagkeeng First Nation']},filing),[])

    def test_failed_identity_checkpoint_retries_after_verified_alias(self):
        import hashlib
        band={'id':262,'name':'Fort Alexander','aliases':['Sagkeeng First Nation']}
        filing={'href':'https://example.test/a.pdf','year':'2024-2025'}
        task=(band,filing,False)
        key=hashlib.sha256((str(band['id'])+filing['href']).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory);source=cache/f'{key}.task.json';output=cache/f'{key}.result.json'
            source.write_text(json.dumps((dict(band,aliases=[]),filing,False)))
            cached=('262',filing['href'],{'parse_status':'manual_review','parserRevision':engine.PARSER_REVISION,'documentChecks':{'identityAndYearConfirmed':False}},None)
            output.write_text(json.dumps(cached))
            def run(*args,**kwargs):output.write_text(json.dumps(cached))
            with patch.object(engine,'CACHE',cache),patch.object(engine.subprocess,'run',side_effect=run) as worker:
                engine.bounded_parse(task)
            worker.assert_called_once()

    def test_valid_capital_does_not_block_same_year_remuneration(self):
        data={'bands':[{'id':261,'name':'Nation','province':'MB','filings':[{'href':'https://example.test/pay.pdf','posted':True,'year':'2024-2025','docType':'Schedule of Remuneration and Expenses','parse_status':'pending','people':[]}]}]}
        capital={'bands':{'261':{'years':{'2024-2025':{'publishable':True,'parseStatus':'parsed','totalRevenue':123}}}}}
        people=[{'name':'Source official','remuneration':100}];writes={}
        update={'parse_status':'ok_pdf_text','verificationStatus':'automated_validated','people':people}
        with patch.object(engine,'PROVINCE','MB'),patch.object(engine,'read',side_effect=lambda p:data if Path(p).name=='data.json' else capital),patch.object(engine,'write',side_effect=lambda p,v:writes.update({Path(p).name:copy.deepcopy(v)})),patch.object(engine,'bounded_parse',return_value=('261','https://example.test/pay.pdf',update,None)):
            engine.parse_documents(limit=1,workers=1)
        self.assertEqual(writes['data.json']['bands'][0]['filings'][0]['people'],people)
        self.assertEqual(writes['capital-data.json'],capital)

    def test_manitoba_review_is_hash_bound_and_reconciles_all_columns(self):
        review=json.loads((SOURCE_CACHE/'remuneration-reviews.json').read_text())['reviews'][0]
        with patch.object(engine,'PROVINCE','MB'),patch.object(engine,'SOURCE_CACHE',SOURCE_CACHE):
            band={'id':review['bandId']};filing={'year':review['year'],'href':review['sourcePdf']}
            result=engine.reviewed_remuneration(band,filing,review['sha256'])
            self.assertEqual(len(result['people']),7)
            self.assertEqual(sum(p['remuneration'] for p in result['people']),197649)
            self.assertEqual(sum(p['travelExpenses'] for p in result['people']),138441)
            self.assertIsNone(engine.reviewed_remuneration(band,filing,'different-source'))

    def test_docx_container_is_recognized_without_becoming_a_pdf(self):
        import io,zipfile
        from tools.manitoba_source_formats import is_docx,parse_non_pdf
        import tools.manitoba_source_formats as formats
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('[Content_Types].xml','<Types/>');archive.writestr('word/document.xml','<document/>')
        payload=buffer.getvalue()
        self.assertTrue(is_docx(payload));self.assertFalse(is_docx(b'not a source document'))
        with tempfile.TemporaryDirectory() as directory,patch.object(formats,'ROOT',Path(directory)),patch.object(engine,'PROVINCE','MB'),patch.object(engine,'SOURCE_CACHE',Path(directory)):
            result=parse_non_pdf({'id':295},{'year':'2017-2018','href':'https://example.test/source'},payload)
            self.assertEqual(result['sourceFormat'],'docx')
            self.assertEqual(result['parse_status'],'manual_review')
            self.assertFalse(result['documentChecks']['identityAndYearConfirmed'])
            self.assertTrue((Path(directory)/result['originalSourceFile'].lstrip('/')).exists())

    def test_ocr_retry_selection_is_backend_specific(self):
        from tools.ingest_manitoba import ocr_attempted
        filing={'ocrStatus':'ok_ocr_text','ocrEngine':'rapidocr'}
        self.assertTrue(ocr_attempted(filing,'rapidocr'))
        self.assertFalse(ocr_attempted(filing,'vision'))
        filing['ocrAttemptHistory']=[{'ocrEngine':'macos_vision','ocrStatus':'error_ocr_timeout'}]
        self.assertTrue(ocr_attempted(filing,'vision'))

    def test_review_checkpoint_digest_includes_transcribed_names(self):
        review=copy.deepcopy(json.loads((SOURCE_CACHE/'remuneration-reviews.json').read_text())['reviews'][0])
        with patch.object(engine,'PROVINCE','MB'),patch.object(engine,'read',side_effect=lambda *a,**k:{'reviews':[review]}):
            band={'id':review['bandId']};filing={'year':review['year'],'href':review['sourcePdf']}
            before=engine.reviewed_remuneration(band,filing,review['sha256'])['manualSourceReview']['reviewContentSha256']
            review['people'][0]['name']='Corrected source spelling'
            after=engine.reviewed_remuneration(band,filing,review['sha256'])['manualSourceReview']['reviewContentSha256']
            self.assertNotEqual(before,after)

    def test_vision_is_optional_and_preserves_coordinate_rows(self):
        from tools import local_ocr
        import os
        from types import SimpleNamespace
        cells=[{'box':[[0,0],[50,0],[50,10],[0,10]],'text':'Chief'}, {'box':[[100,0],[160,0],[160,10],[100,10]],'text':'1,234'}]
        with patch.object(local_ocr.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(cells))):
            self.assertEqual(local_ocr._vision_text('local-image.png'),'Chief 1,234')
        with patch.dict(os.environ,{'OPENBAND_VISION_OCR_BIN':'/not-present/vision-ocr'}),patch.object(local_ocr,'_binary',return_value='/fake/pdftoppm'):
            self.assertFalse(local_ocr.availability('vision')['available'])

    def test_spaced_year_header_preserves_actual_and_comparative_selection(self):
        from tools.capital_parser import current_year_column,parse_page_texts
        page=(ROOT/'tests/fixtures/mb_269_2024_operations.txt').read_text()
        header=current_year_column(page,'2023-2024')
        self.assertTrue(header['validated']);self.assertEqual(header['selectedYear'],'2024')
        summary=parse_page_texts([page],'https://official.test/source','2023-2024',require_reported_totals=True)
        self.assertTrue(summary['publishable'])
        self.assertEqual(summary['totalRevenue'],98035859)
        self.assertEqual(summary['totalExpenses'],96705359)
        self.assertEqual(summary['annualSurplusDeficit'],1330500)
        self.assertFalse(current_year_column(page,'2024-2025')['validated'])
        prior='Year ended March 31, 2024\n2 0 2 3 2 0 2 2\nRevenue 100 90'
        self.assertFalse(current_year_column(prior,'2023-2024')['validated'])

    def test_manitoba_boundaries_preserve_all_protected_features(self):
        from tools.build_manitoba_boundaries import protected_features
        current=json.loads((ROOT/'public/reserve-boundaries.geojson').read_text())
        baseline=json.loads((SOURCE_CACHE/'boundary-baseline.json').read_text())
        self.assertEqual(protected_features(current['features']),baseline['features'])
        mb=[f for f in current['features'] if f['properties']['CPC_CODE']=='MB']
        report=json.loads((ROOT/'manitoba-boundary-validation.json').read_text())
        self.assertEqual(len(mb),report['sourceFeatureCount'])
        self.assertTrue(report['protectedSKABFeaturesUnchanged'])
        self.assertEqual(report['manitobaCommunitiesWithBoundaries'],63)
        maps=json.loads((ROOT/'map-data.json').read_text())
        self.assertEqual(sum(bool(r.get('reserveLandIds')) for r in maps['communities'] if r.get('province')=='MB'),63)
