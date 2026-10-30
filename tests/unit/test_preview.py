from PIL import Image

from presentation.rendering.preview import contact_sheet
from state.io import logical_path, native_path


def test_contact_sheet_reads_and_writes_windows_long_paths(tmp_path):
    folder = tmp_path
    while len(str(folder)) < 280:
        folder /= "nested-preview-directory-with-preserved-lineage"
    native_path(folder).mkdir(parents=True)
    slides = []
    for index, color in enumerate(["red", "blue"], 1):
        path = native_path(folder / f"slide_{index:03}.png")
        Image.new("RGB", (80, 45), color).save(path)
        slides.append({"render": str(logical_path(path))})
    destination = logical_path(folder / "output/contact_sheet.png")
    assert contact_sheet({"slides": slides}, destination, columns=2) == destination
    with Image.open(native_path(destination)) as image:
        assert image.size == (848, 257)
        assert image.getpixel((16, 16)) == (255, 0, 0)
        assert image.getpixel((432, 16)) == (0, 0, 255)
