"""Keep sentence context and cover all input even beyond model request limits."""
from screen_text import sentence_spans


def token_batches(text, tokenizer, limit=128):
    pieces = [text[a:b] for a, b in sentence_spans(text)]
    output = []
    for piece in pieces:
        tokens = tokenizer.encode(piece, out_type=str)
        while tokens:
            end = min(len(tokens), limit)
            if end < len(tokens):
                # Prefer a clause boundary, otherwise start the next batch at
                # a word boundary. No token is omitted or duplicated.
                clauses = [i+1 for i, t in enumerate(tokens[:end])
                           if i >= limit//2 and any(c in t for c in ',;，；：:')]
                words = [i for i, t in enumerate(tokens[:end]) if i >= limit//2 and t.startswith('▁')]
                end = clauses[-1] if clauses else words[-1] if words else end
            output.append(tokens[:end])
            tokens = tokens[end:]
    return output
