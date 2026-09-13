"""Progressive Web App metadata for Vertigo.

Streamlit has no first-class way to edit the document ``<head>``, so once the
page is running we add the manifest, icons and iOS meta tags from the browser
and register the service worker. The static files themselves live in
``static/`` and are served by Streamlit at ``/app/static/``.
"""

from __future__ import annotations

import streamlit as st

PREFIX = "/app/static"
THEME_COLOR = "#2563eb"
TITLE = "Vertigo"

_SCRIPT = """
<script>
(function () {
  if (window.__vertigoPwa) return;
  window.__vertigoPwa = true;
  var head = document.head;
  var prefix = "%(prefix)s";
  function add(tag, attrs) {
    var el = document.createElement(tag);
    for (var key in attrs) el.setAttribute(key, attrs[key]);
    head.appendChild(el);
  }
  add("link", { rel: "manifest", href: prefix + "/manifest.webmanifest" });
  add("link", { rel: "icon", type: "image/png", sizes: "192x192", href: prefix + "/icons/icon-192.png" });
  add("link", { rel: "apple-touch-icon", sizes: "180x180", href: prefix + "/icons/apple-touch-icon.png" });
  add("meta", { name: "theme-color", content: "%(theme)s" });
  add("meta", { name: "mobile-web-app-capable", content: "yes" });
  add("meta", { name: "apple-mobile-web-app-capable", content: "yes" });
  add("meta", { name: "apple-mobile-web-app-status-bar-style", content: "default" });
  add("meta", { name: "apple-mobile-web-app-title", content: "%(title)s" });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(prefix + "/sw.js", { scope: "/" }).catch(function () {});
  }
})();
</script>
"""


def install_pwa() -> None:
    """Add PWA tags to the document and register the service worker."""
    script = _SCRIPT % {"prefix": PREFIX, "theme": THEME_COLOR, "title": TITLE}
    st.html(script, unsafe_allow_javascript=True)
