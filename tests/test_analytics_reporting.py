import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AnalyticsReportingTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript((ROOT/'analytics-worker/schema.sql').read_text())
        self.worker=(ROOT/'analytics-worker/src/index.ts').read_text()

    def event(self,days,session,event,parameters='{}'):
        self.db.execute("INSERT INTO analytics_events(occurred_at,page,event_name,session_id,visitor_id,device_type,browser,referrer,parameters_json) VALUES(strftime('%Y-%m-%dT%H:%M:%fZ','now',?), '/', ?, ?, ?, 'desktop','Chrome','direct',?)",(f'-{days} days',event,session,session,parameters))

    def test_current_previous_boundaries_and_unique_outcomes(self):
        self.event(1,'current','page_view');self.event(1,'current','statement_opened');self.event(1,'current','statement_downloaded');self.event(10,'prior','page_view')
        sql=self.worker.split('const summarySql = `',1)[1].split('`;',1)[0]
        current=dict(self.db.execute(sql,('-7 days','0 days')).fetchone())
        previous=dict(self.db.execute(sql,('-14 days','-7 days')).fetchone())
        self.assertEqual(current['sessions'],1);self.assertEqual(current['outcomeSessions'],1);self.assertEqual(previous['sessions'],1);self.assertEqual(previous['outcomeSessions'],0)

    def test_sql_all_dashboard_queries_execute(self):
        import re
        dashboard=self.worker.split('async function dashboard',1)[1].split('async function handle',1)[0]
        for query in re.findall(r'(?:rows|first)\(env, `([^`]+)`',dashboard):
            self.db.execute(query,tuple('-7 days' for _ in range(query.count('?')))).fetchall()

    def test_same_day_iso_timestamp_is_before_current_instant(self):
        self.event(0.01,'recent','page_view')
        sql=self.worker.split('const summarySql = `',1)[1].split('`;',1)[0]
        self.assertEqual(self.db.execute(sql,('-7 days','0 days')).fetchone()['sessions'],1)

if __name__=='__main__':unittest.main()
