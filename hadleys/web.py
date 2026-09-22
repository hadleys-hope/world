"""Templates and static resource locations, independent of the working directory."""

from pathlib import Path

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
HTML3D = template("html3d.html").replace("</head>", MODULE_PRELOADS + "\n</head>")
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
