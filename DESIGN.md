# doubak-data-specs 设计方案

> 状态：草案 v0.1（2026-07-28）。本文只覆盖 **`bundle/`**（插件产出的容器格式）。
> `canonical/` 按既定判断**推迟**——它要对着真实抓取数据来设计，现在凭空对着 15 年没见过的豆瓣 markup 建模，只会得到一个碰上 2011 年的页面就碎掉的 schema。

## 0. 为什么这份 spec 要先落地

`bundle/` 是**不可逆步骤的产物**。用户跑完一次抓取，写下去的东西就是他永远拥有的东西——不能请人家重爬一遍。所以：

- `bundle/` 一旦有用户跑过，**就冻结了**。之后只能加字段，不能改语义。
- `canonical/` 可以随便改，反正拿 WARC 重跑 parser 不要钱。

这不对称决定了两棵树的一切设计取舍。**把它们当成一个格式来设计是本项目最主要的翻车方式。**

---

## 1. 设计原则

1. **容器不懂豆瓣。** `bundle/` 里不出现「电影」「评分」「看过」这类概念。它描述的是**抓取行为**（抓了哪个 URL、为什么抓、抓到的可信吗），不是抓到的内容。懂豆瓣是 parser 的事。
2. **只增不改。** 同一大版本内永远只加可选字段。绝不复用字段名，绝不改变已有字段的含义。
3. **不可恢复的字段必填，可推导的字段可选。** 判断标准只有一个：这个信息，事后还能不能从 WARC 里重新算出来？算不出来的，第一版就必须有。
4. **JSON 与 NDJSON，不用二进制。** 目标是 2040 年一个陌生人能读懂。`jq` 永远在，`.proto` 文件会丢。（这是对前代 protobuf 方案的刻意反转；MV3 禁 `unsafe-eval` 也让 protobuf.js 动态模式用不了。）
5. **WARC 保持原味。** 不加私有扩展头，pywb 与 ReplayWeb.page 必须能直接打开。所有 doubak 专有元数据一律进 `index.ndjson`。
6. **读者必须容忍未知字段**，且**重写文件时不得丢弃**它们。这是「只增不改」能成立的前提。
7. **诚实优先于好看。** 做不到的事情如实标注（见 §5.4 `capture_fidelity`）。一份标着「保真度有限」的档案有用；一份假装完美的档案在需要它的那天会骗人。

---

## 2. 版本策略

```
spec_version: "bundle/1.0"
```

- **大版本**：老读者会**误读**新数据时才 +1。因为 bundle 会冻结，这个数字理论上应该永远是 1；真要 +1，说明设计出了严重问题。
- **小版本**：加了可选字段。老读者继续正常工作。

`canonical/` 独立编号（`canonical/x.y`），与 `bundle/` 无任何耦合。

**未知枚举值的处理规则**（写进 spec 正文）：

- 遇到未知 `verdict` → **必须当作不可信**，不得当作 `ok`。安全方向的默认值。
- 遇到未知 `intent` / `surface` → 保留原值，不得丢弃，不得猜测。

---

## 3. 目录布局

```
doubak-bundle-<bundle_id>/
├── README.txt                        ← 纯文本，给 2040 年的人看
├── manifest.json                     ← 这次抓取是什么
├── index-<bundle_id>.ndjson          ← 每次抓取一行
├── checkpoint.json                   ← 仅当未完成时存在
├── data-<bundle_id>-00001.warc.gz    ← 标准 WARC
└── data-<bundle_id>-00002.warc.gz
```

`README.txt` 不是文档，是**档案的一部分**：一段纯文本说明这是什么、字段怎么读、WARC 用什么工具打开、spec 的完整定义在哪。成本几乎为零，但它决定了这份档案在项目消失后还有没有人能解读。

### 3.1 标识符文法

```
bundle_id  := <UTC 紧凑时间戳> "-" <6 位小写十六进制随机>
              20260728T101500Z-a3f9c1
capture_id := <bundle_id> "#" <6 位零填充序号>
              20260728T101500Z-a3f9c1#000001
segment    := "data-" <bundle_id> "-" <5 位零填充> ".warc.gz"
```

段文件名带 `bundle_id`：**十次抓取的文件倒进同一个目录也不会互相覆盖**。`bundle_id` 以时间戳打头，天然可排序。

`capture_id` 的序号**在写入前分配**：崩溃只会留下空洞（某个序号没用上），不会留下重复。**空洞合法**，spec 必须明确这一点，否则校验器会误报。

---

## 4. manifest.json

```jsonc
{
  "spec_version": "bundle/1.0",
  "bundle_id": "20260728T101500Z-a3f9c1",
  "previous_bundle_id": "20260601T083000Z-77b201",   // null = 首次抓取
  "status": "complete",                               // in_progress | complete | aborted
  "created_at": "2026-07-28T10:15:00+08:00",
  "completed_at": "2026-07-28T14:52:31+08:00",

  "producer": {
    "name": "doubak-extension",
    "version": "0.1.0",
    "user_agent": "Mozilla/5.0 ...",                  // 浏览器真实 UA，原样
    "platform": "Chrome/141 Linux"
  },

  "account": {
    "user_id": "82160871",                            // 数字 ID，稳定主键
    "username": "mewcatcher",                         // 会变，不可作主键
    "profile_url": "https://www.douban.com/people/82160871/"
  },

  "timezone_assumption": "Asia/Shanghai",             // 见 §7.2

  "segments": [
    {
      "filename": "data-20260728T101500Z-a3f9c1-00001.warc.gz",
      "bytes": 268435456,
      "sha256": "9f2b...",
      "record_count": 12043,
      "first_capture_id": "...#000001",
      "last_capture_id":  "...#012043"
    }
  ],

  "index": {
    "filename": "index-20260728T101500Z-a3f9c1.ndjson",
    "sha256": "1a77...",
    "line_count": 18771
  },

  "coverage":    [ /* §4.1 */ ],
  "crawl_state": [ /* §4.2 */ ],

  "counts": {
    "by_verdict": {"ok": 18650, "blocked": 3, "challenge": 1, "gone": 117},
    "by_surface": {"html": 12100, "api": 6671},
    "by_intent":  {"broadcast.timeline": 431, "...": 0}
  }
}
```

### 4.1 `coverage` 条目 —— 观测，不是证明

> **修订（v0.2）：豆瓣的计数器不可信，coverage 不能用来判断完整性。**
>
> 豆瓣有多套审查／屏蔽机制，其计数**有时统计于审查之前、有时统计于审查之后**。所以「页面说 1234，我抓到 1234」推不出「档案完整」。CLAUDE.md 里「可数列表用 claimed_count 对账」这条安全网**不成立**，必须撤掉。

```jsonc
{
  "route_key": "interest.movie.collect",
  "intent": "interest.list.movie.collect",

  "claimed_count": 1234,                    // 页面声称的数量；拿不到则 null
  "claimed_raw": "看过 1234 部电影",         // 原始文案，永远保留
  "claimed_source": "...#000007",           // ← 读到这个数字的那条捕获
  "claimed_observed_at": "2026-07-28T10:15:42+08:00",

  "captured_count": 1231,
  "delta": -3                               // 中性命名：一个差值，不是一个错误
}
```

两个刻意的设计动作：

1. **不提供 `completeness` / `reconciled` 字段。** 不存在的字段无法被误用——这比在文档里写一句警告可靠得多。校验器发现这两个字段时**报错**。
2. **差值叫 `delta` 不叫 `discrepancy`。** 后者暗示「出错了」，而它其实只是两个数不一样。

**那为什么还要记？** 一是事后不可恢复；二是它有取证价值——`claimed_count` 大于 `captured_count` 可能意味着**豆瓣的计数器知道一些它不肯展示给你的条目**。这个差值是**线索**，不是判决。

`claimed_source` 指向一个 `capture_id`，是「声明页本身也要入 WARC」这条要求的**机器可校验版本**：校验器可以顺着它回到 WARC 里那张页面。没有这个指针，`claimed_count` 就只是一个无从追溯的数字。

**`null` 与 `0` 必须严格区分**：`null` = 不知道，`0` = 确实没有。

完整性的证据在 `crawl_state` 里（§4.2）——来自抓取过程自身的结构化证明，而不是与豆瓣计数器的比对。

### 4.2 `crawl_state` 条目 —— 抓取存档信息

跨次抓取的续抓依据，每条路线一份。

```jsonc
{
  "route_key": "broadcast.timeline",
  "intent": "broadcast.timeline",

  "high_water_time": "2026-07-26T12:34:00+08:00",
  "high_water_raw": "2026-07-26 12:34:00",   // 页面上的原样字符串，无时区
  "high_water_ids": ["9351468114"],          // 同一秒多条时用于去重
  "floor_time": "2026-06-01T00:00:00+08:00", // 本次的下界；null = 抓到最早

  "enumeration": "bounded",                  // full | bounded  ← §7.1
  "contiguous": true,                        // 连续性证明是否成立
  "advanced": true,                          // 水位线本次是否推进
  "gaps": [],                                // 已知缺口，显式记录

  "completed_at": "2026-07-28T11:03:12+08:00",
  "bundle_id": "20260728T101500Z-a3f9c1"
}
```

**schema 必须能表达的不变量**（写进 prose spec，由校验器强制）：

> `advanced: true` 要求 `contiguous: true` 且 `gaps: []`。

中途暂停、被风控打断、用户放弃 → `advanced` 必须为 `false`，下次仍从旧下界重走。重复是免费的，空洞是永久且不可检测的。

---

## 5. index-<bundle_id>.ndjson

每次抓取一行。这是整个 bundle 里唯一放 doubak 专有元数据的地方。

```jsonc
{
  "capture_id": "20260728T101500Z-a3f9c1#000042",
  "warc_record_id": "urn:uuid:3f2a8c11-...",
  "segment": "data-20260728T101500Z-a3f9c1-00001.warc.gz",
  "offset": 4823914,                  // gzip member 起始字节
  "length": 20481,

  "url": "https://www.douban.com/people/82160871/status/9351468114/?_spm_id=ODIx&_dtcc=1",
  "url_key": "https://www.douban.com/people/82160871/status/9351468114/",
  "url_key_rules": "v1",              // 剥离规则版本，可重算

  "intent": "broadcast.item",
  "route_key": "broadcast.timeline",
  "surface": "html",                  // html | api
  "verdict": "ok",
  "capture_fidelity": "decoded_body+observed_headers",

  "observed_at": "2026-07-28T10:22:07+08:00",
  "http_status": 200,
  "content_type": "text/html; charset=utf-8",
  "content_sha256": "c31f...",

  "parent_capture_id": "20260728T101500Z-a3f9c1#000041",
  "cursor": {"kind": "max_id", "value": "9351468114"}
}
```

### 5.1 `url` 与 `url_key`

`url` 是**请求时的原始 URL，跟踪参数照留**（`_spm_id`、`_dtcc` 本来就是当时那个页面的一部分，捕获时不做归一化是铁律）。

`url_key` 是**索引**：剥掉已知跟踪参数、统一尾斜杠后的结果，供去重使用。`url_key_rules` 记规则版本——将来发现新的跟踪参数，可以对存量重算 `url_key`，而 `url` 永远不动。

**事实与索引并存，索引不覆盖事实。**

### 5.2 `surface`

`html` 还是 `api`。同一条广播在两个面上都会被抓到，parser 必须能区分，否则会把同一条内容的两种表示当成两次修订。

### 5.3 `parent_capture_id` 与 `cursor`

谁把这个 URL 放进队列的。有了这条链，整张抓取图可以离线重建——连续性证明因此可被**第三方独立验证**，而不是只能相信插件自己的结论。`cursor` 记下当时用的游标值，让任何一页都可复现。

### 5.4 `capture_fidelity` —— 必须诚实的那个字段

`fetch()` 拿不到真正的原始字节：响应体已经解过 `Content-Encoding`，响应头被过滤过（`Set-Cookie` 拿不到，顺序和大小写也丢了）。

初始取值：

| 值 | 含义 |
|---|---|
| `decoded_body+observed_headers` | 体来自 `fetch()`（已解码），头由 `chrome.webRequest` 观察补全 |
| `decoded_body+filtered_headers` | 体已解码，头是 `fetch()` 给的过滤版 |
| `raw` | 真正的线上原始字节（目前无可行途径，预留） |

十年后有人拿这份档案做取证时，这个字段就是他判断能信到什么程度的依据。**做不到却宣称做到了，比做不到糟糕得多。**

---

## 6. checkpoint.json —— 抓取存档点

仅当 `status != "complete"` 时存在。抓取期间活在 IndexedDB 里，**导出时一并写进 bundle**——这样一份导出的半成品也能被拿到别的机器上续抓。

```jsonc
{
  "spec_version": "bundle/1.0",
  "bundle_id": "20260728T101500Z-a3f9c1",
  "paused_at": "2026-07-28T12:41:09+08:00",
  "pause_reason": "challenge",
  // session_expired | challenge | blocked | user_paused | quota | crash

  "last_capture_id": "20260728T101500Z-a3f9c1#012043",

  "routes": [
    {
      "route_key": "interest.movie.collect",
      "state": "in_progress",
      "cursor": {"kind": "start", "value": 750},
      "items_seen": 750,
      "stall_counter": 0
    }
  ],

  "frontier": [
    {
      "url": "https://movie.douban.com/people/82160871/collect?start=765&...",
      "intent": "interest.list.movie.collect",
      "route_key": "interest.movie.collect",
      "state": "pending",              // pending | in_flight | failed | awaiting_human
      "attempts": 0,
      "enqueued_by": "...#012040"
    }
  ],

  "rate_state": {
    "interval_ms": 4000,
    "backoff_level": 2                 // 降速后不自动恢复原速
  }
}
```

`rate_state` 要进 checkpoint：软封锁之后降了速，**恢复抓取时不能把这件事忘掉**。忘掉就等于一恢复又按原速撞上去。

---

## 7. 三个必须一次做对的建模决定

### 7.1 `enumeration: full | bounded`

这一个字段决定 parser **有没有资格推断删除**：

- `full` —— 本次把整份列表从头到尾枚举完了。「上次有、这次没有」= 真的被删了。
- `bounded` —— 只走到 `floor_time` 就停了，下界以下根本没看。缺失**无法**与「没抓到」区分。

广播永远是 `bounded`（除非首次全量）。标记类列表通常是 `full`。

把它显式写进数据，而不是留给 parser 去猜——猜错的方向是**静默地把没删的当成删了**，而且事后无从发现。

### 7.2 时间

三种时间戳，**永远不许合并**：

| 字段 | 含义 | 通常 |
|---|---|---|
| `occurred_at` | 事情本身发生的时间 | 多为 null |
| `recorded_at` | 豆瓣记录下来的时间 | 页面上的 `title="2026-07-26 12:34:00"` |
| `observed_at` | 爬虫看见的时间 | 客户端时钟 |

两条附加规则：

- **一律 RFC 3339 带显式偏移量。** 豆瓣页面给的是 `2026-07-26 12:34:00`，**没有时区**。所以：原样字符串存进 `*_raw`，解析结果存进主字段，并在 manifest 里记 `timezone_assumption`。海外用户跑抓取时，这一条直接决定水位线会不会偏 8 小时。**绝不静默转换。**
- `recorded_at` 在豆瓣是**记录指纹，不是时钟**——它在编辑时不变，只在删除重建时变。spec 的说明文字必须点明这一点，否则下游一定会拿它当「最后修改时间」用。

### 7.3 摘要

- **WARC 内部**沿用 WARC 惯例（`sha1:` + base32），保证 pywb 等工具能正常校验。
- **`index.ndjson` 与 manifest** 用 `sha256:` 十六进制小写，服务于我们自己的完整性校验。
- 内容摘要的归一化只做三件事：**NFC 规范化、去尾空白、统一换行**。**不折叠简繁、不折叠大小写**——那些是真实编辑，折叠掉就再也看不见了。

---

## 8. 词表（开放词表 + 注册表）

单独成文件，可以独立于 schema 演进。

### 8.1 `intent`

文法：`<family>.<component>*`，点分。初始注册表：

```
profile.overview
profile.category_entry.<medium>      声明数量的来源页
broadcast.timeline                   广播列表
broadcast.item                       单条广播（补全被截断的正文）
interest.list.<medium>.<status>      标记列表；medium ∈ movie|book|music|game|drama
                                     status ∈ collect|wish|do
note.list / note.item                日记
review.list.<medium> / review.item   影评书评
annotation.list / annotation.item    读书笔记
photo.album_list / photo.album / photo.item
doulist.list / doulist.item
doumail.list / doumail.thread        豆邮（私信）
social.following / social.follower / social.blacklist
asset.image.user_upload              用户上传的图
asset.image.catalog_thumbnail        列表页目录缩略图
probe.canary                         金丝雀探测
manual.user_requested                用户手动补抓
```

`medium` 沿用 NeoDB 的枚举（book / movie / tv / music / game / podcast / performance），保持开放词表——那个映射迟早要做，没必要另起炉灶。

### 8.2 `verdict`

`ok | blocked | challenge | login | gone | soft404`

**未知值必须当作不可信**。这是 spec 里少数几条带安全含义的规则之一。

### 8.3 `surface`

`html | api`

---

## 9. 仓库布局

```
doubak-data-specs/
├── README.md
├── DESIGN.md                       ← 本文
├── bundle/
│   └── v1/
│       ├── SPEC.md                 ← 正文（规范性，中文）
│       ├── manifest.schema.json
│       ├── index-entry.schema.json
│       ├── checkpoint.schema.json
│       ├── crawl-state-entry.schema.json
│       ├── coverage-entry.schema.json
│       ├── vocabularies/
│       │   ├── intent.json
│       │   ├── verdict.json
│       │   ├── surface.json
│       │   └── capture-fidelity.json
│       ├── examples/
│       │   └── minimal-bundle/     ← 一个完整的、能跑通校验的最小 bundle
│       └── tests/
│           ├── valid/
│           └── invalid/            ← 每个反例配一句「应该报什么错」
└── canonical/                      ← 暂空，附一份「为什么先不做」的说明
```

`crawl-state-entry` 单独成 schema、但**存放在 manifest 里**：一份 bundle 只有一个真相来源，同时这份 schema 又能被单独引用和校验。

`tests/invalid/` 是让 spec 变成真东西的关键。至少要覆盖：`advanced: true` 但 `contiguous: false`；`claimed_source` 指向不存在的 `capture_id`；段 sha256 对不上；index 行数与 `line_count` 不符；`capture_id` 序号重复（空洞合法、重复非法）。

JSON Schema 用 **2020-12**。

---

## 10. 落地顺序

spec 是基石，但也不必一次写完。按「插件写代码时会撞到什么」排：

| 步骤 | 内容 | 为什么是这个顺序 |
|---|---|---|
| 1 | 目录布局 + 标识符文法（§3） | 插件一开始写文件就要用 |
| 2 | `index-entry.schema.json` | 每抓一条就要写一行，最先撞上 |
| 3 | `manifest.schema.json`（含 coverage / crawl_state） | 第一次跑完一条完整路线时撞上 |
| 4 | `checkpoint.schema.json` | 第一次实现暂停恢复时撞上 |
| 5 | 词表初版 | 与 2、3 并行，先给个够用的初始集合 |
| 6 | `examples/` + `tests/` + 校验器 | 插件 M1 完成前必须有，否则没人知道产出对不对 |
| 7 | `SPEC.md` 正文 | 前面定稿后一次写完 |

**插件的 M1 不能在第 3 步之前开始写 bundle 写入器。**

---

## 11. 需要现在拍板的

1. **`spec_version` 写 `"bundle/1.0"` 还是拆成 `{"tree": "bundle", "version": "1.0"}`？** 倾向前者：一个字符串，`grep` 友好。
2. **段大小上限 256 MB** —— 需要确认对普通用户的档案体量是否合适（几万条广播 + 图片可能到几个 GB）。
3. **`README.txt` 用中文还是中英双语？** 倾向双语：档案的目标读者是「2040 年的陌生人」，不一定读中文。这是项目约定「文档用中文」的合理例外，与 `doubak-website` 同理。
4. **图片是否与页面放同一批段文件？** 分开的好处是想只要文本时可以不下载几个 GB 的图。倾向分开：`data-*` 与 `assets-*` 两套段，manifest 里分别列出。
