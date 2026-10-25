"""Stage a Remotion edit from ordered images, measured events and an Agent-authored plan."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

from douyin_audio import executable, probe


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def bounded_int(value, label, minimum=1):
    if isinstance(value, bool) or int(value) != value or int(value) < minimum:
        raise ValueError(f'{label} must be an integer >= {minimum}.')
    return int(value)


def build(args):
    manifest, report, plan = read(args.manifest), read(args.events), read(args.plan)
    if args.output_dir.exists():
        raise FileExistsError('Use a new edit output directory; existing edits are never overwritten.')
    audio = Path(report['sourceAudio']).resolve()
    fps = bounded_int(plan.get('fps', 60), 'fps')
    width, height = manifest['width'], manifest['height']
    start, end = float(plan['startSeconds']), float(plan['endSeconds'])
    if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
        raise ValueError('Choose a finite positive source-audio interval.')
    if end > float(report['durationSeconds']) + .025:
        raise ValueError('Selected interval exceeds the supplied audio.')
    analysis_start = float(report.get('analysisOffset', 0))
    analysis_end = analysis_start + float(report.get('analysisDurationSeconds', report['durationSeconds']))
    if start < analysis_start - .001 or end > analysis_end + .025:
        raise ValueError('Chosen interval extends outside the analyzed range; analyze that range first.')
    duration = round((end - start) * fps)
    if duration < 2:
        raise ValueError('Selected interval is too short.')
    offset = int(plan.get('visualOffsetFrames', 0))
    mapping = plan.get('eventTransitions', {})
    default_transition = plan.get('transition', 'press')
    valid_transitions = {'dissolve', 'press', 'pulse', 'bounce'}
    if default_transition not in valid_transitions or not set(mapping.values()) <= valid_transitions:
        raise ValueError('Unknown transition; use dissolve, press, pulse or bounce.')
    by_event = {str(e['id']): e for e in report['events']}
    if len(by_event) != len(report['events']):
        raise ValueError('Event IDs must be unique.')
    explicit_events = plan.get('eventIds')
    if explicit_events is None:
        events = [e for e in report['events'] if e.get('accepted', False)
                  and start <= float(e['timeSeconds']) < end]
    else:
        ids = [str(i) for i in explicit_events]
        if len(ids) != len(set(ids)) or any(i not in by_event for i in ids):
            raise ValueError('eventIds must be unique IDs found in events.json.')
        events = [by_event[i] for i in ids]
        if any(not start <= float(e['timeSeconds']) < end for e in events):
            raise ValueError('Explicitly chosen event is outside the chosen source interval.')
    events.sort(key=lambda e: float(e['timeSeconds']))
    # Frame zero is an initial hold, not a fabricated musical attack.
    zero_events, impacts = [], []
    for event in events:
        impact = round((float(event['timeSeconds']) - start) * fps) + offset
        if impact <= 0:
            zero_events.append(event)
        elif impact >= duration - 1:
            raise ValueError(f'Event {event["id"]} is too close to the ending; extend the tail or deselect it.')
        else:
            if impacts and impacts[-1][0] == impact:
                raise ValueError('Two selected events occupy one output frame; merge/select them explicitly.')
            impacts.append((impact, event))
    if len(zero_events) > 1:
        raise ValueError('Several selected events precede frame zero after offset; review clip start/offset.')
    image_by_id = {str(i['id']): i for i in manifest['images']}
    if len(image_by_id) != len(manifest['images']):
        raise ValueError('Image IDs must be unique.')
    image_ids = plan.get('imageIds', list(image_by_id))
    image_ids = [str(i) for i in image_ids]
    count = 1 + len(impacts)
    if len(image_ids) != count:
        raise ValueError(f'This cut has {count} image slots (initial hold + {len(impacts)} changes), '
                         f'but {len(image_ids)} images were selected. Set imageIds/eventIds or adjust the interval.')
    if len(set(image_ids)) != len(image_ids) or any(i not in image_by_id for i in image_ids):
        raise ValueError('imageIds must be unique IDs found in the image manifest.')
    original_order = [str(i['id']) for i in manifest['images'] if str(i['id']) in set(image_ids)]
    if image_ids != original_order and not plan.get('allowReorder', False):
        raise ValueError('imageIds changes manifest order. Order images first, or explicitly set allowReorder.')
    ffmpeg, ffprobe = executable(args.ffmpeg, 'ffmpeg'), executable(args.ffprobe, 'ffprobe')
    source_meta = probe(ffprobe, audio)
    if end > float(source_meta['format']['duration']) + .025:
        raise ValueError('Chosen interval exceeds actual source audio duration.')
    for image_id in image_ids:
        if not Path(image_by_id[image_id]['path']).is_file():
            raise FileNotFoundError(image_by_id[image_id]['path'])
    template = Path(__file__).resolve().parents[1] / 'assets/remotion-template'
    shutil.copytree(template, args.output_dir, ignore=shutil.ignore_patterns('node_modules', '__pycache__'))
    public = args.output_dir / 'public'
    (public / 'images').mkdir(exist_ok=True)
    (public / 'audio').mkdir(exist_ok=True)
    starts = [(0, zero_events[0] if zero_events else None)] + impacts
    shots = []
    pre = bounded_int(plan.get('preFrames', 6), 'preFrames')
    post = bounded_int(plan.get('postFrames', 12), 'postFrames')
    release = bounded_int(plan.get('releaseFrames', 22), 'releaseFrames')
    for index, (image_id, (frame, event)) in enumerate(zip(image_ids, starts)):
        image = image_by_id[image_id]
        path = Path(image['path'])
        name = f'{index + 1:04d}{path.suffix.lower()}'
        shutil.copy2(path, public / 'images' / name)
        previous = starts[index - 1][0] if index else 0
        next_frame = starts[index + 1][0] if index + 1 < len(starts) else duration
        event_type = event.get('type', 'onset') if event else 'initial_hold'
        intensity = min(1.0, max(0.0, float(event['strength']))) if event else 0.0
        shot = {'id': image_id, 'src': f'images/{name}', 'impactFrame': frame,
                'preFrames': min(pre, max(1, (frame - previous) // 2)) if index else 0,
                'postFrames': min(post, max(1, (next_frame - frame) // 2)),
                'releaseFrames': release, 'intensity': intensity, 'eventType': event_type,
                'transition': mapping.get(event_type, default_transition),
                'eventId': str(event['id']) if event else None}
        if event:
            shot['sourceEventSeconds'] = float(event['timeSeconds'])
            shot['visualMinusAudioMs'] = round((frame / fps - (float(event['timeSeconds']) - start)) * 1000, 3)
        shots.append(shot)
    audio_out = public / 'audio/bgm.wav'
    # Decode first, then trim in source seconds; preserve source speed and stereo.
    subprocess.run([ffmpeg, '-n', '-v', 'error', '-i', str(audio), '-ss', str(start),
                    '-t', str(end - start), '-map', '0:a:0', '-vn', '-c:a', 'pcm_s16le', str(audio_out)],
                   check=True, capture_output=True, timeout=300)
    clipped = probe(ffprobe, audio_out)
    actual = float(clipped['format']['duration'])
    if abs(actual - (end - start)) > .025:
        raise ValueError('Clipped audio duration mismatch; edit was not marked complete.')
    timeline = {'schemaVersion': 1, 'width': width, 'height': height, 'fps': fps,
        'durationInFrames': duration, 'audio': {'src': 'audio/bgm.wav',
        'fadeOutSeconds': float(plan.get('fadeOutSeconds', .35))},
        'shots': shots, 'motion': plan.get('motion', {})}
    if plan.get('subjectMask'):
        mask = Path(plan['subjectMask'])
        from PIL import Image
        with Image.open(mask) as source:
            if source.size != (width, height):
                raise ValueError('subjectMask must match the cropped canvas dimensions.')
        (public / 'masks').mkdir(exist_ok=True)
        shutil.copy2(mask, public / 'masks/subject.png')
        timeline['subjectMask'] = 'masks/subject.png'
    save(args.output_dir / 'timeline.json', timeline)
    save(args.output_dir / 'edit-plan.json', plan)
    receipt = {'created_at': datetime.now(timezone.utc).isoformat(), 'stage': 'staged_not_rendered',
        'sourceAudio': str(audio), 'sourceAudioSha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
        'clipStartSeconds': start, 'clipEndSeconds': end, 'clippedDurationSeconds': actual,
        'audioSpeed': 1, 'durationInFrames': duration, 'fps': fps, 'imageCount': len(shots),
        'selectedEventIds': [str(e['id']) for e in events], 'unusedImageIds': [i for i in image_by_id if i not in image_ids],
        'imageOrderChanged': image_ids != original_order, 'visualOffsetFrames': offset,
        'composition': 'ImageBeatStory', 'timeline': str((args.output_dir / 'timeline.json').resolve()),
        'detectionIsHumanVerified': False, 'rendered': False}
    save(args.output_dir / 'build-receipt.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--events', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--ffmpeg', type=Path)
    parser.add_argument('--ffprobe', type=Path)
    args = parser.parse_args()
    build(args)


if __name__ == '__main__':
    main()
