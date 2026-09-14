"""A themed empty-state placeholder built with Streamlit components v2 (CCv2).

Each page shows this while it has nothing to display yet: a large Material
Symbols icon above a semibold title and a muted description, centered inside a
card. Every color comes from Streamlit's ``--st-*`` theme tokens, so the
component follows the active light/dark theme without its own variants.
"""

from __future__ import annotations

import streamlit as st

_HTML = """
<div class="vertigo-empty">
  <span class="vertigo-empty__icon" aria-hidden="true"></span>
  <p class="vertigo-empty__title"></p>
  <p class="vertigo-empty__description"></p>
</div>
"""

_CSS = """
:host {
  display: block;
  height: 100%;
}

.vertigo-empty {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  height: 100%;
  min-height: 17rem;
  padding: 2.25rem 1.75rem;
  text-align: center;
  font-family: var(--st-font, sans-serif);
  color: var(--st-text-color, inherit);
  background: var(--st-secondary-background-color, transparent);
  border: 1px solid var(--st-border-color, transparent);
  border-radius: var(--st-base-radius, 0.5rem);
}

.vertigo-empty__icon {
  font-family: "Material Symbols Rounded";
  font-weight: 400;
  font-style: normal;
  font-size: clamp(2.75rem, 6vw, 3.75rem);
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  white-space: nowrap;
  direction: ltr;
  -webkit-font-feature-settings: "liga";
  font-feature-settings: "liga";
  -webkit-font-smoothing: antialiased;
  color: var(--st-primary-color, currentColor);
  user-select: none;
}

.vertigo-empty__title {
  margin: 0.75rem 0 0;
  font-size: var(--st-heading-font-size-4, 1.0625rem);
  font-weight: 600;
  line-height: 1.35;
  color: var(--st-text-color, inherit);
}

.vertigo-empty__description {
  margin: 0;
  max-width: 34ch;
  font-size: 0.9375rem;
  line-height: 1.55;
  color: var(--st-gray-text-color, var(--st-text-color, inherit));
}

.vertigo-empty__description:empty {
  display: none;
}
"""

_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const root = parentElement.querySelector(".vertigo-empty");
  if (!root) return;
  const icon = root.querySelector(".vertigo-empty__icon");
  const title = root.querySelector(".vertigo-empty__title");
  const description = root.querySelector(".vertigo-empty__description");
  if (icon) icon.textContent = data?.icon ?? "";
  if (title) title.textContent = data?.title ?? "";
  if (description) description.textContent = data?.description ?? "";
}
"""

_EMPTY_STATE = st.components.v2.component(
    "vertigo_empty_state",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def empty_state(
    *,
    icon: str,
    title: str,
    description: str = "",
    height: int | str = "stretch",
    key: str | None = None,
) -> None:
    """Render a centered, theme-aware empty state.

    Parameters
    ----------
    icon:
        A Material Symbols name without the surrounding markers, e.g.
        ``"imagesmode"``.
    title:
        The semibold line shown below the icon.
    description:
        A muted supporting line shown below the title.
    height:
        Forwarded to the component mount; ``"stretch"`` fills its container.
    key:
        Optional unique key when several empty states share a page.
    """
    _EMPTY_STATE(
        data={"icon": icon, "title": title, "description": description},
        key=key,
        height=height,
    )
