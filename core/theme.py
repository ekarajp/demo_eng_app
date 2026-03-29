from __future__ import annotations

from dataclasses import dataclass
import streamlit as st
import streamlit.components.v1 as components


@dataclass(frozen=True, slots=True)
class ThemePalette:
    name: str
    background: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted_text: str
    accent: str
    accent_soft: str
    ok: str
    warning: str
    fail: str
    shadow: str
    plot_background: str


LIGHT_THEME = ThemePalette(
    name="Light Mode",
    background="#f4f6fa",
    surface="#ffffff",
    surface_alt="#edf2f7",
    border="#d7deea",
    text="#122033",
    muted_text="#39485c",
    accent="#1f6fb2",
    accent_soft="#dcecf8",
    ok="#1f8a5b",
    warning="#c07c1d",
    fail="#c23a3a",
    shadow="0 14px 32px rgba(18, 32, 51, 0.08)",
    plot_background="#f8fafc",
)


DARK_THEME = ThemePalette(
    name="Dark Mode",
    background="#0f1722",
    surface="#182231",
    surface_alt="#111b29",
    border="#2d3a4f",
    text="#edf3fb",
    muted_text="#a8b5c8",
    accent="#6fb4ff",
    accent_soft="#1f3550",
    ok="#58c58b",
    warning="#f0b45b",
    fail="#ff7d7d",
    shadow="0 18px 40px rgba(0, 0, 0, 0.28)",
    plot_background="#111b29",
)


CLIENT_THEME = ThemePalette(
    name="Client Theme",
    background="var(--app-bg)",
    surface="var(--surface)",
    surface_alt="var(--surface-alt)",
    border="var(--border)",
    text="var(--text)",
    muted_text="var(--muted-text)",
    accent="var(--accent)",
    accent_soft="var(--accent-soft)",
    ok=LIGHT_THEME.ok,
    warning=LIGHT_THEME.warning,
    fail=LIGHT_THEME.fail,
    shadow=LIGHT_THEME.shadow,
    plot_background="var(--plot-background)",
)


def _normalize_hex_color(color: str | None) -> str | None:
    if not isinstance(color, str):
        return None
    value = color.strip()
    if not value.startswith("#"):
        return None
    hex_digits = value[1:]
    if len(hex_digits) == 3:
        hex_digits = "".join(channel * 2 for channel in hex_digits)
    if len(hex_digits) != 6:
        return None
    try:
        int(hex_digits, 16)
    except ValueError:
        return None
    return f"#{hex_digits.lower()}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = _normalize_hex_color(color)
    if normalized is None:
        raise ValueError(f"Unsupported color value: {color}")
    return tuple(int(normalized[index : index + 2], 16) for index in (1, 3, 5))


def _rgb_to_hex(red: float, green: float, blue: float) -> str:
    channels = [max(0, min(255, round(value))) for value in (red, green, blue)]
    return "#{:02x}{:02x}{:02x}".format(*channels)


def _mix_hex_colors(base: str, overlay: str, ratio: float) -> str:
    clamped_ratio = max(0.0, min(1.0, ratio))
    base_red, base_green, base_blue = _hex_to_rgb(base)
    overlay_red, overlay_green, overlay_blue = _hex_to_rgb(overlay)
    return _rgb_to_hex(
        base_red + (overlay_red - base_red) * clamped_ratio,
        base_green + (overlay_green - base_green) * clamped_ratio,
        base_blue + (overlay_blue - base_blue) * clamped_ratio,
    )


def _relative_luminance(color: str) -> float:
    def linearize(channel: int) -> float:
        normalized = channel / 255
        if normalized <= 0.04045:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    red, green, blue = _hex_to_rgb(color)
    return 0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)


def _is_light_color(color: str) -> bool:
    return _relative_luminance(color) >= 0.45


def contrast_text_color(background: str, *, light_text: str = "#111111", dark_text: str = "#f8fbff") -> str:
    return light_text if _is_light_color(background) else dark_text


def get_palette(theme_name: str) -> ThemePalette:
    return LIGHT_THEME


def resolve_streamlit_theme_type() -> str:
    return "light"


def resolve_palette(theme_name: str) -> ThemePalette:
    return LIGHT_THEME


def _theme_vars_block(*, palette: ThemePalette) -> str:
    return f"""
            --app-bg: var(--beam-app-bg, {LIGHT_THEME.background});
            --surface: var(--beam-surface, {LIGHT_THEME.surface});
            --surface-alt: var(--beam-surface-alt, {LIGHT_THEME.surface_alt});
            --border: var(--beam-border, {LIGHT_THEME.border});
            --text: var(--beam-text, {LIGHT_THEME.text});
            --muted-text: var(--beam-muted-text, {LIGHT_THEME.muted_text});
            --accent: var(--beam-accent, {LIGHT_THEME.accent});
            --accent-soft: var(--beam-accent-soft, {LIGHT_THEME.accent_soft});
            --ok: {palette.ok};
            --warning: {palette.warning};
            --fail: {palette.fail};
            --ok-soft: color-mix(in srgb, {palette.ok} 16%, transparent);
            --warning-soft: color-mix(in srgb, {palette.warning} 18%, transparent);
            --fail-soft: color-mix(in srgb, {palette.fail} 18%, transparent);
            --shadow: {palette.shadow};
            --plot-background: color-mix(in srgb, var(--app-bg) 35%, var(--surface));
            --on-accent: var(--beam-on-accent, #f8fbff);
            --header-surface: color-mix(in srgb, var(--surface) 72%, var(--accent-soft));
            --header-text: var(--text);
            --tab-active-bg: color-mix(in srgb, var(--surface) 45%, var(--accent-soft));
            --tab-active-text: var(--text);
            --tab-active-border: color-mix(in srgb, var(--border) 55%, var(--accent));
            --tab-idle-bg: color-mix(in srgb, var(--surface) 55%, var(--app-bg));
            --sidebar-surface: color-mix(in srgb, var(--app-bg) 45%, var(--surface));
            --sidebar-hover-bg: color-mix(in srgb, var(--sidebar-surface) 65%, var(--accent-soft));
            --sidebar-active-bg: color-mix(in srgb, var(--accent-soft) 60%, var(--accent));
            --sidebar-active-text: var(--on-accent);
            --topbar-bg: color-mix(in srgb, var(--app-bg) 60%, var(--surface));
            --topbar-text: var(--text);
            --topbar-border: color-mix(in srgb, var(--border) 65%, var(--surface));
            --print-button-text: var(--on-accent);
    """


def _render_theme_sync_bridge() -> None:
    components.html(
        """
        <script>
        (function () {
          const parentWindow = window.parent;
          const parentDoc = parentWindow.document;
          const syncVersion = "beam-theme-sync-v4";

          function clamp(value, minValue, maxValue) {
            return Math.min(maxValue, Math.max(minValue, value));
          }

          function parseColor(value) {
            if (!value) return null;
            const match = value.match(/rgba?\\(([^)]+)\\)/i);
            if (!match) return null;
            const parts = match[1].split(",").map((part) => Number.parseFloat(part.trim()));
            if (parts.length < 3 || parts.slice(0, 3).some((part) => Number.isNaN(part))) return null;
            return {
              rgb: parts.slice(0, 3),
              alpha: parts.length >= 4 && !Number.isNaN(parts[3]) ? parts[3] : 1,
            };
          }

          function toCss(rgb) {
            return `rgb(${rgb.map((channel) => clamp(Math.round(channel), 0, 255)).join(", ")})`;
          }

          function mix(base, overlay, ratio) {
            return base.map((channel, index) => channel + (overlay[index] - channel) * ratio);
          }

          function luminance(rgb) {
            const linear = rgb.map((channel) => {
              const normalized = channel / 255;
              return normalized <= 0.04045
                ? normalized / 12.92
                : Math.pow((normalized + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
          }

          function computedStyle(selector) {
            const element = parentDoc.querySelector(selector);
            return element ? parentWindow.getComputedStyle(element) : null;
          }

          function readSchemeHint(value) {
            const normalized = String(value || "").trim().toLowerCase();
            if (!normalized) return null;
            if (/(^|[\\s:_-])dark($|[\\s:_-])/.test(normalized)) return "dark";
            if (/(^|[\\s:_-])light($|[\\s:_-])/.test(normalized)) return "light";
            return null;
          }

          function elementSchemeHint(element) {
            if (!element) return null;
            const valuesToCheck = [
              element.getAttribute && element.getAttribute("data-theme"),
              element.getAttribute && element.getAttribute("data-base-theme"),
              element.dataset && element.dataset.theme,
              element.dataset && element.dataset.baseTheme,
              element.className,
            ];

            for (const value of valuesToCheck) {
              const hintedScheme = readSchemeHint(value);
              if (hintedScheme) return hintedScheme;
            }

            return null;
          }

          function valueSchemeHint(value, depth = 0) {
            if (depth > 3 || value == null) return null;
            if (typeof value === "string") {
              const directHint = readSchemeHint(value);
              if (directHint) return directHint;
              try {
                return valueSchemeHint(JSON.parse(value), depth + 1);
              } catch (error) {
                return null;
              }
            }
            if (Array.isArray(value)) {
              for (const item of value) {
                const hintedScheme = valueSchemeHint(item, depth + 1);
                if (hintedScheme) return hintedScheme;
              }
              return null;
            }
            if (typeof value === "object") {
              const preferredKeys = ["base", "theme", "themeBase", "colorScheme", "appearance", "mode", "name"];
              for (const key of preferredKeys) {
                if (!(key in value)) continue;
                const hintedScheme = valueSchemeHint(value[key], depth + 1);
                if (hintedScheme) return hintedScheme;
              }
            }
            return null;
          }

          function storageSchemeHint(storage) {
            if (!storage) return null;
            try {
              for (let index = 0; index < storage.length; index += 1) {
                const key = storage.key(index);
                if (!key) continue;
                const rawValue = storage.getItem(key);
                const searchText = `${key} ${rawValue || ""}`.toLowerCase();
                if (!/(theme|scheme|appearance|mode)/.test(searchText)) continue;
                const hintedFromValue = valueSchemeHint(rawValue);
                if (hintedFromValue) return hintedFromValue;
                const hintedFromKey = readSchemeHint(key);
                if (hintedFromKey) return hintedFromKey;
              }
            } catch (error) {
              return null;
            }
            return null;
          }

          function detectColorScheme() {
            return "light";
          }

          function firstOpaqueColor(candidates) {
            for (const [selector, propertyName] of candidates) {
              const style = computedStyle(selector);
              if (!style) continue;
              const parsed = parseColor(style[propertyName]);
              if (parsed && parsed.alpha > 0.02) return parsed.rgb;
            }
            return null;
          }

          function firstSolidColor(candidates) {
            for (const [selector, propertyName] of candidates) {
              const style = computedStyle(selector);
              if (!style) continue;
              const parsed = parseColor(style[propertyName]);
              if (parsed && parsed.alpha > 0.02) return parsed.rgb;
            }
            return null;
          }

          function resolveThemeVars() {
            const explicitScheme = detectColorScheme();
            const isLight = true;
            const defaults = {
              background: [244, 246, 250],
              surface: [255, 255, 255],
              surfaceAlt: [237, 242, 247],
              border: [215, 222, 234],
              text: [18, 32, 51],
              mutedText: [57, 72, 92],
            };
            const background = defaults.background;
            const accent =
              firstSolidColor([
                ["button[kind='primary']", "backgroundColor"],
                ["button[kind='secondary']", "borderColor"],
                ["div[data-testid='stSidebarNav'] a[aria-current='page']", "backgroundColor"],
                ["a", "color"],
              ]) ||
              [31, 111, 178];

            const surface = mix(background, defaults.surface, isLight ? 0.88 : 0.78);
            const surfaceAlt = mix(surface, defaults.surfaceAlt, isLight ? 0.78 : 0.82);
            const border = mix(surface, defaults.border, isLight ? 0.72 : 0.68);
            const resolvedText = defaults.text;
            const mutedText = defaults.mutedText;
            const accentSoft = mix(background, accent, isLight ? 0.18 : 0.28);
            const onAccent = luminance(accent) >= 0.45 ? "#111111" : "#f8fbff";

            return {
              scheme: explicitScheme,
              appBg: toCss(background),
              surface: toCss(surface),
              surfaceAlt: toCss(surfaceAlt),
              border: toCss(border),
              text: toCss(resolvedText),
              mutedText: toCss(mutedText),
              accent: toCss(accent),
              accentSoft: toCss(accentSoft),
              onAccent,
            };
          }

          function syncThemeVars() {
            const vars = resolveThemeVars();
            const cssText = `
              :root {
                --beam-scheme: ${vars.scheme};
                --beam-app-bg: ${vars.appBg};
                --beam-surface: ${vars.surface};
                --beam-surface-alt: ${vars.surfaceAlt};
                --beam-border: ${vars.border};
                --beam-text: ${vars.text};
                --beam-muted-text: ${vars.mutedText};
                --beam-accent: ${vars.accent};
                --beam-accent-soft: ${vars.accentSoft};
                --beam-on-accent: ${vars.onAccent};
              }
              html, body {
                color-scheme: ${vars.scheme};
              }
            `;

            if (parentWindow.__beamThemeSyncCss === cssText) {
              return;
            }

            let styleTag = parentDoc.getElementById("beam-theme-sync");
            if (!styleTag) {
              styleTag = parentDoc.createElement("style");
              styleTag.id = "beam-theme-sync";
              parentDoc.head.appendChild(styleTag);
            }

            styleTag.textContent = cssText;
            parentDoc.documentElement.setAttribute("data-beam-scheme", vars.scheme);
            if (parentDoc.body) {
              parentDoc.body.setAttribute("data-beam-scheme", vars.scheme);
            }
            parentWindow.__beamThemeSyncCss = cssText;
          }

          function scheduleSync() {
            if (parentWindow.__beamThemeSyncScheduled) {
              return;
            }
            parentWindow.__beamThemeSyncScheduled = true;
            parentWindow.requestAnimationFrame(() => {
              parentWindow.__beamThemeSyncScheduled = false;
              syncThemeVars();
            });
          }

          if (parentWindow.__beamThemeSyncVersion !== syncVersion) {
            parentWindow.__beamThemeSyncVersion = syncVersion;

            if (parentWindow.__beamThemeSyncIntervalId) {
              parentWindow.clearInterval(parentWindow.__beamThemeSyncIntervalId);
            }
            parentWindow.__beamThemeSyncIntervalId = parentWindow.setInterval(scheduleSync, 700);

            if (parentWindow.__beamThemeSyncObserver) {
              parentWindow.__beamThemeSyncObserver.disconnect();
            }

            const observerTargets = [
              parentDoc.documentElement,
              parentDoc.head,
              parentDoc.body,
              parentDoc.querySelector("[data-testid='stAppViewContainer']"),
              parentDoc.querySelector("section[data-testid='stMain']"),
            ].filter(Boolean);

            const observer = new MutationObserver(() => {
              scheduleSync();
            });

            observerTargets.forEach((target) => {
              observer.observe(target, {
                attributes: true,
                attributeFilter: ["class", "style", "data-theme"],
                childList: true,
                subtree: true,
              });
            });

            parentWindow.__beamThemeSyncObserver = observer;
            parentWindow.addEventListener("focus", scheduleSync, true);
            parentDoc.addEventListener("visibilitychange", scheduleSync, true);
            parentWindow.addEventListener("pageshow", scheduleSync, true);

            if (parentWindow.matchMedia) {
              const colorSchemeQuery = parentWindow.matchMedia("(prefers-color-scheme: dark)");
              if (colorSchemeQuery.addEventListener) {
                colorSchemeQuery.addEventListener("change", scheduleSync);
              } else if (colorSchemeQuery.addListener) {
                colorSchemeQuery.addListener(scheduleSync);
              }
            }
          }

          scheduleSync();
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def apply_theme(theme_name: str | None = None) -> ThemePalette:
    _render_theme_sync_bridge()
    palette = CLIENT_THEME
    st.markdown(
        f"""
        <style>
        :root {{
{_theme_vars_block(palette=palette)}
        }}
        html,
        body,
        div[data-testid="stAppViewContainer"],
        section[data-testid="stMain"],
        div[data-testid="stMainBlockContainer"] {{
            background-color: var(--app-bg) !important;
            color: var(--text) !important;
            color-scheme: var(--beam-scheme) !important;
        }}
        .stApp {{
            color-scheme: var(--beam-scheme) !important;
            background-color: transparent;
            background-image:
                radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 10%, transparent), transparent 24%),
                radial-gradient(circle at top left, color-mix(in srgb, var(--accent-soft) 70%, transparent), transparent 28%);
        }}
        .stApp,
        .stApp p,
        .stApp label,
        .stApp span,
        .stApp div,
        .stApp td,
        .stApp th,
        .stApp li,
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6,
        .stMarkdown,
        .stCaption,
        .stAlert,
        .stRadio,
        .stSelectbox,
        .stNumberInput,
        .stTextInput,
        .stTextArea,
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary *,
        div[data-testid="stDataFrame"] *,
        div[data-testid="stTable"] *,
        div[data-testid="stWidgetLabel"] *,
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] *,
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] *,
        div[data-baseweb="select"] span,
        div[role="radiogroup"] *,
        button[kind] *,
        textarea,
        input,
        select {{
            color: var(--text) !important;
        }}
        input::placeholder,
        textarea::placeholder {{
            color: var(--muted-text) !important;
            opacity: 0.78 !important;
        }}
        div[data-baseweb="base-input"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="input"] input,
        textarea,
        div[data-baseweb="select"] > div {{
            background: var(--surface) !important;
            border-color: var(--border) !important;
            color: var(--text) !important;
        }}
        div[data-baseweb="base-input"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea {{
            border: 1px solid var(--border) !important;
            border-radius: 14px !important;
            box-shadow: none !important;
        }}
        div[data-baseweb="input"] input,
        textarea {{
            caret-color: var(--accent) !important;
        }}
        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"] {{
            background: var(--surface) !important;
            color: var(--text) !important;
            border: 1px solid var(--border) !important;
            border-radius: 14px !important;
            box-shadow: var(--shadow) !important;
        }}
        li[role="option"],
        div[role="option"] {{
            background: transparent !important;
            color: var(--text) !important;
        }}
        li[role="option"][aria-selected="true"],
        div[role="option"][aria-selected="true"] {{
            background: var(--accent-soft) !important;
        }}
        .block-container {{
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }}
        header[data-testid="stHeader"] {{
            background: var(--topbar-bg) !important;
            border-bottom: 1px solid var(--topbar-border) !important;
        }}
        header[data-testid="stHeader"] *,
        div[data-testid="stToolbar"] *,
        div[data-testid="stToolbar"] button,
        div[data-testid="stToolbar"] span,
        div[data-testid="stToolbar"] a {{
            color: var(--topbar-text) !important;
        }}
        div[data-testid="stToolbar"] {{
            background: transparent !important;
        }}
        div[data-testid="stToolbar"] button,
        div[data-testid="stToolbar"] a {{
            background: color-mix(in srgb, var(--topbar-bg) 94%, white) !important;
            border: 1px solid var(--topbar-border) !important;
            border-radius: 12px !important;
        }}
        div[data-testid="stToolbar"] button:hover,
        div[data-testid="stToolbar"] a:hover {{
            background: color-mix(in srgb, var(--accent-soft) 70%, var(--topbar-bg)) !important;
            border-color: var(--border) !important;
        }}
        .app-shell {{
            background: linear-gradient(145deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 1rem 1.1rem;
            box-shadow: var(--shadow);
        }}
        .panel-card, .report-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 1rem 1.05rem;
            box-shadow: var(--shadow);
        }}
        .report-card {{
            margin-bottom: 1rem;
        }}
        .hero-title {{
            font-size: 1.85rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            color: var(--text);
        }}
        .hero-subtitle {{
            color: var(--muted-text);
            font-size: 0.95rem;
            margin-top: 0.15rem;
        }}
        .header-strip {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            padding: 0.75rem 0.95rem;
            margin-bottom: 0.8rem;
            border-radius: 16px;
            background: linear-gradient(135deg, var(--header-surface), var(--accent-soft));
            color: var(--header-text);
            border: 1px solid var(--border);
            box-shadow: 0 8px 20px rgba(18, 32, 51, 0.04);
        }}
        .header-strip *,
        .header-strip .hero-title,
        .header-strip .hero-subtitle,
        .header-strip .section-label {{
            color: var(--header-text) !important;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 0.3rem 0.65rem;
            border-radius: 999px;
            border: 1px solid var(--border);
            background: var(--surface-alt);
            color: var(--text);
            font-size: 0.78rem;
            font-weight: 600;
            margin-right: 0.35rem;
        }}
        .status-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.35rem 0.8rem;
            font-size: 0.8rem;
            font-weight: 700;
            border: 1px solid transparent;
        }}
        .metric-card {{
            background: linear-gradient(160deg, var(--surface), var(--surface-alt));
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 0.85rem 0.95rem;
            margin-bottom: 0.75rem;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
            min-height: 8.5rem;
        }}
        .summary-group-card {{
            background: linear-gradient(160deg, var(--surface), var(--surface-alt));
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 0.95rem 1rem 0.35rem 1rem;
            margin: 0.35rem 0 0.85rem 0;
        }}
        .summary-group-title {{
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 800;
            margin-bottom: 0.7rem;
        }}
        .overall-status-card {{
            border-radius: 20px;
            padding: 1rem 1.05rem;
            margin: 0.35rem 0 0.9rem 0;
            border: 1px solid transparent;
        }}
        .overall-status-label {{
            font-size: 0.8rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.92;
        }}
        .overall-status-value {{
            font-size: 1.45rem;
            font-weight: 800;
            margin-top: 0.18rem;
        }}
        .overall-status-note {{
            font-size: 0.86rem;
            line-height: 1.45;
            margin-top: 0.28rem;
            max-width: 60ch;
        }}
        .metric-label {{
            color: var(--muted-text);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .metric-value {{
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text);
            margin-top: 0.2rem;
        }}
        .metric-note {{
            color: var(--muted-text);
            font-size: 0.78rem;
            margin-top: auto;
            padding-top: 0.35rem;
            min-height: 2.25rem;
        }}
        .rebar-detail-card {{
            padding-top: 0.75rem;
            padding-bottom: 0.75rem;
        }}
        .rebar-detail-row {{
            display: grid;
            grid-template-columns: 7.4rem 1fr;
            gap: 0.35rem;
            align-items: start;
            padding: 0.18rem 0;
        }}
        .rebar-detail-row + .rebar-detail-row {{
            border-top: 1px solid var(--border);
            margin-top: 0.22rem;
            padding-top: 0.42rem;
        }}
        .rebar-detail-value {{
            color: var(--text);
            font-size: 0.92rem;
            font-weight: 600;
        }}
        .rebar-detail-line {{
            line-height: 1.35;
        }}
        .section-label {{
            color: var(--text);
            font-weight: 700;
            font-size: 1rem;
            margin-bottom: 0.5rem;
        }}
        .input-field-label {{
            color: var(--text);
            font-size: 0.82rem;
            font-weight: 600;
            margin: 0 0 0.2rem 0;
        }}
        .field-helper {{
            color: var(--muted-text);
            font-size: 0.78rem;
            line-height: 1.25;
            min-height: 1.15rem;
            margin-top: 0.2rem;
        }}
        .field-helper.blank {{
            visibility: hidden;
        }}
        .layer-inline-warning {{
            color: var(--fail);
            font-size: 0.82rem;
            font-weight: 700;
            margin: 0.2rem 0 0.35rem 0;
        }}
        .workspace-panel .layer-inline-warning,
        .workspace-panel .layer-inline-warning * {{
            color: var(--fail) !important;
        }}
        .design-banner {{
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.55rem 0.75rem;
            margin: 0 0 0.7rem 0;
            font-size: 0.84rem;
            line-height: 1.4;
        }}
        .design-banner.fail {{
            border-color: color-mix(in srgb, var(--fail) 38%, var(--border));
            background: color-mix(in srgb, var(--fail) 10%, var(--surface));
            color: var(--fail);
            font-weight: 700;
        }}
        .design-banner.info {{
            border-color: color-mix(in srgb, var(--accent) 38%, var(--border));
            background: color-mix(in srgb, var(--accent-soft) 65%, var(--surface));
            color: var(--text);
        }}
        .panel-card svg {{
            width: 100%;
            max-width: 280px;
            height: auto;
            display: block;
            margin: 0 auto 0.65rem auto;
        }}
        .small-note {{
            color: var(--muted-text);
            font-size: 0.82rem;
        }}
        .workspace-panel,
        .workspace-panel p,
        .workspace-panel label,
        .workspace-panel span,
        .workspace-panel div,
        .workspace-panel .small-note,
        .workspace-panel .section-label,
        .workspace-panel .hero-subtitle,
        .workspace-panel .stCaption {{
            color: var(--text) !important;
        }}
        .workspace-panel [data-testid="stCaptionContainer"] {{
            color: var(--text) !important;
            opacity: 0.92;
        }}
        .workspace-panel .metric-note,
        .workspace-panel .metric-label {{
            color: var(--text) !important;
            opacity: 0.94;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stForm"] {{
            background: linear-gradient(160deg, var(--surface), var(--surface-alt)) !important;
            border: 1px solid var(--border) !important;
            border-radius: 18px !important;
            box-shadow: var(--shadow) !important;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"] > div,
        div[data-testid="stForm"] > div {{
            background: transparent !important;
        }}
        div[data-testid="stAlert"] {{
            background: color-mix(in srgb, var(--surface) 88%, var(--surface-alt)) !important;
            border: 1px solid var(--border) !important;
            color: var(--text) !important;
            border-radius: 16px !important;
        }}
        section[data-testid="stSidebar"] {{
            background: var(--sidebar-surface) !important;
            border-right: 1px solid var(--border);
        }}
        section[data-testid="stSidebar"] *,
        div[data-testid="stSidebarNav"] *,
        div[data-testid="stSidebarNav"] a,
        div[data-testid="stSidebarNav"] span {{
            color: var(--text) !important;
        }}
        div[data-testid="stSidebarNav"] {{
            padding-top: 0.35rem;
        }}
        div[data-testid="stSidebarNav"] ul {{
            gap: 0.2rem;
        }}
        div[data-testid="stSidebarNav"] a {{
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 12px !important;
            margin-bottom: 0.15rem;
            transition: background 120ms ease, border-color 120ms ease;
        }}
        div[data-testid="stSidebarNav"] a:hover {{
            background: var(--sidebar-hover-bg) !important;
            border-color: var(--border) !important;
        }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: var(--sidebar-active-bg) !important;
            border-color: var(--border) !important;
            color: var(--sidebar-active-text) !important;
            font-weight: 700 !important;
        }}
        div[data-testid="stSidebarNav"] a[aria-current="page"] *,
        div[data-testid="stSidebarNav"] a[aria-current="page"] span {{
            color: var(--sidebar-active-text) !important;
        }}
        div[data-testid="stMetric"] {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 0.65rem 0.75rem;
        }}
        div[data-testid="stButton"] > button {{
            width: 100%;
            min-height: 2.55rem;
            border-radius: 14px;
            border: 1px solid var(--border) !important;
            background: linear-gradient(135deg, var(--accent-soft), var(--surface)) !important;
            color: var(--text) !important;
            font-weight: 700 !important;
            box-shadow: none !important;
        }}
        div[data-testid="stButton"] > button:hover {{
            background: linear-gradient(135deg, var(--accent-soft), var(--surface-alt)) !important;
            border-color: var(--accent) !important;
            color: var(--text) !important;
        }}
        div[data-testid="stButton"] > button:focus,
        div[data-testid="stButton"] > button:focus-visible {{
            color: var(--text) !important;
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 0.18rem var(--accent-soft) !important;
            outline: none !important;
        }}
        div[data-testid="stButton"] > button * {{
            color: var(--text) !important;
        }}
        div[data-baseweb="tab-list"] {{
            gap: 0.35rem;
            background: transparent !important;
        }}
        button[data-baseweb="tab"] {{
            background: var(--tab-idle-bg) !important;
            border: 1px solid var(--border) !important;
            border-radius: 14px 14px 0 0 !important;
            color: var(--text) !important;
        }}
        button[data-baseweb="tab"] *,
        button[data-baseweb="tab"] span {{
            color: inherit !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{
            background: var(--tab-active-bg) !important;
            border-color: var(--tab-active-border) !important;
            color: var(--tab-active-text) !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] *,
        button[data-baseweb="tab"][aria-selected="true"] span {{
            color: var(--tab-active-text) !important;
        }}
        div[data-testid="stRadio"] div[role="radiogroup"] {{
            gap: 0.35rem;
        }}
        div[data-testid="stRadio"] div[role="radiogroup"] label {{
            background: color-mix(in srgb, var(--surface) 84%, var(--surface-alt)) !important;
            border: 1px solid var(--border) !important;
            border-radius: 12px !important;
            padding: 0.3rem 0.55rem !important;
        }}
        div[data-testid="stExpander"] {{
            border: 1px solid var(--border);
            border-radius: 16px;
            background: rgba(255,255,255,0.02);
            overflow: hidden;
        }}
        div[data-testid="stExpander"] summary {{
            background: var(--surface-alt);
            color: var(--text) !important;
            padding: 0.35rem 0.5rem;
            border-radius: 14px;
        }}
        div[data-testid="stExpander"] summary:hover {{
            background: var(--accent-soft);
        }}
        div[data-testid="stExpanderDetails"] {{
            background: var(--surface) !important;
            color: var(--text) !important;
            padding: 0.4rem 0.75rem 0.75rem 0.75rem;
        }}
        .print-button {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 2.5rem;
            width: 100%;
            border-radius: 14px;
            border: 1px solid var(--border);
            background: linear-gradient(135deg, var(--accent), var(--accent-soft));
            color: var(--print-button-text);
            font-weight: 700;
            font-size: 0.9rem;
            cursor: pointer;
            text-decoration: none;
        }}
        .print-sheet {{
            background: var(--surface);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: var(--shadow);
            padding: 10mm;
            margin-bottom: 1rem;
        }}
        .print-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8mm;
        }}
        .print-block {{
            break-inside: avoid;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 3.5mm;
            background: var(--surface);
        }}
        .print-title {{
            font-size: 18px;
            font-weight: 800;
            margin-bottom: 2mm;
        }}
        .print-subtitle {{
            font-size: 11px;
            color: var(--muted-text);
            margin-bottom: 4mm;
        }}
        .print-section-title {{
            font-size: 11px;
            font-weight: 800;
            margin-bottom: 2mm;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .print-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 9px;
            line-height: 1.25;
        }}
        .print-table th,
        .print-table td {{
            border: 1px solid var(--border);
            padding: 1.6mm 1.8mm;
            vertical-align: top;
            text-align: left;
        }}
        .print-table th {{
            background: var(--surface-alt);
            font-weight: 700;
        }}
        .print-hero {{
            display: grid;
            grid-template-columns: 1.3fr 0.7fr;
            gap: 6mm;
            margin-bottom: 6mm;
            align-items: start;
        }}
        .print-meta {{
            display: flex;
            gap: 2mm;
            flex-wrap: wrap;
            margin-top: 1.5mm;
        }}
        .print-meta span {{
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 1mm 2.5mm;
            font-size: 9px;
            background: var(--surface-alt);
        }}
        .screen-only {{
            display: block;
        }}
        .print-svg-box {{
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 42mm;
            background: var(--surface-alt);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 2mm;
        }}
        @page {{
            size: A4 portrait;
            margin: 8mm;
        }}
        @media print {{
            .stApp {{
                background: #ffffff !important;
            }}
            .print-sheet {{
                box-shadow: none !important;
                border: none !important;
                margin: 0 !important;
                padding: 0 !important;
            }}
            .print-button,
            .screen-only,
            header[data-testid="stHeader"],
            div[data-testid="stToolbar"],
            div[data-testid="stDecoration"],
            div[data-testid="stStatusWidget"],
            div[data-testid="stSidebar"],
            div[data-testid="collapsedControl"] {{
                display: none !important;
            }}
            .block-container {{
                padding: 0 !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    return palette


def status_badge_html(status: str, palette: ThemePalette) -> str:
    normalized = status.upper()
    if normalized in {"PASS", "OK"}:
        color = "var(--ok)"
        background = "var(--ok-soft)"
    elif "FAIL" in normalized or "NOT OK" in normalized:
        color = "var(--fail)"
        background = "var(--fail-soft)"
    else:
        color = "var(--warning)"
        background = "var(--warning-soft)"
    return (
        f"<span class='status-badge' style='color:{color};background:{background};"
        f"border-color:color-mix(in srgb, {color} 32%, transparent);'>"
        f"{status}</span>"
    )


def status_text_html(status: str, palette: ThemePalette) -> str:
    normalized = status.upper()
    if normalized in {"PASS", "OK"}:
        color = "var(--ok)"
    elif "FAIL" in normalized or "NOT OK" in normalized:
        color = "var(--fail)"
    else:
        color = "var(--warning)"
    return f"<span style='color:{color};font-weight:700;'>{status}</span>"


def capacity_ratio_html(ratio: float | None) -> str:
    if ratio is None:
        return "<span style='font-weight:700;'>N/A</span>"
    if ratio <= 0.50:
        background = "#16dce7"
        color = "#0b1b21"
    elif ratio <= 0.70:
        background = "#25f000"
        color = "#091607"
    elif ratio <= 0.90:
        background = "#fff200"
        color = "#231f00"
    elif ratio <= 1.00:
        background = "#ff00ff"
        color = "#ffffff"
    else:
        background = "#ff1f1f"
        color = "#ffffff"
    return (
        f"<span style='display:inline-block;min-width:4.6rem;padding:0.16rem 0.5rem;border-radius:999px;"
        f"background:{background};color:{color};font-weight:800;text-align:center;'>{ratio:.4f}</span>"
    )


def capacity_ratio_legend_html() -> str:
    bands = [
        ("#16dce7", "#0b1b21", "0.00-0.50", "Low utilization"),
        ("#25f000", "#091607", "0.50-0.70", "Efficient range"),
        ("#fff200", "#231f00", "0.70-0.90", "High utilization"),
        ("#ff00ff", "#ffffff", "0.90-1.00", "Near capacity"),
        ("#ff1f1f", "#ffffff", "> 1.00", "Over capacity"),
    ]
    items = "".join(
        f"<div style='display:flex;align-items:center;gap:0.45rem;'>"
        f"<span style='display:inline-block;min-width:4.8rem;padding:0.14rem 0.45rem;border-radius:999px;"
        f"background:{background};color:{text};font-weight:800;text-align:center;'>{band}</span>"
        f"<span>{meaning}</span></div>"
        for background, text, band, meaning in bands
    )
    return (
        "<div class='metric-card' style='margin-top:0.2rem'>"
        "<div class='metric-label'>Capacity Ratio Color Guide</div>"
        "<div style='display:grid;grid-template-columns:1fr;gap:0.4rem;margin-top:0.55rem;font-size:0.82rem;'>"
        f"{items}</div></div>"
    )


def overall_status_card_html(status: str, note: str, palette: ThemePalette) -> str:
    normalized = status.upper()
    if normalized in {"PASS", "OK"}:
        color = "var(--ok)"
        background = "var(--ok-soft)"
    elif "FAIL" in normalized or "NOT OK" in normalized:
        color = "var(--fail)"
        background = "var(--fail-soft)"
    else:
        color = "var(--warning)"
        background = "var(--warning-soft)"
    note_html = f"<div class='overall-status-note'>{note}</div>" if note else ""
    return (
        f"<div class='overall-status-card' style='background:{background};"
        f"border-color:color-mix(in srgb, {color} 40%, transparent);color:{color};'>"
        "<div class='overall-status-label'>Overall</div>"
        f"<div class='overall-status-value'>{status}</div>"
        f"{note_html}"
        "</div>"
    )
