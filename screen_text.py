"""Sentence-sized screen OCR regions, without additional models or services.

Coordinates are relative to the original image. ``boxes`` preserves the individual
line fragments so that a mouse in the gap beside a wrapped sentence does not select
it merely because it falls inside a large enclosing rectangle.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import statistics
import unicodedata


_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "vs",
    "etc", "e.g", "i.e", "a.m", "p.m", "u.s", "u.k", "inc", "ltd", "no",
}
_CLOSERS = '\"\'”’）)]』」'


@dataclass
class _Line:
    text: str
    box: tuple[float, float, float, float]
    confidence: float


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _height(box):
    return max(1., box[3] - box[1])


def _weight(character):
    if character.isspace():
        return .45
    return 2. if unicodedata.east_asian_width(character) in {'W', 'F'} else 1.


def _slice_box(text, box, start, end):
    """Approximate a substring's horizontal location within an OCR line."""
    weights = [_weight(c) for c in text]
    total = sum(weights) or 1.
    width = box[2] - box[0]
    return (box[0] + width * sum(weights[:start]) / total, box[1],
            box[0] + width * sum(weights[:end]) / total, box[3])


def _normalize(text):
    text = re.sub(r'\s+', ' ', str(text)).strip()
    # Preserve normal English word spacing even on bilingual screens.
    text = re.sub(r'(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])', '', text)
    text = re.sub(r' +([，。！？；：、])', r'\1', text)
    text = re.sub(r'([（「『]) +', r'\1', text)
    return text


def _source_parts(text, box, language):
    """Filter target-language rows; separate an obvious bilingual row if possible.

    An English product name inside a Chinese sentence is kept as context. Script
    filtering does not pretend to identify Latin-script languages beyond English.
    """
    if language not in {'en', 'zh'}:
        return [(text, box)]
    latin, cjk = len(_LATIN.findall(text)), len(_CJK.findall(text))
    if language == 'en' and not cjk:
        return [(text, box)] if latin >= 2 else []
    if language == 'zh' and not latin:
        return [(text, box)] if cjk else []
    if not latin or not cjk:
        return []
    # Parallel translations joined by a divider or a clear multiword English run.
    for match in re.finditer(r'\s*[|/｜]\s*|\s{1,}', text):
        left, right = text[:match.start()].strip(), text[match.end():].strip()
        if not left or not right:
            continue
        left_cjk, right_cjk = len(_CJK.findall(left)), len(_CJK.findall(right))
        left_latin, right_latin = len(_LATIN.findall(left)), len(_LATIN.findall(right))
        separated = ((left_cjk == 0 and left_latin >= 4 and right_cjk >= 2 and right_latin == 0)
                     or (right_cjk == 0 and right_latin >= 4 and left_cjk >= 2 and left_latin == 0))
        if separated:
            english_left = left_cjk == 0
            take_left = english_left if language == 'en' else not english_left
            start, end = (0, match.start()) if take_left else (match.end(), len(text))
            part = text[start:end].strip(' /|｜')
            return [(part, _slice_box(text, box, start, end))]
    # A predominantly Chinese sentence may include English names and UI labels.
    is_chinese = cjk * 2 >= latin
    return [(text, box)] if (language == 'zh') == is_chinese else []


def _boundary_end(text, index):
    char = text[index]
    if char not in '.!?。！？':
        return None
    if char == '.':
        before, after = text[:index], text[index + 1:]
        if before[-1:].isdigit() and after[:1].isdigit():
            return None
        token_match = re.search(r'([A-Za-z][A-Za-z.]*)$', before)
        token = token_match.group(1) if token_match else ''
        if token.lower() in _ABBREVIATIONS or (len(token) == 1 and token.isupper()):
            return None
        if re.fullmatch(r'(?:[A-Za-z]\.)+[A-Za-z]', token):
            return None
        if after and not after[0].isspace() and after[0] not in '.' + _CLOSERS:
            return None
    end = index + 1
    while end < len(text) and text[end] in '.!?。！？' + _CLOSERS:
        end += 1
    return end


def sentence_spans(text):
    """Return sentence spans while preserving abbreviations, initials and decimals."""
    start = index = 0
    spans = []
    while index < len(text):
        end = _boundary_end(text, index)
        if end is not None:
            left, right = start, end
            while left < right and text[left].isspace():
                left += 1
            if left < right:
                spans.append((left, right))
            start = index = end
        else:
            index += 1
    left, right = start, len(text)
    while left < right and text[left].isspace():
        left += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    if left < right:
        spans.append((left, right))
    return spans


def _complete(text):
    text = text.rstrip()
    return any(_boundary_end(text, i) == len(text)
               for i in range(max(0, len(text) - 8), len(text)))


def _joiner(left, right):
    if not left or not right:
        return ''
    if right[0] in ',.;:!?，。！？；：、)]）』」' or left[-1] in '([（『「':
        return ''
    if _CJK.fullmatch(left[-1]) or _CJK.fullmatch(right[0]):
        return ''
    return ' '


def _same_row(left, right):
    a, b = left.box, right.box
    height = min(_height(a), _height(b))
    center_a, center_b = (a[1] + a[3]) / 2, (b[1] + b[3]) / 2
    gap = b[0] - a[2]
    return (abs(center_a - center_b) <= .45 * height
            and -.6 * height <= gap <= 1.3 * height)


def _merge_fragments(lines):
    rows = []
    for line in sorted(lines, key=lambda r: (r.box[1], r.box[0])):
        group = next((group for group in rows if abs((group[0].box[1]+group[0].box[3]-line.box[1]-line.box[3])/2)
                      <= .45*min(_height(group[0].box),_height(line.box))),None)
        if group is None:
            rows.append([line])
        else:
            group.append(line)
    merged = []
    for group in rows:
        joined=[]
        for line in sorted(group,key=lambda r:r.box[0]):
            if joined and _same_row(joined[-1],line):
                other=joined[-1]
                joined[-1]=_Line(other.text+_joiner(other.text,line.text)+line.text,
                                _union([other.box,line.box]),min(other.confidence,line.confidence))
            else:
                joined.append(line)
        merged.extend(joined)
    return sorted(merged, key=lambda r: (r.box[1], r.box[0]))


def _paragraphs(lines):
    paragraphs = []
    for line in lines:
        candidates = []
        for index, group in enumerate(paragraphs):
            previous = group[-1]
            a, b = previous.box, line.box
            height = max(_height(a), _height(b))
            vertical_gap = b[1] - a[3]
            # Join only a nearby aligned continuation, never a second column.
            aligned = abs(b[0] - group[0].box[0]) <= max(12., .8 * height)
            overlap = max(0., min(a[2], b[2]) - max(a[0], b[0]))
            narrow_width = max(1., min(a[2] - a[0], b[2] - b[0]))
            same_size = min(_height(a), _height(b)) / height >= .65
            if (not _complete(previous.text) and len(group) < 12 and aligned and same_size
                    and -.1 * height <= vertical_gap <= 1.05 * height
                    and overlap / narrow_width >= .65
                    and sum(len(r.text) for r in group) + len(line.text) <= 1800):
                candidates.append((vertical_gap + abs(a[0] - b[0]), index))
        if candidates:
            paragraphs[min(candidates)[1]].append(line)
        else:
            paragraphs.append([line])
    return paragraphs


def _sentences(group):
    text = ''
    pieces = []
    for line in group:
        if text and re.search(r'[A-Za-z]-$', text) and re.match(r'[a-z]', line.text):
            text = text[:-1]
            if pieces:
                old_start, old_end, old_text, old_box = pieces[-1]
                pieces[-1] = (old_start, old_end - 1, old_text[:-1], old_box)
            join = ''
        else:
            join = _joiner(text, line.text)
        text += join
        start = len(text)
        text += line.text
        pieces.append((start, len(text), line.text, line.box))
    output = []
    for start, end in sentence_spans(text):
        selected = text[start:end].strip()
        if not selected or not (_LATIN.search(selected) or _CJK.search(selected)):
            continue
        boxes = []
        for a, b, line_text, box in pieces:
            if a < end and start < b:
                boxes.append(_slice_box(line_text, box, max(0, start - a), min(b, end) - a))
        if boxes:
            output.append({'text': selected, 'box': _union(boxes), 'boxes': boxes,
                           'confidence': min(line.confidence for line in group)})
    return output


def blocks_from_rows(rows, language='en', scale_x=1., scale_y=1.):
    """Convert RapidOCR quadrilaterals/text/confidence into sentence dictionaries."""
    lines = []
    for row in rows if rows is not None else []:
        try:
            points, text, confidence = row[:3]
            confidence = float(confidence)
            text = _normalize(text)
            xs, ys = [float(p[0]) / scale_x for p in points], [float(p[1]) / scale_y for p in points]
            box = (min(xs), min(ys), max(xs), max(ys))
            if (not text or not math.isfinite(confidence) or confidence < .45
                    or not all(math.isfinite(c) for c in box)
                    or box[2] <= box[0] or box[3] <= box[1]):
                continue
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            continue
        for selected, selected_box in _source_parts(text, box, language):
            lines.append(_Line(selected, selected_box, confidence))
    output = []
    for group in _paragraphs(_merge_fragments(lines)):
        output.extend(_sentences(group))
    return sorted(output, key=lambda block: (block['box'][1], block['box'][0]))


def read_scene(ocr, image, language='en'):
    """Read once with bounded enlargement, keeping CPU/memory use bounded.

    A small selected crop gets up to 2x enlargement. Large frames are capped at
    2000 pixels on their longest edge, matching the OCR runtime's own limit.
    """
    import numpy as np
    from PIL import Image

    width, height = image.size
    if width <= 0 or height <= 0:
        return [], []
    scale = min(2., 2000. / max(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    prepared = image.convert('RGB')
    if size != image.size:
        prepared = prepared.resize(size, Image.Resampling.LANCZOS)
    # RapidOCR treats numpy arrays as BGR; PIL screenshots are RGB.
    bgr = np.ascontiguousarray(np.asarray(prepared)[:, :, ::-1])
    result, _ = ocr(bgr,
                    use_cls=False, text_score=.45, box_thresh=.4)
    if language in ('en', None):
        from ocr_english import refine_english
        result = refine_english(ocr, bgr, result)
    sx, sy = size[0] / width, size[1] / height
    blocks = blocks_from_rows(result, language, sx, sy)
    obstacles = []
    for row in result if result is not None else []:
        try:
            points = row[0]
            xs, ys = [float(p[0])/sx for p in points], [float(p[1])/sy for p in points]
            box = [min(xs), min(ys), max(xs), max(ys)]
            if all(math.isfinite(v) for v in box) and box[0] < box[2] and box[1] < box[3]:
                obstacles.append(box)
        except (TypeError, ValueError, IndexError):
            continue
    return blocks, obstacles


def read_blocks(ocr, image, language='en'):
    return read_scene(ocr, image, language)[0]


def _box_distance(box, point):
    x, y = point
    return math.hypot(max(box[0] - x, 0., x - box[2]),
                      max(box[1] - y, 0., y - box[3]))


def choose_nearest(blocks, point, max_distance=100.):
    """Choose the nearest actual sentence line, or None outside the search radius."""
    candidates = []
    for index, block in enumerate(blocks):
        boxes = block.get('boxes') or [block['box']]
        distance = min(_box_distance(box, point) for box in boxes)
        if distance <= max_distance:
            center_distance = min(math.hypot((box[0] + box[2]) / 2 - point[0],
                                            (box[1] + box[3]) / 2 - point[1]) for box in boxes)
            candidates.append((distance, center_distance, index))
    return blocks[min(candidates)[2]] if candidates else None
