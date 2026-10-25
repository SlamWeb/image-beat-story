"""Prepare image files without stretching or modifying their sources."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def new_output(path):
    path = Path(path).resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f'Output must be new or empty; existing files will not be overwritten: {path}')
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_manifest(path):
    data = read_json(path)
    if data.get('schemaVersion') != 1 or data.get('width') != 1080 or data.get('height') != 1440:
        raise ValueError('Expected schemaVersion=1, width=1080, height=1440.')
    if not isinstance(data.get('images'), list) or not data['images']:
        raise ValueError('Manifest images must be a nonempty list.')
    ids = []
    for item in data['images']:
        for key in ('id', 'path', 'sourceName', 'originalIndex'):
            if key not in item:
                raise ValueError(f'Missing image field: {key}')
        if not isinstance(item['id'], str) or not item['id']:
            raise ValueError('Image IDs must be nonempty strings.')
        if not isinstance(item['originalIndex'], int) or isinstance(item['originalIndex'], bool) or item['originalIndex'] < 1:
            raise ValueError('originalIndex must be a positive, one-based integer.')
        image_path = Path(item['path'])
        if not image_path.is_absolute() or not image_path.is_file():
            raise ValueError(f'Image path must be an existing absolute file: {image_path}')
        with Image.open(image_path) as image:
            if image.size != (1080, 1440):
                raise ValueError(f'Image size differs from the prepared canvas: {image_path}: {image.size}')
        ids.append(item['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate manifest image IDs.')
    return data


def contact_sheet(items, output, labels=None, rectangles=None, columns=8):
    """A viewing aid only; all analysis uses full prepared images."""
    columns = min(columns, max(1, len(items)))
    sheet = Image.new('RGB', (columns * 156, max(1, math.ceil(len(items) / columns)) * 238), '#16191f')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, item in enumerate(items):
        x, y = index % columns * 156, index // columns * 238
        with Image.open(item['path']) as image:
            thumb = image.convert('RGB').resize((150, 200), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x + 3, y))
        for rect in rectangles or []:
            rx, ry, rw, rh = rect
            draw.rectangle((x + 3 + rx * 150 / 1080, y + ry * 200 / 1440,
                            x + 3 + (rx + rw) * 150 / 1080, y + (ry + rh) * 200 / 1440), outline='#00ffb3', width=1)
        label = labels[index] if labels else f"{index + 1:03d} {item['id']}"
        # IDs/status are intentionally ASCII, avoiding font-dependent filename loss.
        draw.text((x + 4, y + 202), label, fill='white', font=font)
        draw.text((x + 4, y + 219), f"source #{item['originalIndex']}", fill='#b4bcc8', font=font)
    sheet.save(output, quality=92)


def natural_key(value):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)', value)]


def prepare(args):
    source = Path(args.input).resolve()
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    archive = None
    if source.is_file() and source.suffix.lower() == '.zip':
        archive = zipfile.ZipFile(source)
        entries = [(entry.filename, entry, index + 1) for index, entry in enumerate(archive.infolist())
                   if not entry.is_dir() and Path(entry.filename).suffix.lower() in EXTENSIONS
                   and not entry.filename.startswith('__MACOSX/')]
        enumeration = 'ZIP central-directory image entry order'
        def get_bytes(entry):
            return archive.read(entry)
    elif source.is_dir():
        entries = [(str(path.relative_to(source)).replace('\\', '/'), path, None)
                   for path in source.rglob('*') if path.is_file() and path.suffix.lower() in EXTENSIONS]
        enumeration = 'Filesystem recursive enumeration order (recorded; not portable across filesystems)'
        def get_bytes(entry):
            return entry.read_bytes()
    else:
        raise ValueError('Input must be a ZIP archive or directory.')
    try:
        if not entries:
            raise ValueError('No supported images were found.')
        original = [{'id': f'img-{index:04d}', 'sourceName': name, 'originalIndex': index,
                     'sourceArchiveIndex': archive_index, '_entry': entry}
                    for index, (name, entry, archive_index) in enumerate(entries, 1)]
        selected = original.copy()
        if args.order == 'natural':
            selected.sort(key=lambda item: natural_key(item['sourceName']))
        elif args.order == 'list':
            if not args.order_file:
                raise ValueError('--order list requires --order-file JSON sourceName array.')
            names = read_json(args.order_file)
            if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                raise ValueError('Order file must contain a JSON array of exact sourceName strings.')
            lookup = {item['sourceName']: item for item in original}
            if len(lookup) != len(original):
                raise ValueError('Duplicate sourceName values make explicit name ordering ambiguous.')
            if len(names) != len(set(names)) or set(names) != set(lookup):
                raise ValueError('Prepare order list must contain every sourceName exactly once.')
            selected = [lookup[name] for name in names]
        elif args.order_file:
            raise ValueError('--order-file requires --order list.')
        output_path = Path(args.output_dir).resolve()
        if source.is_dir() and (output_path == source or source in output_path.parents):
            raise ValueError('Output directory must be outside the input directory.')
        output = new_output(output_path)
        anomalies = []
        for item in original:
            try:
                with Image.open(io.BytesIO(get_bytes(item['_entry']))) as raw:
                    image = ImageOps.exif_transpose(raw)
                    width, height = image.size
                    if getattr(raw, 'n_frames', 1) != 1:
                        raise ValueError('Animated/multipage image requires explicit frame selection.')
                    allowed = (width, height) in ((1080, 1440), (1086, 1448))
                    if not allowed and not (args.allow_center_crop and width >= 1080 and height >= 1440):
                        anomalies.append({'id': item['id'], 'sourceName': item['sourceName'],
                                          'sizeAfterExif': [width, height], 'reason': 'unexpected_dimensions'})
                    item['sourceSizeAfterExif'] = [width, height]
            except Exception as error:
                anomalies.append({'id': item['id'], 'sourceName': item['sourceName'], 'reason': str(error)})
        if anomalies:
            write_json(output / 'report.json', {'status': 'rejected', 'source': str(source), 'anomalies': anomalies,
                       'sourceFilesChanged': False, 'imagesWritten': 0})
            raise ValueError(f'{len(anomalies)} image anomalies; see {output / "report.json"}. No images written.')
        images_dir = output / 'images'
        images_dir.mkdir()
        result = []
        for item in selected:
            payload = get_bytes(item['_entry'])
            with Image.open(io.BytesIO(payload)) as raw:
                image = ImageOps.exif_transpose(raw)
                width, height = image.size
                left, top = (width - 1080) // 2, (height - 1440) // 2
                prepared = image.crop((left, top, left + 1080, top + 1440))
                if prepared.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                    prepared = prepared.convert('RGBA' if 'transparency' in image.info else 'RGB')
                path = images_dir / f"{item['id']}.png"
                prepared.save(path)
            record = {key: value for key, value in item.items() if not key.startswith('_')}
            record.update(path=str(path.resolve()), sourceSha256=hashlib.sha256(payload).hexdigest(),
                          cropRect=[left, top, 1080, 1440], resized=False)
            result.append(record)
        manifest = {'schemaVersion': 1, 'width': 1080, 'height': 1440, 'images': result,
                    'source': str(source), 'order': args.order, 'sourceEnumeration': enumeration}
        write_json(output / 'manifest.json', manifest)
        report = {'status': 'prepared', 'imageCount': len(result), 'order': args.order,
                  'originalOrder': [{'id': item['id'], 'sourceName': item['sourceName'],
                                     'originalIndex': item['originalIndex']} for item in original],
                  'preparedOrder': [item['id'] for item in result], 'sourceFilesChanged': False,
                  'resized': False, 'allowCenterCrop': args.allow_center_crop,
                  'pixelNote': 'EXIF orientation is applied before crop; PNG output is re-encoded. Sources are untouched.'}
        write_json(output / 'report.json', report)
        contact_sheet(result, output / 'contact-sheet.jpg')
        return {'imageCount': len(result), 'manifest': str(output / 'manifest.json')}
    finally:
        if archive:
            archive.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--order', choices=['preserve', 'natural', 'list'], default='preserve')
    parser.add_argument('--order-file')
    parser.add_argument('--allow-center-crop', action='store_true', help='Explicitly allow cropping larger unexpected canvases; never resize.')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), ensure_ascii=False, indent=2))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
