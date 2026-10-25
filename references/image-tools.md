# 图片准备、固定锚点筛选与排序

这三个脚本从已验证工程的 `color_sequence.py`、`filter_title_jitter.py` 提取通用算法。读取输入后保留原件，输出写入新的空目录。Python 依赖：Pillow、numpy、opencv-python（`cv2`）、scikit-image；不安装额外框架。Windows 示例使用已配置这些库的 `py -3.11`。脚本禁用技能目录内的字节码缓存。

## 共用输入与输出

图片坐标均为**完成 EXIF 方向处理与裁切之后**的 1080×1440 像素；ROI 为 `[x,y,width,height]`，左上原点，右/下边界不包含。不要把原图 ROI 原封不动复制到裁切图：1086×1448 中心硬裁时，原图 x 减 3、y 减 4。

统一 manifest：

```json
{
  "schemaVersion": 1,
  "width": 1080,
  "height": 1440,
  "images": [
    {
      "id": "img-0001",
      "path": "D:/work/prepared/images/img-0001.png",
      "sourceName": "original-folder/001.png",
      "originalIndex": 1
    }
  ]
}
```

`id` 在准备阶段按原始图片顺序分配，之后重排不变；`originalIndex` 从 1 开始，始终表示原始图片顺序。`path` 为已存在的绝对路径。其他追踪字段可保留。ZIP 会额外记录包含非图片条目的 `sourceArchiveIndex`，图片序号与 ZIP 全条目序号分别记录。

每步输出 `manifest.json`、`report.json`、`contact-sheet.jpg`。filter/order 的 manifest 引用 prepare 的图片绝对路径，不复制图片，因此携带整个制作工程时应同时保留 prepared 目录。所有输出目录必须为新目录或空目录，既有产物不会被覆盖。联系表只供查看；分析使用准备后的原尺寸图片。Agent 阅读报告，并查看联系表后，才能确认是否继续；技术指标不代表人类质量验收。

## 1. prepare_images.py

```powershell
py -3.11 "<skill>/scripts/prepare_images.py" --input "D:/input/images.zip" --output-dir "D:/work/prepared"
```

- 输入支持 ZIP 或图片目录（递归），扩展名为 PNG/JPG/JPEG/WEBP/BMP/TIF/TIFF；动画、多页图片需先明确选择单帧。
- 默认 `--order preserve`：ZIP 保留中央目录的图片条目顺序，目录保留此次文件系统递归枚举顺序。目录枚举顺序可能因文件系统变化，报告始终记录本次原始顺序。
- `--order natural` 明确按完整相对来源名自然排序；`--order list --order-file "D:/work/source-order.json"` 按 JSON 字符串数组中的完整 `sourceName` 顺序，必须覆盖所有图片且无重复。目录或 ZIP 内同名路径重复时拒绝显式名称排序。
- 1080×1440 不裁切；1086×1448 仅裁左右各 3、上下各 4 像素。全程不拉伸、不缩放。输出重编码 PNG，保存源字节 SHA256、尺寸与裁切框，原件不变。
- 其他尺寸默认写异常报告并拒绝整个批次，尚未写入准备图片。先看异常，再由 Agent 决定裁切方案。只有已明确接受中心裁切时才用 `--allow-center-crop`，允许尺寸不小于 1080×1440 的图片中心裁切；较小图片始终拒绝。若差值为奇数，多裁右/下侧 1 像素。
- 目录输入的输出目录放在输入目录之外，避免再次输入时把旧输出混进素材。

完成条件：报告无异常、图片数与来源一致、manifest 路径可读，联系表未见不当裁切。1080×1440“不变”指像素和取景保持，文件会重编码；嵌入色彩配置不保证传递，先检查需严格色彩管理的素材。

## 2. filter_anchors.py

先查看 prepared 图片并选定参考图、每个固定锚点及其搜索区域，复制并修改 `assets/examples/anchors.example.json` 到本次工程。例子仅示范旧集合的锚点坐标，换图片必须重新选区。锚点可以是文字、人物局部、标识或其他稳定边缘；脚本没有内置“标题/人物”坐标。

```powershell
py -3.11 "<skill>/scripts/filter_anchors.py" --manifest "D:/work/prepared/manifest.json" --reference img-0001 --anchors "D:/work/anchors.json" --output-dir "D:/work/filtered"
```

`--reference` 可为 manifest ID 或准备后的绝对图片路径，优先于配置的 `reference`。配置的 `anchors` 支持任意多个对象；`defaults` 及单个锚点均可设置下列参数，锚点值覆盖 defaults：

| 字段 | 默认值 | 含义 |
|---|---|---|
| `name` | 按序分配 | 唯一锚点名 |
| `roi` | 必填 | 参考图模板范围 |
| `searchRoi` | 必填 | 每张候选图内的搜索范围，应容纳模板和预期位移 |
| `maxXShift` / `maxYShift` | 32 / 24 | 最大绝对横向/纵向位移（像素） |
| `maxScaleChange` | 0.08 | 最大相对尺寸变化 |
| `minConfidence` | 0.30 | Canny 模板相关分数阈值，不是概率 |
| `scaleRange` | `[0.90,1.10,21]` | 均匀采样最小/最大尺度及采样数 |
| `canny` | `[60,150]` | Canny 低/高阈值 |
| `minEdgePixels` | 20 | 模板、搜索区最小边缘像素数 |
| `baseline` | `reference` | 对照参考 ROI 中心与尺度 1；`median` 复用旧工程的可靠检测中位数基准 |

算法保留旧工程的 Canny、多尺度最近邻模板缩放、`TM_CCOEFF_NORMED` 最大相关搜索。超过任意锚点容差的可靠检测标为候选排除。若任何锚点分数不足，该整张图片保留并标 `needs_review`；匹配不了不等于图片有错。一个锚点不足半数图片可靠时，该锚点判为整组不可靠，本批次所有图片进入复核并保留；如果本来会全部排除，也保留整组并报告保护原因。

报告逐图记录 confidence、中心、scale、dx、dy、scaleChange、候选理由与复核理由。输出清单仅移除可靠超差项，源图片不删除；另输出每个锚点的搜索区联系表，十字标记匹配中心。已有来源中的 `excludedIds` 是上游记录；本步报告的 `excludedIds` 仅表示本次排除结果，串联多步时保留每步报告。

限制：只搜索位移和有限的等比缩放，不支持任意旋转、透视、非刚体变化、遮挡或复杂背景中的可靠匹配。重复形状也可能产生错误高分，Agent 需看图。本版仅筛选，不自动修正锚点位置；轻微修正应由 Agent 根据实际画面另判断。`median` 适合大多数图片位置一致的集合，若多数图片共同偏移，它无法保留对原参考的绝对锚定。扩大搜索区、修改阈值需据报告和画面判断。

完成条件：排除清单与逐图证据相符；`needs_review` 项已由 Agent 看图处理，或明确保留给用户复核。不要把筛选脚本退出成功解释为审美或几何完全对齐。

## 3. order_images.py

叙事/时间/因果顺序默认保留：

```powershell
py -3.11 "<skill>/scripts/order_images.py" --manifest "D:/work/filtered/manifest.json" --output-dir "D:/work/ordered"
```

Agent 明确编排可以选择子集；JSON 为非空 ID 数组，如 `["img-0007","img-0001","img-0004"]`：

```powershell
py -3.11 "<skill>/scripts/order_images.py" --manifest "D:/work/prepared/manifest.json" --mode explicit --order-file "D:/work/image-ids.json" --output-dir "D:/work/ordered-explicit"
```

重复 ID、未知 ID 都拒绝；未采用图片记录为 `unusedIds`，原件保留。只有内容适合按画面颜色衔接，且 Agent 明确决定如此时才运行颜色排序：

```powershell
py -3.11 "<skill>/scripts/order_images.py" --manifest "D:/work/prepared/manifest.json" --mode color --color-config "D:/work/color-config.json" --output-dir "D:/work/ordered-color"
```

颜色配置可省略，默认分析整幅图片；要避免固定主体影响颜色排序，提供裁切后像素坐标：

```json
{
  "excludeRects": [[245,266,587,317], [138,778,519,547]],
  "weights": {
    "background_mean_delta_e_2000": 0.25,
    "spatial_lab": 0.35,
    "color_distribution_hellinger": 0.25,
    "brightness_distribution": 0.15
  }
}
```

此算法复用旧工程：缩小至 108×144 仅供分析，CIELAB 均值 ΔE2000、3×4 空间 Lab、10×10 a/b 直方图 Hellinger 距离、20 档亮度 CDF 距离；各项按全体两两距离中位数归一化并加权。所有起点做最近邻初始化，取最好的 16 条进行最多 120 轮开放路径 2-opt。输出图片保持原像素，仅清单顺序变化。可选 `--warm-opening` 在同一条路径的两个方向中选择较暖/亮的一端起步，保留旧工程的方向启发式。

报告提供前后邻接代价、最大跳变和采用顺序。它是确定性启发式，不证明全局最优；代价下降仅说明该指标下降，不证明人类偏好或叙事质量提升。大集合具有两两距离与多起点 2-opt 成本，优先用于数十张量级；先小样本检查再扩展。

完成条件：输出顺序与 Agent 的表达目标相符；查看联系表确认开头、结尾和跳变，明确记录未采用图片。传给节奏/合成脚本时直接使用本步 `manifest.json`。
