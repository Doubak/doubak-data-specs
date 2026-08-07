# canonical/tests —— 一致性用例

```sh
python3 make-tests.py     # 重新生成 cases/
```

## 与 `bundle/v1/tests` 不是一回事

那边的反例是**坏掉的文档**：把一个合法 bundle 破坏一处，校验器应当拒绝它。

这边不行 —— canonical 的产出是解析器**算**出来的，光看文档合不合 schema 说明不了什么。canonical 真正的不变量全是**行为**上的：

> 给这样一堆 bundle，解析器**不得**得出那样的结论。

所以每个用例是：**一组合法的 bundle**，外加一句「必须怎样、且不得怎样」。合法这一点是要害 —— 它们不是坏数据。坏的是一个天真的解析器从它们身上得出的结论，而它翻车的时候**不会报错**，会安安静静地产出错数据。

（`no-manifest-still-readable` 是唯一故意过不了 bundle 校验器的夹具：它模拟抓取进行到一半、manifest 还没写的档案。别去「修」它。）

## 目录

```
cases/<用例名>/
  EXPECTED.txt   人看的：这个用例在守什么，为什么
  expect.json    机器看的：断言
  bundles/       输入（一份或多份 bundle）
```

## 断言词表

| 键 | 意思 |
|---|---|
| `marks` | 必须产出多少条标记 |
| `mark_revisions` | 全部标记的修订数之和 |
| `authorities` | 出现过的 `absence_authority` 集合（去重排序） |
| `identity_layers` | 出现过的身份层集合 |
| `warning_types` | 必须报出的告警类型 |
| `broadcasts` / `broadcast_revisions` / `broadcast_observations` | 广播的记录数 / 修订数 / 观测数 |
| `broadcast_statuses` | 出现过的非 null 状态集合 |
| `longform` / `longform_revisions` | 日记与评论的记录数 / 修订数 |
| `longform_body_contains` | 正文里必须出现的子串 |

**记录数、修订数、观测数是三个不同的量**，别只断言前两个。真实撞到过：广播抽取器
去掉去重之后，记录数与修订数**都还是 1**（按 sid 归并会把重复合起来），只有观测数
从 1 变成 2。只看前两个的话，那一步被删掉也测不出来。

## 每个用例都必须**咬得住**

写完用例要反过来验一遍：故意把参考实现打断，看是不是**恰好对应的那一个**变红。
两次这么做都揪出了套件自己的漏洞：

- `gap-revokes-authority` 原来把 `contiguous=false` 与非空 `gaps` 写在同一份夹具里
  ——删掉任何一条检查，另一条都会替它挡住。拆成两个独立用例才各咬各的。
- `pagination-overlap-is-not-a-duplicate` 原来只断言记录数与修订数，而那两个数在
  去重被删掉之后**不变**。补上观测数才咬得住。

一个全绿但咬不住的套件比没有套件更糟：它会让人以为那条不变量有人看着。

## 谁来跑

用例是**实现无关**的：输入是 bundle，断言是 JSON。任何语言写的解析器都能跑。

第一个实现是 `doubak-data-parser/test/conformance.test.js`。
