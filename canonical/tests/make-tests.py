#!/usr/bin/env python3
"""生成 canonical 的一致性用例。

    python3 make-tests.py

## 与 bundle/v1/tests 不是一回事

那边的反例是**坏掉的文档**：把一个合法 bundle 破坏一处，校验器应当拒绝它。
这边不行——canonical 的产出是解析器算出来的，光看文档合不合 schema 说明不了什么。
canonical 真正的不变量全是**行为**上的：

> 给这样一堆 bundle，解析器**不得**得出那样的结论。

所以每个用例是：一组**合法**的 bundle（合法这一点很关键，它们不是坏数据），
外加一句「解析器必须怎样、且不得怎样」。一个天真的实现会在每个用例上翻车，
而且翻车的时候**不会报错**——它会安安静静地产出错数据。这正是要拦的。

## 用例是实现无关的

输入是 bundle（规范里已经定死的格式），断言写在 expect.json 里。任何语言写的
解析器都能跑这套；`doubak-data-parser` 的 test/conformance.test.js 是第一个。
"""

import hashlib
import importlib.util
import json
import pathlib
import shutil

HERE = pathlib.Path(__file__).parent
SPEC = HERE.parent.parent / "bundle" / "v1"

# WARC 的写法从 bundle 那边的例子生成器【导入】而不是抄一份——抄的那份一旦漂移，
# 用例就会去校验一种规范里并不存在的字节布局，而且看起来还全是绿的。
_spec = importlib.util.spec_from_file_location(
    "make_minimal_bundle", SPEC / "examples" / "make-minimal-bundle.py"
)
mkb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mkb)

USER = {"user_id": "82160871", "username": "example"}


def list_page(items, logged_in=True, claimed=None):
    """一张电影「看过」列表页。

    结构照真实页面写：条目容器 `item comment-item`、id 走 /subject/N/、
    日期在 span.date、评分在 class 上、rel 是状态的第二份编码。
    """
    rows = []
    for it in items:
        rating = f'<span class="rating{it["rating"]}-t"></span>' if it.get("rating") else ""
        tags = f'<span class="tags">标签: {it["tags"]}</span>' if it.get("tags") else ""
        comment = f'<span class="comment">{it["comment"]}</span>' if it.get("comment") else ""
        rows.append(
            f'<div class="item comment-item" data-cid="{it["cid"]}">'
            f'<div class="pic"><a href="https://movie.douban.com/subject/{it["id"]}/">'
            f'<img src="https://img1.doubanio.com/view/photo/s_ratio_poster/public/p{it["id"]}.jpg"></a></div>'
            f'<li class="title"><a><em>{it.get("title", "片名")}</em></a></li>'
            f'<li class="intro">{it.get("meta", "2020 / 导演 / 剧情")}</li>'
            f'{rating}<span class="date">{it["date"]}</span>{tags}{comment}'
            f'<a class="d_link" rel="{it["id"]}:P"></a></div>'
        )
    nav = (
        '<li class="nav-user-account"><a href="/accounts/logout">退出</a></li>'
        if logged_in
        else '<li><a class="nav-login" href="/accounts/login">登录</a></li>'
    )
    n = claimed if claimed is not None else len(items)
    return (
        f"<html><head><title>我看过的影视</title></head><body>{nav}"
        f'<h1>我看过的影视({n})</h1><div class="grid-view">{"".join(rows)}</div>'
        "</body></html>"
    ).encode()


def make_bundle(root, bundle_id, pages, *, status="complete", crawl_state=None, previous=None):
    """造一份真的能通过 bundle 校验器的档案。

    `pages` 是 [(intent, route_key, verdict, observed_at, html_bytes)]。
    """
    d = root / f"doubak-bundle-{bundle_id}"
    d.mkdir(parents=True, exist_ok=True)
    seg_name = f"data-{bundle_id}-00001.warc.gz"

    info_block = (
        f"software: doubak-conformance/0\r\nformat: WARC File Format 1.1\r\n"
        f"isPartOf: {bundle_id}\r\n"
    ).encode()
    seg = mkb.gzip_member(
        mkb.warc_record(
            [
                ("WARC-Type", "warcinfo"),
                ("WARC-Record-ID", "<urn:uuid:00000000-0000-4000-8000-000000000001>"),
                ("WARC-Date", "2026-07-28T02:15:00Z"),
                ("WARC-Filename", seg_name),
                ("WARC-Block-Digest", mkb.sha1_base32(info_block)),
                ("Content-Type", "application/warc-fields"),
            ],
            info_block,
        )
    )

    index, n = [], 0
    for intent, route_key, verdict, observed_at, body in pages:
        n += 1
        url = f"https://movie.douban.com/people/example/collect?start={n - 1}"
        block = mkb.http_response(
            "HTTP/1.1 200 OK",
            [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))],
            body,
        )
        rec = mkb.warc_record(
            [
                ("WARC-Type", "response"),
                ("WARC-Record-ID", f"<urn:uuid:00000000-0000-4000-8000-{n:012d}>"),
                ("WARC-Date", "2026-07-28T02:16:00Z"),
                ("WARC-Target-URI", url),
                ("WARC-Block-Digest", mkb.sha1_base32(block)),
                ("WARC-Payload-Digest", mkb.sha1_base32(body)),
                ("Content-Type", "application/http;msgtype=response"),
            ],
            block,
        )
        member = mkb.gzip_member(rec)
        index.append(
            {
                "capture_id": f"{bundle_id}#{n:06d}",
                "warc_record_id": f"urn:uuid:00000000-0000-4000-8000-{n:012d}",
                "segment": seg_name,
                "offset": len(seg),
                "length": len(member),
                "url": url,
                "url_key": url,
                "url_key_rules": "v1",
                "intent": intent,
                "route_key": route_key,
                "surface": "html",
                "verdict": verdict,
                "capture_fidelity": "decoded_body+filtered_headers",
                "observed_at": observed_at,
                "http_status": 200,
                "content_type": "text/html; charset=utf-8",
                "content_sha256": hashlib.sha256(body).hexdigest(),
                "parent_capture_id": None,
                "cursor": None,
            }
        )
        seg += member

    (d / seg_name).write_bytes(seg)
    idx_text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in index)
    (d / f"index-{bundle_id}.ndjson").write_text(idx_text, encoding="utf-8")

    # 档案必须自解释（bundle SPEC §2）。这些夹具是【合法的 bundle】——那正是用例
    # 设计的要害：它们不是坏数据，坏的是天真的解析器从它们身上得出的结论。
    (d / "README.txt").write_text(
        "doubak 备份档案 / doubak backup bundle\n"
        "======================================\n\n"
        "规范版本 / Spec version: bundle/1.1\n"
        f"档案编号 / Bundle ID:    {bundle_id}\n\n"
        "这是 canonical 一致性用例的合成夹具，不含任何真人数据。\n"
        "见同级目录的 EXPECTED.txt。\n\n"
        "怎么打开\n--------\n"
        "data-*.warc.gz 是标准 WARC，pywb / ReplayWeb.page 可直接打开；\n"
        "index-*.ndjson 每行一条捕获记录，用 jq 即可查阅。\n",
        encoding="utf-8",
    )

    # status=aborted / in_progress 的档案【必须】有 checkpoint（bundle SPEC）。
    # 夹具要是合法的 bundle，否则「被中断的档案照样能读」这个用例就变成了
    # 「坏档案能不能读」——那是另一个问题。
    if status in ("aborted", "in_progress"):
        (d / "checkpoint.json").write_text(
            json.dumps(
                {
                    "spec_version": "bundle/1.1",
                    "bundle_id": bundle_id,
                    "paused_at": "2026-07-28T10:16:30+08:00",
                    "pause_reason": "user_paused",
                    "last_capture_id": index[-1]["capture_id"] if index else None,
                    "routes": [],
                    "frontier": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if status is not None:
        (d / "manifest.json").write_text(
            json.dumps(
                {
                    "spec_version": "bundle/1.1",
                    "bundle_id": bundle_id,
                    "previous_bundle_id": previous,
                    "status": status,
                    "created_at": "2026-07-28T10:15:00+08:00",
                    "completed_at": "2026-07-28T10:16:00+08:00",
                    "producer": {"name": "doubak-conformance", "version": "0"},
                    "account": USER,
                    "timezone_assumption": "Asia/Shanghai",
                    "segments": [
                        {
                            "filename": seg_name,
                            "bytes": len(seg),
                            "sha256": hashlib.sha256(seg).hexdigest(),
                            "record_count": len(index),
                            "first_capture_id": index[0]["capture_id"],
                            "last_capture_id": index[-1]["capture_id"],
                        }
                    ],
                    "index": {
                        "filename": f"index-{bundle_id}.ndjson",
                        "sha256": hashlib.sha256(idx_text.encode()).hexdigest(),
                        "line_count": len(index),
                    },
                    "coverage": [],
                    "crawl_state": crawl_state or [],
                    "counts": {"by_verdict": {}, "by_surface": {}, "by_intent": {}},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return d


def cs(route_key, **over):
    base = {
        "route_key": route_key,
        "intent": "interest.list.movie.collect",
        "high_water_time": "2026-07-01T00:00:00+08:00",
        "high_water_raw": "2026-07-01",
        "high_water_ids": [],
        "low_water_time": None,
        "low_water_raw": None,
        "floor_time": None,
        "floor_from_bundle_id": None,
        "enumeration": "full",
        "contiguous": True,
        "gaps": [],
        "advanced": True,
        "completed_at": "2026-07-28T10:16:00+08:00",
        "bundle_id": "x",
    }
    base.update(over)
    return base


def case(name, why, expect):
    d = HERE / "cases" / name
    if d.exists():
        shutil.rmtree(d)
    (d / "bundles").mkdir(parents=True)
    (d / "EXPECTED.txt").write_text(why + "\n", encoding="utf-8")
    (d / "expect.json").write_text(
        json.dumps(expect, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return d / "bundles"


ROUTE = ("interest.list.movie.collect", "interest.movie.collect")
T1, T2 = "2026-07-28T10:16:00+08:00", "2026-08-04T10:16:00+08:00"


def c_login_is_not_content():
    b = case(
        "login-is-not-content",
        "【login 不得作为内容摄取】\n"
        "那 3 条标记只出现在一份 verdict=login 的捕获里。页面结构完整、条目一条不少\n"
        "——但那是公开视图：标签整批消失，私密条目根本不在里面。\n"
        "实测前代档案 2023-01 那批 105 张电影页全是匿名抓的，条目 1554 条，标签 0 个\n"
        "（前后两批是 945 和 1051）。当内容读会得出「用户删光了标签又加回来」。\n"
        "解析器必须产出 0 条标记。",
        {"marks": 0},
    )
    items = [
        {"id": "101", "cid": "9001", "date": "2026-07-01", "rating": 4},
        {"id": "102", "cid": "9002", "date": "2026-07-02"},
        {"id": "103", "cid": "9003", "date": "2026-07-03"},
    ]
    make_bundle(
        b, "20260728T101500Z-aaaaa1",
        [(*ROUTE, "login", T1, list_page(items, logged_in=False))],
        crawl_state=[cs("interest.movie.collect")],
    )


def c_incremental_grants_no_absence():
    b = case(
        "incremental-grants-no-absence",
        "【增量抓取不得授予「整条路线」的缺失推断权】\n"
        "第一份是全量（enumeration=full），第二份是增量（bounded + floor_time），\n"
        "第二份里少了一条标记。天真的实现会判定那条被删了——而增量只读到下界为止，\n"
        "下界以下这次压根没看。\n"
        "解析器必须：两条标记都在（第一份看到的不许丢），且第二份那次观测的\n"
        "absence_authority 是 above_floor 而不是 whole_route。",
        {"marks": 2, "authorities": ["whole_route", "above_floor"]},
    )
    a = [
        {"id": "201", "cid": "9101", "date": "2026-07-01"},
        {"id": "202", "cid": "9102", "date": "2026-06-01"},
    ]
    make_bundle(b, "20260728T101500Z-bbbbb1", [(*ROUTE, "ok", T1, list_page(a))],
                crawl_state=[cs("interest.movie.collect")])
    make_bundle(b, "20260804T101500Z-bbbbb2", [(*ROUTE, "ok", T2, list_page(a[:1]))],
                previous="20260728T101500Z-bbbbb1",
                crawl_state=[cs("interest.movie.collect", enumeration="bounded",
                                floor_time="2026-07-01T00:00:00+08:00")])


def c_gap_revokes_authority():
    """两个条件【各测一个】，不许合在一起。

    第一版把 contiguous=False 与 gaps=[...] 写在同一份夹具里，结果是：把解析器里
    检查 gaps 的那一行删掉，用例照样通过——因为 contiguous 那一条替它挡住了。
    一个只看 contiguous 的实现会蒙混过关，而它是错的：`contiguous: true` 配上
    非空 gaps 是可表示的（manifest 只在 advanced=true 时才拦这个组合）。

    合并条件的用例测的是「这两条里至少有一条在起作用」，那不是我们想守的东西。
    """
    b = case(
        "gap-revokes-authority",
        "【记了缺口就没有任何缺失推断权】\n"
        "这一份 enumeration=full、status=complete、**contiguous 还是 true**——只是记了\n"
        "一处缺口。解析器仍然必须把 absence_authority 降为 none。\n"
        "不是「缺口那一段不算」：缺口意味着我们不知道漏了什么，而漏掉的东西完全\n"
        "可能正好在别处。",
        {"marks": 1, "authorities": ["none"]},
    )
    make_bundle(b, "20260728T101500Z-ccccc1",
                [(*ROUTE, "ok", T1, list_page([{"id": "301", "cid": "9201", "date": "2026-07-01"}]))],
                crawl_state=[cs("interest.movie.collect", contiguous=True,
                                gaps=[{"reason": "blocked"}], advanced=False)])


def c_discontiguous_revokes_authority():
    b = case(
        "discontiguous-revokes-authority",
        "【连续性证明不成立就没有缺失推断权】\n"
        "与 gap-revokes-authority 是**两个独立的条件**，各测一个：这一份 gaps 是空的，\n"
        "只是 contiguous=false。合成一个用例的话，删掉解析器里任何一条检查都测不出来。\n"
        "解析器必须把 absence_authority 降为 none。",
        {"marks": 1, "authorities": ["none"]},
    )
    make_bundle(b, "20260728T101500Z-ccccc2",
                [(*ROUTE, "ok", T1, list_page([{"id": "302", "cid": "9202", "date": "2026-07-01"}]))],
                crawl_state=[cs("interest.movie.collect", contiguous=False,
                                gaps=[], advanced=False)])


def c_aborted_still_readable():
    b = case(
        "aborted-still-readable",
        "【被中断的抓取，看到的东西照样是真的】\n"
        "这一份 status=aborted。它的数据【必须】照常摄取——丢弃的应该是「凭它能下\n"
        "什么结论」，不是数据本身。\n"
        "解析器必须：产出 2 条标记，且 absence_authority 为 none。",
        {"marks": 2, "authorities": ["none"]},
    )
    make_bundle(b, "20260728T101500Z-ddddd1",
                [(*ROUTE, "ok", T1, list_page([
                    {"id": "401", "cid": "9301", "date": "2026-07-01"},
                    {"id": "402", "cid": "9302", "date": "2026-07-02"}]))],
                status="aborted", crawl_state=[cs("interest.movie.collect")])


def c_catalog_churn_is_not_user_edit():
    b = case(
        "catalog-churn-is-not-user-edit",
        "【豆瓣改目录数据，不得表现为用户编辑了标记】\n"
        "两份档案里同一条标记：status / 日期 / 评分 / 短评 / 标签一模一样，只有那一行\n"
        "无标签的元信息变了（上映日期从「2027(美国)」变成「2027(未定)」——真实档案里\n"
        "撞到过 3 条）。\n"
        "解析器必须：这条标记只有 1 条修订。元信息属于作品，不属于标记。",
        {"marks": 1, "mark_revisions": 1},
    )
    it = {"id": "501", "cid": "9401", "date": "2026-07-01", "rating": 4,
          "comment": "很好看", "tags": "经典"}
    make_bundle(b, "20260728T101500Z-eeeee1",
                [(*ROUTE, "ok", T1, list_page([{**it, "meta": "2027(美国) / 甲 / 乙"}]))],
                crawl_state=[cs("interest.movie.collect")])
    make_bundle(b, "20260804T101500Z-eeeee2",
                [(*ROUTE, "ok", T2, list_page([{**it, "meta": "2027(未定) / 甲 / 乙"}]))],
                previous="20260728T101500Z-eeeee1",
                crawl_state=[cs("interest.movie.collect")])


def c_status_transition_is_one_record():
    b = case(
        "status-transition-is-one-record",
        "【状态迁移是一条记录的两次修订，不是一删一增】\n"
        "同一个 data-cid，从「想看」变成「看过」，日期、评分、短评全都跟着换。\n"
        "身份取 (作品, 状态) 的话这会变成两条记录，修订历史随之作废。\n"
        "解析器必须：产出 1 条标记、2 条修订，且 identity_layer 是 upstream_id。",
        {"marks": 1, "mark_revisions": 2, "identity_layers": ["upstream_id"]},
    )
    make_bundle(b, "20260728T101500Z-fffff1",
                [("interest.list.movie.wish", "interest.movie.wish", "ok", T1,
                  list_page([{"id": "601", "cid": "9501", "date": "2026-07-18",
                              "comment": "能上6分我觉得都是国产好片"}]))],
                crawl_state=[cs("interest.movie.wish", intent="interest.list.movie.wish")])
    make_bundle(b, "20260804T101500Z-fffff2",
                [(*ROUTE, "ok", T2,
                  list_page([{"id": "601", "cid": "9501", "date": "2026-08-01",
                              "rating": 4, "comment": "确实还不错"}]))],
                previous="20260728T101500Z-fffff1",
                crawl_state=[cs("interest.movie.collect")])


def c_unknown_verdict_is_not_ok():
    b = case(
        "unknown-verdict-is-not-ok",
        "【封闭词表出现未知取值时，当作判不出来，不当作 ok】\n"
        "这一份的 verdict 是 quarantined——本解析器不认识。它意味着生产者知道一种\n"
        "我们不认识的失败方式；把它当成 ok 的代价，正是这套规则从头到尾在防的事。\n"
        "这个不对称是刻意的。\n"
        "解析器必须产出 0 条标记，并报出一条 unknown_verdict 告警。",
        {"marks": 0, "warning_types": ["unknown_verdict"]},
    )
    make_bundle(b, "20260728T101500Z-99999a",
                [(*ROUTE, "quarantined", T1,
                  list_page([{"id": "701", "cid": "9601", "date": "2026-07-01"}]))],
                crawl_state=[cs("interest.movie.collect")])


def c_no_manifest_still_readable():
    b = case(
        "no-manifest-still-readable",
        "【没有 manifest 的档案照样要能读】\n"
        "manifest.json 只在收尾时写一次，所以整个抓取过程中它都不存在。那些捕获是\n"
        "真实观测，必须照常摄取；只是没有连续性证明，所以没有缺失推断权。\n"
        "解析器必须：产出 1 条标记，absence_authority 为 none，且不得抛异常。\n\n"
        "注意：这份夹具【故意】过不了 bundle 校验器（「缺少 manifest.json」）——它模拟的\n"
        "正是抓取进行到一半的档案，而那时 manifest 还没写。别去「修」它。",
        {"marks": 1, "authorities": ["none"]},
    )
    make_bundle(b, "20260728T101500Z-8888a1",
                [(*ROUTE, "ok", T1, list_page([{"id": "801", "cid": "9701", "date": "2026-07-01"}]))],
                status=None)


def main():
    (HERE / "cases").mkdir(exist_ok=True)
    c_login_is_not_content()
    c_incremental_grants_no_absence()
    c_gap_revokes_authority()
    c_discontiguous_revokes_authority()
    c_aborted_still_readable()
    c_catalog_churn_is_not_user_edit()
    c_status_transition_is_one_record()
    c_unknown_verdict_is_not_ok()
    c_no_manifest_still_readable()
    print("用例已生成。")


if __name__ == "__main__":
    main()
