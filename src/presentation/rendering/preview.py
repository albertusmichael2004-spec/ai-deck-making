from pathlib import Path

from PIL import Image

from state.io import native_path


def contact_sheet(report: dict, destination: Path, columns=3):
    """Preview combines actual slide renders; no illustrative slide approximation."""
    paths = [native_path(Path(s["render"])) for s in report["slides"]]
    thumb_width, thumb_height, gap = 400, 225, 16
    rows = (len(paths) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * (thumb_width + gap) + gap, rows * (thumb_height + gap) + gap), "#e7e9ef")
    for index, path in enumerate(paths):
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((thumb_width, thumb_height))
            canvas.paste(image, (gap + (index % columns) * (thumb_width + gap), gap + (index // columns) * (thumb_height + gap)))
    target = native_path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target)
    return destination
