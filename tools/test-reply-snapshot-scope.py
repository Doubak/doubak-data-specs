"""Optional scope is backward compatible, but opt-in is self/authenticated only."""
import copy
import json
import pathlib
import unittest
import jsonschema
from referencing import Registry, Resource

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'bundle' / 'v1'
SCHEMA = json.loads((ROOT / 'manifest.schema.json').read_text())
REGISTRY = Registry().with_resources(
    (d['$id'], Resource.from_contents(d))
    for p in ROOT.glob('*.schema.json') for d in [json.loads(p.read_text())]
)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, registry=REGISTRY)
BASE = json.loads((ROOT / 'examples/minimal-bundle/manifest.json').read_text())

class ScopeTest(unittest.TestCase):
    def test_legacy_and_declared_views(self):
        VALIDATOR.validate(BASE)
        for visibility, operator in [('self', 'authenticated'), ('public', 'authenticated'), ('public', 'anonymous')]:
            for flag in [None, False, True]:
                with self.subTest(visibility=visibility, operator=operator, flag=flag):
                    m = copy.deepcopy(BASE)
                    m['crawl_scope'] = dict(visibility=visibility, operator_mode=operator)
                    if flag is not None:
                        m['crawl_scope']['broadcast_reply_snapshot'] = flag
                    self.assertEqual(VALIDATOR.is_valid(m), flag is not True or visibility == 'self')

    def test_nonboolean_and_anonymous_self_rejected(self):
        for flag, mode in [('yes', 'authenticated'), (True, 'anonymous')]:
            m = copy.deepcopy(BASE)
            m['crawl_scope'] = dict(visibility='self', operator_mode=mode, broadcast_reply_snapshot=flag)
            self.assertFalse(VALIDATOR.is_valid(m))

if __name__ == '__main__':
    unittest.main()
