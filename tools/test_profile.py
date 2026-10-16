#!/usr/bin/env python3
"""Execute the profile schema and the CLI: optional old inputs, omissions, null and UID identity."""
import copy
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = ROOT / 'canonical/v1'
spec = importlib.util.spec_from_file_location('validator', HERE / 'validate.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
EXAMPLE = json.loads((HERE / 'examples/profile-avatar-observations.json').read_text())

class ProfileTests(unittest.TestCase):
    def validate(self, record):
        errors, unknown = [], set()
        v.check(record, v.load('profile.schema.json'), 'profile.schema.json', '$', errors, unknown)
        v.check_digest_coverage(record, 'profile.schema.json', errors)
        self.assertFalse(unknown)
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            pass
        else:
            registry = Registry().with_resources((json.loads(p.read_text())['$id'], Resource.from_contents(json.loads(p.read_text()))) for p in HERE.glob('*.schema.json'))
            independent = list(Draft202012Validator(v.load('profile.schema.json'), registry=registry).iter_errors(record))
            # Digest key equality is an additional semantic check, outside JSON Schema.
            if independent:
                self.assertTrue(errors)
        return errors

    def test_example_missing_null_and_old_version(self):
        self.assertFalse(self.validate(EXAMPLE))
        for fields in [{}, {'avatar_url': None}, {'nickname': '名字'}, {'avatar_url': 'https://img3.doubanio.com/icon/up82160871-1.jpg'}]:
            r = copy.deepcopy(EXAMPLE)
            r['revisions'][0]['fields'] = fields
            r['revisions'][0]['digests'] = {k: None if val is None else 'sha256:'+'a'*64 for k,val in fields.items()}
            self.assertFalse(self.validate(r))

    def test_wrong_types_and_missing_digest(self):
        for value in ['', 1, [], {}]:
            r = copy.deepcopy(EXAMPLE)
            r['revisions'][0]['fields']['avatar_url'] = value
            self.assertTrue(self.validate(r))
        r = copy.deepcopy(EXAMPLE)
        del r['revisions'][0]['digests']['avatar_url']
        self.assertTrue(self.validate(r))
        r['account']['user_id'] = 'slug'
        self.assertTrue(self.validate(r))

    def test_cli_old_eight_files_and_profile_uid_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            for name in v.FILES:
                if name != 'profile.ndjson': (root / name).write_text('')
            def run():
                return subprocess.run([sys.executable, str(HERE/'validate.py'), d], capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            (root/'profile.ndjson').write_text(json.dumps(EXAMPLE)+'\n')
            self.assertEqual(run().returncode, 0)
            r = copy.deepcopy(EXAMPLE); r['upstream_id'] = '999'
            (root/'profile.ndjson').write_text(json.dumps(r)+'\n')
            result=run();self.assertEqual(result.returncode,1);self.assertIn('account.user_id',result.stdout)

if __name__ == '__main__': unittest.main()
