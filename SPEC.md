# PROJECT SPECIFICATION: Duosis Dashboard (Final Version)

## 1. STRICT DEVELOPMENT RULES
- **NO NEW CSS FILES:** You are FORBIDDEN from creating new CSS. You MUST use the classes defined in `assets/style.css` (e.g., `nexus-card`, `nexus-glass`, `status-running`, `sidebar-link`).
- **NO NEW PYTHON FILES:** You must ONLY write code into the files defined in Section 2. Do not create `utils.py` or `config.py`.
- **BACKEND FIRST:** Data logic must be solid before UI is touched.

## 2. File Structure & Responsibilities
You are restricted to these exact files:
- `src/data/mock_data.py`: Handles ALL data generation (Faker).
- `src/components/sidebar.py`: Navigation component.
- `src/components/charts.py`: Reusable Plotly charts.
- `src/pages/home.py`: Overview Dashboard.
- `src/pages/datacenters.py`: List of Data Centers.
- `src/pages/dc_view.py`: Drill-down Level 1 (Clusters).
- `src/pages/cluster_view.py`: Drill-down Level 2 (Hosts).
- `app.py`: Main entry point.

## 3. Data Logic (Backend - Crucial)
In `src/data/mock_data.py`, create a class `MockService`.
- **Constraint:** Generate data in `__init__` so IDs do not change on refresh.
- **Hierarchy:**
    1.  **Data Center:** (Fields: `id`, `name`, `location`, `status='Healthy'`)
    2.  **Cluster:** (Fields: `id`, `dc_id`, `name`, `host_count`, `cpu_avg`, `ram_avg`)
    3.  **Host:** (Fields: `id`, `cluster_id`, `name`, `ip`, `cpu`, `ram`, `status='RUNNING'|'STOPPED'`)
- **Methods:**
    - `get_summary()`: Returns total hosts, active hosts, total revenue (fake).
    - `get_all_datacenters()`
    - `get_clusters_by_dc(dc_id)`
    - `get_hosts_by_cluster(cluster_id)`

## 4. Visual Rules (The "Nexus" Premium Look)
- **Cards:** Wrap every major block in `html.Div(className="nexus-card")`.
- **Headers:** Use `html.Div(className="nexus-glass")` for page titles.
- **Navigation:** Use `dmc.NavLink` with `className="sidebar-link"`.
- **Tables:** Use `dmc.Table` with `className="nexus-table"`.
- **Status Animation:**
    - If status is RUNNING -> `<div className="status-dot status-running"></div>`
    - If status is STOPPED -> `<div className="status-dot status-stopped"></div>`

## 5. Chart Rules (Plotly Graph Objects)
- **Library:** Use `plotly.graph_objects` ONLY (not express).
- **Style:**
    - `plot_bgcolor="rgba(0,0,0,0)"` (Transparent)
    - `paper_bgcolor="rgba(0,0,0,0)"` (Transparent)
    - `showgrid=False`, `zeroline=False`.
    - **Colors:** Gradient Fill (`fill='tozeroy'`). Color sequence: `#4318FF`, `#00DBE3`.

## 6. Drill-Down Navigation Flow
- **Home (`/`)**: Overview metrics.
- **Data Centers (`/datacenters`)**: List cards. Click -> `/datacenter/<id>`.
- **DC Detail (`/datacenter/<id>`)**: Show Clusters. Click -> `/cluster/<id>`.
- **Cluster Detail (`/cluster/<id>`)**: Show Host Table with status dots.