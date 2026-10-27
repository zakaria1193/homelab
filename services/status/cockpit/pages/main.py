"""The cockpit itself: the page served at /."""

from . import load_template

PAGE = load_template("main.html")
