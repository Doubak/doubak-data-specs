#!/usr/bin/env python3
"""doubak bundle v1 参考校验器。

    python3 validate.py <bundle 目录>
    python3 validate.py --tests            # 跑 tests/ 下的全部用例

分两层：

1. **结构性检查**（始终运行，无外部依赖）——跨文件的一致性。这是最有价值
   的部分，而且大多【无法】用 JSON Schema 表达：偏移量真的指向一个 gzip
   member 吗？claimed_source 真的指向一条存在的捕获吗？
2. **schema 校验**（装了 jsonschema 才运行）——字段层面的形状。

退出码 0 = 通过。
"""

import argparse
import collections
import gzip
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent

CAPTURE_ID_RE = re.compile(r"^([0-9]{8}T[0-9]{6}Z-[0-9a-f]{6})#([0-9]{6,})$")
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
TS_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$"
)

SCHEMA_FILES = {
    "manifest": "manifest.schema.json",
    "index-entry": "index-entry.schema.json",
    "checkpoint": "checkpoint.schema.json",
}


class Report:
    def __init__(self) -> None:
        self.errors: "list[str]" = []
        self.warnings: "list[str]" = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------
# schema 层（可选）
# --------------------------------------------------------------------------

def load_schema_validator():
    try:
        import jsonschema  # type: ignore
        from referencing import Registry, Resource  # type: ignore
    except ImportError:
        return None

    registry = Registry()
    for path in HERE.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(path.name, Resource.from_contents(schema))

    def validate(kind: str, instance, rep: Report, where: str) -> None:
        schema = json.loads((HERE / SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema, registry=registry)
        for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(根)"
            rep.error(f"{where}: schema 校验失败于 {loc}: {err.message}")

    return validate


# --------------------------------------------------------------------------
# 结构层（始终运行）
# --------------------------------------------------------------------------

def check_bundle(root: pathlib.Path, rep: Report, schema_validate=None) -> None:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        rep.error(f"{root.name}: 缺少 manifest.json")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # README.txt 是档案的一部分：项目消失后，它是这份目录唯一的自解释入口。
    readme = root / "README.txt"
    if not readme.exists():
        rep.error("缺少 README.txt（档案必须自解释，见 SPEC §2）")
    else:
        text = readme.read_text(encoding="utf-8")
        # 版本号从 manifest 里取，不写死：写死 "bundle/1.0" 的话，1.1 的档案会因为
        # README 里如实写着 1.1 而被判不合格——一条只会在小版本递增时才炸、
        # 且看起来完全无关的规则。顺带这样还更严：README 说的版本必须与 manifest 一致。
        declared = manifest.get("spec_version", "")
        if "WARC" not in text or declared not in text:
            rep.error("README.txt 必须至少说明规范版本（与 manifest 一致）与 WARC 的打开方式")

    if schema_validate:
        schema_validate("manifest", manifest, rep, "manifest.json")

    bundle_id = manifest.get("bundle_id", "")

    # -- 段文件 ------------------------------------------------------------
    segment_bytes: "dict[str, bytes]" = {}
    for seg in manifest.get("segments", []):
        name = seg.get("filename", "")
        path = root / name
        if not path.exists():
            rep.error(f"manifest 列出的段文件不存在: {name}")
            continue
        data = path.read_bytes()
        segment_bytes[name] = data
        if bundle_id and bundle_id not in name:
            rep.error(f"段文件名未内嵌 bundle_id，多次抓取混放时会互相覆盖: {name}")
        if seg.get("bytes") != len(data):
            rep.error(f"{name}: 大小不符，manifest 记 {seg.get('bytes')}，实际 {len(data)}")
        actual = hashlib.sha256(data).hexdigest()
        if seg.get("sha256") != actual:
            rep.error(f"{name}: sha256 不符\n  manifest: {seg.get('sha256')}\n  实际:     {actual}")

    # -- index -------------------------------------------------------------
    index_meta = manifest.get("index", {})
    index_path = root / index_meta.get("filename", "")
    if not index_path.exists():
        rep.error(f"manifest 列出的 index 文件不存在: {index_meta.get('filename')}")
        return
    index_text = index_path.read_text(encoding="utf-8")

    if "sha256" in index_meta:
        actual = hashlib.sha256(index_text.encode()).hexdigest()
        if index_meta["sha256"] != actual:
            rep.error(f"index sha256 不符\n  manifest: {index_meta['sha256']}\n  实际:     {actual}")

    entries = []
    for lineno, line in enumerate(index_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append((lineno, json.loads(line)))
        except json.JSONDecodeError as e:
            rep.error(f"index 第 {lineno} 行不是合法 JSON: {e}")

    if index_meta.get("line_count") != len(entries):
        rep.error(
            f"index 行数不符，manifest 记 {index_meta.get('line_count')}，实际 {len(entries)}"
        )

    # -- 每条捕获 ----------------------------------------------------------
    seen_capture_ids: "dict[str, int]" = {}
    seq_by_bundle: "dict[str, list[int]]" = {}

    for lineno, e in entries:
        where = f"index 第 {lineno} 行"
        if schema_validate:
            schema_validate("index-entry", e, rep, where)

        cid = e.get("capture_id", "")
        m = CAPTURE_ID_RE.match(cid)
        if not m:
            rep.error(f"{where}: capture_id 格式非法: {cid!r}")
        else:
            # 空洞合法（序号先分配后写入，崩溃即留洞），重复非法。
            if cid in seen_capture_ids:
                rep.error(
                    f"{where}: capture_id 重复（首见于第 {seen_capture_ids[cid]} 行）: {cid}"
                )
            seen_capture_ids[cid] = lineno
            seq_by_bundle.setdefault(m.group(1), []).append(int(m.group(2)))
            if bundle_id and m.group(1) != bundle_id:
                rep.error(f"{where}: capture_id 的 bundle 前缀与 manifest 不符: {cid}")

        for field in ("intent", "surface", "verdict", "capture_fidelity", "observed_at"):
            if field not in e:
                rep.error(f"{where}: 缺少必填字段 {field}（此字段事后不可恢复）")

        # SPEC §6.5.2：零长度载荷不得被记为 ok。真实旧档案里出现过 7 个
        # 零字节文件，与一次会话失效同批，磁盘上没有任何失败标记。
        if e.get("content_sha256") == EMPTY_SHA256 and e.get("verdict") == "ok":
            rep.error(
                f"{where}: 载荷为零长度却记为 verdict=ok。"
                f"空响应必须如实判定，否则就是静默的数据丢失。"
            )

        if "observed_at" in e and not TS_RE.match(str(e["observed_at"])):
            rep.error(f"{where}: observed_at 必须是带显式时区偏移的 RFC 3339: {e['observed_at']!r}")

        # 偏移量必须真的指向一个可解压的 gzip member。
        seg = e.get("segment")
        if seg in segment_bytes and "offset" in e and "length" in e:
            data = segment_bytes[seg]
            off, ln = e["offset"], e["length"]
            if off + ln > len(data):
                rep.error(f"{where}: offset+length 超出段文件长度")
            else:
                member = data[off : off + ln]
                try:
                    raw = gzip.decompress(member)
                except Exception as exc:
                    rep.error(f"{where}: offset 处不是合法的 gzip member: {exc}")
                else:
                    if not raw.startswith(b"WARC/"):
                        rep.error(f"{where}: 解压结果不是 WARC 记录")
                    rid = e.get("warc_record_id", "")
                    if rid and f"<{rid}>".encode() not in raw:
                        rep.error(f"{where}: WARC 记录中找不到 warc_record_id {rid}")

    # 每段的 record_count 必须等于指向它的 index 行数。
    # warcinfo 不是捕获，不进 index，也不计入 record_count。
    per_segment = collections.Counter(
        e.get("segment") for _, e in entries if e.get("segment")
    )
    for seg in manifest.get("segments", []):
        name = seg.get("filename", "")
        declared = seg.get("record_count")
        actual = per_segment.get(name, 0)
        if declared is not None and declared != actual:
            rep.error(
                f"{name}: record_count 为 {declared}，但 index 中指向本段的行数为 {actual}。"
                f"（record_count 不含段首的 warcinfo）"
            )

    # 只在有重复时报错；空洞仅提示。
    for bid, seqs in seq_by_bundle.items():
        holes = sorted(set(range(1, max(seqs) + 1)) - set(seqs)) if seqs else []
        if holes:
            rep.warn(
                f"capture_id 序号存在 {len(holes)} 处空洞（合法：序号先分配后写入，"
                f"崩溃会留洞而非留重复）"
            )

    # -- coverage ----------------------------------------------------------
    for cov in manifest.get("coverage", []):
        rk = cov.get("route_key", "?")
        claimed = cov.get("claimed_count")
        src = cov.get("claimed_source")
        if claimed is not None:
            if src is None:
                rep.error(
                    f"coverage[{rk}]: claimed_count 非 null 但 claimed_source 为 null——"
                    f"无从追溯的数字等于没有记"
                )
            elif src not in seen_capture_ids:
                rep.error(f"coverage[{rk}]: claimed_source 指向不存在的捕获: {src}")
        if claimed is not None and cov.get("delta") is not None:
            expect = cov.get("captured_count", 0) - claimed
            if cov["delta"] != expect:
                rep.error(f"coverage[{rk}]: delta 应为 {expect}，实际 {cov['delta']}")
        if "completeness" in cov or "reconciled" in cov:
            rep.error(
                f"coverage[{rk}]: 出现了 completeness/reconciled 字段。本规范刻意不提供它们——"
                f"豆瓣的计数器有时统计于审查之前、有时之后，不可作为完整性判据。"
                f"完整性证据在 crawl_state 里。"
            )

    # -- crawl_state：核心不变量 -------------------------------------------
    for cs in manifest.get("crawl_state", []):
        rk = cs.get("route_key", "?")
        if cs.get("advanced"):
            if not cs.get("contiguous"):
                rep.error(
                    f"crawl_state[{rk}]: advanced=true 但 contiguous=false。"
                    f"水位线只能在连续走完时推进，否则会留下永久且不可检测的空洞。"
                )
            if cs.get("gaps"):
                rep.error(
                    f"crawl_state[{rk}]: advanced=true 但存在 {len(cs['gaps'])} 处缺口。"
                )
            if cs.get("high_water_time") is None:
                rep.error(f"crawl_state[{rk}]: advanced=true 但 high_water_time 为 null。")
        for field in ("high_water_time", "floor_time"):
            v = cs.get(field)
            if v is not None and not TS_RE.match(str(v)):
                rep.error(f"crawl_state[{rk}]: {field} 必须带显式时区偏移: {v!r}")
        if cs.get("enumeration") not in ("full", "bounded"):
            rep.error(
                f"crawl_state[{rk}]: enumeration 必须是 full 或 bounded——"
                f"下游据此判断是否有资格推断删除。"
            )
        elif cs.get("floor_time") is not None and cs.get("enumeration") == "full":
            rep.error(
                f"crawl_state[{rk}]: floor_time={cs['floor_time']} 却写 enumeration=full。"
                f"走到下界就停的路线是 bounded——下界以下这次根本没看过。"
                f"标成 full 等于告诉下游「缺的就是删掉的」，"
                f"于是一份增量与一份全量做差就会把没删的当成删了。"
            )

    # -- checkpoint --------------------------------------------------------
    cp_path = root / "checkpoint.json"
    status = manifest.get("status")
    if status in ("in_progress", "aborted") and not cp_path.exists():
        rep.error(f"status={status} 但缺少 checkpoint.json，无法续抓")
    if status == "complete" and cp_path.exists():
        rep.warn("status=complete 但仍存在 checkpoint.json")
    if cp_path.exists():
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
        if schema_validate:
            schema_validate("checkpoint", cp, rep, "checkpoint.json")
        if cp.get("bundle_id") != bundle_id:
            rep.error("checkpoint.bundle_id 与 manifest.bundle_id 不符")


# --------------------------------------------------------------------------

def run_one(root: pathlib.Path, schema_validate) -> Report:
    rep = Report()
    check_bundle(root, rep, schema_validate)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", nargs="?", help="bundle 目录")
    ap.add_argument("--tests", action="store_true", help="跑 tests/ 下的全部用例")
    args = ap.parse_args()

    schema_validate = load_schema_validator()
    if schema_validate is None:
        print("提示: 未安装 jsonschema，跳过 schema 层校验，仅运行结构性检查。")
        print("      pip install jsonschema referencing\n")

    if args.tests:
        failed = 0
        for kind in ("valid", "invalid"):
            for case in sorted((HERE / "tests" / kind).iterdir()):
                if not case.is_dir():
                    continue
                rep = run_one(case, schema_validate)
                expect_ok = kind == "valid"
                got_ok = rep.ok
                mark = "PASS" if got_ok == expect_ok else "FAIL"
                if mark == "FAIL":
                    failed += 1
                print(f"[{mark}] {kind}/{case.name}  (期望 {'通过' if expect_ok else '报错'})")
                for e in rep.errors:
                    print(f"        → {e.splitlines()[0]}")
        # 例子本身也必须过。
        example = HERE / "examples" / "minimal-bundle"
        if example.exists():
            rep = run_one(example, schema_validate)
            mark = "PASS" if rep.ok else "FAIL"
            if not rep.ok:
                failed += 1
            print(f"[{mark}] examples/minimal-bundle  (期望 通过)")
            for e in rep.errors:
                print(f"        → {e}")
        print(f"\n{'全部通过' if failed == 0 else f'{failed} 个用例未达预期'}")
        return 1 if failed else 0

    if not args.bundle:
        ap.error("需要指定 bundle 目录，或使用 --tests")

    rep = run_one(pathlib.Path(args.bundle), schema_validate)
    for w in rep.warnings:
        print(f"警告: {w}")
    for e in rep.errors:
        print(f"错误: {e}")
    print("\n通过" if rep.ok else f"\n失败：{len(rep.errors)} 个错误")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
