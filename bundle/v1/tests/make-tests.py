#!/usr/bin/env python3
"""生成 tests/valid 与 tests/invalid 下的用例。

每个反例都是在最小合法 bundle 上做一处、且只做一处破坏，并配一句
「应该报什么错」。反例套件是让规范从「一篇文档」变成「一件真东西」的关键：
没有它，没人知道校验器到底拦不拦得住。

    python3 make-tests.py
"""

import hashlib
import importlib.util
import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).parent
EXAMPLE = HERE.parent / "examples" / "minimal-bundle"

# WARC 的写法从生成例子的脚本里【导入】而不是抄一份：抄的那份一旦与例子生成器
# 漂移，用例就会去校验一种规范里并不存在的字节布局，而且看起来还全是绿的。
_spec = importlib.util.spec_from_file_location(
    "make_minimal_bundle", HERE.parent / "examples" / "make-minimal-bundle.py"
)
mkb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mkb)
BUNDLE_ID = "20260728T101500Z-a3f9c1"
SEGMENT = f"data-{BUNDLE_ID}-00001.warc.gz"
INDEX = f"index-{BUNDLE_ID}.ndjson"


def fresh(kind: str, name: str, why: str) -> pathlib.Path:
    dst = HERE / kind / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(EXAMPLE, dst)
    (dst / "EXPECTED.txt").write_text(why + "\n", encoding="utf-8")
    return dst


def load_manifest(d: pathlib.Path) -> dict:
    return json.loads((d / "manifest.json").read_text(encoding="utf-8"))


def save_manifest(d: pathlib.Path, m: dict) -> None:
    (d / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def index_lines(d: pathlib.Path) -> list:
    return [
        json.loads(l)
        for l in (d / INDEX).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


def save_index(d: pathlib.Path, lines: list, fix_hash: bool = True) -> None:
    text = "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines)
    (d / INDEX).write_text(text, encoding="utf-8")
    if fix_hash:
        m = load_manifest(d)
        m["index"]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
        m["index"]["line_count"] = len(lines)
        save_manifest(d, m)


# --- valid ----------------------------------------------------------------

def case_valid_with_holes() -> None:
    """序号空洞必须【合法】：序号先分配后写入，崩溃会留洞而非留重复。
    校验器若把空洞当错误，会在真实崩溃恢复后误报。"""
    d = fresh("valid", "capture-id-holes", "应通过：capture_id 序号空洞是合法的（分配后崩溃）。")
    lines = index_lines(d)
    old_id = lines[1]["capture_id"]
    new_id = f"{BUNDLE_ID}#000005"  # 跳过 2、3、4
    lines[1]["capture_id"] = new_id
    save_index(d, lines)
    # 指向该捕获的引用必须一并更新，否则会触发引用完整性检查——
    # 这正是 claimed_source 该起的作用。
    m = load_manifest(d)
    for cov in m["coverage"]:
        if cov.get("claimed_source") == old_id:
            cov["claimed_source"] = new_id
    save_manifest(d, m)


def case_valid_cross_bundle_parent() -> None:
    """跨档案的 parent_capture_id 必须【合法】（规范 §6.2.1）。

    真实生产路径：一次增量只取回水位线以上的页面，但从**旧档案里已经存下来的**
    页面中仍可能算出当时没抓的附属资源（正文图片、附件）。把它们放进队列的那次
    捕获，客观上就发生在旧档案里。

    这个用例守的是「校验器不许把它当悬空引用」。没有它，将来有人给
    parent_capture_id 加一条「必须存在于本档案」的检查，就会让一批真实档案
    集体变成不合法——而那些档案已经冻结，改不了。
    """
    d = fresh(
        "valid",
        "cross-bundle-parent",
        "应通过：parent_capture_id 指向另一份档案是合法的（规范 §6.2.1）。\n"
        "读者不得把它当悬空引用；不可达不等于无效——用户可以在导出后删掉旧档案。",
    )
    lines = index_lines(d)
    lines[1]["parent_capture_id"] = "20260101T000000Z-000000#000007"
    save_index(d, lines)


def case_valid_asset_capture() -> None:
    """bundle/1.1：图片捕获走 assets-* 段、surface=asset。

    这个用例守的是三件很容易同时做错的事：

    ① **surface 是封闭词表，asset 必须在里面。** 不在，就只能把 JPEG 标成 html——
       下游会拿它去解析页面结构。
    ② **1.0 的校验器必须仍然认 1.0 的档案。** spec_version 原来是 const，1.1 一
       落地它就自相矛盾了。这里的 1.1 用例与其余 15 个 1.0 用例同时通过，才说明
       改成 pattern 是对的。
    ③ **图片走自己的段。** assets-* 与 catalog-* 分开，是为了让「丢掉可重抓的部分」
       保持为一次纯文件操作。
    """
    d = fresh(
        "valid",
        "asset-capture",
        "应通过：bundle/1.1 的图片捕获——独立的 assets-* 段，surface=asset。",
    )

    # 一个真的 1×1 PNG。用真字节而不是占位符：校验器要算 sha256 与长度。
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000d49444154789c63f8cfc0f01f00050001ff89993d"
        "1d0000000049454e44ae426082"
    )

    seg_name = f"assets-{BUNDLE_ID}-00001.warc.gz"
    cap_id = f"{BUNDLE_ID}#000003"
    rec_id = "urn:uuid:00000000-0000-4000-8000-000000000013"
    url = "https://img3.doubanio.com/view/status/l/public/b79771d06053dd7.jpg"

    warcinfo_block = (
        f"software: doubak-extension/0.1.0\r\n"
        f"format: WARC File Format 1.1\r\n"
        f"isPartOf: {BUNDLE_ID}\r\n"
        f"conformsTo: https://spec.doubak.com/bundle/v1/\r\n"
    ).encode()
    warcinfo = mkb.warc_record(
        [
            ("WARC-Type", "warcinfo"),
            ("WARC-Record-ID", "<urn:uuid:00000000-0000-4000-8000-000000000012>"),
            ("WARC-Date", "2026-07-28T02:16:00Z"),
            ("WARC-Filename", seg_name),
            ("WARC-Block-Digest", mkb.sha1_base32(warcinfo_block)),
            ("Content-Type", "application/warc-fields"),
        ],
        warcinfo_block,
    )
    seg = mkb.gzip_member(warcinfo)

    block = mkb.http_response(
        "HTTP/1.1 200 OK",
        [("Content-Type", "image/png"), ("Content-Length", str(len(png)))],
        png,
    )
    record = mkb.warc_record(
        [
            ("WARC-Type", "response"),
            ("WARC-Record-ID", f"<{rec_id}>"),
            ("WARC-Date", "2026-07-28T02:16:04Z"),
            ("WARC-Target-URI", url),
            ("WARC-Block-Digest", mkb.sha1_base32(block)),
            ("WARC-Payload-Digest", mkb.sha1_base32(png)),
            ("Content-Type", "application/http;msgtype=response"),
        ],
        block,
    )
    member = mkb.gzip_member(record)
    offset = len(seg)
    seg += member
    (d / seg_name).write_bytes(seg)

    lines = index_lines(d)
    lines.append(
        {
            "capture_id": cap_id,
            "warc_record_id": rec_id,
            "segment": seg_name,
            "offset": offset,
            "length": len(member),
            "url": url,
            "url_key": url,
            "url_key_rules": "v1",
            # 用户自己上传的图，不是目录缩略图——留存等级不同，段也不同。
            "intent": "asset.image.user_upload",
            "route_key": "broadcast.timeline",
            "surface": "asset",
            "verdict": "ok",
            "capture_fidelity": "decoded_body+observed_headers",
            "observed_at": "2026-07-28T10:16:04+08:00",
            "http_status": 200,
            "content_type": "image/png",
            "content_sha256": hashlib.sha256(png).hexdigest(),
            "parent_capture_id": f"{BUNDLE_ID}#000001",
            "cursor": None,
        }
    )
    save_index(d, lines)

    m = load_manifest(d)
    m["spec_version"] = "bundle/1.1"
    m["segments"].append(
        {
            "filename": seg_name,
            "bytes": len(seg),
            "sha256": hashlib.sha256(seg).hexdigest(),
            "record_count": 1,
            "first_capture_id": cap_id,
            "last_capture_id": cap_id,
        }
    )
    save_manifest(d, m)

    # README 里的版本号必须跟着改：校验器要求两者一致（写死版本号的检查已经改掉了）。
    readme = d / "README.txt"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("bundle/1.0", "bundle/1.1"),
        encoding="utf-8",
    )


# --- invalid --------------------------------------------------------------

def case_advanced_without_contiguity() -> None:
    d = fresh(
        "invalid",
        "advanced-without-contiguity",
        "应报错：crawl_state.advanced=true 但 contiguous=false。\n"
        "水位线只能在连续走完时推进，否则下次抓取会从一个假的下界开始，"
        "中间那段永远补不回来，且事后无从发现。",
    )
    m = load_manifest(d)
    m["crawl_state"][0]["contiguous"] = False
    save_manifest(d, m)


def case_advanced_with_gaps() -> None:
    d = fresh(
        "invalid",
        "advanced-with-gaps",
        "应报错：crawl_state.advanced=true 但 gaps 非空。同上——有缺口就不许推进水位线。",
    )
    m = load_manifest(d)
    m["crawl_state"][0]["gaps"] = [
        {"reason": "fetch_failed", "detail": "第 3 页连续失败"}
    ]
    save_manifest(d, m)


def case_dangling_claimed_source() -> None:
    d = fresh(
        "invalid",
        "dangling-claimed-source",
        "应报错：coverage.claimed_source 指向不存在的 capture_id。\n"
        "声明数量必须能追溯回读出它的那张页面，否则它只是一个无从核实的数字。",
    )
    m = load_manifest(d)
    m["coverage"][0]["claimed_source"] = f"{BUNDLE_ID}#999999"
    save_manifest(d, m)


def case_claimed_without_source() -> None:
    d = fresh(
        "invalid",
        "claimed-without-source",
        "应报错：claimed_count 非 null 但 claimed_source 为 null。",
    )
    m = load_manifest(d)
    m["coverage"][0]["claimed_source"] = None
    save_manifest(d, m)


def case_forbidden_completeness_field() -> None:
    d = fresh(
        "invalid",
        "coverage-completeness-field",
        "应报错：coverage 中出现 completeness/reconciled。\n"
        "豆瓣有多套审查/屏蔽机制，其计数有时统计于审查之前、有时之后，"
        "因此声明数量在任何情况下都不能作为完整性判据。规范刻意不提供这些字段——"
        "不存在的字段无法被误用。完整性证据在 crawl_state 里。",
    )
    m = load_manifest(d)
    m["coverage"][0]["completeness"] = "complete"
    save_manifest(d, m)


def case_segment_hash_mismatch() -> None:
    d = fresh(
        "invalid",
        "segment-hash-mismatch",
        "应报错：段文件 sha256 与 manifest 不符（档案已损坏或被篡改）。",
    )
    (d / SEGMENT).write_bytes((d / SEGMENT).read_bytes() + b"\x00")


def case_line_count_mismatch() -> None:
    d = fresh(
        "invalid",
        "index-line-count-mismatch",
        "应报错：index 实际行数与 manifest.index.line_count 不符（导出被截断）。",
    )
    m = load_manifest(d)
    m["index"]["line_count"] = 99
    save_manifest(d, m)


def case_duplicate_capture_id() -> None:
    d = fresh(
        "invalid",
        "duplicate-capture-id",
        "应报错：capture_id 重复。空洞合法，重复非法——重复意味着索引指向不明。",
    )
    lines = index_lines(d)
    lines[1]["capture_id"] = lines[0]["capture_id"]
    save_index(d, lines)


def case_naive_timestamp() -> None:
    d = fresh(
        "invalid",
        "naive-timestamp",
        "应报错：observed_at 缺少时区偏移。\n"
        "豆瓣页面给的是不带时区的裸时间，若在此处也丢掉偏移量，"
        "海外时区的用户会得到整体偏移数小时的水位线。",
    )
    lines = index_lines(d)
    lines[0]["observed_at"] = "2026-07-28 10:15:03"
    save_index(d, lines)


def case_missing_intent() -> None:
    d = fresh(
        "invalid",
        "missing-intent",
        "应报错：index 行缺少 intent。\n"
        "一份标记列表的第 7 页，事后无法区分它当初是「看过」还是「想看」的第 7 页。"
        "此字段丢失不可恢复。",
    )
    lines = index_lines(d)
    del lines[0]["intent"]
    save_index(d, lines)


def case_bad_offset() -> None:
    d = fresh(
        "invalid",
        "bad-offset",
        "应报错：offset 处不是合法的 gzip member。索引与段文件已失去对应关系。",
    )
    lines = index_lines(d)
    lines[0]["offset"] = lines[0]["offset"] + 3
    save_index(d, lines)


def case_missing_checkpoint() -> None:
    d = fresh(
        "invalid",
        "missing-checkpoint",
        "应报错：status=in_progress 但没有 checkpoint.json，这份半成品无法续抓。",
    )
    m = load_manifest(d)
    m["status"] = "in_progress"
    m["completed_at"] = None
    save_manifest(d, m)


def case_empty_payload_ok() -> None:
    d = fresh(
        "invalid",
        "empty-payload-marked-ok",
        "应报错：载荷零长度却记为 verdict=ok（SPEC §6.5.2）。\n"
        "（这份夹具是把 content_sha256 改成空串的哈希、正文原样留着造出来的，\n"
        " 所以现在还会额外报一条 content_sha256 不符——同一句谎被两条检查\n"
        " 分别看见，不是两个毛病。）\n"
        "真实旧档案里出现过 7 个零字节文件，与一次会话失效同批产生，"
        "文件名齐全地躺在目录里，磁盘上没有任何东西表明抓取失败过——"
        "下游只会看到「文件在」。空响应必须如实判定。",
    )
    lines = index_lines(d)
    # 空字符串的 sha256
    lines[0]["content_sha256"] = (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    lines[0]["verdict"] = "ok"
    save_index(d, lines)


def case_content_hash_mismatch() -> None:
    d = fresh(
        "invalid",
        "content-hash-mismatch",
        "应报错（完整性）：index 行的 content_sha256 与该 offset 处的正文不符。\n"
        "这一条模拟的是【自洽的生产者 bug】：段文件没动、manifest 里的 index\n"
        "sha256 已经改成与篡改后的索引一致，所以段哈希、gzip 的 CRC、行数\n"
        "全都对得上。在加这条检查之前，这份 bundle 会被判为完全合格。\n"
        "\n"
        "它比 bad-offset 窄：偏移量错位由 warc_record_id 那一条抓，位腐坏由\n"
        "gzip 自己的 CRC 抓。剩给它的是「记录 id 对得上、gzip 也解得开，但\n"
        "正文不是当初摘要的那一段」——写字节与算哈希这两步之间出的岔子。",
    )
    lines = index_lines(d)
    # 换成另一个合法的 sha256（就是「不是这条正文的那个」）。
    # 【不能】用空串的哈希：那会撞上 SPEC §6.5.2 那条规则，用例就同时踩中
    # 两条检查，谁也说不清它到底在测哪一条。
    lines[0]["content_sha256"] = hashlib.sha256(b"another page entirely").hexdigest()
    save_index(d, lines)  # fix_hash=True —— 让 manifest 自洽，这才是要模拟的形状


def case_record_count_mismatch() -> None:
    d = fresh(
        "invalid",
        "record-count-mismatch",
        "应报错：段的 record_count 与指向该段的 index 行数不符。\n"
        "常见成因是把段首的 warcinfo 也算进了 record_count——它不是一次捕获，\n"
        "不进 index，也不该计入。两个数对不上意味着段与索引已经失去对应关系。",
    )
    m = load_manifest(d)
    m["segments"][0]["record_count"] = 3  # 实际 index 里只有 2 行
    save_manifest(d, m)


def case_bad_enumeration() -> None:
    d = fresh(
        "invalid",
        "bad-enumeration",
        "应报错：crawl_state.enumeration 取值非法。\n"
        "下游据此判断有无资格推断删除；取值不明时，猜错的方向是静默地把没删的当成删了。",
    )
    m = load_manifest(d)
    m["crawl_state"][0]["enumeration"] = "maybe"
    save_manifest(d, m)


def case_full_with_floor() -> None:
    d = fresh(
        "invalid",
        "full-with-floor",
        "应报错：这条路线有 floor_time，enumeration 却写 full。\n"
        "走到下界就停的路线，下界以下这次根本没看过，所以是 bounded。\n"
        "写成 full 等于告诉下游「整份都枚举过了，缺的就是删掉的」——\n"
        "拿一份增量与一份全量做差，就会把没删的当成删了。",
    )
    m = load_manifest(d)
    m["crawl_state"][0]["floor_time"] = "2026-07-20T00:00:00+08:00"
    m["crawl_state"][0]["enumeration"] = "full"
    save_manifest(d, m)


def case_valid_unknown_verdict() -> None:
    """bundle/1.2：verdict=unknown 配 verdict_reason 必须【合法】。

    守的是两件事：新取值进了封闭词表（1.1 的校验器会拒绝，那是对的），
    以及 verdict_reason 是开放词表——校验器不得因为不认识某个取值就报错。
    """
    d = fresh(
        "valid",
        "unknown-verdict",
        "应通过：bundle/1.2 的 verdict=unknown + verdict_reason。\n"
        "unknown 与 blocked 处置相反（前者该改抽取器，后者该等一等），必须分开表示。\n"
        "verdict_reason 是开放词表，读者遇到不认识的取值必须原样保留、不得报错。",
    )
    lines = index_lines(d)
    lines[1]["verdict"] = "unknown"
    lines[1]["verdict_reason"] = "frame_anchors_missing"
    lines[1]["note"] = "判不出来：一个内容区块都没有（试过 class=\"note-container\"）"
    save_index(d, lines)
    m = load_manifest(d)
    m["spec_version"] = "bundle/1.2"
    save_manifest(d, m)
    readme = d / "README.txt"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("bundle/1.0", "bundle/1.2"),
        encoding="utf-8",
    )


def case_valid_from_the_future() -> None:
    """一份「来自未来」的档案：更高的小版本 + 今天还不认识的字段与取值。

    ## 为什么需要它

    规范 §10 写着两条读者义务：容忍未知字段、原样保留开放词表里的未知取值。
    但**在此之前没有任何东西验证过它们**——一致性用例验的都是「写出来的东西合不合
    规范」，那是生产者方向；读者方向一条都没有。

    `bundle/1.0` 从未公开发布过，所以对它不兼容是可以接受的。真正必须守住的是反过来
    那一半：**今天写好的读取端，将来遇到更新的档案不能崩、不能静默丢东西。**
    这一条今天就能验，不必等到真有 1.3。

    ## 这里放什么、不放什么

    放：更高的小版本号、manifest 与 index 行上的未知字段、开放词表（intent、
    route_key）里的未知取值。这些**校验器必须放行**——放不行就说明 schema 把「只增
    不改」写死了，而那正是 §10 要避免的。

    不放：封闭词表（verdict、surface、capture_fidelity）的未知取值。那种情况按 §10
    是小版本变更，**旧校验器拒绝它是刻意的**，所以它不属于 valid 用例。读者对那一类
    的义务是「保守处置」（不得当成 ok），由各实现自己的测试覆盖。
    """
    d = fresh(
        "valid",
        "from-the-future",
        "应通过：来自未来的档案。更高的小版本号、未知字段、开放词表里的未知取值。\n"
        "规范 §10 要求读者容忍未知字段、并原样保留开放词表的未知取值——这一条验的正是它。\n"
        "校验器若拒绝本例，说明 schema 把「只增不改」写死了，那是 schema 的问题。",
    )
    m = load_manifest(d)
    # 一个我们今天不认识的小版本。pattern 是 ^bundle/1\.[0-9]+$，所以它合法。
    m["spec_version"] = "bundle/1.9"
    # 未来版本新增的可选字段。读者必须忽略它，重写时不得丢弃。
    m["future_top_level_field"] = {"note": "1.9 新增的东西，今天的读者不认识"}
    save_manifest(d, m)

    lines = index_lines(d)
    # 开放词表：未知取值必须原样保留，不得猜测、不得丢弃。
    lines[1]["intent"] = "future.route.that.does.not.exist.yet"
    lines[1]["route_key"] = "future.route"
    lines[1]["future_line_field"] = 42
    save_index(d, lines)

    readme = d / "README.txt"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("bundle/1.0", "bundle/1.9"),
        encoding="utf-8",
    )


def main() -> None:
    if not EXAMPLE.exists():
        raise SystemExit("请先运行 examples/make-minimal-bundle.py")
    for kind in ("valid", "invalid"):
        (HERE / kind).mkdir(parents=True, exist_ok=True)
    case_valid_with_holes()
    case_valid_asset_capture()
    case_valid_from_the_future()
    case_valid_cross_bundle_parent()
    case_valid_unknown_verdict()
    case_advanced_without_contiguity()
    case_advanced_with_gaps()
    case_dangling_claimed_source()
    case_claimed_without_source()
    case_forbidden_completeness_field()
    case_segment_hash_mismatch()
    case_line_count_mismatch()
    case_duplicate_capture_id()
    case_naive_timestamp()
    case_missing_intent()
    case_bad_offset()
    case_missing_checkpoint()
    case_bad_enumeration()
    case_full_with_floor()
    case_empty_payload_ok()
    case_record_count_mismatch()
    case_content_hash_mismatch()
    print("用例已生成。")


if __name__ == "__main__":
    main()
