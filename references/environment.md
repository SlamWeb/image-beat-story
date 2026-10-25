# 运行环境

先检查已有运行环境。可复用同版本 Remotion 工程，避免每条内容各装一份依赖。脚本与模板路径都相对本仓库。

## Python 与音频工具

已验证 Python 3.11。使用当前环境的 Python 安装脚本依赖：

```sh
python -m pip install -r scripts/requirements.txt
```

需要 FFmpeg 与 ffprobe。脚本可通过 `imageio_ffmpeg` 找到 FFmpeg，ffprobe 需在 PATH 中或通过 `--ffprobe` 指定。已有 Remotion compositor 包中也可能包含 ffprobe，按平台查看实际文件。

## Remotion

安装 Node.js 后，可在内置模板目录准备共享运行环境：

```sh
cd assets/remotion-template
npm install
```

模板固定 Remotion 4.0.534，各 Remotion 包保持同版本。生成具体视频时，`build_edit.py` 会把模板和本次素材复制到新的工程目录；`remotion_job.mjs --runtime` 指向这个已安装依赖的模板目录，或你已有的兼容工程。

浏览器渲染可显式传 `--browser-executable` 使用现有 Chrome；先查看机器上的实际路径。Studio 预览、参数与导出步骤见 [edit-and-render.md](edit-and-render.md)。

## 链接输入

本地 BGM 文件可以直接分析。抖音分享链接由 Agent 配合浏览器读取实际播放器资源，获取步骤与失败处理见 [bgm-input.md](bgm-input.md)。仅有脚本而没有浏览器工具的运行环境，不能保证完成链接解析。
