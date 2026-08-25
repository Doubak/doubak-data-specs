# doubak-specs

[![validate](https://github.com/Doubak/doubak-data-specs/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Doubak/doubak-data-specs/actions/workflows/validate.yml?query=branch%3Amain) [![Coverage Status](https://coveralls.io/repos/github/Doubak/doubak-data-specs/badge.svg?branch=main)](https://coveralls.io/github/Doubak/doubak-data-specs?branch=main)

> **这是源码仓库。** 项目主页在 **<https://doubak.com>**。

豆备 (Doubak) 的数据格式定义。从豆瓣 (Douban.com) 上备份下来的数据会存储为这个项目里所约定的格式。

## 两棵独立的树

| 目录 | 谁写 | 生命周期 | 状态 |
|---|---|---|---|
| [`bundle/`](bundle/) | 浏览器扩展 | 用户跑过一次就**冻结**（没法请人重爬） | [草案 v1.0](bundle/README.md) |
| [`canonical/`](canonical/) | 解析器 | **随时可改**（重跑解析器不要钱） | [摄取规则 + 标记与作品的 schema](canonical/README.md) |

把这两者当成同一个格式来设计，是本项目最主要的翻车方式。

## canonical

- **[canonical/README.md](canonical/README.md)** —— 这棵树的入口
- **[INGESTION.md](canonical/INGESTION.md)** —— 给一堆 bundle，哪些能读、读出来**能推出什么结论**
- **[IDENTITY.md](canonical/IDENTITY.md)** —— 两次抓取之间怎么知道是同一条
- **[FIELDS.md](canonical/FIELDS.md)** —— 能拿到什么，以及哪些**不该**在解析时拆
- JSON Schema：`mark` / `subject` / `broadcast` / `longform` / `common`
- [一致性用例](canonical/tests/)：17 组，多数是**「解析器不得得出什么结论」**

### 校验

```sh
cd canonical/v1 && python3 validate.py <canonical 目录>   # 零依赖
cd canonical/tests && python3 make-tests.py
```

对着真实档案 9279 行全部通过（标记 2940 · 作品 2940 · 广播 3394 · 长文 5）。

数据模型整体仍然刻意滞后于抓取——拿十五年没见过的豆瓣页面去设计 schema，只会得到一个碰上 2011 年的页面就碎掉的 schema。这四类是已经有真实数据可以对着量的部分。

## bundle

- **[bundle/README.md](bundle/README.md)** —— 这棵树的入口
- **[bundle/v1/SPEC.md](bundle/v1/SPEC.md)** —— 规范性文本，先读这个
- **[DESIGN.md](DESIGN.md)** —— 设计理由与取舍
- JSON Schema（2020-12）：`manifest` / `index-entry` / `checkpoint` / `crawl-state-entry` / `coverage-entry` / `common`
- [词表](bundle/v1/vocabularies/)：`intent` / `verdict` / `surface` / `capture-fidelity`

### 校验

```sh
cd bundle/v1
python3 validate.py examples/minimal-bundle   # 校验一个 bundle
python3 validate.py --tests                   # 跑全部用例
```

结构性检查无需任何依赖；装了 `jsonschema` 与 `referencing` 后会额外运行 schema 层校验。

### 重新生成例子与用例

```sh
cd bundle/v1
python3 examples/make-minimal-bundle.py   # 偏移量与摘要都是实算的
python3 tests/make-tests.py
```
