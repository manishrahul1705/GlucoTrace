"""Production replay accounting, end-of-stream and bounded access regressions."""
import tempfile,unittest
from pathlib import Path
from dataclasses import replace
from glucotwin.stage6.sources import synthetic,Registry,SourceUnavailable
from glucotwin.stage6.engine import Session,Store

class TestCompletion(unittest.TestCase):
    def test_malformed_local_inventory_is_unavailable_without_fallback(self):
        import json
        for payload in [{},[],[None],[{'participant_id':'bad'}]]:
            with self.subTest(payload=payload),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);path=root/'data/processed/stage5/calibration_artifacts.json';path.parent.mkdir(parents=True)
                path.write_text(json.dumps(payload));runtime=root/'runtime';runtime.mkdir()
                registry=Registry(root,runtime,True)
                self.assertEqual(registry.list()['sources'][1]['reason'],'LOCAL_ARTIFACTS_UNAVAILABLE')
                with self.assertRaises(SourceUnavailable):registry.load('local-unavailable','clean')
                self.assertEqual(registry.load('synthetic-dawn','clean').mode,'synthetic')

    def test_missing_model_and_mismatched_protocol_fail_explicitly(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'runtime';runtime.mkdir()
            inventory=root/'data/processed/stage5/calibration_artifacts.json';inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps([{'participant_id':1}]))
            registry=Registry(root,runtime,True);identifier=next(iter(registry.mapping))
            with self.assertRaisesRegex(SourceUnavailable,'LOCAL_ARTIFACTS_UNAVAILABLE'):registry.load(identifier,'clean')
            required=['data/processed/stage2/observations/p001.csv','data/processed/stage5/model_001.joblib','data/processed/stage5/model_reproduction.json','data/processed/stage5/partition_adequacy.csv','reports/stage2/split_manifest.json','configs/stage5_protocol.json','reports/stage5/protocol_freeze.json','data/processed/stage5/input_hashes.json','data/processed/stage5/partition_predictions.csv']
            for name in required:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
            (root/'reports/stage5/protocol_freeze.json').write_text(json.dumps({'protocol_sha256':'incorrect'}))
            with self.assertRaisesRegex(SourceUnavailable,'INCOMPATIBLE_ARTIFACTS'):registry.load(identifier,'clean')

    def test_pending_missing_and_scored_are_distinct_issued_sets(self):
        source=synthetic();reference=dict(source.reference);reference.pop(90)
        session=Session(replace(source,reference=reference));session.advance_to(90)
        summary=session.snapshot()['summaries'][0]
        self.assertEqual(summary['issued'],7)  # origins 60..90 inclusive
        self.assertEqual(summary['missing_targets'],1)  # issued at 60, exact target absent
        self.assertEqual(summary['pending'],6)
        self.assertEqual(summary['scored'],0)
        self.assertEqual(summary['interval_available'],0)
        self.assertEqual(summary['coverage_denominators'],{'0.10':0,'0.05':0})
        session.advance_to(95);summary=session.snapshot()['summaries'][0]
        self.assertEqual(summary['issued'],summary['pending']+summary['scored']+summary['missing_targets'])
        self.assertEqual(summary['scored'],1)

    def test_end_is_stable_and_pagination_covers_sqlite_forecasts_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'events.sqlite3');session=Session(synthetic('dropout120'),store)
            session.status='running';session.speed=300;session.tick(1000)
            self.assertEqual(session.status,'ended');before=session.snapshot();session.tick(1000)
            self.assertEqual(before,session.snapshot());self.assertLessEqual(len(before['history']),181)
            after=0;ids=[]
            while True:
                page=session.snapshot(7,after);ids.extend(f['id'] for f in page['forecasts'])
                if not page['has_more']:break
                after=page['next_after_seq']
            self.assertEqual(len(ids),len(set(ids)));self.assertEqual(len(ids),len(session.forecasts))
            self.assertEqual(store.db.execute("select count(*) from events where kind='forecast'").fetchone()[0],len(ids))
            store.db.close()
