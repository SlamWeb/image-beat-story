"""Preserve a sequence, apply explicit IDs, or opt into perceptual-color ordering."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.color import deltaE_ciede2000, rgb2hsv, rgb2lab

from prepare_images import contact_sheet, load_manifest, new_output, read_json, write_json

WEIGHTS = {'background_mean_delta_e_2000': 0.25, 'spatial_lab': 0.35,
           'color_distribution_hellinger': 0.25, 'brightness_distribution': 0.15}


def describe(path, exclude_rects):
    with Image.open(path) as source:
        rgb = np.asarray(source.convert('RGB').resize((108, 144), Image.Resampling.LANCZOS), dtype=np.float64) / 255.0
    lab, hsv = rgb2lab(rgb), rgb2hsv(rgb)
    yy, xx = np.mgrid[0:144, 0:108]
    pixel_x, pixel_y = (xx + 0.5) * 10, (yy + 0.5) * 10
    mask = np.ones((144, 108), dtype=bool)
    for x, y, w, h in exclude_rects:
        mask &= ~((pixel_x >= x) & (pixel_x < x + w) & (pixel_y >= y) & (pixel_y < y + h))
    if np.count_nonzero(mask) < 16:
        raise ValueError('excludeRects leave fewer than 16 analysis samples; choose smaller exclusions.')
    values = lab[mask]
    mean_lab = values.mean(axis=0)
    grid = []
    for row in range(4):
        for col in range(3):
            region = mask & (xx // 36 == col) & (yy // 36 == row)
            grid.append(lab[region].mean(axis=0) if region.any() else mean_lab)
    color_hist, _, _ = np.histogram2d(values[:, 1], values[:, 2], bins=10, range=[[-100, 100], [-100, 100]])
    color_hist = color_hist.ravel()
    color_hist /= max(color_hist.sum(), 1)
    light_hist, _ = np.histogram(values[:, 0], bins=20, range=(0, 100))
    light_hist = light_hist / max(light_hist.sum(), 1)
    vivid = mask & (hsv[:, :, 1] > 0.15) & (hsv[:, :, 2] > 0.12)
    hue_hist, _ = np.histogram(hsv[:, :, 0][vivid], bins=24, range=(0, 1), weights=hsv[:, :, 1][vivid])
    return {'mean_lab': mean_lab, 'grid': np.asarray(grid), 'color_hist': color_hist,
            'light_cdf': light_hist.cumsum(), 'mean_rgb': rgb[mask].mean(axis=0),
            'dominant_hue_deg': (float(np.argmax(hue_hist)) + 0.5) * 15 if hue_hist.sum() else None}


def distances(records, weights):
    means = np.stack([record['mean_lab'] for record in records])
    grid = np.stack([record['grid'] for record in records])
    hist = np.sqrt(np.stack([record['color_hist'] for record in records]))
    light = np.stack([record['light_cdf'] for record in records])
    components = {
        'background_mean_delta_e_2000': deltaE_ciede2000(means[:, None, :], means[None, :, :]),
        'spatial_lab': np.linalg.norm(grid[:, None, :, :] - grid[None, :, :, :], axis=-1).mean(axis=-1),
        'color_distribution_hellinger': np.linalg.norm(hist[:, None, :] - hist[None, :, :], axis=-1) / np.sqrt(2),
        'brightness_distribution': np.abs(light[:, None, :] - light[None, :, :]).mean(axis=-1),
    }
    upper = np.triu_indices(len(records), k=1)
    scales = {name: max(float(np.median(value[upper])), 1e-9) if len(upper[0]) else 1.0
              for name, value in components.items()}
    cost = sum(weights[name] * value / scales[name] for name, value in components.items())
    np.fill_diagonal(cost, 0)
    return cost, {'weights': weights, 'medianNormalization': scales}


def path_cost(order, cost):
    return float(sum(cost[a, b] for a, b in zip(order[:-1], order[1:])))


def improve(order, cost):
    """Deterministic open-path 2-opt, retaining the legacy 120-pass limit."""
    order = order.copy()
    n = len(order)
    for _ in range(120):
        best_gain, best_pair = 1e-10, None
        for first in range(n - 1):
            for last in range(first + 1, n):
                old = new = 0.0
                if first:
                    old += cost[order[first - 1], order[first]]
                    new += cost[order[first - 1], order[last]]
                if last + 1 < n:
                    old += cost[order[last], order[last + 1]]
                    new += cost[order[first], order[last + 1]]
                gain = old - new
                if gain > best_gain:
                    best_gain, best_pair = gain, (first, last)
        if best_pair is None:
            break
        first, last = best_pair
        order[first:last + 1] = reversed(order[first:last + 1])
    return order


def optimize(cost):
    n = len(cost)
    candidates = []
    for start in range(n):
        order, unseen = [start], set(range(n)) - {start}
        while unseen:
            nxt = min(unseen, key=lambda index: (cost[order[-1], index], index))
            order.append(nxt)
            unseen.remove(nxt)
        candidates.append(order)
    candidates.sort(key=lambda order: path_cost(order, cost))
    optimized = [improve(order, cost) for order in candidates[:16]]
    return min(optimized, key=lambda order: path_cost(order, cost))


def summary(order, cost):
    edges = np.asarray([cost[a, b] for a, b in zip(order[:-1], order[1:])])
    if not len(edges):
        return dict.fromkeys(('total', 'mean', 'median', 'p95', 'max'), 0.0)
    return {'total': float(edges.sum()), 'mean': float(edges.mean()), 'median': float(np.median(edges)),
            'p95': float(np.percentile(edges, 95)), 'max': float(edges.max())}


def run(args):
    manifest = load_manifest(args.manifest)
    items = manifest['images']
    original_ids = [item['id'] for item in items]
    order = list(range(len(items)))
    report = {'mode': args.mode, 'sourceCount': len(items), 'sourceOrder': original_ids,
              'sourceFilesChanged': False}
    if args.mode != 'explicit' and args.order_file:
        raise ValueError('--order-file requires --mode explicit.')
    if args.mode != 'color' and (args.color_config or args.warm_opening):
        raise ValueError('--color-config and --warm-opening require --mode color.')
    if args.mode == 'explicit':
        if not args.order_file:
            raise ValueError('--mode explicit requires --order-file JSON ID array.')
        ids = read_json(args.order_file)
        if not isinstance(ids, list) or not ids or any(not isinstance(image_id, str) for image_id in ids):
            raise ValueError('Explicit order must be a nonempty JSON array of image IDs.')
        if len(ids) != len(set(ids)):
            raise ValueError('Explicit order contains duplicate IDs.')
        lookup = {item['id']: index for index, item in enumerate(items)}
        missing = [image_id for image_id in ids if image_id not in lookup]
        if missing:
            raise ValueError(f'Explicit order contains unknown IDs: {missing}')
        order = [lookup[image_id] for image_id in ids]
    elif args.mode == 'color':
        config = read_json(args.color_config) if args.color_config else {}
        exclude_rects = config.get('excludeRects', [])
        if not isinstance(exclude_rects, list):
            raise ValueError('excludeRects must be an array of [x,y,w,h] rectangles.')
        for rectangle in exclude_rects:
            if not isinstance(rectangle, list) or len(rectangle) != 4 or any(type(v) is not int for v in rectangle):
                raise ValueError('Each excludeRect must contain four integer pixel values.')
            x, y, w, h = rectangle
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1080 or y + h > 1440:
                raise ValueError('excludeRect lies outside the prepared 1080x1440 canvas.')
        weights = {**WEIGHTS, **config.get('weights', {})}
        if set(weights) != set(WEIGHTS) or any(not isinstance(v, (int, float)) or not np.isfinite(v) or v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
            raise ValueError(f'weights must be finite, nonnegative, nonzero in total, using only {list(WEIGHTS)}.')
        records = [describe(item['path'], exclude_rects) for item in items]
        cost, method = distances(records, weights)
        order = optimize(cost)
        if args.warm_opening:
            first, last = records[order[0]]['mean_lab'], records[order[-1]]['mean_lab']
            if first[2] + 0.2 * first[0] < last[2] + 0.2 * last[0]:
                order.reverse()
        before, after = summary(list(range(len(items))), cost), summary(order, cost)
        report.update(method='Legacy Lab/spatial/histogram open path; all-start nearest neighbor, best 16 starts, up to 120 2-opt passes.',
                      heuristic=True, globallyOptimal=False, excludeRects=exclude_rects, warmOpening=args.warm_opening,
                      **method, before=before, after=after,
                      meanNeighborCostReduction=1 - after['mean'] / before['mean'] if before['mean'] else None,
                      interpretation='Metric reduction alone does not establish human preference, narrative quality, or geometric alignment.',
                      records=[{'id': item['id'], 'meanLab': record['mean_lab'].tolist(),
                                'meanRgb': record['mean_rgb'].tolist(), 'dominantHueDegrees': record['dominant_hue_deg']}
                               for item, record in zip(items, records)],
                      largestJumps=[{'position': i + 1, 'from': items[order[i]]['id'],
                                     'to': items[order[i + 1]]['id'], 'cost': float(cost[order[i], order[i + 1]])}
                                    for i in sorted(range(len(order) - 1), key=lambda i: cost[order[i], order[i + 1]], reverse=True)[:8]])
    selected = [items[index] for index in order]
    selected_ids = {item['id'] for item in selected}
    unused = [image_id for image_id in original_ids if image_id not in selected_ids]
    report.update(outputOrder=[item['id'] for item in selected], outputCount=len(selected), unusedIds=unused)
    output = new_output(args.output_dir)
    write_json(output / 'manifest.json', {**manifest, 'images': selected, 'order': args.mode,
                                         'sourceManifest': str(Path(args.manifest).resolve()), 'unusedIds': unused})
    write_json(output / 'report.json', report)
    contact_sheet(selected, output / 'contact-sheet.jpg')
    return {'mode': args.mode, 'imageCount': len(selected), 'unusedIds': unused, 'manifest': str(output / 'manifest.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--mode', choices=['preserve', 'color', 'explicit'], default='preserve')
    parser.add_argument('--order-file', help='JSON image ID array. Explicit order may select a subset.')
    parser.add_argument('--color-config', help='JSON excludeRects and optional weights.')
    parser.add_argument('--warm-opening', action='store_true', help='Color mode only: orient the path toward the warmer/brighter endpoint.')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
