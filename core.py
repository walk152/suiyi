"""Pure layout helpers; no capture and no application modification."""
import re

def overlaps(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]

def valid_rect(r):
    return bool(r and len(r) == 4 and r[2] - r[0] >= 20 and r[3] - r[1] >= 15)

def relative_rect(rect, window):
    x, y, right, bottom = window
    return [(rect[0]-x)/(right-x), (rect[1]-y)/(bottom-y),
            (rect[2]-x)/(right-x), (rect[3]-y)/(bottom-y)]

def absolute_rect(r, w):
    return [round(w[0]+r[0]*(w[2]-w[0])), round(w[1]+r[1]*(w[3]-w[1])),
            round(w[0]+r[2]*(w[2]-w[0])), round(w[1]+r[3]*(w[3]-w[1]))]

def fit_lines(text, width, measure):
    """Wrap without dropping words; split long tokens rather than clipping."""
    tokens = re.findall(r'[\u3400-\u9fff]|[^\u3400-\u9fff\s]+|\s+', text.strip())
    lines, current = [], ''
    for token in tokens:
        if measure(current + token) <= width:
            current += token
            continue
        if current.strip():
            lines.append(current.strip())
        current = ''
        for char in token.lstrip():
            if current and measure(current + char) > width:
                lines.append(current.rstrip())
                current = ''
            current += char
    if current.strip():
        lines.append(current.strip())
    return lines or ['']

def caption_rect(mode, source_roi, dock, desktop, line_height, lines=1):
    if mode == 'A':
        available = max(0, (desktop[3]-source_roi[3]-10)//line_height)
        count = min(max(1,lines), available)
        if count < 1:
            return None
        rect = [source_roi[0], source_roi[3] + 6, source_roi[2], source_roi[3] + 6 + line_height*count + 4]
        if rect[3] > desktop[3] or rect[2] > desktop[2] or rect[0] < desktop[0]:
            return None
        return rect
    return list(dock) if valid_rect(dock) else None
