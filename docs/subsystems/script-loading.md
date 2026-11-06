# 文本脚本读取与编译错误

`cpp/core/base/TextStream.cpp` 负责 `Scripts.execStorage`、`Array.load` 等接口使用的
文本流。mode 0/1 的简单编码格式为三字节 `FE FE mode`，随后是两字节 UTF-16LE BOM
`FF FE`；正文从偏移 5 开始。读取器验证头和正文的偶数字节长度，按字节组合 UTF-16LE
码元，避免奇数地址上的 `char16_t` 指针访问。普通文本移除 BOM 后按剩余长度转换。

该格式契约与本文件写入器及
[Kirikiroid2 的读取器](https://github.com/zeas2/Kirikiroid2/blob/d1c2b1259423542c893e0b65eaeb46c848848f2b/src/core/base/TextStream.cpp)
一致。这里沿用现有实现和位变换，未整体移植其文本流代码；原文件的许可/版权声明保留。

TJS 的 Bison `parser::error` 进入已有 `_yyerror` 路径，记录首个错误及源位置，增加
`CompileErrorCount`。`tTJSScriptBlock::Parse` 在编译失败后抛出脚本异常，不能执行未完成的
顶层上下文；即使解析器从语法错误恢复并返回成功，已记录的错误也会阻止执行。
诊断包含脚本名称和行号，调用脚本可以捕获异常后继续执行其他合法脚本。

## 实引擎回归

在已有桌面应用构建配置中启用 `KRKR2_ENABLE_SCRIPT_SMOKE=ON`，重新构建 `krkr2`。
测试不依赖商业游戏素材，Linux 需要有效的 X11 显示，例如：

```sh
ctest --test-dir out/build -N -R '^(textstream|parser-error)-runtime$'
LIBGL_ALWAYS_SOFTWARE=1 ALSOFT_DRIVERS=null xvfb-run -a \
  ctest --test-dir out/build -R '^(textstream|parser-error)-runtime$' \
  --output-on-failure --no-tests=error
```

测试运行真实应用及脚本 API，报告和进程日志保存在构建目录 `script-smoke/`。
它们覆盖编码、异常传播和错误后的继续执行，不代表全部游戏兼容性、音视频或存读档验收。

对应上游贡献为 [PR #56](https://github.com/2468785842/krkr2/pull/56)，当前为草稿。

ATRI 的原始故障和同机差分证据见
[调查记录](../../.agents/notes/proposed/bug-fix/2026-11-06-atri-script-compat.md)。
