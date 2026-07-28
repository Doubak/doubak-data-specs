# doubak-specs
豆备 (Doubak) 的数据格式定义。从豆瓣 (Douban.com) 上备份下来的数据会存储为这个项目里所约定的格式。

## 两棵独立的树

| 目录 | 谁写 | 生命周期 | 状态 |
|---|---|---|---|
| [`bundle/`](bundle/) | 浏览器扩展 | 用户跑过一次就**冻结**（没法请人重爬） | [草案 v1.0](bundle/README.md) |
| [`canonical/`](canonical/) | 解析器 | **随时可改**（重跑解析器不要钱） | [刻意留空](canonical/README.md) |

把这两者当成同一个格式来设计，是本项目最主要的翻车方式。

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
