# 实测成功路径与弯路

2026-10-25，输入为 `https://v.douyin.com/dwNKaLJs4Z4/`，目标标题“翻山越岭，生命随我流动#卓越山#风与山”。以下为单个案例的实测记录，网站接口可能变化，不能推断全部链接都支持。

## 成功路径

1. 普通 HTTP 跟随短链，先到 `iesdouyin.com/share/video/7681242969178125254/`，桌面继续到 `www.douyin.com/note/7681242969178125254`。分享中间页叫 video，并不代表作品真是视频。
2. 浏览器实际载入作品页。DOM 媒体读取显示两个 VIDEO，其中一个有媒体源，另一个无源；页面标题和作品标题吻合。
3. 有源播放器 `currentSrc` 为 `https://lf9-music-east.douyinstatic.com/obj/ies-music-hj/7646401861532109626.mp3?is_ssr=1&temp=1`，另有同文件的 lf26 备用 CDN。该 URL 仅作为当次证据，后续任务重新读取。
4. 下载播放器资源。ffprobe：MP3、44100 Hz、双声道、39.079175 秒；与浏览器 duration 一致。文件 1,563,371 字节，完整解码成功；另转 PCM WAV 供卡点分析。
5. 源文件 SHA256：`7e2447606572b342bda6f636af3da52f1b963b3f2a4a1f0eb0f29788e37197ca`。曲名辅助核对为 12LUFS《Running Up On Hill (带感氛围版)》。这是作品加载的配乐资源，不是另搜的歌曲。

## 走过的弯路及下一次的决策

| 当时尝试 / 现象 | 得到了什么 | 下次怎么处理 |
| --- | --- | --- |
| HTTP 获取桌面作品页 | 200，约 72KB，实际是风控 JS | 200 不代表内容可用；转正常浏览器作品页，不反复解析同一脚本 |
| 只在 URL 中匹配 `/video/` | `/note/` 的作品 ID 漏掉 | 同时识别 note、video、share/video；以最后有效作品页类型为准 |
| 把 note 改成 video 后跑 yt-dlp | `Fresh cookies (not necessarily logged in) are needed` | 这是本次路径失败，不代表作品不存在；保留真实 URL，优先浏览器 DOM。yt-dlp 在别的环境能用时仍可用 |
| `/aweme/v1/web/aweme/detail/` | `Blocked by ArgusSecurityPlugin Uifid Not Found` | 停止同类详情重试，切换正常页面路线 |
| 移动分享页 `_ROUTER_DATA` | 有 itemId、上下文及实验参数，没有作品媒体 | 不把出现 router JSON 视为拿到音频；无需继续下载各个页面 bundle |
| `/web/api/v2/aweme/iteminfo/` | 空返回 | 用浏览器播放器，不靠换 UA 反复撞同一接口 |
| `/web/api/v2/aweme/slidesinfo/` 更换 ID 数组格式 | 空 aweme_details 或 filter_list reason 8 | 停止排列组合请求参数；避免为一次输入逆向签名协议 |
| 从分享跳转的 `mid` 查音乐接口 | 曲名、作者、duration 39；没有 play_url | 仅辅助曲目核对。音乐 ID 不是 CDN 文件 ID，不能据此拼下载地址 |
| 浏览器 getTab / 全量快照 30 秒超时 | 页面其实已载入，作品标题可见 | 复用已有页/绑定，最小 DOM 媒体读取；一次合理延长工具超时即可，避免重复建页和输出巨量 AX |
| 用 metadata 的 39 秒直接当作品时长 | 元数据是整秒，图文停留时间不固定 | 以播放器资源和实际文件的 39.079175 秒核对，说明是一次配乐资源 |

## 失败结果如何保留

保存已解析出的作品 URL、媒体观察和错误阶段。若拿到曲名但拿不到音频，明确“已识别音乐，未取得文件”。若只有 HTTP/解码错误，保留诊断信息，后续尝试新目录或新名字。所有回执以实际文件验证为准。

## Skill 脚本验证边界

2026-10-25 创建 skill 时，实际分享文案经 `resolve` 成功定位同一 note，`acquire` 使用刚才浏览器记录的资源重新下载、生成 WAV、完整解码；原始 MP3 哈希与上述首次取得的文件一致。另用本地合成 AAC 视频验证视频转 MP3/WAV，并验证重名拒绝覆盖、播放器时长不匹配时不生成成功回执、链接紧接中文和括号时正确截取。

这些是一个真实抖音案例和本地转换分支的测试。没有据此宣称所有抖音页面都可解析，也没有验证无人值守浏览器批处理或音乐听感。独立检查发现并修复了分享 URL 尾部误含中文、带封面 MP3 被再次编码的问题。

## 相邻输入：汽水音乐

曾验证 `https://qishui.douyin.com/s/iXnCdbhR/`，曲目 `7667507112771160083`，SHA211《Never see me again( 纯音乐)》。公开分享页 `_ROUTER_DATA.loaderData.track_page.audioWithLyricsOption` 暴露未加密试听资源。

- 元数据整首 156.824 秒，实际公开资源 59.977007 秒，对应原曲 56.448–116.426 秒。
- 返回的音频 URL **已经裁好试听片段**。不能再按原曲的 56.448 秒在该文件上裁一次。
- `encrypt:false`、试听状态和 URL 可用后，先核对资源实际时长，再下载和完整解码；清楚标注试听。
- 当时的源脚本位于 SelfMedia 的 `管理/工具/媒体输入/resolve_qishui_share.py`；现已迁入本 skill 的 `scripts/qishui_preview.py`，使用内置副本即可，旧路径仅用于历史追溯。
- 用户要求只使用提供链接内的可得片段。试听结束不转而搜索整首或其他版本。
