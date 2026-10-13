#!/usr/bin/env python3
"""账号昵称的兼容性与类型约束，逐个执行真实 schema。零依赖也能跑。"""

import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("canonical_validate", ROOT / "canonical/v1/validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

SCHEMAS = [ROOT / "bundle/v1/manifest.schema.json"] + [
    ROOT / "canonical/v1" / name
    for name in validator.FILES.values() if name != "subject.schema.json"
]


class AccountNicknameTests(unittest.TestCase):
    def test_crawl_scope_is_optional_but_known_values_are_checked(self):
        schema = json.loads(SCHEMAS[0].read_text(encoding="utf-8"))
        self.assertNotIn("crawl_scope", schema["required"])
        scope_schema = schema["properties"]["crawl_scope"]
        for value, valid in [
            ({"visibility": "self", "operator_mode": "authenticated"}, True),
            ({"visibility": "public", "operator_mode": "anonymous", "skip_catalog": True}, True),
            ({"visibility": "public", "operator_mode": "anonymous", "operator_user_id": None}, True),
            ({"visibility": "public", "operator_mode": "authenticated", "operator_user_id": "123"}, True),
            ({"visibility": "public", "operator_mode": "authenticated", "operator_user_id": "slug"}, False),
            ({"visibility": "public", "operator_mode": "authenticated", "operator_user_id": 123}, False),
            ({"visibility": "private", "operator_mode": "authenticated"}, False),
            ({"visibility": "public", "operator_mode": "anonymous", "skip_catalog": "yes"}, False),
            ({"visibility": "public"}, False),
        ]:
            with self.subTest(value=value):
                errors, unknown = [], set()
                validator.check(value, scope_schema, "manifest", "$.crawl_scope", errors, unknown)
                self.assertFalse(unknown)
                self.assertEqual(not errors, valid)

    def check_account(self, path, account):
        schema = json.loads(path.read_text(encoding="utf-8"))["properties"]["account"]
        errors, unknown = [], set()
        validator.check(account, schema, path.name, "$.account", errors, unknown)
        self.assertFalse(unknown, f"{path}: 有约束未检查")
        # 有可选依赖时再让独立的 JSON Schema 实现检查同一份契约。
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            pass
        else:
            independent = list(Draft202012Validator(schema).iter_errors(account))
            self.assertEqual(bool(errors), bool(independent), str(path))
        return errors

    def test_all_user_record_schemas_are_checked(self):
        self.assertEqual(len(SCHEMAS), 8, "manifest + 七类用户记录，不能漏一类")
        for path in SCHEMAS:
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))["properties"]["account"]
                self.assertIn("nickname", schema["properties"])
                self.assertNotIn("nickname", schema.get("required", []))

    def test_old_accounts_null_and_unicode_names_remain_valid(self):
        for path in SCHEMAS:
            for extra in [{}, {"nickname": None}, {"nickname": "MewX"},
                          {"nickname": "昵称 & <文字> 🌱"}]:
                with self.subTest(schema=path.name, account=extra):
                    self.assertFalse(self.check_account(path, {"user_id": "123", **extra}))

    def test_wrong_types_are_rejected_in_every_schema(self):
        for path in SCHEMAS:
            for nickname in [0, True, [], {}]:
                with self.subTest(schema=path.name, nickname=nickname):
                    errors = self.check_account(path, {"user_id": "123", "nickname": nickname})
                    self.assertTrue(errors, "未定义 nickname 会被 additionalProperties 放行")
                    self.assertTrue(any("nickname" in error for error in errors))

    def test_subjects_do_not_gain_account_ownership(self):
        schema = json.loads((ROOT / "canonical/v1/subject.schema.json").read_text(encoding="utf-8"))
        self.assertNotIn("account", schema["properties"])


if __name__ == "__main__":
    unittest.main()
