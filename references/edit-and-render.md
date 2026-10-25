# 从素材与事件生成 Remotion 工程

这里规定工具交接，不规定故事结构。Agent 阅读选题、联系表和音乐后写计划。使用新目录保存每次实验，避免覆盖已经校对的事件或成片。

## edit-plan.json

结构示例在 `assets/examples/edit-plan.example.json`。主要字段：

| 字段 | 含义 |
|---|---|
| `startSeconds`、`endSeconds` | 相对 `events.json.sourceAudio` 的选段，首含尾不含；必须落在已分析范围内 |
| `imageIds` | 这次确实使用的图片 ID，有序且不重复；来自所传 manifest |
| `eventIds` | 可选的明确事件 ID；省略时使用该片段内 accepted 候选，显式指定可采用已复核的弱点 |
| `fps` | 默认 60 |
| `visualOffsetFrames` | 默认 0；负数表示视觉中心先于音频事件，旧案例试过 -1 |
| `transition` | dissolve / press / pulse / bounce |
| `eventTransitions` | 例如 `{"piano_attack":"press","kick":"bounce"}`；事件分类须先有依据 |
| `preFrames`、`postFrames` | 默认 6/12，表示混合中点前后展开长度；脚本按相邻间隔缩短，避免重叠窗口冲突 |
| `releaseFrames` | 默认 22，控制按键释放；尾部允许与下一事件共存 |
| `motion` | Remotion 模板的可选参数覆盖，见其参考文档 |
| `subjectMask` | 可选的 1080×1440 RGBA 保护蒙版绝对路径 |
| `fadeOutSeconds` | 默认 0.35，只用于最终音量淡出；不能代替选择自然乐句结尾 |

初始画面从第 0 帧显示，之后每个内部切点需要一张新图。片段开头附近落在第 0 帧的真实事件合并到初始图，**不会凭空制造音符**。因此图片槽数通常是“内部切点数 + 1”，并不永远等于事件总数。脚本会报出准确槽数；数量不符时 Agent 调整选段/事件/图片计划，不自动均匀补点或截掉故事结尾。相同帧的两个事件需先合并或选择一个。

图片 ID 默认保持 manifest 中的相对顺序；需要改变顺序时先运行 order_images.py，或计划显式写 `allowReorder:true`。多余图片可不用，但明确选择子集并保留故事关键画面。脚本记录 unusedImageIds。

事件时间减 `startSeconds` **一次**才是成片内时间。`build_edit.py` 会裁出原速 WAV，所以模板中的音频从零开始，不再加旧曲目偏移。剪辑不会自动加速 BGM。

```powershell
py -3.11 "<skill>/scripts/build_edit.py" --manifest "<有序manifest.json>" --events "<events.json>" --plan "<edit-plan.json>" --output-dir "<制作资料>/edit-v001" --ffprobe "<ffprobe路径>"
```

产物包含 `timeline.json`、计划、构建回执、TSX 模板和 `public/` 素材。模板带少量合成示例 SVG，正式编排使用复制进来的真实图片；无需把原来的 70 张图或音乐打进 skill。构建回执仅表示已准备工程，不表示渲染或听感通过。

## 复用已有 Remotion

需要兼容模板的 Remotion 4.0.534 / React 19.3.0 运行环境。模板 package.json 列出依赖，可以在 `assets/remotion-template/` 安装依赖作为共享运行环境，避免为每条内容复制 node_modules。

渲染助手从指定 runtime 加载 bundler/renderer，并为独立工程设置模块解析，常规导出无需在制作目录安装新依赖：

```powershell
node "<skill>/scripts/remotion_job.mjs" --project "<制作资料>/edit-v001" --runtime "<已有Remotion工程>" --output "<预览>/transition.png" --still-frame 60 --browser-executable "<Chrome路径>"
node "<skill>/scripts/remotion_job.mjs" --project "<制作资料>/edit-v001" --runtime "<已有Remotion工程>" --output "<账号目录>/<选题>-v001.mp4" --browser-executable "<Chrome路径>"
```

若本机已有 Chrome，显式指定可以避免环境默认下载浏览器。本次验证路径为 `C:/Program Files/Google/Chrome/Application/chrome.exe`；换机器先查实际路径。新环境需要安装模板依赖时，先检查已有环境再安装；独立 renderer 助手还需要 runtime 有 `@remotion/bundler` 和 `@remotion/renderer` 同版本包。

要交互调整，使用 Remotion Studio。新工程可链接共享 node_modules，确认目标与占用后再建链接；随后在该工程运行 `npx remotion studio index.tsx --no-open` 并打开工具实际打印的地址。已有相关 Remotion skill 可用于 Studio/React API 细节。不要凭空指定端口或覆盖已有预览。

## 验收

先抽看开头、转场中点、最密集段、曝光保护边界和结尾。再播放带原声的短预览，判断转场力度、尾音和读字时间。最后导出时用 ffprobe 核对画布、帧率、时长、音轨，再用 FFmpeg 全片解码。

脚本渲染回执把 `fullDecodeVerified` 和人工视听状态保留为未验证，后续检查独立记录。无条件重复检测和重渲染不会替代审美判断。修改影响了某个环节时，只补对应检查。
