"""Templates and static resource locations, independent of the working directory."""

from pathlib import Path
import posixpath
import re

ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = ROOT / "web" / "static"
TEMPLATE_ROOT = ROOT / "web" / "templates"


def template(name):
    return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")


NAV_CSS = (STATIC_ROOT / "css/navigation.css").read_text(encoding="utf-8")
NAV_HTML = template("nav_html.html")
HTML = template("html.html")
# Eager preload avoids a waterfall of requests through the module dependency graph.
MODULE_PRELOADS = "\n".join(
    f'<link rel="modulepreload" href="/static/{p.relative_to(STATIC_ROOT).as_posix()}">'
    for p in sorted((STATIC_ROOT / "js/map3d").rglob("*.js"))
)
THREE_ADDONS = ("controls/OrbitControls.js", "postprocessing/EffectComposer.js", "postprocessing/RenderPass.js",
                "postprocessing/UnrealBloomPass.js")


def _addon_closure(entries, root=ROOT / "vendor" / "three" / "examples" / "jsm"):
    """The three.js addons the viewer imports plus everything they import relatively, so all are preloaded."""
    seen, todo = set(), list(entries)
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        path = root / rel
        if path.is_file():
            for dep in re.findall(r"from\s+['\"](\.\.?/[^'\"]+)['\"]", path.read_text(encoding="utf-8")):
                todo.append(posixpath.normpath(posixpath.join(posixpath.dirname(rel), dep)))
    return sorted(seen)


# three.js and its addons are otherwise discovered only after the viewer's modules are parsed; /geometry and
# /state only after three.js runs. Preloading them starts every download at once (__THREE_BASE__ is set by cli).
EARLY_PRELOADS = "\n".join(
    ['<link rel="modulepreload" href="__THREE_BASE__build/three.module.js">']
    + [f'<link rel="modulepreload" href="__THREE_BASE__examples/jsm/{a}">' for a in _addon_closure(THREE_ADDONS)]
    + ['<link rel="preload" href="/geometry" as="fetch" crossorigin="anonymous">']
)
HTML3D = template("html3d.html").replace("</head>", EARLY_PRELOADS + "\n" + MODULE_PRELOADS + "\n</head>")
HTMLBUS = template("htmlbus.html")
HTMLHOUSE = (
    template("htmlhouse.html").replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)
)
HTMLGRAPH = (
    template("htmlgraph.html").replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)
)
HTMLATTR = (
    template("htmlattr.html").replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)
)
HTMLFINANCE = (
    template("htmlfinance.html").replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)
)
