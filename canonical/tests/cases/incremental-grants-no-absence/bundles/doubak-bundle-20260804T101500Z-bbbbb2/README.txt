doubak 备份档案 / doubak backup bundle
======================================

规范版本 / Spec version: bundle/1.1
档案编号 / Bundle ID:    20260804T101500Z-bbbbb2

这是 canonical 一致性用例的合成夹具，不含任何真人数据。
见同级目录的 EXPECTED.txt。

怎么打开
--------
data-*.warc.gz 是标准 WARC，pywb / ReplayWeb.page 可直接打开；
index-*.ndjson 每行一条捕获记录，用 jq 即可查阅。
