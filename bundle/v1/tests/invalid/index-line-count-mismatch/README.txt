doubak 备份档案 / doubak backup bundle
======================================

规范版本 / Spec version: bundle/1.0
档案编号 / Bundle ID:    20260728T101500Z-a3f9c1

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
