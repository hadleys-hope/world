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
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
    '&family=IBM+Plex+Sans+Condensed:wght@400;500;600&display=swap">'
)
NAV_HTML = template("nav_html.html").replace("CONSOLEBTN", "")
NAV_HTML_3D = template("nav_html.html").replace(
    "CONSOLEBTN",
    '<button class="hh-console" id="panel-toggle" aria-expanded="false" aria-controls="side" '
    'title="Show or hide the console"><span data-i18n="Console">Console</span><kbd>M</kbd></button>',
)


def page(name, last_css="/static/css/shell.css"):
    """A 2D page in the shared shell: the top bar, the fonts, and the shell stylesheet after the page's own."""
    return (
        template(name)
        .replace("NAVCSS", NAV_CSS)
        .replace("NAVHTML", NAV_HTML)
        .replace("</head>", f'{FONTS}<link rel="stylesheet" href="{last_css}">\n</head>', 1)
    )


HTML = page("html.html")
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
HTML3D = (
    template("html3d.html")
    .replace("NAVHTML", NAV_HTML_3D)
    .replace("</head>", FONTS + "\n" + EARLY_PRELOADS + "\n" + MODULE_PRELOADS + "\n</head>", 1)
)
HTMLBUS = page("htmlbus.html")
HTMLHOUSE = page("htmlhouse.html")
HTMLGRAPH = page("htmlgraph.html")
HTMLATTR = page("htmlattr.html")
HTMLFINANCE = page("htmlfinance.html")
HTMLPROGRAMS = page("htmlprograms.html")
