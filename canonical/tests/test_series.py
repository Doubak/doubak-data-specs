import copy
import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).parents[1] / 'v1' / 'validate.py'
spec = importlib.util.spec_from_file_location('validator', path)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

class SeriesContract(unittest.TestCase):
    def record(self):
        return {'canonical_version': 'canonical/1.4', 'medium': 'movie', 'id': '1', 'revisions': [{
            'fields': {'series': {'kind': 'douban_same_series', 'source': 'embedded_config', 'scope': 'unknown',
                'items': [{'medium': 'movie', 'id': '2', 'title': None}], 'claimed_total': 2}},
            'observations': [{'observed_at': '2026-01-01T00:00:00Z', 'absence_authority': 'none'}]}]}
    def errors(self, r):
        errors = []
        v.check_subject_series(r, errors)
        for rev in r['revisions']:
            if 'series' in rev['fields']:
                v.check(rev['fields']['series'], v.load('subject.schema.json')['$defs']['series'], 'subject.schema.json', '$', errors, set())
        return errors
    def test_valid_and_extensible(self):
        r = self.record()
        self.assertEqual(self.errors(r), [])
        r['revisions'][0]['fields']['series']['scope'] = 'complete'
        self.assertEqual(self.errors(r), [])
        r['revisions'][0]['fields']['series'].update(source='future', scope='future', extra=True)
        self.assertEqual(self.errors(r), [])
    def test_missing_old_and_new(self):
        r = self.record(); r['revisions'][0]['fields'] = {'aliases': None, 'info': None}
        self.assertTrue(self.errors(r))
        r['revisions'][0]['observations'][0]['omitted_fields'] = ['series']
        self.assertEqual(self.errors(r), [])
        r['canonical_version'] = 'canonical/1.3'; r['revisions'][0]['observations'][0].pop('omitted_fields')
        self.assertEqual(self.errors(r), [])
    def test_bad_series_and_provenance(self):
        for value in [None, [], {'kind':'douban_same_series'}, {**self.record()['revisions'][0]['fields']['series'], 'claimed_total': -1}]:
            r=self.record(); r['revisions'][0]['fields']['series']=value
            self.assertTrue(self.errors(r))
        r=self.record(); r['revisions'][0]['fields']['series']['items'][0]['id']={}
        self.assertTrue(self.errors(r))
        r=self.record(); items=r['revisions'][0]['fields']['series']['items']; items.append(copy.deepcopy(items[0]))
        self.assertTrue(self.errors(r))
        r=self.record(); r['revisions'][0]['observations'][0]['omitted_fields']=['tags']
        self.assertTrue(self.errors(r))
        r=self.record(); r['revisions'][0]['observations'][0]['absence_authority']='whole_route'
        self.assertTrue(self.errors(r))
    def test_time_order_and_digest(self):
        r=self.record(); r['revisions'].append(copy.deepcopy(r['revisions'][0]))
        r['revisions'][1]['observations'][0]['observed_at']='2025-01-01T00:00:00Z'
        self.assertTrue(self.errors(r))
        r=self.record(); r['revisions'][0]['digests']={}
        errors=[]; v.check_digest_coverage(r,'subject.schema.json',errors)
        self.assertTrue(any('series' in e for e in errors))

if __name__ == '__main__': unittest.main()
