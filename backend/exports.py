"""Bounded exports with CSV formula-neutralization."""

import csv, io, json


def cell(value):
    text = (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, (list, dict))
        else "" if value is None else str(value)
    )
    return (
        "'" + text
        if text.lstrip().startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r", "\n"))
        else text
    )


def render(rows, format):
    if format == "json":
        return json.dumps(rows, ensure_ascii=False, allow_nan=False, indent=2)
    fields = sorted({key for row in rows for key in row})
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: cell(row.get(key)) for key in fields})
    return output.getvalue()
