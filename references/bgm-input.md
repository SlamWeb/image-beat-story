# BGM 是总流程的输入环节

本地文件直接交给音频分析。抖音分享文案先运行：

```powershell
py -3.11 "<skill>/scripts/douyin_audio.py" resolve "<分享文案>" --output-dir "<制作资料>/bgm-resolve"
```

拿到 work_url 后按 [bgm-browser.md](bgm-browser.md) 打开该作品、核对标题并读取实际播放器 `currentSrc`。记录浏览器观察 JSON，再运行：

```powershell
py -3.11 "<skill>/scripts/douyin_audio.py" acquire --observation "<制作资料>/browser-observation.json" --output-dir "<制作资料>/bgm" --ffprobe "<ffprobe路径>" --wav
```

下载后会检查音轨、时长、完整解码，原本是 MP3 则保留字节；视频源提取现有音轨，可能含人声/环境声。图文作品的独立配乐也可提取。下一环节读取所得 MP3 或 WAV 和来源回执。这里只取得来源，不提前改变音乐速度或选视频片段。

脚本不会自动操作浏览器，这是 Agent 编排的一环。首页 `?recommend=1` 不指向确定作品；使用作品分享链接。`/note/` 保留为图文类型。音乐名称或 ID 仅用于核对，真正完成以音频文件验证为准。失败路线和实测案例见 [bgm-lessons.md](bgm-lessons.md)，尤其是接口风控、空详情、浏览器初始大快照超时。

需要 FFmpeg、ffprobe；已有系统路径优先，`imageio_ffmpeg` 可以提供 FFmpeg，但不提供 ffprobe。Windows 上可检查已有 Remotion 工程的 `node_modules/@remotion/compositor-win32-x64-msvc/ffprobe.exe`，其他平台检查对应包；用 `--ffprobe` 指定实际程序。

## 汽水链接

`scripts/qishui_preview.py <汽水分享URL> --output-dir <新目录> --ffprobe <路径> --wav` 保留公开试听资源和 WAV，不声称取得整首。返回的文件可能已经裁好试听段，按回执的 `local_audio_time_zero` 使用，不能把歌曲偏移再减一次。该辅助脚本从本机已验证的输入试验迁入，范围与限制见 [bgm-lessons.md](bgm-lessons.md)。

默认只用用户链接中实际可得的音频，不另搜更长版本。若用户另外指定需要整首，应重新确定合法可用来源和实际版本，不能把当前试听当整首。
