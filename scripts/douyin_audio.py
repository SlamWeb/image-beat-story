"""Resolve a Douyin share, then acquire a media URL observed in its browser player."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse

import requests


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def work_identity(url):
    parsed = urlparse(url)
    if parsed.hostname not in {'www.douyin.com', 'douyin.com', 'www.iesdouyin.com', 'iesdouyin.com'}:
        return None
    match = re.search(r'/(?:share/)?(video|note)/(\d+)(?:/|$)', parsed.path)
    return (match[1], match[2]) if match else None


def resolve(args):
    text = args.input_file.read_text(encoding='utf-8-sig') if args.input_file else args.text
    urls = re.findall(r'https?://[A-Za-z0-9._~:/?#@!$&*+,;=%-]+', text or '')
    urls = list(dict.fromkeys(u.rstrip(',.;!') for u in urls
        if (urlparse(u).hostname or '').lower() in {
            'v.douyin.com', 'www.douyin.com', 'douyin.com', 'www.iesdouyin.com', 'iesdouyin.com'}))
    if len(urls) != 1:
        raise ValueError('Supply exactly one Douyin work/share URL (share text is accepted).')
    response = requests.get(urls[0], headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    response.raise_for_status()
    identity = work_identity(response.url)
    if not identity:
        raise ValueError('No work ID in final URL. Get the current work share link, not the recommendation homepage.')
    kind, work_id = identity
    page = f'https://www.douyin.com/{kind}/{work_id}'
    result = {'input_share_url': urls[0], 'resolved_url': response.url,
              'work_url': page, 'work_id': work_id, 'url_kind': kind,
              'stage': 'resolved_only', 'next_step': 'Observe target player media in the browser.'}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / 'resolve.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def executable(explicit, name):
    if explicit:
        path = str(explicit)
    else:
        path = shutil.which(name)
        if not path and name == 'ffmpeg':
            try:
                import imageio_ffmpeg
                path = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                pass
    if not path or not Path(path).is_file():
        raise ValueError(f'{name} unavailable; pass --{name} or use an existing installation on PATH.')
    return path


def probe(ffprobe, path):
    result = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', str(path)], check=True, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def run_media(command):
    subprocess.run(command, check=True, capture_output=True, timeout=300)


def acquire(args):
    observed = json.loads(args.observation.read_text(encoding='utf-8-sig'))
    identity = work_identity(observed['work_url'])
    if not identity or observed.get('kind') not in {'note_music', 'video_audio'}:
        raise ValueError('Observation needs a Douyin work_url and kind note_music or video_audio.')
    if observed['kind'] != ('note_music' if identity[0] == 'note' else 'video_audio'):
        raise ValueError('Observation kind must match the canonical work URL type.')
    if not observed.get('media_match_reason'):
        raise ValueError('Record how this media was matched to the target work in media_match_reason.')
    media_url = observed['current_src']
    if urlparse(media_url).scheme != 'https' or not urlparse(media_url).hostname:
        raise ValueError('Expected an actual HTTPS media source observed in the target player.')
    expected = observed.get('media_duration_seconds')
    if expected is not None and (not math.isfinite(float(expected)) or float(expected) <= 0):
        raise ValueError('Player duration must be positive and finite, or null if unavailable.')
    ffprobe, ffmpeg = executable(args.ffprobe, 'ffprobe'), executable(args.ffmpeg, 'ffmpeg')
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', args.name).strip(' .')
    if not name:
        raise ValueError('Output name is empty.')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mp3 = args.output_dir / f'{name}.mp3'
    wav = args.output_dir / f'{name}.wav'
    receipt_path = args.output_dir / f'{name}-source-receipt.json'
    obs_path = args.output_dir / f'{name}-browser-observation.json'
    source = args.output_dir / f'{name}.source-media'
    partial = args.output_dir / f'{name}.download.part'
    mp3_part = args.output_dir / f'{name}.encode.part.mp3'
    for path in [mp3, receipt_path, obs_path, source, partial, mp3_part] + ([wav] if args.wav else []):
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite {path}; use a new output name/directory.')
    write_json(obs_path, observed)
    with requests.get(media_url, headers={'User-Agent': 'Mozilla/5.0',
            'Referer': observed['work_url']}, stream=True, timeout=(15, 45)) as response:
        response.raise_for_status()
        with partial.open('xb') as stream:
            for chunk in response.iter_content(128 * 1024):
                if chunk:
                    stream.write(chunk)
    metadata = probe(ffprobe, partial)
    audio = [s for s in metadata['streams'] if s['codec_type'] == 'audio']
    if len(audio) != 1:
        raise ValueError('Expected exactly one audio stream; inspect source before selecting a track.')
    duration = float(metadata['format']['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Downloaded source has no valid finite duration.')
    if expected is not None and abs(duration - float(expected)) > max(.25, float(expected) * .001):
        raise ValueError(f'Download duration {duration}s differs from player {expected}s; verify target source.')
    run_media([ffmpeg, '-v', 'error', '-xerror', '-i', str(partial), '-map', '0:a:0', '-f', 'null', '-'])
    original_hash = hashlib.sha256(partial.read_bytes()).hexdigest()
    if metadata['format']['format_name'] == 'mp3':
        partial.rename(mp3)
        source = mp3
        conversion = 'original_mp3_bytes'
    else:
        partial.rename(source)
        run_media([ffmpeg, '-n', '-v', 'error', '-i', str(source), '-map', '0:a:0', '-vn',
                   '-c:a', 'libmp3lame', '-q:a', '2', str(mp3_part)])
        run_media([ffmpeg, '-v', 'error', '-xerror', '-i', str(mp3_part), '-f', 'null', '-'])
        mp3_part.rename(mp3)
        conversion = 'audio_extracted_and_encoded_mp3'
    delivered = probe(ffprobe, mp3)
    if args.wav:
        # Analyze the source rather than a newly lossy MP3 when transcoding was necessary.
        run_media([ffmpeg, '-n', '-v', 'error', '-i', str(source), '-map', '0:a:0', '-vn',
                   '-c:a', 'pcm_s16le', str(wav)])
        run_media([ffmpeg, '-v', 'error', '-xerror', '-i', str(wav), '-f', 'null', '-'])
    result = {'created_at': datetime.now(timezone.utc).isoformat(), 'stage': 'verified_audio',
        'work_id': identity[1], 'work_url': observed['work_url'],
        'input_share_url': observed.get('input_share_url'), 'work_title': observed.get('title'),
        'acquired_kind': observed['kind'], 'source_url': media_url,
        'media_match_reason': observed['media_match_reason'],
        'browser_player_duration_seconds': expected, 'player_duration_compared': expected is not None,
        'scope_verification': 'player_duration_matched' if expected is not None else 'duration_unconfirmed_against_player',
        'source_duration_seconds': duration, 'mp3_duration_seconds': float(delivered['format']['duration']),
        'source_audio_codec': audio[0]['codec_name'], 'source_sample_rate': audio[0].get('sample_rate'),
        'source_channels': audio[0].get('channels'),
        'source_file': str(source.resolve()), 'source_sha256': original_hash,
        'mp3_file': str(mp3.resolve()), 'mp3_sha256': hashlib.sha256(mp3.read_bytes()).hexdigest(),
        'wav_file': str(wav.resolve()) if args.wav else None,
        'conversion': conversion, 'full_decode_verified': True, 'human_listening_verified': False}
    write_json(receipt_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    resolver = commands.add_parser('resolve', help='Extract share URL and follow ordinary redirects.')
    resolver.add_argument('text', nargs='?')
    resolver.add_argument('--input-file', type=Path)
    resolver.add_argument('--output-dir', type=Path, required=True)
    resolver.set_defaults(action=resolve)
    downloader = commands.add_parser('acquire', help='Download and validate a browser-observed media source.')
    downloader.add_argument('--observation', type=Path, required=True)
    downloader.add_argument('--output-dir', type=Path, required=True)
    downloader.add_argument('--name', default='作品配乐-v001')
    downloader.add_argument('--ffmpeg', type=Path)
    downloader.add_argument('--ffprobe', type=Path)
    downloader.add_argument('--wav', action='store_true')
    downloader.set_defaults(action=acquire)
    args = parser.parse_args()
    try:
        args.action(args)
    except (ValueError, KeyError, OSError, requests.RequestException, subprocess.SubprocessError) as error:
        parser.exit(1, f'Audio acquisition incomplete: {error}\n')


if __name__ == '__main__':
    main()
