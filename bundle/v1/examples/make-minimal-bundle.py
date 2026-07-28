#!/usr/bin/env python3
"""生成 examples/minimal-bundle/ —— 一个最小但完全合法的 bundle。

例子必须是真的：偏移量、长度、摘要都由本脚本实算，不是手写的。
改动 schema 后重跑本脚本，再跑校验器。

    python3 make-minimal-bundle.py
"""

import base64
import gzip
import hashlib
import io
import json
import pathlib

HERE = pathlib.Path(__file__).parent
OUT = HERE / "minimal-bundle"

BUNDLE_ID = "20260728T101500Z-a3f9c1"
SEGMENT = f"data-{BUNDLE_ID}-00001.warc.gz"
INDEX = f"index-{BUNDLE_ID}.ndjson"
TZ = "+08:00"


def sha1_base32(data: bytes) -> str:
    """WARC 惯例的摘要形式：sha1 + base32。"""
    return "sha1:" + base64.b32encode(hashlib.sha1(data).digest()).decode()


def gzip_member(data: bytes) -> bytes:
    """把一条记录压成独立的 gzip member，使其可单独定位与解压，
    并让撕裂的文件尾部可被检测和截断修复。"""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        f.write(data)
    return buf.getvalue()


def warc_record(headers: "list[tuple[str, str]]", block: bytes) -> bytes:
    out = b"WARC/1.1\r\n"
    for k, v in headers:
        out += f"{k}: {v}\r\n".encode()
    out += f"Content-Length: {len(block)}\r\n".encode()
    out += b"\r\n" + block + b"\r\n\r\n"
    return out


def http_response(status_line: str, headers: "list[tuple[str, str]]", body: bytes) -> bytes:
    out = f"{status_line}\r\n".encode()
    for k, v in headers:
        out += f"{k}: {v}\r\n".encode()
    return out + b"\r\n" + body


# --- 两条捕获：一条 HTML 页面（保真面），一条 API 响应（枚举面）----------------

HTML_BODY = (
    "<!DOCTYPE html><html><head><title>mewcatcher 的广播</title></head><body>"
    '<div class="status-wrapper"><div class="status-item" data-target-type="sns">'
    '<span class="created_at" title="2026-07-26 12:34:00">'
    '<a href="https://www.douban.com/people/82160871/status/9351468114/'
    '?_spm_id=ODIxNjA4NzE&amp;_dtcc=1">7月26日</a></span>'
    "</div></div></body></html>"
).encode()

API_BODY = json.dumps(
    {"total": 1234, "count": 1, "start": 0, "interests": []},
    ensure_ascii=False,
).encode()

CAPTURES = [
    {
        "capture_id": f"{BUNDLE_ID}#000001",
        "warc_record_id": "urn:uuid:3f2a8c11-0d4e-4a91-9b77-1c2e5a8f0011",
        "url": "https://www.douban.com/people/82160871/statuses?p=1",
        "url_key": "https://www.douban.com/people/82160871/statuses?p=1",
        "intent": "broadcast.timeline",
        "route_key": "broadcast.timeline",
        "surface": "html",
        "verdict": "ok",
        "observed_at": f"2026-07-28T10:15:03{TZ}",
        "content_type": "text/html; charset=utf-8",
        "parent_capture_id": None,
        "cursor": {"kind": "page", "value": 1},
        "body": HTML_BODY,
        "http_headers": [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Date", "Tue, 28 Jul 2026 02:15:03 GMT"),
        ],
    },
    {
        "capture_id": f"{BUNDLE_ID}#000002",
        "warc_record_id": "urn:uuid:7c19b4de-55a0-4c2f-8f31-9d0b6e2a4402",
        # 声明数量的来源：这条捕获被 coverage.claimed_source 指着
        "url": "https://m.douban.com/rexxar/api/v2/user/82160871/interests"
               "?ck=REDACTED&count=1&for_mobile=1",
        "url_key": "https://m.douban.com/rexxar/api/v2/user/82160871/interests"
                   "?count=1&for_mobile=1",
        "intent": "profile.category_entry.movie",
        "route_key": "interest.movie.collect",
        "surface": "api",
        "verdict": "ok",
        "observed_at": f"2026-07-28T10:15:42{TZ}",
        "content_type": "application/json",
        "parent_capture_id": f"{BUNDLE_ID}#000001",
        "cursor": {"kind": "start", "value": 0},
        "body": API_BODY,
        "http_headers": [
            ("Content-Type", "application/json"),
            ("Date", "Tue, 28 Jul 2026 02:15:42 GMT"),
        ],
    },
]


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    segment_bytes = b""
    index_lines = []

    # 每个段以一条 warcinfo 记录开头（WARC 惯例）。
    warcinfo_block = (
        f"software: doubak-extension/0.1.0\r\n"
        f"format: WARC File Format 1.1\r\n"
        f"isPartOf: {BUNDLE_ID}\r\n"
        f"conformsTo: https://spec.doubak.com/bundle/v1/\r\n"
    ).encode()
    warcinfo = warc_record(
        [
            ("WARC-Type", "warcinfo"),
            ("WARC-Record-ID", "<urn:uuid:00000000-0000-4000-8000-000000000001>"),
            ("WARC-Date", "2026-07-28T02:15:00Z"),
            ("WARC-Filename", SEGMENT),
            ("WARC-Block-Digest", sha1_base32(warcinfo_block)),
            ("Content-Type", "application/warc-fields"),
        ],
        warcinfo_block,
    )
    segment_bytes += gzip_member(warcinfo)

    for cap in CAPTURES:
        block = http_response("HTTP/1.1 200 OK", cap["http_headers"], cap["body"])
        record = warc_record(
            [
                ("WARC-Type", "response"),
                # WARC 要求记录 ID 用尖括号包裹；index.ndjson 里存的是不带尖括号的裸 URI。
                ("WARC-Record-ID", f"<{cap['warc_record_id']}>"),
                ("WARC-Date", "2026-07-28T02:15:03Z"),
                ("WARC-Target-URI", cap["url"]),
                ("WARC-Block-Digest", sha1_base32(block)),
                ("WARC-Payload-Digest", sha1_base32(cap["body"])),
                ("Content-Type", "application/http;msgtype=response"),
            ],
            block,
        )
        member = gzip_member(record)

        index_lines.append(
            {
                "capture_id": cap["capture_id"],
                "warc_record_id": cap["warc_record_id"],
                "segment": SEGMENT,
                "offset": len(segment_bytes),
                "length": len(member),
                "url": cap["url"],
                "url_key": cap["url_key"],
                "url_key_rules": "v1",
                "intent": cap["intent"],
                "route_key": cap["route_key"],
                "surface": cap["surface"],
                "verdict": cap["verdict"],
                "capture_fidelity": "decoded_body+observed_headers",
                "observed_at": cap["observed_at"],
                "http_status": 200,
                "content_type": cap["content_type"],
                "content_sha256": hashlib.sha256(cap["body"]).hexdigest(),
                "parent_capture_id": cap["parent_capture_id"],
                "cursor": cap["cursor"],
            }
        )
        segment_bytes += member

    (OUT / SEGMENT).write_bytes(segment_bytes)

    index_text = "".join(
        json.dumps(line, ensure_ascii=False, sort_keys=False) + "\n" for line in index_lines
    )
    (OUT / INDEX).write_text(index_text, encoding="utf-8")

    manifest = {
        "spec_version": "bundle/1.0",
        "bundle_id": BUNDLE_ID,
        "previous_bundle_id": None,
        "status": "complete",
        "created_at": f"2026-07-28T10:15:00{TZ}",
        "completed_at": f"2026-07-28T10:16:11{TZ}",
        "producer": {
            "name": "doubak-extension",
            "version": "0.1.0",
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "platform": "Chrome/141 Linux",
        },
        "account": {
            "user_id": "82160871",
            "username": "mewcatcher",
            "profile_url": "https://www.douban.com/people/82160871/",
        },
        "timezone_assumption": "Asia/Shanghai",
        "segments": [
            {
                "filename": SEGMENT,
                "bytes": len(segment_bytes),
                "sha256": hashlib.sha256(segment_bytes).hexdigest(),
                "record_count": len(CAPTURES),
                "first_capture_id": CAPTURES[0]["capture_id"],
                "last_capture_id": CAPTURES[-1]["capture_id"],
            }
        ],
        "index": {
            "filename": INDEX,
            "sha256": hashlib.sha256(index_text.encode()).hexdigest(),
            "line_count": len(index_lines),
        },
        "coverage": [
            {
                "route_key": "interest.movie.collect",
                "intent": "interest.list.movie.collect",
                "claimed_count": 1234,
                "claimed_raw": "{\"total\": 1234}",
                "claimed_source": f"{BUNDLE_ID}#000002",
                "claimed_observed_at": f"2026-07-28T10:15:42{TZ}",
                "captured_count": 0,
                "delta": -1234,
            },
            {
                # 广播没有可信的声明数量，故为 null。null ≠ 0。
                "route_key": "broadcast.timeline",
                "intent": "broadcast.timeline",
                "claimed_count": None,
                "claimed_raw": None,
                "claimed_source": None,
                "claimed_observed_at": None,
                "captured_count": 1,
                "delta": None,
            },
        ],
        "crawl_state": [
            {
                "route_key": "broadcast.timeline",
                "intent": "broadcast.timeline",
                "high_water_time": f"2026-07-26T12:34:00{TZ}",
                "high_water_raw": "2026-07-26 12:34:00",
                "high_water_ids": ["9351468114"],
                "floor_time": None,
                "enumeration": "bounded",
                "contiguous": True,
                "gaps": [],
                "advanced": True,
                "completed_at": f"2026-07-28T10:16:11{TZ}",
                "bundle_id": BUNDLE_ID,
            }
        ],
        "counts": {
            "by_verdict": {"ok": 2},
            "by_surface": {"html": 1, "api": 1},
            "by_intent": {"broadcast.timeline": 1, "profile.category_entry.movie": 1},
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # README.txt 是档案的一部分，不是文档：它面向的是若干年后偶然拿到这个
    # 目录、而项目本身可能早已不在的人。故必须中英双语、纯文本、自包含。
    (OUT / "README.txt").write_text(
        f"""\
doubak 备份档案 / doubak backup bundle
======================================

规范版本 / Spec version: bundle/1.0
档案编号 / Bundle ID:    {BUNDLE_ID}

这是什么
--------
这是从豆瓣 (douban.com) 抓取的个人数据存档，由 doubak 生成。
它保存的是抓取当时的**原始网页与接口响应**，而不只是提取出来的数据。

文件说明
--------
  manifest.json     本次抓取的清单：抓了谁、产出哪些文件、走到了哪里。
  index-*.ndjson    每行一条抓取记录（JSON）。用 `jq` 即可查阅，无需专门工具。
  data-*.warc.gz    网页与接口响应，标准 WARC 格式。
  assets-*.warc.gz  图片等二进制资源（本例中没有）。
  checkpoint.json   仅在抓取未完成时存在，用于续抓。

怎么打开
--------
  WARC 是国际通行的网页存档格式 (ISO 28500)。可用以下工具打开：
    - ReplayWeb.page   https://replayweb.page/   （浏览器内直接打开，无需安装）
    - pywb             https://github.com/webrecorder/pywb
  索引是 NDJSON（每行一个 JSON 对象），可直接用 jq 查询，例如：
    jq -r '.url' index-*.ndjson

重要提示
--------
  index 中的 capture_fidelity 字段说明每条记录的保真程度。浏览器环境下
  无法取得完全未经处理的原始字节，该字段如实记录了实际成色。
  manifest 中的 coverage 记录了豆瓣当时声称的条目数量，但**该数字不可作为
  档案完整性的依据**；完整性证据在 crawl_state 中。

完整规范 / Full specification
  https://spec.doubak.com/bundle/v1/


What this is
------------
A personal data archive captured from douban.com by doubak. It preserves the
original web pages and API responses as they were at capture time, not merely
the data extracted from them.

Files
  manifest.json     Inventory of this capture run.
  index-*.ndjson    One JSON object per line, one line per capture. Readable
                    with `jq`; no special tooling required.
  data-*.warc.gz    Pages and API responses, standard WARC format.
  assets-*.warc.gz  Images and other binary assets (none in this example).
  checkpoint.json   Present only if the capture run is incomplete.

Opening it
  WARC is a standard web archive format (ISO 28500). Open with
  ReplayWeb.page (in-browser, no install) or pywb.

Important
  The `capture_fidelity` field states how faithful each record is; a browser
  cannot obtain fully unprocessed bytes, and this field records what was
  actually achieved. The `coverage` section records the item counts Douban
  claimed at capture time, but those counts MUST NOT be treated as proof of
  completeness -- see `crawl_state` for the actual completeness evidence.

Full specification: https://spec.doubak.com/bundle/v1/
""",
        encoding="utf-8",
    )

    print(f"wrote {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}  {p.stat().st_size} bytes")


if __name__ == "__main__":
    build()
