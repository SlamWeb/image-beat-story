"""Filter excessive fixed-anchor displacement using multiscale Canny templates."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prepare_images import contact_sheet, load_manifest, new_output, read_json, write_json


DEFAULTS = {'maxXShift': 32, 'maxYShift': 24, 'maxScaleChange': 0.08,
            'minConfidence': 0.30, 'scaleRange': [0.90, 1.10, 21], 'canny': [60, 150],
            'minEdgePixels': 20, 'baseline': 'reference'}


def rect(value, name):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        raise ValueError(f'{name} must be integer pixels [x,y,w,h].')
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1080 or y + h > 1440:
        raise ValueError(f'{name} lies outside the prepared 1080x1440 canvas.')
    return value


def gray(path):
    with Image.open(path) as image:
        if image.size != (1080, 1440):
            raise ValueError(f'Reference/candidate must be a prepared 1080x1440 image: {path}')
        return cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)


def validate(config):
    anchors = config.get('anchors')
    if not isinstance(anchors, list) or not anchors:
        raise ValueError('Anchor JSON requires a nonempty anchors array.')
    result = []
    for index, original in enumerate(anchors):
        settings = {**DEFAULTS, **config.get('defaults', {}), **original}
        settings['name'] = settings.get('name', f'anchor-{index + 1}')
        if not isinstance(settings['name'], str) or not settings['name'].strip():
            raise ValueError('Anchor name must be a nonempty string.')
        settings['roi'] = rect(settings.get('roi'), f"{settings['name']}.roi")
        settings['searchRoi'] = rect(settings.get('searchRoi'), f"{settings['name']}.searchRoi")
        for key in ('maxXShift', 'maxYShift', 'maxScaleChange'):
            if not isinstance(settings[key], (int, float)) or not math.isfinite(settings[key]) or settings[key] < 0:
                raise ValueError(f'{key} must be finite and nonnegative.')
        if not isinstance(settings['minConfidence'], (int, float)) or not 0 <= settings['minConfidence'] <= 1:
            raise ValueError('minConfidence must be in [0,1].')
        sr = settings['scaleRange']
        if not isinstance(sr, list) or len(sr) != 3 or not 0 < sr[0] <= sr[1] or type(sr[2]) is not int or sr[2] < 1:
            raise ValueError('scaleRange must be [positive min, max, integer sample count].')
        if settings['baseline'] not in ('reference', 'median'):
            raise ValueError('baseline must be reference or median.')
        if not isinstance(settings['canny'], list) or len(settings['canny']) != 2 or not 0 <= settings['canny'][0] < settings['canny'][1]:
            raise ValueError('canny must be [low, high] with 0 <= low < high.')
        if type(settings['minEdgePixels']) is not int or settings['minEdgePixels'] < 1:
            raise ValueError('minEdgePixels must be a positive integer.')
        result.append(settings)
    if len({a['name'] for a in result}) != len(result):
        raise ValueError('Anchor names must be unique.')
    return result


def measure(template, image_gray, settings):
    sx, sy, sw, sh = settings['searchRoi']
    search = cv2.Canny(image_gray, *settings['canny'])[sy:sy + sh, sx:sx + sw]
    best = None
    if np.count_nonzero(search) < settings['minEdgePixels']:
        return {'confidence': None, 'centerX': None, 'centerY': None, 'scale': None, 'issue': 'insufficient_search_edges'}
    for scale in np.linspace(*settings['scaleRange']):
        tw, th = round(template.shape[1] * scale), round(template.shape[0] * scale)
        if min(tw, th) < 2 or tw > sw or th > sh:
            continue
        scaled = cv2.resize(template, (tw, th), interpolation=cv2.INTER_NEAREST)
        if np.count_nonzero(scaled) < settings['minEdgePixels']:
            continue
        scores = cv2.matchTemplate(search, scaled, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(scores)
        if math.isfinite(score) and (best is None or score > best['confidence']):
            best = {'confidence': float(score), 'centerX': sx + location[0] + tw / 2,
                    'centerY': sy + location[1] + th / 2, 'scale': float(scale)}
    return best or {'confidence': None, 'centerX': None, 'centerY': None, 'scale': None, 'issue': 'no_fitting_template'}


def anchor_sheet(items, records, settings, destination):
    x, y, w, h = settings['searchRoi']
    cols = min(8, len(items))
    tile_w, preview_h, tile_h = 200, 150, 190
    sheet = Image.new('RGB', (cols * tile_w, math.ceil(len(items) / cols) * tile_h), '#16191f')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (item, record) in enumerate(zip(items, records)):
        cx, cy = index % cols * tile_w, index // cols * tile_h
        with Image.open(item['path']) as image:
            crop = image.convert('RGB').crop((x, y, x + w, y + h))
            crop.thumbnail((tile_w - 4, preview_h), Image.Resampling.LANCZOS)
        sheet.paste(crop, (cx + 2, cy))
        sx, sy = crop.width / w, crop.height / h
        found = record['anchors'][settings['name']]
        if found['centerX'] is not None:
            px, py = cx + 2 + (found['centerX'] - x) * sx, cy + (found['centerY'] - y) * sy
            draw.line((px - 8, py, px + 8, py), fill='#ff6377', width=1)
            draw.line((px, py - 8, px, py + 8), fill='#ff6377', width=1)
        confidence = found['confidence']
        score = f'{confidence:.3f}' if confidence is not None else 'none'
        draw.text((cx + 3, cy + 151), f"{item['id']} conf={score}", fill='white', font=font)
        draw.text((cx + 3, cy + 169), record['status'], fill='#ff9e9e' if record['excluded'] else '#bce5d4', font=font)
    sheet.save(destination, quality=94)


def run(args):
    manifest = load_manifest(args.manifest)
    config = read_json(args.anchors)
    anchors = validate(config)
    reference_value = args.reference or config.get('reference')
    if not reference_value:
        raise ValueError('Specify --reference as a manifest image ID or absolute prepared image path.')
    lookup = {item['id']: item for item in manifest['images']}
    reference = Path(lookup[reference_value]['path']) if reference_value in lookup else Path(reference_value)
    if not reference.is_absolute() or not reference.is_file():
        raise ValueError('Reference must be a manifest image ID or an existing absolute prepared image path.')
    reference_gray = gray(reference)
    templates = {}
    for settings in anchors:
        x, y, w, h = settings['roi']
        template = cv2.Canny(reference_gray[y:y + h, x:x + w], *settings['canny'])
        if np.count_nonzero(template) < settings['minEdgePixels']:
            raise ValueError(f"Reference anchor {settings['name']} has insufficient edges; select a textured ROI.")
        templates[settings['name']] = template
    records = []
    for item in manifest['images']:
        candidate_gray = gray(item['path'])
        measured = {settings['name']: measure(templates[settings['name']], candidate_gray, settings) for settings in anchors}
        records.append({'id': item['id'], 'sourceName': item['sourceName'], 'anchors': measured})
    baselines, quality = {}, {}
    for settings in anchors:
        name = settings['name']
        reliable = [r['anchors'][name] for r in records if r['anchors'][name]['confidence'] is not None
                    and r['anchors'][name]['confidence'] >= settings['minConfidence']]
        quality[name] = {'reliableCount': len(reliable), 'sourceCount': len(records),
                         'usable': len(reliable) >= math.ceil(len(records) / 2)}
        if settings['baseline'] == 'median' and reliable:
            baseline = np.median([[r['centerX'], r['centerY'], r['scale']] for r in reliable], axis=0).tolist()
        else:
            x, y, w, h = settings['roi']
            baseline = [x + w / 2, y + h / 2, 1.0]
        baselines[name] = dict(zip(('centerX', 'centerY', 'scale'), baseline))
    for record in records:
        reasons, review_reasons = [], []
        for settings in anchors:
            name = settings['name']
            found, baseline = record['anchors'][name], baselines[name]
            confident = found['confidence'] is not None and found['confidence'] >= settings['minConfidence']
            if not quality[name]['usable']:
                review_reasons.append(f'{name}: collection_matching_unreliable')
            if not confident:
                review_reasons.append(f'{name}: low_confidence')
            found.update(dx=None, dy=None, scaleChange=None)
            if confident:
                found['dx'] = found['centerX'] - baseline['centerX']
                found['dy'] = found['centerY'] - baseline['centerY']
                found['scaleChange'] = found['scale'] / baseline['scale'] - 1
                for key, threshold, reason in [('dx', 'maxXShift', 'horizontal_shift'), ('dy', 'maxYShift', 'vertical_shift'),
                                               ('scaleChange', 'maxScaleChange', 'scale_change')]:
                    if abs(found[key]) > settings[threshold]:
                        reasons.append(f'{name}: {reason}')
        record.update(candidateReasons=reasons, reviewReasons=review_reasons,
                      needs_review=bool(review_reasons), excluded=bool(reasons) and not review_reasons)
    safeguards = []
    if all(record['excluded'] for record in records):
        safeguards.append('All images would be excluded; filtering suppressed pending anchor review.')
        for record in records:
            record.update(excluded=False, needs_review=True)
            record['reviewReasons'].append('all_excluded_safeguard')
    for record in records:
        record['status'] = 'EXCLUDE' if record['excluded'] else 'REVIEW' if record['needs_review'] else 'KEEP'
    excluded = {record['id'] for record in records if record['excluded']}
    output = new_output(args.output_dir)
    result = {**manifest, 'images': [item for item in manifest['images'] if item['id'] not in excluded],
              'sourceManifest': str(Path(args.manifest).resolve()), 'excludedIds': sorted(excluded)}
    write_json(output / 'manifest.json', result)
    report = {'method': 'Canny edges + multiscale TM_CCOEFF_NORMED template matching; no geometric correction.',
              'coordinateSystem': 'Prepared 1080x1440 pixels [x,y,width,height]',
              'reference': str(reference), 'anchors': anchors, 'baselines': baselines, 'anchorQuality': quality,
              'sourceCount': len(records), 'keptCount': len(result['images']), 'excludedCount': len(excluded),
              'needsReviewCount': sum(r['needs_review'] for r in records), 'excludedIds': sorted(excluded),
              'safeguards': safeguards, 'sourceFilesDeleted': False,
              'uncertainAction': 'Keep the entire image if any anchor is uncertain; flag for Agent/human review.',
              'limitations': 'Translation and sampled uniform scale only; rotation, perspective, deformation, clutter and occlusion can defeat matching.',
              'records': records}
    write_json(output / 'report.json', report)
    contact_sheet(manifest['images'], output / 'contact-sheet.jpg',
                  labels=[f"{r['id']} {r['status']}" for r in records], rectangles=[a['roi'] for a in anchors])
    for index, settings in enumerate(anchors, 1):
        anchor_sheet(manifest['images'], records, settings, output / f'anchor-{index:02d}-contact-sheet.jpg')
    return {key: report[key] for key in ('sourceCount', 'keptCount', 'excludedCount', 'needsReviewCount', 'safeguards')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--anchors', required=True, help='JSON anchors/defaults, all ROI coordinates after preparation.')
    parser.add_argument('--reference', help='Manifest image ID or absolute prepared image path; overrides JSON reference.')
    args = parser.parse_args()
    try:
        import json
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (ValueError, OSError, cv2.error) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
