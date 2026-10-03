"""crew-diagrams' readability checker: it measures the drawn diagram, not the
source. Real Mermaid 11 renders are the fixtures for crossing / clean /
sequence (fixtures/diagrams/); the shapes Mermaid will not draw on request --
an edge through a node, overlapping labels -- are minimal hand-written SVGs."""
import os

import context  # noqa: F401  pylint: disable=unused-import
import diagram_check

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "diagrams")


def _measure(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return diagram_check.measure(fh.read())


def _svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" aria-roledescription="flowchart-v2">'
            f'<g class="root">{body}</g></svg>')


def _node(name, x, y, w=80, h=40):
    return (f'<g class="node default" id="x-flowchart-{name}-0" transform="translate({x}, {y})">'
            f'<rect x="{-w / 2}" y="{-h / 2}" width="{w}" height="{h}"></rect></g>')


def _edge(src, dst, d):
    return f'<path class="flowchart-link" id="x-L_{src}_{dst}_0" d="{d}"></path>'


def test_the_crossing_a_reader_saw_is_measured():
    """The QA gate diagram before its fix: fix->stop looped back across ci->merge."""
    r = _measure("crossing.svg")
    assert r["status"] == diagram_check.FAIL
    assert r["crossings"] == ["fix->stop x ci->merge at (322,520)"]


def test_the_fixed_diagram_passes():
    r = _measure("clean.svg")
    assert r["status"] == diagram_check.PASS and r["nodes"] == 8 and r["edges"] == 7


def test_a_sequence_diagram_is_not_checked_never_passed():
    assert _measure("sequence.svg")["status"] == diagram_check.NOT_CHECKED


def test_an_edge_through_a_third_node_fails():
    svg = _svg(_node("a", 100, 50) + _node("b", 100, 150) + _node("c", 100, 250)
               + _edge("a", "c", "M100,70L100,230"))
    r = diagram_check.measure(svg)
    assert r["status"] == diagram_check.FAIL and r["through"] == ["a->c through b"]


def test_arrows_converging_on_their_shared_node_are_not_a_crossing():
    """Arrows into one node cross each other just short of it (c's top is y=180);
    that is the drawing converging, not two lines crossing."""
    svg = _svg(_node("a", 50, 50) + _node("b", 250, 50) + _node("c", 150, 200)
               + _edge("a", "c", "M50,70L152,181") + _edge("b", "c", "M250,70L148,181"))
    assert diagram_check.measure(svg)["status"] == diagram_check.PASS


def test_an_edge_starting_inside_its_own_node_is_not_through_it():
    svg = _svg(_node("a", 100, 50) + _node("b", 100, 150) + _edge("a", "b", "M100,55L100,140"))
    assert diagram_check.measure(svg)["status"] == diagram_check.PASS


def test_two_edges_crossing_in_open_space_fail():
    svg = _svg(_node("a", 50, 50) + _node("b", 250, 50) + _node("c", 50, 250) + _node("d", 250, 250)
               + _edge("a", "d", "M50,70L250,230") + _edge("b", "c", "M250,70L50,230"))
    assert len(diagram_check.measure(svg)["crossings"]) == 1


def test_a_label_on_a_node_fails():
    label = ('<g class="edgeLabel" transform="translate(100, 50)"><g class="label" '
             'transform="translate(-10, -10)"><foreignObject width="20" height="20"></foreignObject></g></g>')
    svg = _svg(_node("a", 100, 50) + label)
    assert diagram_check.measure(svg)["overlaps"] == ["label 0 on a"]


def test_too_many_nodes_fails_with_a_reason():
    svg = _svg("".join(_node(f"n{i}", 100 * i, 50) for i in range(diagram_check.MAX_NODES + 1)))
    r = diagram_check.measure(svg)
    assert r["status"] == diagram_check.FAIL and "split it" in r["why"]


def test_an_unparseable_svg_is_unknown():
    assert diagram_check.measure("<svg><g></svg>")["status"] == diagram_check.UNKNOWN


def test_html_void_tags_from_a_browser_render_still_parse():
    svg = _svg(_node("a", 50, 50)).replace("</rect>", "</rect><foreignObject><div>x<br>y</div></foreignObject>")
    assert diagram_check.measure(svg)["status"] == diagram_check.PASS


def test_cli_exit_codes(capsys):
    assert diagram_check.main([os.path.join(FIX, "clean.svg"), os.path.join(FIX, "sequence.svg")]) == 0
    assert diagram_check.main([os.path.join(FIX, "crossing.svg")]) == 1
    assert "FAIL" in capsys.readouterr().out


def _cylinder(name, x, y):
    """Mermaid's cylinder ([( )] shape): relative arcs and lines, no absolute coordinates."""
    return (f'<g class="node default" id="x-flowchart-{name}-0" transform="translate({x}, {y})">'
            '<path d="M-40,-14 a40,6 0,0,0 80,0 a40,6 0,0,0 -80,0 l0,28 a40,6 0,0,0 80,0 l0,-28"></path></g>')


def test_a_cylinder_is_measured_and_a_line_through_it_fails():
    """Mermaid draws [( )] with relative arcs; the first checker skipped it, so a
    line through a database box passed unseen (found by the splitting agents)."""
    svg = _svg(_node("a", 100, 50) + _cylinder("db", 100, 150) + _node("c", 100, 250)
               + _edge("a", "c", "M100,70L100,230"))
    r = diagram_check.measure(svg)
    assert r["nodes"] == 3 and r["through"] == ["a->c through db"]


def test_a_node_whose_shape_cannot_be_measured_is_unknown_not_skipped():
    svg = _svg('<g class="node default" id="x-flowchart-odd-0"><text>?</text></g>' + _node("a", 50, 50))
    r = diagram_check.measure(svg)
    assert r["status"] == diagram_check.UNKNOWN and "odd" in r["why"]


def test_a_wordy_box_is_a_warning_not_a_fail():
    tall = ('<g class="node default" id="x-flowchart-tall-0" transform="translate(100, 100)">'
            '<rect x="-60" y="-100" width="120" height="200"></rect><g class="label">'
            f'<foreignObject width="100" height="{24 * (diagram_check.MAX_BOX_LINES + 1)}"></foreignObject></g></g>')
    r = diagram_check.measure(_svg(tall))
    assert r["status"] == diagram_check.PASS and r["wordy"] == [f"tall ({diagram_check.MAX_BOX_LINES + 1} lines)"]
    short = tall.replace(f'height="{24 * (diagram_check.MAX_BOX_LINES + 1)}"', 'height="48"')
    assert diagram_check.measure(_svg(short))["wordy"] == []


def _label(owner, x, y, w=60, h=24):
    return (f'<g class="edgeLabel" transform="translate({x}, {y})"><g class="label" data-id="{owner}" '
            f'transform="translate({-w / 2}, {-h / 2})">'
            f'<foreignObject width="{w}" height="{h}"></foreignObject></g></g>')


def test_a_line_through_another_edges_label_fails_but_its_own_label_does_not():
    """The review diagram's CLEAN line ran through the FINDINGS label: unreadable,
    though nothing crossed and no box was hit."""
    base = (_node("a", 100, 50) + _node("b", 100, 250) + _node("c", 300, 250)
            + _edge("a", "b", "M100,70L100,230") + _label("L_a_b_0", 100, 150))
    assert diagram_check.measure(_svg(base))["overlaps"] == []
    crossed = base + _edge("a", "c", "M110,70L110,150L300,230")
    assert diagram_check.measure(_svg(crossed))["overlaps"] == ["a->c through label of a->b"]


def test_a_wordy_edge_label_is_a_warning():
    svg = _svg(_node("a", 100, 50) + _node("b", 100, 450) + _edge("a", "b", "M100,70L100,430")
               + _label("L_a_b_0", 100, 250, h=24 * (diagram_check.MAX_BOX_LINES + 1)))
    r = diagram_check.measure(svg)
    assert r["status"] == diagram_check.PASS
    assert r["wordy"] == [f"label of a->b ({diagram_check.MAX_BOX_LINES + 1} lines)"]


# --- review of PR #375: no verdict may PASS without measuring ---------------

def test_no_node_boxes_at_all_is_unknown_not_pass():
    r = diagram_check.measure('<svg xmlns="http://www.w3.org/2000/svg" aria-roledescription="flowchart-v2">'
                              '<g><path class="x" d="M0 0L5 5"/></g></svg>')
    assert r["status"] == diagram_check.UNKNOWN and r["nodes"] == 0 and "no node" in r["why"]


def test_an_edge_with_no_measured_node_is_unknown_not_pass():
    r = diagram_check.measure(_svg(_edge("a", "b", "M0,0L100,100")))
    assert r["status"] == diagram_check.UNKNOWN and r["edges"] == 1 and "no node box" in r["why"]


def test_numbers_after_closepath_are_a_value_error_not_a_key_error():
    try:
        diagram_check.path_points("M0 0 L10 10 Z 5 5")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    r = diagram_check.measure(_svg(_node("a", 50, 50) + _node("b", 50, 250)
                                   + _edge("a", "b", "M50,70 L50,230 Z 5 5")))
    assert r["status"] == diagram_check.UNKNOWN


def test_an_unexpected_checker_error_is_unknown_never_a_crash(monkeypatch):
    def boom(*_):
        raise KeyError("Z")
    monkeypatch.setattr(diagram_check, "path_points", boom)
    r = diagram_check.measure(_svg(_node("a", 50, 50) + _edge("a", "a", "M0,0L1,1")))
    assert r["status"] == diagram_check.UNKNOWN and "KeyError" in r["why"]


def test_smooth_curves_reflect_the_previous_control_point():
    # S after C: its first control point is (50,100) reflected about (50,50) = (50,0).
    pts = diagram_check.path_points("M0,50 C0,100 50,100 50,50 S100,0 100,50")
    assert pts == diagram_check.path_points("M0,50 C0,100 50,100 50,50 C50,0 100,0 100,50")
    rel = diagram_check.path_points("M0,50 c0,50 50,50 50,0 s50,-50 50,0")
    assert [tuple(round(v, 6) for v in p) for p in rel] == [tuple(round(v, 6) for v in p) for p in pts]
    # T after Q reflects too: the curve from (100,0) bows below y=0.
    tq = diagram_check.path_points("M0,0 Q50,100 100,0 T200,0")
    assert tq == diagram_check.path_points("M0,0 Q50,100 100,0 Q150,-100 200,0")


def test_an_s_curve_through_a_node_is_seen():
    """Before S/s was read, its numbers were parsed as the previous command."""
    svg = _svg(_node("a", 0, 0) + _node("b", 300, 0) + _node("mid", 150, -60)
               + _edge("a", "b", "M40,0 C60,0 100,-60 150,-60 S240,0 260,0"))
    assert diagram_check.measure(svg)["through"] == ["a->b through mid"]


def test_one_argument_translate_is_x_only():
    el = diagram_check.ET.fromstring('<g transform="translate(10)"/>')
    assert diagram_check._offset(el, (1.0, 2.0)) == (11.0, 2.0)  # pylint: disable=protected-access
    svg = _svg('<g transform="translate(200)">' + _node("a", 0, 50) + _node("b", 0, 250) + '</g>'
               + _node("c", 200, 150) + _edge("a", "b", "M200,70L200,230"))
    assert diagram_check.measure(svg)["through"] == ["a->b through c"]


def test_a_scale_or_rotate_above_a_measured_element_is_unknown():
    for t in ("scale(2)", "rotate(90)", "matrix(1 0 0 1 0 0)", "skewX(10)", "translate(5,5) scale(2)"):
        svg = _svg(f'<g transform="{t}">' + _node("a", 50, 50) + "</g>")
        r = diagram_check.measure(svg)
        assert r["status"] == diagram_check.UNKNOWN and "not measured" in r["why"], t


def test_a_scaled_shape_that_is_not_measured_does_not_matter():
    svg = _svg('<defs><path transform="scale(.5)" d="M0 0L1 1"/></defs>' + _node("a", 50, 50))
    assert diagram_check.measure(svg)["status"] == diagram_check.PASS


def test_an_arc_edge_is_sampled_along_its_curve():
    """A half-circle from (0,0) to (200,0) bulging to y=-100 passes through a
    node at its top; the endpoints-plus-radii approximation did not see it."""
    pts = diagram_check.path_points("M0,0 A100,100 0 0,1 200,0")
    assert abs(min(p[1] for p in pts) + 100) < 1 and pts[-1] == (200.0, 0.0)
    svg = _svg(_node("a", -40, 0, w=40) + _node("b", 240, 0, w=40) + _node("top", 100, -100, w=20, h=10)
               + _edge("a", "b", "M0,0 A100,100 0 0,1 200,0"))
    assert diagram_check.measure(svg)["through"] == ["a->b through top"]
