# doubak-specs

[![validate](https://github.com/Doubak/doubak-data-specs/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Doubak/doubak-data-specs/actions/workflows/validate.yml?query=branch%3Amain) [![Coverage Status](https://coveralls.io/repos/github/Doubak/doubak-data-specs/badge.svg?branch=main)](https://coveralls.io/github/Doubak/doubak-data-specs?branch=main)

> **这是源码仓库。** 项目主页在 **<https://doubak.com>**。

豆备（Doubak）的数据格式规范定义。从豆瓣（douban.com）备份的数据，均按本项目约定的格式规范进行存储与解析。

## 两棵独立的树

| 目录 | 写入方 | 生命周期 | 状态 |
|---|---|---|---|
| [`bundle/`](bundle/) | 抓取工具与导入器 | 用户抓取完成后即**永久冻结**（原始页面无法要求用户重复抓取） | [草案 bundle/1.3](bundle/README.md) |
| [`canonical/`](canonical/) | 解析器 | **随时可迭代演进**（本地重新解析成本极低） | [摄取规则 + 标记与作品的 schema](canonical/README.md) |

若将二者混淆为同一种格式去设计，是本项目早期最主要的经验教训。

## canonical

- **[canonical/README.md](canonical/README.md)** —— 本树入口文档
- **[INGESTION.md](canonical/INGESTION.md)** —— 面对多个 bundle 归档，哪些可以读取、读取后**可以得出哪些确定结论**
- **[IDENTITY.md](canonical/IDENTITY.md)** —— 如何识别与判定跨抓取批次的同一条记录
- **[FIELDS.md](canonical/FIELDS.md)** —— 定义可提取字段，以及哪些复合字段**不应**在解析阶段过早拆解
- JSON Schema：`mark` / `subject` / `broadcast` / `longform` / `common`
- [一致性用例](canonical/tests/)：17 组，重点约束**「解析器绝不得推导出的错误结论」**

### 校验

```sh
cd canonical/v1 && python3 validate.py <canonical 目录>   # 零依赖
cd canonical/tests && python3 make-tests.py
```

基于真实用户归档 9279 行数据实测验证全部通过（标记 2940 · 作品 2940 · 广播 3394 · 长文 5）。

数据模型的演进刻意滞后于抓取——脱离历史页面去空想设计 schema，只会得到脆弱易损的数据结构。当前这四类格式，均已基于大量跨年份的历史真实页面完成了实测与对齐。

## bundle

- **[bundle/README.md](bundle/README.md)** —— 本树入口文档
- **[bundle/v1/SPEC.md](bundle/v1/SPEC.md)** —— 规范性技术文本，建议优先阅读
- **[DESIGN.md](DESIGN.md)** —— 设计原则与技术取舍
- JSON Schema（2020-12）：`manifest` / `index-entry` / `checkpoint` / `crawl-state-entry` / `coverage-entry` / `common`
- [词表](bundle/v1/vocabularies/)：`intent` / `verdict` / `surface` / `capture-fidelity`

### 校验

```sh
cd bundle/v1
python3 validate.py examples/minimal-bundle   # 校验单个 bundle
python3 validate.py --tests                   # 运行全量用例
python3 validate.py --integrity-only <目录>   # 仅在底层字节损坏时报错
```

结构性检查无需任何第三方依赖；安装 `jsonschema` 与 `referencing` 后会额外运行 schema 层校验。
**未安装依赖时，终端输出会显式明确说明**：

```
通过（**只跑了结构层** —— 没装 jsonschema，schema 层没查）
```

此前最初的设计是在开头输出「提示: 未安装 jsonschema，跳过 schema 层校验」，末尾输出「通过」——用户往往只注意末尾的「通过」而忽略提示。这并非空穴来风：在开发 `bundle/1.4` 的 `gap.url` 期间，产出的归档曾有一段时间存在不合规字段（`gap` 设置了 `additionalProperties: false`，多出字段即违规），而本机校验器却一直报告「通过」，因为该违规**仅能在 schema 校验层被捕获**。此时保持退出码不变——未安装可选校验工具并不属于归档本身的损坏缺陷。

错误严格划分为**完整性错误**（数据损坏或哈希不匹配，退出码 `2`）与**合规性错误**（字节完整但结构声明不合规范，退出码 `1`）两类。详见 SPEC §12.1。

### 重新生成样例与用例

```sh
cd bundle/v1
python3 examples/make-minimal-bundle.py   # 偏移量与哈希摘要均严格依据文件内容动态计算
python3 tests/make-tests.py
```
