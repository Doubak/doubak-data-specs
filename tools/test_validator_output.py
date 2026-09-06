#!/usr/bin/env python3
"""校验器最后那句话，必须说清它有没有跳过一层。

## 为什么要为一句话写测试

`bundle/v1/validate.py` 分两层：结构层永远跑，**schema 层只在装了 jsonschema
时才跑**。没装的时候它开头印一句「提示: 未安装 jsonschema，跳过 schema 层校验」，
末尾印一句「通过」——**被读进去的是后面那两个字**。

这不是假想。写 `bundle/1.4` 的 `gap.url` 时，产出的档案有一小段时间是不合规的
（`gap` 是 `additionalProperties: false`，多一个字段就不合规），而本机的校验器
一路只说「通过」，因为那种不合规**恰恰只有 schema 那一层看得见**。

所以这里守两件事，而且**两个方向都要守**：跳过时那句话必须带上「没查什么」，
没跳过时必须**不带**——一句永远挂着「只跑了结构层」的话，跟没有是一样的，
读的人两周之后就不再看它了。

跑法：`python3 tools/test_validator_output.py`
"""

import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VALIDATE = ROOT / "bundle" / "v1" / "validate.py"
CANON = ROOT / "canonical" / "v1" / "validate.py"

failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global failed
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failed += 1
        if detail:
            print("\n".join(f"        {line}" for line in detail.splitlines()[:12]))


def run(args: list[str], *, block_jsonschema: bool) -> subprocess.CompletedProcess:
    """跑一次校验器。`block_jsonschema` 用一个抬手就抛 ImportError 的桩包挡住它。

    不能靠「这台机器上装没装」来测——CI 里装了、本机没装，两边各自只跑到一半，
    而两个分支都得验。桩包放在 sys.path 最前面，`import jsonschema` 于是抛
    ImportError，正好走进 `load_schema_validator` 那个 except。
    """
    env = None
    with tempfile.TemporaryDirectory() as tmp:
        if block_jsonschema:
            (pathlib.Path(tmp) / "jsonschema.py").write_text(
                "raise ImportError('测试用：挡住 jsonschema')\n", encoding="utf-8")
            import os
            env = {**os.environ, "PYTHONPATH": tmp}
        return subprocess.run([sys.executable, *args], capture_output=True,
                              text=True, env=env, cwd=ROOT)


def last_line(out: str) -> str:
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# ── bundle/v1/validate.py --tests
no_schema = run([str(VALIDATE), "--tests"], block_jsonschema=True)
check("没装 jsonschema：最后一句要说自己只跑了结构层",
      "只跑了结构层" in last_line(no_schema.stdout), no_schema.stdout)
check("没装 jsonschema：退出码不变（少个可选依赖不是档案的毛病）",
      no_schema.returncode == 0, f"退出码 {no_schema.returncode}\n{no_schema.stderr}")

# ── 反方向：schema 层真的跑了的时候，那句话**不许**带附注
#
# 这一条不能靠「这台机器上装没装 jsonschema」来决定跑不跑——那样它在没装的机器上
# 永远跳过，而永远跳过的检查等于没有。所以这里**不装库也要走这条分支**：直接把
# `load_schema_validator` 换成一个返回空校验函数的桩，`main()` 会照常拿到一个
# 「非 None」的返回值，也就走进 caveat 为空的那一支。
#
# 用 `examples/minimal-bundle` 而不是 `--tests`：桩不做任何校验，而 tests/invalid
# 里有几例**只有 schema 层看得见**，拿桩去跑会把它们误判成「该报错却通过了」。
# 一个本来就合规的 bundle 不吃这套。
import contextlib
import importlib.util
import io

spec = importlib.util.spec_from_file_location("doubak_validate", VALIDATE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.load_schema_validator = lambda: (lambda kind, instance, rep, where: None)
buf = io.StringIO()
argv = sys.argv
sys.argv = ["validate.py", str(ROOT / "bundle" / "v1" / "examples" / "minimal-bundle")]
try:
    with contextlib.redirect_stdout(buf):
        rc = mod.main()
finally:
    sys.argv = argv
check("schema 层跑了的时候，最后一句**不带**附注",
      last_line(buf.getvalue()) == "通过", buf.getvalue())
check("schema 层跑了的时候，退出码是 0", rc == 0, buf.getvalue())

# 真装了库时的端到端，只在装了的机器上跑（CI 装了）。上面那条已经保证了
# 「不带附注」这个性质在哪儿都验得到，这一条是额外的一层。
# **单份 bundle 那条路要单独验。** `--tests` 与「校验一个目录」印的是两句不同的话
# （「全部通过」和「通过」），改了一处忘了另一处的话，另一处就悄悄退回原样。
# 变异验过：只测 --tests 时，把「通过」那一行的附注删掉，五条断言全绿。
one = run([str(VALIDATE), str(ROOT / "bundle" / "v1" / "examples" / "minimal-bundle")],
          block_jsonschema=True)
check("没装 jsonschema 时，校验单份 bundle 那句「通过」也要带附注",
      "只跑了结构层" in last_line(one.stdout), one.stdout)
check("校验单份合规 bundle：退出码 0", one.returncode == 0, one.stdout + one.stderr)

with_schema = run([str(VALIDATE), "--tests"], block_jsonschema=False)
if "未安装 jsonschema" in with_schema.stdout:
    print("[提示] 这台机器上没有 jsonschema，端到端那一遍没跑（性质已由上一条覆盖）")
else:
    check("装了 jsonschema：--tests 最后一句不带附注",
          last_line(with_schema.stdout) == "全部通过", with_schema.stdout)
    check("装了 jsonschema：全部用例通过", with_schema.returncode == 0, with_schema.stdout)

# ── canonical/v1/validate.py：同一条规矩，另一个校验器
src = CANON.read_text(encoding="utf-8")
check("canonical 校验器也把附注拼进最后那句，而不是只在上面提一句",
      'print(f"\\n全部通过{caveat}"' in src)
check("canonical 的附注说得出「没查的是哪几条」",
      "本校验器不认识" in src)

print(f"\n{'全部通过' if failed == 0 else f'{failed} 条未达预期'}")
sys.exit(1 if failed else 0)
