# 浏览器读取及脚本交接

先阅读当前浏览器工具的文档。以下是 2026-10-25 在 Codex CUA 的验证示例，`tab` 代表已经绑定的目标作品页；工具 API 变化时依当前文档调整。

```javascript
nodeRepl.write(await tab.playwright.evaluate(() => ({
  title: document.title,
  media: Array.from(document.querySelectorAll('video,audio')).map(e => ({
    tag: e.tagName,
    currentSrc: e.currentSrc,
    src: e.getAttribute('src'),
    sources: Array.from(e.querySelectorAll('source')).map(s => s.getAttribute('src')),
    duration: Number.isFinite(e.duration) ? e.duration : null,
    currentTime: e.currentTime,
    readyState: e.readyState
  }))
})));
```

这是读取页面 DOM 的媒体状态。读取 `currentSrc` 无需抓包、登录信息或隐藏的应用状态。`VIDEO` 标签也可能承载图文的纯音频，最终以 ffprobe 检查到的流为准。

若 `currentSrc` 为空而 `source` 有值，可先观察一次目标播放控件是否需要正常播放。`source` URL 可作为候选，但只有下载后验证成功才有效。多个候选通常是 CDN 备用域名，先试当前加载地址；网络失败再试同一播放器的备用地址。

用 UI 快照/作品容器确认当前标题和媒体归属。目标页有多个有效播放器时，先缩小到目标容器再读取；保留匹配理由。不要整页打印长达数万字的 AX 树或加载全部评论，只返回这几个字段。以往 `getTab` 自动初始快照曾超过 30 秒，但导航已成功；先确认绑定还在，再做小范围 DOM 读取，勿重复新建页。那次允许 60 秒的读取成功了，这不是需要固定等待 60 秒。

把确认后的结果保存成下面的交接结构（字段值替换为本次实际观察）：

```json
{
  "input_share_url": "https://v.douyin.com/dwNKaLJs4Z4/",
  "work_url": "https://www.douyin.com/note/7681242969178125254",
  "title": "翻山越岭，生命随我流动#卓越山#风与山",
  "kind": "note_music",
  "current_src": "<目标播放器本次实际加载的 HTTPS 媒体地址>",
  "media_duration_seconds": 39.079175,
  "media_match_reason": "目标作品页的标题匹配；仅一个播放器有实际媒体源",
  "observed_at": "<本次观察时间>"
}
```

`kind` 必须是 `note_music` 或 `video_audio`，明确来源类型；时长未加载时用 null，回执将标为没有播放器时长比对。旧试验文件没有 `kind` 时，执行脚本前补齐，原始文件保持不动。这里的例子只说明结构，不可直接拿示例 URL 作为其他作品的来源。

来源回执中的时长比较验证“下载文件与播放器资源一致”，不证明声部纯净、节拍正确或适合剪辑。后续 BGM 分析模块读取 WAV 和回执时仍需试听。
