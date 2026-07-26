"""PDF export uses no third-party library, so it must be checked closely."""
import re
import zlib

from helix.layout import registry
from helix.layout.base import LayoutSettings
from helix.layout.engines import linear, radial  # noqa: F401
from helix.render import pdf as pdfrender
from helix.style.tokens import Style

MM_TO_PT = 72.0 / 25.4


def _plan(graph, key="radial_sunburst", style=None):
    st = Style.load(style)
    return registry.run(key, graph,
                        LayoutSettings(engine=key, subject_id=graph.subject_id,
                                       max_generations=4), st)


def test_writes_a_structurally_valid_pdf(graph, tmp_path):
    p = tmp_path / "t.pdf"
    pdfrender.write(_plan(graph), p)
    data = p.read_bytes()
    assert data.startswith(b"%PDF-1.")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"startxref" in data and b"/Catalog" in data and b"/Pages" in data


def test_page_is_the_true_physical_size(graph, tmp_path):
    """A framer measures the page. It must equal the piece."""
    plan = _plan(graph)
    p = tmp_path / "t.pdf"
    pdfrender.write(plan, p)
    m = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", p.read_bytes())
    assert m
    assert abs(float(m.group(1)) - plan.canvas.width_mm * MM_TO_PT) < 0.1
    assert abs(float(m.group(2)) - plan.canvas.height_mm * MM_TO_PT) < 0.1


def test_xref_offsets_point_at_real_objects(graph, tmp_path):
    p = tmp_path / "t.pdf"
    pdfrender.write(_plan(graph, "icicle"), p)
    data = p.read_bytes()
    start = int(re.search(rb"startxref\s+(\d+)", data).group(1))
    assert data[start:start + 4] == b"xref"
    for off in [int(x) for x in re.findall(rb"^(\d{10}) 00000 n", data[start:],
                                           re.M)]:
        assert re.match(rb"\d+ 0 obj", data[off:off + 20]), f"bad offset {off}"


def test_content_stream_decompresses_and_draws(graph, tmp_path):
    p = tmp_path / "t.pdf"
    pdfrender.write(_plan(graph, "metro_map", "tubemap"), p)
    data = p.read_bytes()
    raw = data.split(b"stream\n", 1)[1].rsplit(b"\nendstream", 1)[0]
    content = zlib.decompress(raw).decode("latin-1")
    assert " m\n" in content and " l\n" in content     # moveto / lineto
    assert " S" in content                             # stroke
    assert "BT " in content and " Tj " in content      # text
    assert "nan" not in content.lower()


def test_every_built_design_exports(graph, tmp_path):
    for key in ("radial_sunburst", "radial_rings", "metro_map",
                "timeline_lanes", "radial_lifeline", "circle_pack",
                "arc_diagram", "dendrogram", "icicle", "radial_spiral",
                "radial_organic"):
        out = tmp_path / f"{key}.pdf"
        pdfrender.write(_plan(graph, key), out)
        assert out.stat().st_size > 1000, key


def test_text_widths_are_real_metrics():
    """Centred labels land wrong if widths are guessed. 'W' is wide, 'i'
    is narrow, and the metrics must know it."""
    w = pdfrender._text_width
    assert w("W", 10, "helv") > w("i", 10, "helv") * 3
    assert w("iiii", 10, "helv") < w("WWWW", 10, "helv")
    # H722 + e556 + l222 + l222 + o556 = 2278/1000 em = 22.78 pt at 10 pt
    assert abs(w("Hello", 10, "helv") - 22.78) < 0.01
    assert abs(w("Hello", 10, "times") - 22.22) < 0.01


def test_special_characters_survive_escaping():
    e = pdfrender._esc
    assert e("(brackets)") == r"\(brackets\)"
    assert e("back\\slash") == "back\\\\slash"
    assert "\\226" in e("1841\u20131902")           # en dash -> WinAnsi
