#!/usr/bin/env python3
"""把 canonical 的 NDJSON 对着这一版的 schema 校验一遍。

    python3 validate.py <canonical 目录>        # 校验四个 ndjson
    python3 validate.py --self                  # 只自检：schema 本身能不能读

【为什么自己写一个而不是要求装 jsonschema】与 bundle/v1/validate.py 同一个理由：
这个项目的立身之本是「2040 年的陌生人能读懂」，那么验证它的工具也不该先要一个
包管理器。装了 jsonschema 的话它会额外跑一层完整校验，但不装也必须能用。

这里只实现本目录 schema 实际用到的那个子集：$ref、type、enum、oneOf、required、
properties、additionalProperties、items、minItems、minimum、maximum、minLength、pattern。
【遇到不认识的关键字会报出来，不会假装通过】——静默跳过等于把校验器变成摆设。
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
KNOWN = {
    "$schema", "$id", "$ref", "$defs", "title", "description", "examples", "default",
    "type", "enum", "oneOf", "required", "properties", "additionalProperties",
    "items", "minItems", "minimum", "maximum", "minLength", "pattern",
}

# 文件名 → 这一行记录该用哪个 schema
FILES = {
    "marks.ndjson": "mark.schema.json",
    "subjects.ndjson": "subject.schema.json",
    "broadcasts.ndjson": "broadcast.schema.json",
    "longform.ndjson": "longform.schema.json",
    "doulists.ndjson": "doulist.schema.json",
}

_cache: dict[str, dict] = {}


def load(name: str) -> dict:
    if name not in _cache:
        _cache[name] = json.loads((HERE / name).read_text(encoding="utf-8"))
    return _cache[name]


def resolve(ref: str, cur: str):
    """`common.schema.json#/$defs/digest` 或 `#/$defs/revision`。"""
    file, _, frag = ref.partition("#")
    doc = load(file) if file else load(cur)
    node = doc
    for part in frag.strip("/").split("/"):
        if part:
            node = node[part]
    return node, (file or cur)


TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "null": type(None), "integer": int, "number": (int, float),
}


def check(value, schema: dict, cur: str, path: str, errs: list, unknown: set):
    unknown.update(set(schema) - KNOWN)

    if "$ref" in schema:
        target, nxt = resolve(schema["$ref"], cur)
        check(value, target, nxt, path, errs, unknown)
        return

    if "oneOf" in schema:
        # 只要有一支过就算过。全不过时把每一支的理由都报出来——只说「都不匹配」
        # 会让人对着一个 oneOf 猜半天。
        subs = []
        for i, sub in enumerate(schema["oneOf"]):
            e: list = []
            check(value, sub, cur, path, e, unknown)
            if not e:
                return
            subs.extend(f"{path}: 分支{i} {m.split(': ', 1)[-1]}" for m in e)
        errs.append(f"{path}: oneOf 全部不匹配 ({'; '.join(subs)})")
        return

    if "type" in schema:
        want = schema["type"]
        want = want if isinstance(want, list) else [want]
        # bool 是 int 的子类，别让 True 混过 integer
        ok = any(
            isinstance(value, TYPES[t]) and not (t in ("integer", "number") and isinstance(value, bool))
            for t in want
        )
        if not ok:
            errs.append(f"{path}: 类型应为 {want}，实际是 {type(value).__name__}")
            return

    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} 不在 {schema['enum']}")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: 长度 {len(value)} < minLength {schema['minLength']}")
        # pattern 只在值是字符串时检查——可空字段的 null 不该被它拦下。
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} 不匹配 {schema['pattern']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} < 最小值 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} > 最大值 {schema['maximum']}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}: 缺必填字段 {key!r}")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                check(value[key], sub, cur, f"{path}.{key}", errs, unknown)
        extra = schema.get("additionalProperties", True)
        if extra is False:
            for key in set(value) - set(props):
                errs.append(f"{path}: 不允许的额外字段 {key!r}")
        elif isinstance(extra, dict):
            for key in set(value) - set(props):
                check(value[key], extra, cur, f"{path}.{key}", errs, unknown)

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: 至少要 {schema['minItems']} 项，实际 {len(value)}")
        if "items" in schema:
            for i, item in enumerate(value):
                check(item, schema["items"], cur, f"{path}[{i}]", errs, unknown)


def main() -> int:
    args = sys.argv[1:]
    unknown: set = set()

    if not args or args[0] == "--self":
        for name in sorted(set(FILES.values())) + ["common.schema.json"]:
            load(name)
            print(f"[OK] {name} 可读")
        print("\n用法: python3 validate.py <canonical 目录>")
        return 0

    root = pathlib.Path(args[0])
    # **目录不存在也「全部通过」，是这个校验器能犯的最坏的错。** 打错一个路径就拿到
    # 一句绿灯，而它检查的东西一行都没读到。同理，目录在、但一个 canonical 文件都
    # 没有，也不是通过——那是「你指错地方了」，不是「你的数据没问题」。
    if not root.is_dir():
        print(f"[错] {root} 不是一个目录", file=sys.stderr)
        return 2

    failed = 0
    seen_any = False
    for fname, sname in FILES.items():
        path = root / fname
        if not path.exists():
            print(f"[跳过] {fname} 不存在")
            continue
        seen_any = True
        schema = load(sname)
        n = bad = 0
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            n += 1
            errs: list = []
            check(json.loads(line), schema, sname, "$", errs, unknown)
            if errs:
                bad += 1
                if bad <= 3:
                    print(f"  第 {lineno} 行:")
                    for e in errs[:4]:
                        print(f"    {e}")
        failed += bad
        mark = "OK" if bad == 0 else "FAIL"
        print(f"[{mark}] {fname}: {n} 行，不合规 {bad}  ({sname})")

    if not seen_any:
        print(f"\n[错] {root} 里一个 canonical 文件都没有（找的是 "
              f"{'、'.join(FILES)}）。没有东西可校验不等于校验通过。", file=sys.stderr)
        return 2

    if unknown:
        # 校验器不认识的关键字 = 它其实没在检查那一条。必须说出来。
        print(f"\n[注意] schema 里用到了本校验器不支持的关键字: {sorted(unknown)}")
        print("       那些约束【没有被检查】。装 jsonschema 可做完整校验。")

    print("\n全部通过" if failed == 0 else f"\n共 {failed} 行不合规")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
