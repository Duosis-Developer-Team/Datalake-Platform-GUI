# EXECUTION PROTOCOL: Wiring & Running (Duosis V3)

## 1. Objective
Ensure the application runs flawlessly without "Circular Import" errors, "Layout Missing" errors, or "Port Conflicts".

## 2. strict_app_structure.py (The Entry Point)
The `app.py` file must follow this EXACT structure to prevent circular imports:

1.  **Imports:**
    - `from dash import Dash, _dash_renderer, html, dcc, page_container`
    - `import dash_mantine_components as dmc`
    - `from src.components.sidebar import create_sidebar` (Import the function, not the layout directly)

2.  **Initialization:**
    - `_dash_renderer._set_react_version("18.2.0")` (Crucial for DMC 0.14)
    - `app = Dash(__name__, use_pages=True, pages_folder="src/pages", suppress_callback_exceptions=True)`
    - `server = app.server` (For Gunicorn deployment readiness)

3.  **Global Layout (The Shell):**
    - Wrap everything in `dmc.MantineProvider` (Theme: DM Sans).
    - Use a Grid or AppShell layout:
        - **Left:** Sidebar Component.
        - **Right:** `dash.page_container` (This is where pages render).
    - **CRITICAL:** Do NOT import specific pages into `app.py`. `use_pages=True` handles this automatically.

## 3. Page Registration Rules (Avoiding Conflicts)
In every page file (`src/pages/*.py`):
- **MUST:** Start with `dash.register_page(__name__, path='/...')`.
- **MUST NOT:** Import `app` from `app.py` inside the page file (causes Circular Import Loop).
- **MUST NOT:** Overwrite `app.layout`. Instead, define `layout = html.Div(...)` and assign it.

## 4. Package Initialization
Ensure empty `__init__.py` files exist in:
- `src/`
- `src/components/`
- `src/pages/`
- `src/data/`
*Reason:* Python needs these to treat folders as modules.

## 5. Execution Guard
At the end of `app.py`:
```python
if __name__ == "__main__":
    app.run(debug=True, port=8050)