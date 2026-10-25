# Remotion 模板与参数

模板位于 `assets/remotion-template/`，版本固定为 Remotion **4.0.534**。复制整个目录到内容制作资料的工程中，把真实素材放进工程的 `public/`，再替换 `timeline.json`。入口为 `index.tsx`，composition ID 为 `ImageBeatStory`。示例只有两张抽象 SVG、两秒淡入淡出，不带音乐，不是实际内容交付。

复用已有兼容工程或已安装依赖的 `assets/remotion-template/` 作为共享运行环境，避免为每条内容复制 node_modules。`remotion_job.mjs --runtime` 会配置模块解析；需要 Studio 时也可为新工程链接共享依赖。不要把机器绝对路径写回便携模板。

## Timeline 契约

```json
{
  "schemaVersion": 1,
  "width": 1080,
  "height": 1440,
  "fps": 60,
  "durationInFrames": 180,
  "audio": {"src": "audio/bgm.wav", "fadeOutSeconds": 0.35},
  "mode": "press",
  "shots": [
    {"id": "shot-001", "src": "images/001.png", "impactFrame": 0, "preFrames": 0, "postFrames": 12, "releaseFrames": 22, "intensity": 0.8, "eventType": "onset"},
    {"id": "shot-002", "src": "images/002.png", "impactFrame": 60, "preFrames": 6, "postFrames": 12, "releaseFrames": 22, "intensity": 0.9, "eventType": "onset", "transition": "pulse"}
  ],
  "motion": {"environmentEV": 0},
  "subjectMask": "masks/subject.png"
}
```

`audio`、`mode`、`motion`、`subjectMask` 和逐镜头 `transition` 可省略。音频必须已裁好，模板从第零秒按原速播放，不再次偏移、伸缩或拼接。末尾音量按 `fadeOutSeconds` 平滑降至零，默认 0.35 秒；省略 `audio` 就无音轨。所有素材路径相对 `public/`，不接受绝对路径或 `..`。

首镜头要求 `impactFrame=0, preFrames=0`；之后 impact 必须严格递增、位于视频范围内。后续 `preFrames` 正整数且不大于 impact；`postFrames`、`releaseFrames` 正整数；强度在 0–1。不得为通过校验而静默重排检测事件。`eventType` 保存检测来源信息，模板不根据它虚构节拍。

图片过渡从 `impactFrame-preFrames` 开始，在 impact **恰好混合 50%**，到 `impactFrame+postFrames` 完成。前后时间可不对称，混合使用 smoothstep。它不是在音符处突然硬切；若用户希望视觉更柔和，延长 pre/post，同时保留 impact。节奏运动使用独立的 attack/release 包络，多个音符的释放尾部以 soft union 共存，不因下一音符重置。波形、敲击峰与人耳听感仍需核对。

## 模式

逐镜头 `transition` 优先于顶级 `mode`，缺省为 `press`。所有模式都有图片淡入淡出。

| 名称 | 有 subjectMask | 没有 subjectMask |
|---|---|---|
| dissolve | 无节奏形变，正常混合 | 无节奏形变，正常混合 |
| press | A：环境收缩/按下/回弹；保护层位置、尺寸和亮度固定 | 整幅图片收缩/按下/回弹 |
| pulse | B：同一环境运动，保护层随敲击变暗再恢复 | 整幅图片运动并发生亮度脉冲 |
| bounce | C：同一环境运动，保护层亮度脉冲，轻缩放与垂直震动 | 整幅图片运动，叠加亮度和轻缩放/震动 |

主体与环境都使用同一个 `Worlds` 混合时钟。“固定”仅指保护层的几何变换，不意味着跨图人物/标题像素完全相同：源图位置、轮廓或文字不同依然会在交叉渐变时重影。没有 mask 时不能宣称人物或标题固定。若素材本身有未分离的主体，环境放大层可能在保护区边缘露出重复轮廓，必须逐帧检查；扩大 mask、减少运动幅度、改成普通 dissolve 或换可分离素材。

## Motion 参数

完整类型与默认值在 `types.ts`；timing/像素/强度均可由 timeline 覆盖。默认取自已有琴键运动实现，时间参数针对 **60fps**；换 fps 时，应按 `fps/60` 调整 attack、rebound、shake 的帧数参数，并让分析脚本按目标 fps 生成每镜头 pre/post/release。`shakeRadiansPerFrame` 应除以同一倍率。

| 参数 | 默认 | 含义 |
|---|---:|---|
| attackFrames | 3 | 运动按下的提前帧数，独立于图片 preFrames |
| environmentBaseScale | 1.07 | 环境基准放大，留出移动余量；全 dissolve 时不放大 |
| environmentContraction / environmentRebound | .058 / .019 | 环境按下收缩、回弹幅度 |
| environmentPressPixels / environmentReboundPixels | 7 / 2 | 环境垂直按下、回弹距离 |
| environmentOrigin / subjectOrigin | 50% 50% | 变换中心；应根据当前画面选择，不预设人物坐标 |
| environmentEV | 0 | 环境曝光补偿；负数压暗，零不处理 |
| subjectBrightnessDrop / subjectBrightnessRebound | .28 / .045 | pulse/bounce 的保护层亮度变化 |
| subjectContraction / subjectRebound | .025 / .009 | bounce 的保护层缩放 |
| subjectPressPixels / subjectShakePixels | 4 / 2.5 | bounce 的按下/振动距离 |
| reboundPeakFrames / reboundWidthFrames | 5.5 / 3.4 | 回弹高斯包络 |
| shakeRadiansPerFrame / shakeDecayFrames | 2.35619 / 3.4 | 震动频率与衰减时间 |
| releaseDecay | 3.8 | 指数释放衰减系数 |

`environmentEV` 使用 SVG `linearRGB` 滤镜动态乘以 `2**EV`，无需复制整套压暗图片。保护层覆在其上保留原始曝光；羽化区自然混合。pulse 的亮度变化另用 CSS brightness，是节奏效果，不能称为精确的线性光 EV。位移与曝光的遮罩效果必须在实际渲染中检查。

无 mask 的整图运动会约束最小缩放，给默认居中变换保留垂直移动余量。若将变换中心改为边角或明显增大位移，需重新检查四边覆盖；这种自选构图不保证自动消除露边。

## 可选：广软椭圆保护罩

优先用现成真实透明主体/标题 mask；没有时可用 `scripts/make_exposure_mask.py` 生成宽羽化的椭圆 alpha 保护罩。RGBA 中 RGB 为白色，**alpha 才是保护强度**：全不透明区保留主体，透明区显示环境。普通全不透明灰度图不能直接充当 alpha mask。

配置中的坐标与半径均按当前输出尺寸的像素填写，例如下面只是通用输入格式示范，不是固定构图推荐：

```json
{"width":1080,"height":1440,"ellipses":[
  {"cx":540,"cy":720,"rx":250,"ry":360,"feather":180}
]}
```

```powershell
py -3.11 <skill>/scripts/make_exposure_mask.py --config mask-config.json --output public/masks/subject.png
```

内椭圆为完全保护平台，外围按从中心穿过边界的射线距离做高斯衰减；`feather` 为边界外一倍标准差的像素宽度。它不是最短欧氏距离。多个椭圆以 soft union 合并，不设有限的外硬边。Agent 应先看实际图、按主体/标题自选区域，再做原尺寸静帧和运动预览，不要照搬示例坐标。

旧有硬框光晕已被用户否定，不作为默认风格。更广软的 feather 目前只有静态候选，**未获用户认可，也未证明运动时无接缝**；模板仅提供可选技术，不能把它写成已确认视觉方案。压暗 2.6EV 等旧数值也不是通用默认。

## 检查与验证

在 staged 工程执行 `tsc --noEmit`；再用同版本 Remotion CLI 验证入口：

```powershell
remotion still index.tsx ImageBeatStory midpoint.png --frame=60
remotion studio index.tsx --no-open
```

在 impact 前、impact、impact 后、密集事件尾部重叠处、最后淡出段检查，至少包括有/无 mask 和所选模式。确认过渡中点、运动释放、分辨率、尾部音量与时长。静帧/编译通过不代表音画同步或人类审美已验证。生成视频须遵守调用方交付与版本要求，不覆盖已交付成片。
