# ATRI 文本解码与脚本解析兼容性

Status: proposed

## 问题和基线

DroidDeck 0.6.9 集成的 Linux ARM64 引擎 `72932a4` 读取 ATRI 的 `data.xp3` 后，
在 `PackinOne.dll` 加载失败日志之后报告 `syntax error` 并以 139 退出。
已安装二进制 SHA-256 为
`f6a030e40f0adc8db688d53df83f1d4d6f85fe0da826fc1028880a7f05e7350e`。

2026-11-06 在同一 Android 15/ARM64 手机的隔离目录，使用该二进制、Xvfb 和
software GL 复现：相同脚本，UTF-16LE BOM 编码退出 0；mode1 编码退出 139；
独立的 `var broken =` 也退出 139。三次失败的主程序偏移均为 `0x29375b0`。
发行二进制无完整符号，不把 addr2line 的最近导出符号当作真实栈帧。

## 已确认原因

- `TextStream.cpp` mode0/1 将五字节头当作四字节；同源写入器写入 3+2 字节。
- `parser::error` 只记录日志，未进入已有编译错误计数/异常路径；`Parse` 忽略返回值。
- 两者均在 `2468785842/krkr2` 上游存在。文本回归由
  `37b15c7712a3062aae8e20c66b15f5ff2146a747` 引入。
- 对照 Kirikiroid2 `d1c2b1259423542c893e0b65eaeb46c848848f2b` 的
  `src/core/base/TextStream.cpp` 和 `src/core/tjs2/tjsInterCodeGen.cpp` 恢复既有契约，
  保留本分支的 Bison C++ 结构。

仅在测试副本转码 `data.xp3` 的252个文本条目，逐项回读验证另2023项资源/索引未改，
初始化推进到 `AppConfig.tjs` 之后仍有解析错误。此时尚未得到后续错误的准确文件/行号。
`PackinOne` 没有内建实现，但不能据此把它当作最初语法崩溃的唯一原因。
原游戏和原存档保持不变；商业素材和解包脚本不入库、不上传 CI。

## 本轮修改及下一步

修正文本头、长度边界和编译错误传播，新增两个实引擎回归并注册为
`textstream-runtime`、`parser-error-runtime`。运行结果须核对构建提交及二进制哈希。

待 ARM64 构建及回归完成后，用原始游戏的隔离副本重新运行，按新诊断定位后续阻塞。
完成条件是回归通过、无原始崩溃，并明确实际游戏到达范围；不能以转码副本或编译成功
代替真实游戏兼容结论。若仍需其他兼容修复，本记录继续保持 proposed。
