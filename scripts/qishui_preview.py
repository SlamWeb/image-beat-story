"""Resolve a public Qishui share page and retain only its exposed preview asset.

No login, browser cookies, decryption or full-track endpoint is used.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import argparse
import hashlib
import json
import re
import shutil
import subprocess

import requests
import imageio_ffmpeg


def probe(executable,source):
    response=subprocess.run([str(executable),'-v','error','-show_streams','-show_format','-of','json',str(source)],
                            check=True,capture_output=True,text=True,timeout=45)
    return json.loads(response.stdout)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--ffprobe',type=Path)
    parser.add_argument('--wav',action='store_true')
    args=parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError('Use a new or empty output directory; preserve prior receipts and partial downloads.')
    if urlparse(args.url).hostname not in {'qishui.douyin.com','music.douyin.com'}:
        raise ValueError('Expected a Qishui public share URL.')
    ffprobe=args.ffprobe or shutil.which('ffprobe')
    if not ffprobe:
        raise FileNotFoundError('Pass --ffprobe or make ffprobe available on PATH.')
    page=requests.get(args.url,timeout=30);page.raise_for_status()
    match=re.search(r'_ROUTER_DATA\s*=\s*',page.text)
    if not match:raise ValueError('No public track metadata in share page; no audio acquired.')
    metadata,_=json.JSONDecoder().raw_decode(page.text[match.end():])
    option=metadata['loaderData']['track_page']['audioWithLyricsOption']
    if option.get('status_code')!=0 or option.get('encrypt') is not False or not option.get('url'):
        raise ValueError('No unencrypted public preview asset; no audio acquired.')
    preview_duration=float(option.get('offsetDuration') or (option['previewEnd']-option['previewStart']))
    source_start=float(option.get('offsetStart',option['previewStart']))
    remote=probe(ffprobe,option['url'])
    actual=float(remote['format']['duration'])
    if abs(actual-preview_duration)>.12:
        raise ValueError(f'Asset duration {actual}s does not match the exposed preview {preview_duration}s; stop rather than retrieve a full track.')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    filename=f'{option["trackName"]}-{option["artistName"]}-汽水试听-v001'
    filename=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',filename).strip(' .')
    output=args.output_dir/f'{filename}.m4a'
    if output.exists():raise FileExistsError(f'Refusing to overwrite {output}')
    partial=output.with_suffix('.m4a.part')
    with requests.get(option['url'],stream=True,timeout=35) as media:
        media.raise_for_status()
        with partial.open('wb') as stream:
            for chunk in media.iter_content(128*1024):
                if chunk:stream.write(chunk)
    local=probe(ffprobe,partial)
    audio=[s for s in local['streams'] if s['codec_type']=='audio']
    if len(audio)!=1 or abs(float(local['format']['duration'])-preview_duration)>.12:
        raise ValueError('Downloaded preview metadata mismatch; partial retained for diagnosis.')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(partial),'-f','null','-'],check=True,capture_output=True)
    partial.rename(output)
    wav_path=None
    if args.wav:
        wav_path=output.with_suffix('.wav')
        if wav_path.exists():raise FileExistsError(f'Refusing to overwrite {wav_path}')
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(output),'-c:a','pcm_s16le',str(wav_path)],check=True)
    receipt={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
             'input_url':args.url,'canonical_track_url':f'https://music.douyin.com/qishui/share/track?track_id={option["track_id"]}',
             'track_id':option['track_id'],'title':option['trackName'],'artist':option['artistName'],
             'track_duration_seconds':option['duration'],'acquired_kind':'public_preview_audio',
             'actual_duration_seconds':actual,'page_preview_duration_seconds':preview_duration,
             'track_preview_start_seconds':source_start,'track_preview_end_seconds':option['previewEnd'],
             'local_audio_time_zero':'Start of the preview file, corresponding to track_preview_start_seconds; do not trim that offset again.',
             'file':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
             'codec':audio[0]['codec_name'],'sample_rate':audio[0]['sample_rate'],'channels':audio[0]['channels'],
             'original_public_media_retained':True,'full_decode_succeeded':True,
             'login_or_browser_cookies_used':False,'decryption_used':False,'full_song_downloaded':False,
             'existing_video_bgm_replaced':False,
             'wav':str(wav_path) if wav_path else None}
    (args.output_dir/'source-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
