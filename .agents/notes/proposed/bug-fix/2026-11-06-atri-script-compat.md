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

## 修复分支与公开回归

修复已推送到 `fix/atri-kirikiroid-compat`；生产 C++ 修改在 `6d09408`，
`ed06690` 另补测试超时回收竞态。DroidDeck 的 `fix/atri-krkr2-engine` 将源码 pin
指向 `ed06690`，注册并检查两项新回归；现有预编译安装包 pin 尚未改变。

上游独立分支基于 `main@dca7264`，现已 ready for review 的
[PR #56](https://github.com/2468785842/krkr2/pull/56) 只带相关修复、两个合成测试和
构建说明，没有 fork 的其他功能或游戏资源。上游 CI 当前需要维护者批准。

2026-11-06 将新测试 fixture 放到手机私有隔离目录，再次测试原已安装二进制：

- textstream：退出 0，但报告 `TEXTSTREAM_SMOKE_FAILED`，固定 mode 0 向量内容错误。
  验收必须检查断言标记，不能只看进程退出码。
- parser：`exec-caught`、`exec-no-side-effect` 两项失败，证明语法错误未抛出且
  执行前置赋值；随后未闭合函数在 EOF 报语法错误并退出 139。
- 两轮前后正式引擎 SHA-256 一致，测试 Xvfb 和子进程已退出。

用户重新开启 DroidDeck Actions 后，构建修正已快进同步到现有
`feat/onsyuri-emulator-integration`，避免新分支无法读取旧依赖缓存。
[CI 42152474926](https://github.com/realRurichan/DroidDeck/actions/runs/42152474926)
完整构建 `ed06690`，六项 CTest 及目录/XP3 启动均通过。
本地备用容器与临时依赖已清理，Colima 恢复原先 Stopped 状态。

同一手机的私有目录实测新二进制 SHA-256
`e4a8e24869c6da6b060e8d1263e90522d9333d10119ee9df2f54f1615ce3cecd`：
TextStream 41 项、Parser 12 项及 4 条定位诊断全部通过，正常退出 0。
正式引擎及原始 `data.xp3` 前后哈希一致，未替换正式安装。

未转码 ATRI 越过原始崩溃并完成 KAG 初始化，随后在 `custom.ks:172` 的
`calcRelative` 编译旧式四位十六进制正则转义时报 `too short multibyte code string`。
25 秒观察超时停止（124），尚不能声称标题或游戏可玩。该后续错误不属于 PR #56。
游戏补丁的 `kirikiriz=false` 正常加载；初始化又按预处理符号推导此变量。
全局启用 `@set(kirikiriz=1)` 会进入不支持的 Windows 对话框分支，不能直接采用。
运行期开关只用于定位差异，相关临时钩子已经移除。原始补丁和游戏资源保持不变。

后续修复位于通用 RegExp 编译路径：原生语法报字节不足后，重试旧式三位及以上
十六进制 Unicode 转义。不判断游戏名称、不注入游戏脚本、不改 `kirikiriz`。
新增 `regexp-compat-runtime` 覆盖各编译入口、Unicode 范围、已有语法及错误恢复。
修复前 `ed06690` 手机红测首批 25 项中 15 项旧语法失败、10 项已有语法通过；
虽然进程退出 0，验证器仍正确按断言判失败。最终合成测试为 30 项（后补字符类、注释及扩展模式边界）；验证结果如下。

## 通用修复验收完成

生产修改为 `8dd33cf` 和 `03aa34b`，均在 RegExp 共用编译路径；原生已支持的表达式
保持原行为，内联扩展模式混用旧式转义时保留错误，避免不完整语法扫描改变含义。
[CI 42158953991](https://github.com/realRurichan/DroidDeck/actions/runs/42158953991)
构建源码 `03aa34b212063624dce52f9a76d22c5ffd5801e0`，七项 CTest 及目录/XP3
启动检查全部通过。可执行文件 SHA-256 为
`83b5513c63a1af46bd701ae5814230f247e78e6b1716446cfbb17c96b7864ca0`，
配套调试符号 BuildID 为 `da6e6e2aabb56604`。

同一手机的隔离验证中，TextStream 41 项、Parser 12 项及 4 条诊断、RegExp 30 项
全部通过且正常退出 0；原游戏 data.xp3、131 字节 patch.tjs 哈希前后保持不变，
不存在松散 AfterStartup.tjs。65 秒画面已出现完整标题菜单，90 秒按计划结束观测
（124，非自然退出）。首两轮因虚拟显示 socket 路径过长未启动引擎，缩短专用 /tmp
映射后正常运行；没有把环境准备失败记成引擎兼容失败。

随后保留完整旧 `/opt/krkr2` 备份并独立替换可执行文件和 BUILD.txt，全部随包资源
已逐项确认一致。DroidDeck APK 未替换；通过正常 Launch in Krkr2 入口已进入剧情，
看到背景、人物及中英文文字，按虚拟 A 后推进画面和文字。原始共享存储中的游戏数据
与补丁再次核对一致，没有增加游戏专用设置。完整剧情、音频及存读档尚未验收。

独立包为 `krkr2-linux-arm64-03aa34b-r1`，下载配置另在 DroidDeck 分支更新。
旧 APK 内建重新安装入口仍固定旧 pin，发布新包不会让旧 APK 自动发现版本。
上游 PR #56 仍仅包含先前的文本和解析修复，不包含后续 RegExp 修改。
