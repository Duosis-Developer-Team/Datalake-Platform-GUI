# Global View — Full Implementation Reference for Mock Dashboard

> This document contains every component, callback, CSS rule, custom Dash component,
> and API contract needed to replicate the **Global View** page's **UI structure** in a mock dashboard.
>
> **ÖNEMLİ:** Mock dashboard'un kendi mock data altyapısı zaten mevcut. Bu dokümandaki API kontratları
> (§10) sadece **format referansı** içindir — production verilerini kopyalamak veya yeni mock data
> oluşturmak için DEĞİL. Executor, mock dashboard'un mevcut data katmanını keşfedip onu kullanmalıdır.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Inventory](#2-file-inventory)
3. [DashGlobe Custom Component (MapLibre)](#3-dashglobe-custom-component-maplibre)
4. [Page Layout — `global_view.py`](#4-page-layout--global_viewpy)
5. [Floor Map Sub-Page — `floor_map.py`](#5-floor-map-sub-page--floor_mappy)
6. [Region Drilldown Stub — `region_drilldown.py`](#6-region-drilldown-stub--region_drilldownpy)
7. [App-Level Callbacks (app.py)](#7-app-level-callbacks-apppy)
8. [Sidebar Navigation Entry](#8-sidebar-navigation-entry)
9. [CSS — Complete Rules](#9-css--complete-rules)
10. [API Contracts (Data Shapes)](#10-api-contracts-data-shapes)
11. [Client-side JS (PDF Export)](#11-client-side-js-pdf-export)
12. [Stores & Intervals Used](#12-stores--intervals-used)
13. [Dependencies & Packages](#13-dependencies--packages)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ /global-view  (route)                                          │
│                                                                 │
│  ┌──────────────────┐   ┌─────────────────────────────────────┐│
│  │  Region Menu      │   │  DashGlobe (MapLibre 2D map)       ││
│  │  (Accordion)      │   │  pointsData → colored pin markers  ││
│  │  Europe / Turkey  │   │  clickedPoint → fires callback     ││
│  │  Asia & CIS       │   │  focusRegion → flyTo animation     ││
│  └──────┬───────────┘   └──────────┬──────────────────────────┘│
│         │                           │                           │
│         ▼                           ▼                           │
│  ┌──────────────────────────────────────────────────────────────┤
│  │  global-detail-panel                                        │
│  │  → Region detail panel (multi-DC cards with RingProgress)   │
│  │  → DC Info Card (single pin click)                          │
│  └─────────────────────────┬───────────────────────────────────┤
│                             │ double-click same pin             │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────────────┤
│  │  Building Reveal Layer → animated emoji building icon       │
│  │  → 1800ms timer → Floor Map Layout (Plotly rack grid)       │
│  └──────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────────┤
│  │  3D Hologram Modal (hologram-scene overlay)                 │
│  │  → triggered by "Detail" button on DC info card             │
│  └──────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### View Mode State Machine

```
globe  ──(double-click pin)──▶  building  ──(1800ms timer)──▶  floor_map
                                                                  │
  ◀────────────────(back-to-global-btn click)─────────────────────┘
```

---

## 2. File Inventory

| File | Role |
|------|------|
| `src/pages/global_view.py` | Main page layout + helper functions (1236 lines) |
| `src/pages/floor_map.py` | Floor map rack layout sub-page (513 lines) |
| `src/pages/region_drilldown.py` | Placeholder/stub page (39 lines) |
| `src/components/sidebar.py` | Sidebar with "Global View" nav link |
| `app.py` | 11 callbacks for global view interactions |
| `assets/style.css` | All CSS for global view, floor map, hologram, map pins |
| `assets/export_pdf.js` | Client-side PDF export via html2canvas + jsPDF |
| `dash_globe_component/` | Custom Dash component wrapping MapLibre GL map |

---

## 3. DashGlobe Custom Component (MapLibre)

### 3.1 Package Structure

```
dash_globe_component/
├── package.json           # npm deps: maplibre-gl ^5.22.0, react ^18.2.0
├── webpack.config.js      # Bundles to dash_globe_component.min.js
├── setup.py               # Python package installer
├── src/
│   └── lib/
│       ├── index.js       # export { default as DashGlobe } from './components/DashGlobe.react';
│       └── components/
│           └── DashGlobe.react.js  # React component (179 lines)
└── dash_globe_component/
    ├── __init__.py         # _js_dist loader
    ├── DashGlobe.py        # Python component class
    ├── dash_globe_component.min.js  # Compiled bundle (~1.1MB)
    └── package-info.json
```

### 3.2 React Component — `DashGlobe.react.js`

```javascript
import React, { useRef, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

const STATUS_COLOR = {
    active:   '#17B26A',
    planned:  '#2E90FA',
    inactive: '#F04438',
    unknown:  '#98A2B3',
};

const DashGlobe = ({ id, setProps, pointsData, focusRegion, height }) => {
    const containerRef  = useRef();
    const mapRef        = useRef();
    const markersRef    = useRef([]);
    const popupRef      = useRef(null);
    const hideTimerRef  = useRef(null);

    useEffect(() => {
        const map = new maplibregl.Map({
            container: containerRef.current,
            style: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
            center: [30.0, 38.0],
            zoom: 3,
            minZoom: 1.5,
            maxZoom: 18,
            attributionControl: false,
            pitchWithRotate: false,
            dragRotate: false,
        });

        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
        map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

        mapRef.current = map;

        return () => map.remove();
    }, []);

    const buildMarker = useCallback((d) => {
        const status = (d.status || 'unknown').toLowerCase();
        const color  = d.color || STATUS_COLOR[status] || STATUS_COLOR.unknown;

        const el = document.createElement('div');
        el.className  = 'dc-map-pin';
        el.title      = d.site_name || d.dc_id || '';

        el.innerHTML = `
            <div class="dc-pin-pulse" style="--pin-color:${color}"></div>
            <div class="dc-pin-dot" style="background:${color};box-shadow:0 0 0 2.5px #fff,0 2px 8px ${color}88"></div>
        `;

        // Hover popup
        el.addEventListener('mouseenter', () => {
            const map = mapRef.current;
            if (!map) return;
            if (hideTimerRef.current) { clearTimeout(hideTimerRef.current); hideTimerRef.current = null; }
            if (popupRef.current) { popupRef.current.remove(); popupRef.current = null; }

            const statusLabel = status.charAt(0).toUpperCase() + status.slice(1);
            const vmCount   = d.vm_count   != null ? d.vm_count   : '—';
            const hostCount = d.host_count != null ? d.host_count : '—';
            const health    = d.health     != null ? `${Math.round(d.health)}%` : '—';

            popupRef.current = new maplibregl.Popup({
                closeButton: false,
                closeOnClick: false,
                offset: [0, -14],
                className: 'dc-premium-popup',
                maxWidth: '240px',
            })
            .setLngLat([d.lng, d.lat])
            .setHTML(`
                <div class="dc-popup-inner">
                    <div class="dc-popup-header">
                        <span class="dc-popup-id">${d.dc_id || ''}</span>
                        <span class="dc-popup-status-dot" style="background:${color}"></span>
                        <span class="dc-popup-status-label">${statusLabel}</span>
                    </div>
                    <div class="dc-popup-name">${d.site_name || ''}</div>
                    <div class="dc-popup-stats">
                        <div class="dc-popup-stat-item">
                            <span class="dc-stat-label">VMs</span>
                            <span class="dc-stat-value">${vmCount}</span>
                        </div>
                        <div class="dc-popup-stat-item">
                            <span class="dc-stat-label">Hosts</span>
                            <span class="dc-stat-value">${hostCount}</span>
                        </div>
                        <div class="dc-popup-stat-item">
                            <span class="dc-stat-label">Avg Load</span>
                            <span class="dc-stat-value">${health}</span>
                        </div>
                    </div>
                </div>
            `)
            .addTo(map);
        });

        el.addEventListener('mouseleave', () => {
            hideTimerRef.current = setTimeout(() => {
                if (popupRef.current) { popupRef.current.remove(); popupRef.current = null; }
                hideTimerRef.current = null;
            }, 120);
        });

        // Click: report to Dash + fly in close
        el.addEventListener('click', () => {
            if (popupRef.current) { popupRef.current.remove(); popupRef.current = null; }
            if (setProps) setProps({ clickedPoint: { ...d, _ts: Date.now() } });

            const map = mapRef.current;
            if (!map) return;
            map.flyTo({ center: [d.lng, d.lat], zoom: 13, speed: 1.4, curve: 1.2 });
        });

        return el;
    }, [setProps]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !pointsData) return;

        markersRef.current.forEach(m => m.remove());
        markersRef.current = [];

        pointsData.forEach(d => {
            if (d.lat == null || d.lng == null) return;
            const el     = buildMarker(d);
            const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
                .setLngLat([d.lng, d.lat])
                .addTo(map);
            markersRef.current.push(marker);
        });
    }, [pointsData, buildMarker]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !focusRegion) return;

        const zoom = focusRegion.zoom != null
            ? focusRegion.zoom
            : focusRegion.altitude != null
            ? Math.max(1.5, Math.round(14 - focusRegion.altitude * 6))
            : 8;

        map.flyTo({ center: [focusRegion.lng, focusRegion.lat], zoom, speed: 1.6, curve: 1.2 });
    }, [focusRegion]);

    return (
        <div
            id={id}
            ref={containerRef}
            style={{ width: '100%', height: height || 600, borderRadius: 'inherit' }}
        />
    );
};

DashGlobe.defaultProps = {
    pointsData:  [],
    focusRegion: null,
    clickedPoint: null,
    height: 600,
};

DashGlobe.propTypes = {
    id:           PropTypes.string,
    setProps:     PropTypes.func,
    pointsData:   PropTypes.array,
    focusRegion:  PropTypes.object,
    clickedPoint: PropTypes.object,
    height:       PropTypes.number,
};

export default DashGlobe;
```

### 3.3 Python Wrapper — `DashGlobe.py`

```python
import dash
from dash.development.base_component import Component, _explicitize_args


class DashGlobe(Component):
    _children_props = []
    _base_nodes = ['children']
    _namespace = 'dash_globe_component'
    _type = 'DashGlobe'

    @_explicitize_args
    def __init__(self, id=Component.UNDEFINED, pointsData=Component.UNDEFINED,
                 focusRegion=Component.UNDEFINED, clickedPoint=Component.UNDEFINED,
                 globeImageUrl=Component.UNDEFINED, width=Component.UNDEFINED,
                 height=Component.UNDEFINED, **kwargs):
        self._prop_names = ['id', 'pointsData', 'focusRegion', 'clickedPoint',
                            'globeImageUrl', 'width', 'height']
        self._valid_wildcard_attributes = []
        self.available_properties = self._prop_names
        self.available_wildcard_properties = []
        _explicit_args = kwargs.pop('_explicit_args')
        _locals = locals()
        _locals.update(kwargs)
        args = {k: _locals[k] for k in _explicit_args}
        super(DashGlobe, self).__init__(**args)
```

### 3.4 `__init__.py`

```python
import os as _os
import sys as _sys
import json

_basepath = _os.path.dirname(__file__)
_filepath = _os.path.abspath(_os.path.join(_basepath, 'package-info.json'))

if _os.path.exists(_filepath):
    with open(_filepath) as _f:
        package = json.load(_f)
    __version__ = package['version']
else:
    __version__ = '0.1.0'

_js_dist = [
    {
        'relative_package_path': 'dash_globe_component.min.js',
        'external_url': None,
        'namespace': 'dash_globe_component'
    }
]

_css_dist = []

from .DashGlobe import DashGlobe
```

### 3.5 `package.json`

```json
{
  "name": "dash_globe_component",
  "version": "0.1.0",
  "description": "A Dash component for Globe.gl",
  "main": "dash_globe_component/dash_globe_component.min.js",
  "scripts": {
    "build": "webpack --mode production",
    "build:dev": "webpack --mode development"
  },
  "dependencies": {
    "css-loader": "^7.1.4",
    "maplibre-gl": "^5.22.0",
    "prop-types": "^15.8.1",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-globe.gl": "^2.27.2",
    "style-loader": "^4.0.0"
  },
  "devDependencies": {
    "@babel/core": "^7.23.0",
    "@babel/preset-env": "^7.23.0",
    "@babel/preset-react": "^7.22.15",
    "babel-loader": "^9.1.3",
    "webpack": "^5.89.0",
    "webpack-cli": "^5.1.4"
  }
}
```

### 3.6 `webpack.config.js`

```javascript
const path = require('path');

module.exports = {
    entry: './src/lib/index.js',
    output: {
        path: path.resolve(__dirname, 'dash_globe_component'),
        filename: 'dash_globe_component.min.js',
        library: 'dash_globe_component',
        libraryTarget: 'window',
    },
    resolve: {
        extensions: ['.js', '.jsx'],
    },
    module: {
        rules: [
            {
                test: /\.jsx?$/,
                exclude: /node_modules/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env', '@babel/preset-react'],
                    },
                },
            },
            {
                test: /\.css$/,
                use: ['style-loader', 'css-loader'],
            },
        ],
    },
    externals: {
        react: 'React',
        'react-dom': 'ReactDOM',
    },
    mode: 'production',
};
```

### 3.7 `setup.py`

```python
from setuptools import setup, find_packages

setup(
    name='dash_globe_component',
    version='0.1.0',
    author='',
    packages=find_packages(),
    include_package_data=True,
    license='MIT',
    description='A Globe.gl component for Dash',
    install_requires=['dash'],
    package_data={
        'dash_globe_component': ['*.js', '*.map', '*.json'],
    },
)
```

---

## 4. Page Layout — `global_view.py`

### 4.1 Constants & Coordinate Maps

```python
CITY_COORDINATES = {
    "ISTANBUL":    {"lat": 41.01, "lon": 28.96},
    "ANKARA":      {"lat": 39.93, "lon": 32.85},
    "IZMIR":       {"lat": 38.42, "lon": 27.13},
    "AZERBAYCAN":  {"lat": 40.41, "lon": 49.87},
    "ALMANYA":     {"lat": 50.11, "lon": 8.68},
    "INGILTERE":   {"lat": 51.51, "lon": -0.13},
    "OZBEKISTAN":  {"lat": 41.30, "lon": 69.24},
    "HOLLANDA":    {"lat": 52.37, "lon": 4.90},
    "FRANSA":      {"lat": 48.85, "lon": 2.35},
}

DC_COORDINATES = {
    "DC11":      {"lat": 41.037961428839395,  "lon": 28.932597596324076},
    "DC13":      {"lat": 40.99624339876133,   "lon": 29.171462274232628},
    "DC15":      {"lat": 41.07269534784402,   "lon": 28.657853053455625},
    "DC17":      {"lat": 41.10716190578305,   "lon": 28.80144412392166},
    "DC12":      {"lat": 38.32499698249641,   "lon": 27.14179605187827},
    "DC14":      {"lat": 39.79603052359003,   "lon": 32.422135925099674},
    "DC16":      {"lat": 39.78445603075798,   "lon": 32.813705565035825},
    "AZ11":      {"lat": 40.38073354513049,   "lon": 49.8333150827992},
    "ICT11":     {"lat": 50.144014412507744,  "lon": 8.739884781472139},
    "ICT21":     {"lat": 51.528941788230235,  "lon": 0.27753550495317736},
    "Vadi Ofis": {"lat": 41.112041365157516,  "lon": 28.987566791632712},
}

REGION_HIERARCHY = {
    "Europe": {
        "icon": "solar:earth-bold-duotone",
        "children": {
            "ALMANYA":   {"label": "Germany",         "flag": "twemoji:flag-germany"},
            "INGILTERE": {"label": "United Kingdom",  "flag": "twemoji:flag-united-kingdom"},
            "HOLLANDA":  {"label": "Netherlands",     "flag": "twemoji:flag-netherlands"},
            "FRANSA":    {"label": "France",          "flag": "twemoji:flag-france"},
        },
    },
    "Turkey Region": {
        "icon": "twemoji:flag-turkey",
        "children": {
            "ISTANBUL": {"label": "Istanbul"},
            "ANKARA":   {"label": "Ankara"},
            "IZMIR":    {"label": "Izmir"},
        },
    },
    "Asia & CIS": {
        "icon": "solar:earth-bold-duotone",
        "children": {
            "AZERBAYCAN": {"label": "Azerbaijan", "flag": "twemoji:flag-azerbaijan"},
            "OZBEKISTAN": {"label": "Uzbekistan",  "flag": "twemoji:flag-uzbekistan"},
        },
    },
}

REGION_ZOOM_TARGETS = {
    "ISTANBUL":   {"lon": 28.96,  "lat": 41.01, "scale": 33.0},
    "ANKARA":     {"lon": 32.85,  "lat": 39.93, "scale": 15.0},
    "IZMIR":      {"lon": 27.13,  "lat": 38.42, "scale": 15.0},
    "AZERBAYCAN": {"lon": 49.87,  "lat": 40.41, "scale": 6.0},
    "ALMANYA":    {"lon": 8.68,   "lat": 50.11, "scale": 6.0},
    "INGILTERE":  {"lon": -0.13,  "lat": 51.51, "scale": 6.0},
    "OZBEKISTAN": {"lon": 69.24,  "lat": 41.30, "scale": 6.0},
    "HOLLANDA":   {"lon": 4.90,   "lat": 52.37, "scale": 6.0},
    "FRANSA":     {"lon": 2.35,   "lat": 48.85, "scale": 6.0},
}

_CITY_OFFSETS = [
    (0.00,  0.00), (1.50,  0.00), (-1.50,  0.00),
    (0.00,  1.50), (0.00, -1.50), ( 1.50,  1.50),
    (-1.50, 1.50), (1.50, -1.50),
]
```

### 4.2 Imports

```python
import math
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import dash_globe_component
from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.utils.export_helpers import (
    records_to_dataframe,
    dataframes_to_excel_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
    build_report_info_df,
)
```

### 4.3 `_build_globe_data(summaries)` — Prepare pin data for DashGlobe

```python
def _build_globe_data(summaries):
    city_index: dict[str, int] = {}
    data = []
    for dc in summaries:
        dc_id = dc.get("id", "")
        site_name = (dc.get("site_name") or "").upper().strip()
        exact = DC_COORDINATES.get(dc_id)
        if exact:
            lat = exact["lat"]
            lng = exact["lon"]
        else:
            base = CITY_COORDINATES.get(site_name)
            if not base:
                continue
            idx = city_index.get(site_name, 0)
            city_index[site_name] = idx + 1
            dlat, dlon = _CITY_OFFSETS[idx % len(_CITY_OFFSETS)]
            lat = base["lat"] + dlat
            lng = base["lon"] + dlon
        stats = dc.get("stats", {})
        cpu_pct = stats.get("used_cpu_pct", 0.0)
        ram_pct = stats.get("used_ram_pct", 0.0)
        health = (cpu_pct + ram_pct) / 2.0
        color = "#F04438" if health >= 70 else ("#F79009" if health >= 40 else "#17B26A")
        capacity = max(dc.get("vm_count", 0) or 0, (dc.get("host_count", 0) or 0) * 5)
        size = round(min(0.07, max(0.015, 0.015 + math.sqrt(capacity) * 0.0012)), 4)
        data.append({
            "lat": float(lat),
            "lng": float(lng),
            "dc_id": dc_id,
            "size": size,
            "color": color,
            "site_name": dc.get("site_name", ""),
            "status": (dc.get("status") or "active").lower(),
            "vm_count": dc.get("vm_count", 0) or 0,
            "host_count": dc.get("host_count", 0) or 0,
            "health": round(health, 1),
        })
    return data
```

### 4.4 `_health_colors(health_value)` — Color palette for health indicators

```python
def _health_colors(health_value):
    if health_value >= 70:
        return {
            "pin": "#E85347",
            "pin_rgba": "rgba(232, 83, 71, 0.95)",
            "halo": "rgba(232, 83, 71, 0.18)",
            "shadow": "rgba(120, 30, 20, 0.35)",
            "gradient": "rgba(255, 180, 170, 0.90)",
        }
    if health_value >= 40:
        return {
            "pin": "#FFB547",
            "pin_rgba": "rgba(255, 181, 71, 0.95)",
            "halo": "rgba(255, 181, 71, 0.18)",
            "shadow": "rgba(140, 100, 20, 0.35)",
            "gradient": "rgba(255, 230, 180, 0.90)",
        }
    return {
        "pin": "#05CD99",
        "pin_rgba": "rgba(5, 205, 153, 0.95)",
        "halo": "rgba(5, 205, 153, 0.18)",
        "shadow": "rgba(2, 90, 60, 0.35)",
        "gradient": "rgba(150, 245, 220, 0.90)",
    }
```

### 4.5 `_pct_color(v)` — Color helper for ring progress

```python
def _pct_color(v):
    if v >= 80:
        return "red"
    if v >= 50:
        return "orange"
    return "teal"
```

### 4.6 `_create_map_figure(df)` — Plotly Scattergeo figure (fallback, not actively used with DashGlobe)

This function creates a Plotly orthographic globe with 3 layers (shadow, halo, pin) using `go.Scattergeo`. It is present in the code as a reference/fallback but the primary map is rendered by the DashGlobe MapLibre component.

Full function length: ~190 lines (lines 303-494 in global_view.py).

### 4.7 `_build_region_menu(summaries)` — Region accordion sidebar

```python
def _build_region_menu(summaries):
    region_dc_counts = {}
    region_health = {}
    for dc in summaries:
        sn = (dc.get("site_name") or "").upper().strip()
        region_dc_counts[sn] = region_dc_counts.get(sn, 0) + 1
        stats = dc.get("stats", {})
        cpu = stats.get("used_cpu_pct", 0.0)
        ram = stats.get("used_ram_pct", 0.0)
        region_health.setdefault(sn, []).append((cpu + ram) / 2.0)
    avg_health = {k: sum(v) / len(v) for k, v in region_health.items() if v}

    items = []
    for group_name, group_data in REGION_HIERARCHY.items():
        children_components = []
        group_total = 0
        for site_key, site_data in group_data["children"].items():
            count = region_dc_counts.get(site_key, 0)
            group_total += count
            flag_icon = site_data.get("flag")
            left_section = DashIconify(icon=flag_icon, width=18) if flag_icon else None
            avg = avg_health.get(site_key, 0)
            children_components.append(
                dmc.NavLink(
                    id={"type": "region-nav", "region": site_key},
                    label=site_data["label"],
                    description=f"Avg Load: {avg:.0f}%",
                    leftSection=left_section,
                    rightSection=dmc.Badge(
                        f"{count} DC{'s' if count != 1 else ''}",
                        size="xs",
                        variant="light",
                        color="indigo" if count > 0 else "gray",
                    ),
                    className="region-nav-link",
                )
            )
        items.append(
            dmc.AccordionItem(
                value=group_name,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="sm",
                            children=[
                                DashIconify(icon=group_data["icon"], width=20, color="#4318FF"),
                                dmc.Text(group_name, fw=700, size="sm", c="#2B3674"),
                                dmc.Badge(f"{group_total} DCs", variant="light", color="gray", size="xs"),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(p="xs", children=children_components),
                ],
            )
        )

    return dmc.Accordion(
        id="region-accordion",
        variant="separated",
        radius="md",
        chevronPosition="right",
        multiple=True,
        value=[],
        className="region-accordion",
        style={"width": "100%"},
        children=items,
    )
```

### 4.8 `build_region_detail_panel(region, tr)` — Region detail cards (multi-DC)

This function:
1. Fetches all DC summaries, filters by region
2. Uses `ThreadPoolExecutor` to fetch `get_dc_details` for each DC in parallel
3. Builds cards with `dmc.RingProgress` gauges (CPU, RAM, Storage)
4. Shows host count, VM count, energy kW for each DC
5. Shows architecture text (VMware/Nutanix/IBM breakdown)
6. Has "Detail" button with `{"type": "open-3d-hologram-btn", "index": dc_id}` pattern-matching ID

Full function: lines 574-756 in `global_view.py` (see Section 4 source code)

### 4.9 `build_global_view(time_range)` — Main page builder

Creates the full page layout with:
- **Stores**: `selected-region-store`, `global-export-store`, `current-view-mode`, `selected-building-dc-store`, `last-clicked-dc-id`
- **Download**: `global-export-download`
- **Timer**: `building-reveal-timer` (1800ms, max_intervals=1)
- **Header**: Glass-effect paper with gradient title, time range badge, export buttons (CSV/Excel/PDF), active DC count badge
- **Grid (8/4)**:
  - Left (span=8): Map paper with Reset button + DashGlobe component
  - Right (span=4): Region menu panel with scroll area
- **Detail panel**: `global-detail-panel` with empty state placeholder
- **3D Modal**: `global-3d-modal-container` (fixed overlay, initially hidden)
- **Building reveal layer**: Emoji building icon + animated dots
- **Floor map layer**: Empty div, populated by callback

Full function: lines 759-1061 in `global_view.py`

### 4.10 `build_dc_info_card(dc_id, tr, site_name)` — Single DC info panel (on pin click)

Shows:
- DC name + location with ThemeIcon
- Health badge
- 4-column grid: CPU/RAM/Storage RingProgress gauges + host/VM/kW stats
- Architecture text
- "Detail" button

Full function: lines 1064-1200 in `global_view.py`

### 4.11 `build_3d_rack_overlay(dc_id, dc_name, racks)` — 3D Hologram modal content

Creates a cyberpunk-styled overlay with:
- Dark gradient background with perspective transforms
- Halls grouped from racks data
- Animated rack micro-cards with status indicators
- Close button and "Racks Details" link
- CSS classes: `hologram-scene`, `dc-hologram-base`, `hall-layer`, `rack-micro-grid`, `rack-micro-card`

Full function: lines 22-133 in `global_view.py`

### 4.12 `_global_export_table(summaries)` — Export data formatter

```python
def _global_export_table(summaries: list) -> list[dict]:
    rows: list[dict] = []
    for dc in summaries or []:
        if not isinstance(dc, dict):
            continue
        stats = dc.get("stats") or {}
        site = dc.get("site_name", "")
        rows.append(
            {
                "DC_ID": dc.get("id", ""),
                "Site_Name": site,
                "Location": dc.get("location", ""),
                "Region": site or dc.get("location", ""),
                "Hosts": dc.get("host_count", 0),
                "VMs": dc.get("vm_count", 0),
                "Clusters": dc.get("cluster_count", 0),
                "Platforms": dc.get("platform_count", 0),
                "CPU_Used_pct": stats.get("used_cpu_pct", ""),
                "RAM_Used_pct": stats.get("used_ram_pct", ""),
                "Total_Energy_kW": stats.get("total_energy_kw", ""),
                "IBM_Energy_kW": stats.get("ibm_kw", ""),
            }
        )
    return rows
```

### 4.13 Export callback (inside `global_view.py`)

```python
@callback(
    Output("global-export-download", "data"),
    Input("global-export-csv", "n_clicks"),
    Input("global-export-xlsx", "n_clicks"),
    State("global-export-store", "data"),
    State("app-time-range", "data"),
    State("selected-region-store", "data"),
    prevent_initial_call=True,
)
def export_global_view(nc, nx, store, time_range, selected_region):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]["prop_id"].split(".")[0]
    fmt_map = {"global-export-csv": "csv", "global-export-xlsx": "xlsx"}
    fmt = fmt_map.get(tid)
    if not fmt:
        return dash.no_update
    store = store or {}
    rows = store.get("rows") or []
    df = records_to_dataframe(rows)
    extra = {}
    if selected_region is not None:
        extra["map_selected_region"] = selected_region
    sheets = {"DC_Summary": df}
    if fmt == "xlsx":
        content = dataframes_to_excel_with_meta(sheets, time_range, "Global_View", extra or None)
        return dash_send_excel_workbook(content, "global_view")
    report_info = build_report_info_df(time_range, "Global_View", extra or None)
    return dash_send_csv_bytes(
        csv_bytes_with_report_header(report_info, [("DC_Summary", df)]),
        "global_view",
    )
```

---

## 5. Floor Map Sub-Page — `floor_map.py`

### 5.1 Overview

The floor map is a Plotly-based 2D top-down view of data center rack positions. It renders a building floor with multiple hall zones, each containing racks in a grid pattern with aisles.

### 5.2 Key Constants

```python
RACK_W = 22
RACK_H = 34
GAP_X  = 8
GAP_Y  = 10
AISLE_H = 30
ZONE_PAD_X   = 22
ZONE_PAD_TOP = 14
ZONE_PAD_BOT = 14
ZONE_LABEL_H = 24
FLOOR_PAD = 28
HALL_COL_GAP = 0
HALL_ROW_GAP = 0
HALLS_PER_ROW = 2
STATUS_FILL   = {"active": "#17B26A", "planned": "#2E90FA", "inactive": "#F04438", "unknown": "#98A2B3"}
STATUS_DARK   = {"active": "#027A48", "planned": "#175CD3", "inactive": "#B42318", "unknown": "#667085"}
```

### 5.3 Key Functions

- `_parse_row_col(identifier)` — Parse facility IDs like "A1", "B2" into row/col indices
- `_hall_dimensions(hall_racks)` — Calculate zone dimensions for a hall
- `_draw_rack(fig, rx, ry, status, name, rack_data, dc_id)` — Draw a single rack shape (shadow, body, gloss, LED, hover trace)
- `_draw_hall_zone(fig, hx, hy, hall_name, dims, dc_id)` — Draw one hall zone with label, racks, aisle
- `build_floor_map_figure(racks, dc_id)` — Main figure builder with multi-hall grid layout
- `build_floor_map_layout(dc_id, dc_name, racks)` — Full page layout with header, canvas, legend, detail panel

### 5.4 Layout Structure

```
┌──────────────────────────────────────────────────────┐
│ Header: [← Back] DC Name  | status badges | hall badges │
├──────────────────────────────────────────────────────┤
│ Grid (8/4):                                          │
│  Left (8): Plotly Graph (floor plan) + legend        │
│  Right (4): Rack detail panel (click to inspect)     │
└──────────────────────────────────────────────────────┘
```

Full source: 513 lines — `src/pages/floor_map.py`

---

## 6. Region Drilldown Stub — `region_drilldown.py`

```python
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html, dcc


def build_region_drilldown(region, time_range=None):
    return html.Div(
        dmc.Paper(
            p="xl",
            radius="lg",
            style={
                "textAlign": "center",
                "marginTop": "80px",
                "background": "rgba(255,255,255,0.90)",
                "boxShadow": "0 8px 32px rgba(67,24,255,0.10)",
            },
            children=[
                DashIconify(icon="solar:lock-keyhole-bold-duotone", width=64, color="#A3AED0"),
                html.H3("Reserved", style={"color": "#2B3674", "marginTop": "16px"}),
                dmc.Text(
                    "This page is reserved for future hardware/rack data from loki_racks.",
                    c="#A3AED0",
                    size="sm",
                ),
                dcc.Link(
                    dmc.Button(
                        "Back to Global View",
                        variant="light",
                        color="indigo",
                        radius="md",
                        mt="lg",
                    ),
                    href="/global-view",
                    style={"textDecoration": "none"},
                ),
            ],
        ),
    )
```

---

## 7. App-Level Callbacks (app.py)

### 7.1 Route Handler (line 392-416)

```python
@app.callback(
    dash.Output("main-content", "children"),
    dash.Input("url", "pathname"),
    dash.Input("app-time-range", "data"),
    dash.Input("customer-select", "value"),
    dash.State("url", "search"),
)
def render_main_content(pathname, time_range, selected_customer, search):
    # ...
    if pathname == "/global-view":
        return global_view.build_global_view(tr)
    if pathname == "/region-drilldown":
        from urllib.parse import parse_qs
        params = parse_qs((search or "").lstrip("?"))
        region = params.get("region", [""])[0]
        return region_drilldown.build_region_drilldown(region, tr)
    # ...
```

### 7.2 Globe Pin Click → DC Info Card (line 617-642)

```python
@app.callback(
    dash.Output("global-detail-panel", "children"),
    dash.Output("last-clicked-dc-id", "data"),
    dash.Output("current-view-mode", "data", allow_duplicate=True),
    dash.Output("selected-building-dc-store", "data"),
    dash.Input("global-map-graph", "clickedPoint"),
    dash.State("last-clicked-dc-id", "data"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def handle_globe_pin_click(clicked_point, last_dc_id, time_range):
    if not clicked_point:
        return [], None, dash.no_update, dash.no_update
    dc_id = clicked_point.get("dc_id")
    site_name = clicked_point.get("site_name", "")
    if not dc_id:
        return [], None, dash.no_update, dash.no_update
    # Double-click same pin → building mode
    if dc_id == last_dc_id:
        return dash.no_update, dc_id, "building", {"dc_id": dc_id, "dc_name": dc_id}
    # First click → show info card
    tr = time_range or default_time_range()
    panel = build_dc_info_card(dc_id, tr, site_name=site_name)
    return panel, dc_id, dash.no_update, dash.no_update
```

### 7.3 3D Hologram Modal Open (line 645-685)

```python
@app.callback(
    dash.Output("global-3d-modal-container", "children"),
    dash.Output("global-3d-modal-container", "style"),
    dash.Input({"type": "open-3d-hologram-btn", "index": ALL}, "n_clicks"),
    dash.State("global-3d-modal-container", "style"),
    prevent_initial_call=True,
)
def open_3d_hologram_modal(btn_clicks, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update
    if all(x is None for x in btn_clicks):
        return dash.no_update, dash.no_update
    trig = ctx.triggered[0]["prop_id"].split(".")[0]
    try:
        trig_dict = json.loads(trig)
    except Exception:
        return dash.no_update, dash.no_update
    dc_id = trig_dict.get("index")
    if not dc_id:
        return dash.no_update, dash.no_update
    info = api.get_dc_details(dc_id, default_time_range())
    dc_name = info.get("meta", {}).get("name", dc_id)
    racks_resp = api.get_dc_racks(dc_id)
    racks = racks_resp.get("racks", [])
    if racks:
        content = build_3d_rack_overlay(dc_id, dc_name, racks)
        new_style = current_style.copy() if current_style else {}
        new_style["display"] = "flex"
        new_style["pointerEvents"] = "auto"
        return content, new_style
    return [], current_style
```

### 7.4 3D Hologram Modal Close (line 688-700)

```python
@app.callback(
    dash.Output("global-3d-modal-container", "style", allow_duplicate=True),
    dash.Input("close-3d-overlay-btn", "n_clicks"),
    dash.State("global-3d-modal-container", "style"),
    prevent_initial_call=True,
)
def close_3d_hologram_modal(n_clicks, current_style):
    if not n_clicks:
        return dash.no_update
    new_style = current_style.copy() if current_style else {}
    new_style["display"] = "none"
    new_style["pointerEvents"] = "none"
    return new_style
```

### 7.5 View Mode Controller (line 704-724)

```python
@app.callback(
    dash.Output("globe-layer", "style"),
    dash.Output("building-reveal-layer", "style"),
    dash.Output("floor-map-layer", "style"),
    dash.Output("building-reveal-timer", "disabled"),
    dash.Output("building-reveal-timer", "n_intervals"),
    dash.Output("building-reveal-dc-name", "children"),
    dash.Input("current-view-mode", "data"),
    dash.State("selected-building-dc-store", "data"),
)
def view_controller(mode, dc_store):
    shown = {"display": "block"}
    hidden = {"display": "none"}
    reveal_shown = {"display": "flex"}
    dc_label = (dc_store or {}).get("dc_name", "")
    if mode == "building":
        return hidden, reveal_shown, hidden, False, 0, dc_label
    if mode == "floor_map":
        return hidden, hidden, shown, True, dash.no_update, dc_label
    return shown, hidden, hidden, True, dash.no_update, dc_label
```

### 7.6 Building Timer → Floor Map (line 727-743)

```python
@app.callback(
    dash.Output("current-view-mode", "data", allow_duplicate=True),
    dash.Output("floor-map-layer", "children"),
    dash.Input("building-reveal-timer", "n_intervals"),
    dash.State("selected-building-dc-store", "data"),
    dash.State("current-view-mode", "data"),
    prevent_initial_call=True,
)
def advance_to_floor_map(n_intervals, dc_store, current_mode):
    if not n_intervals or current_mode != "building" or not dc_store:
        return dash.no_update, dash.no_update
    dc_id = dc_store.get("dc_id", "")
    dc_name = dc_store.get("dc_name", dc_id)
    racks_resp = api.get_dc_racks(dc_id)
    racks = racks_resp.get("racks", [])
    from src.pages.floor_map import build_floor_map_layout
    return "floor_map", build_floor_map_layout(dc_id, dc_name, racks)
```

### 7.7 Back to Globe (line 746-755)

```python
@app.callback(
    dash.Output("current-view-mode", "data", allow_duplicate=True),
    dash.Output("last-clicked-dc-id", "data", allow_duplicate=True),
    dash.Input("back-to-global-btn", "n_clicks"),
    prevent_initial_call=True,
)
def back_to_globe(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return "globe", None
```

### 7.8 Floor Map Rack Detail Click (line 895-1002)

```python
@app.callback(
    dash.Output("floor-map-rack-detail", "children"),
    dash.Input("floor-map-graph", "clickData"),
    dash.State("selected-building-dc-store", "data"),
    prevent_initial_call=True,
)
def show_rack_detail(click_data, dc_store):
    # Fetches rack details, builds rack unit diagram (_build_rack_unit_diagram)
    # Shows: status bar, rack identity header, quick stats (U Height, Power),
    #        rack unit diagram with device slots and legend
```

Also uses `_build_rack_unit_diagram(rack_name, u_height, devices, fill, dark)` (line 758-879) and `_detail_row(icon, label, value)` (line 882-892).

### 7.9 Reset Global Detail (line 1005-1014)

```python
@app.callback(
    dash.Output("global-detail-panel", "children", allow_duplicate=True),
    dash.Output("global-map-graph", "focusRegion", allow_duplicate=True),
    dash.Input("global-map-reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_global_detail(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return [], {"lat": 38.0, "lng": 30.0, "zoom": 3}
```

### 7.10 Region Menu Click → Store Update (line 1019-1045)

```python
@app.callback(
    dash.Output("selected-region-store", "data"),
    dash.Input({"type": "region-nav", "region": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_region_store(n_clicks_list):
    import time as _time
    import json
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    triggered = ctx.triggered[0]
    if not triggered.get("value"):
        return dash.no_update
    prop_id = json.loads(triggered["prop_id"].rsplit(".", 1)[0])
    region = prop_id.get("region", "")
    target = REGION_ZOOM_TARGETS.get(region, {})
    if not target:
        return dash.no_update
    return {
        "region": region,
        "lon": target["lon"],
        "lat": target["lat"],
        "scale": target["scale"],
        "ts": _time.time(),
    }
```

### 7.11 Region Store → Globe Camera (line 1050-1072)

```python
@app.callback(
    dash.Output("global-map-graph", "focusRegion"),
    dash.Input("selected-region-store", "data"),
    prevent_initial_call=True,
)
def update_globe_camera(region):
    if not region:
        return dash.no_update
    lat = region.get("lat")
    lng = region.get("lon")
    scale = region.get("scale", 6.0)
    if scale >= 35:
        zoom = 10
    elif scale >= 10:
        zoom = 8
    else:
        zoom = 5
    if lat is not None and lng is not None:
        return {"lat": float(lat), "lng": float(lng), "zoom": zoom}
    return dash.no_update
```

### 7.12 Region Store → Detail Panel (line 1075-1087)

```python
@app.callback(
    dash.Output("global-detail-panel", "children", allow_duplicate=True),
    dash.Input("selected-region-store", "data"),
    dash.State("app-time-range", "data"),
    prevent_initial_call=True,
)
def update_global_detail_from_menu(store_data, time_range):
    if not store_data or not store_data.get("region"):
        return dash.no_update
    region = store_data["region"]
    tr = time_range or default_time_range()
    return build_region_detail_panel(region, tr)
```

### 7.13 Client-side PDF Export (line 254-290)

```python
app.clientside_callback(
    """
    function(homePdf, dcListPdf, dcPdf, globalPdf, customerPdf, qePdf) {
        const triggered = dash_clientside.callback_context.triggered;
        if (!triggered || !triggered.length || !triggered[0]) {
            return window.dash_clientside.no_update;
        }
        const propId = triggered[0].prop_id || "";
        const id = propId.split(".")[0];
        const map = {
            "home-export-pdf": "home_overview",
            "datacenters-export-pdf": "datacenters",
            "dc-export-pdf": "dc_detail",
            "global-export-pdf": "global_view",
            "customer-export-pdf": "customer_view",
            "qe-export-pdf": "query_explorer"
        };
        const prefix = map[id];
        if (!prefix) {
            return window.dash_clientside.no_update;
        }
        const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        if (typeof window.triggerPagePDF === "function") {
            window.triggerPagePDF("main-content", prefix + "_" + ts + ".pdf");
        }
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("export-pdf-clientside-dummy", "children"),
    dash.Input("home-export-pdf", "n_clicks"),
    dash.Input("datacenters-export-pdf", "n_clicks"),
    dash.Input("dc-export-pdf", "n_clicks"),
    dash.Input("global-export-pdf", "n_clicks"),
    dash.Input("customer-export-pdf", "n_clicks"),
    dash.Input("qe-export-pdf", "n_clicks"),
    prevent_initial_call=True,
)
```

---

## 8. Sidebar Navigation Entry

In `src/components/sidebar.py`, the Global View link:

```python
dmc.NavLink(
    label="Global View",
    leftSection=DashIconify(icon="solar:global-bold-duotone", width=20),
    href="/global-view",
    className="sidebar-link",
    active=active_path == "/global-view",
    variant="subtle",
    color="indigo",
    style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
),
```

---

## 9. CSS — Complete Rules

All CSS rules relevant to Global View from `assets/style.css`:

### 9.1 Base Animations

```css
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}
```

### 9.2 Region Navigation Links

```css
.region-nav-link {
    border-radius: 8px !important;
    margin-bottom: 4px !important;
    transition: all 0.2s ease;
}

.region-nav-link:hover {
    background-color: rgba(67, 24, 255, 0.05) !important;
    padding-left: 20px !important;
}

.region-nav-link[data-active="true"] {
    background: linear-gradient(135deg, #4318FF 0%, #5630FF 100%) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0px 6px 16px rgba(67, 24, 255, 0.20) !important;
}
```

### 9.3 Detail Panel Animation

```css
.detail-panel-animate {
    animation: fadeInUp 0.35s ease-out;
}
```

### 9.4 Region Accordion

```css
.region-accordion {
    width: 100% !important;
}

.region-accordion .mantine-Accordion-item {
    width: 100% !important;
    box-sizing: border-box !important;
}

.region-accordion .mantine-Accordion-control {
    width: 100% !important;
    box-sizing: border-box !important;
}

.region-accordion .mantine-Accordion-control:hover {
    background-color: rgba(67, 24, 255, 0.03) !important;
}

.region-accordion .mantine-Accordion-content {
    padding: 4px 8px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
```

### 9.5 DC Detail Card

```css
.detail-dc-card {
    transition: transform 0.25s cubic-bezier(0.25, 0.8, 0.25, 1),
                box-shadow 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.detail-dc-card:hover {
    transform: translateY(-4px);
    box-shadow:
        0px 16px 40px rgba(67, 24, 255, 0.12),
        0px 6px 16px rgba(67, 24, 255, 0.06) !important;
}
```

### 9.6 3D Holographic Rack Overlay

```css
.hologram-scene {
    perspective: 1400px;
    pointer-events: auto;
    width: 650px;
    max-height: 560px;
    margin-top: 0;
}

.dc-hologram-base {
    transform-style: preserve-3d;
    background: linear-gradient(145deg, rgba(12, 18, 48, 0.95) 0%, rgba(35, 45, 95, 0.95) 100%);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(67, 24, 255, 0.5);
    box-shadow: 0 30px 60px rgba(0, 0, 0, 0.4), inset 0 0 40px rgba(67, 24, 255, 0.15);
    border-radius: 16px;
    padding: 28px;
    width: 100%;
    max-height: 540px;
    overflow-y: auto;
    -ms-overflow-style: none;
    scrollbar-width: none;
    animation: riseUpHologram 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    animation-delay: 0.5s;
    opacity: 0;
}

.dc-hologram-base::-webkit-scrollbar { display: none; }

.hologram-halls {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.hall-layer {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 10px;
    border-left: 4px solid #05CD99;
    padding: 16px;
    transform: translateZ(-150px) rotateX(-20deg);
    opacity: 0;
    animation: bladeSlideOut 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    animation-delay: calc(800ms + (var(--delay) * 180ms));
}

.hall-title {
    color: #FFF;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}

.rack-micro-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 12px;
}

.rack-micro-card {
    background: rgba(255, 255, 255, 0.95);
    border-radius: 8px;
    padding: 10px;
    border: 1px solid rgba(67, 24, 255, 0.15);
    transform: translateZ(50px) translateY(20px) scale(0.7);
    opacity: 0;
    animation: rackCardPop 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    animation-delay: calc(1100ms + (var(--delay) * 180ms) + (var(--card-delay) * 60ms));
    transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
}

.rack-micro-card:hover {
    transform: translateY(-5px) scale(1.08) translateZ(40px) !important;
    box-shadow: 0 12px 28px rgba(67, 24, 255, 0.3);
    border-color: #4318FF;
    cursor: default;
}

@keyframes riseUpHologram {
    0% {
        opacity: 0;
        transform: rotateX(60deg) rotateY(-15deg) translateY(200px) scale(0.7);
    }
    100% {
        opacity: 1;
        transform: rotateX(15deg) rotateY(-5deg) translateY(0) scale(1);
    }
}

@keyframes bladeSlideOut {
    0% {
        opacity: 0;
        transform: translateZ(-200px) translateY(50px) rotateX(-30deg);
    }
    100% {
        opacity: 1;
        transform: translateZ(0) translateY(0) rotateX(0deg);
    }
}

@keyframes rackCardPop {
    0% {
        opacity: 0;
        transform: translateZ(60px) translateY(30px) scale(0.5);
    }
    100% {
        opacity: 1;
        transform: translateZ(0) translateY(0) scale(1);
    }
}
```

### 9.7 Building Reveal Layer

```css
#building-reveal-layer {
    width: 100%;
    min-height: 600px;
    align-items: center;
    justify-content: center;
    background: #F8F9FC;
    border-radius: 20px;
}

.building-reveal-inner {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
    animation: buildingEnter 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.building-reveal-icon {
    filter: drop-shadow(0 20px 48px rgba(0, 0, 0, 0.14)) drop-shadow(0 4px 12px rgba(0, 0, 0, 0.08));
    animation: buildingFloat 1.8s ease-in-out infinite;
}

@keyframes buildingEnter {
    0%   { opacity: 0; transform: scale(0.7) translateY(32px); }
    60%  { opacity: 1; transform: scale(1.04) translateY(-4px); }
    100% { opacity: 1; transform: scale(1.0) translateY(0); }
}

@keyframes buildingFloat {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-10px); }
}

.building-reveal-name {
    font-size: 22px;
    font-weight: 700;
    color: #101828;
    letter-spacing: 0.02em;
    font-family: 'DM Sans', sans-serif;
    animation: fadeUp 0.5s 0.25s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}

.building-reveal-dots {
    display: flex;
    gap: 8px;
    align-items: center;
    animation: fadeUp 0.5s 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.brd-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #D0D5DD;
    display: inline-block;
    animation: dotPulse 1.2s ease-in-out infinite;
}

.brd-dot:nth-child(2) { animation-delay: 0.2s; }
.brd-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes dotPulse {
    0%, 80%, 100% { background: #D0D5DD; transform: scale(1); }
    40%            { background: #4318FF; transform: scale(1.35); }
}
```

### 9.8 MapLibre DC Pins

```css
.dc-map-pin {
    position: relative;
    width: 16px;
    height: 16px;
    cursor: pointer;
}

.dc-pin-dot {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    transition: transform 0.15s ease;
}

.dc-map-pin:hover .dc-pin-dot {
    transform: scale(1.45);
}

.dc-pin-pulse {
    position: absolute;
    inset: -6px;
    border-radius: 50%;
    border: 2px solid var(--pin-color, #17B26A);
    opacity: 0;
    animation: pinPulse 2.4s ease-out infinite;
}

@keyframes pinPulse {
    0%   { transform: scale(0.6); opacity: 0.7; }
    100% { transform: scale(2.2); opacity: 0; }
}
```

### 9.9 MapLibre Controls Override

```css
.maplibregl-ctrl-group {
    border-radius: 10px !important;
    box-shadow: 0 2px 8px rgba(16,24,40,0.10) !important;
    border: 1px solid #EAECF0 !important;
    overflow: hidden;
}
.maplibregl-ctrl-group button {
    width: 32px !important;
    height: 32px !important;
}
.maplibregl-ctrl-attrib {
    font-size: 10px !important;
    background: rgba(255,255,255,0.75) !important;
    border-radius: 6px !important;
}
```

### 9.10 MapLibre Premium DC Popup

```css
.dc-premium-popup,
.dc-premium-popup .maplibregl-popup-content {
    padding: 0;
    background: transparent;
    box-shadow: none;
    border-radius: 14px;
    pointer-events: none !important;
}

.dc-premium-popup .maplibregl-popup-tip {
    display: none;
}

.dc-popup-inner {
    background: rgba(255, 255, 255, 0.97);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(67, 24, 255, 0.10);
    border-radius: 14px;
    padding: 13px 15px 12px;
    min-width: 185px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.13), 0 2px 8px rgba(67, 24, 255, 0.08);
    pointer-events: none;
}

.dc-popup-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 5px;
}

.dc-popup-id {
    font-size: 10px;
    font-weight: 700;
    color: #4318FF;
    background: rgba(67, 24, 255, 0.08);
    padding: 2px 8px;
    border-radius: 20px;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}

.dc-popup-status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-left: 2px;
}

.dc-popup-status-label {
    font-size: 10px;
    color: #A3AED0;
    font-weight: 600;
    margin-left: auto;
}

.dc-popup-name {
    font-size: 13px;
    font-weight: 700;
    color: #1B2559;
    margin-bottom: 10px;
    line-height: 1.3;
}

.dc-popup-stats {
    display: flex;
    gap: 14px;
    padding-top: 9px;
    border-top: 1px solid rgba(67, 24, 255, 0.07);
}

.dc-popup-stat-item {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
}

.dc-stat-label {
    font-size: 9px;
    font-weight: 600;
    color: #A3AED0;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

.dc-stat-value {
    font-size: 16px;
    font-weight: 800;
    color: #1B2559;
    line-height: 1.2;
}
```

### 9.11 Floor Map Page

```css
.floor-map-page {
    padding: 0 28px 36px;
    animation: floorMapEnter 0.45s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

@keyframes floorMapEnter {
    from { opacity: 0; transform: translateY(12px); }
    to   { opacity: 1; transform: translateY(0); }
}

.floor-map-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 22px 0 18px;
    border-bottom: 1px solid #EAECF0;
    margin-bottom: 4px;
}

.floor-map-canvas-wrap {
    background:
        radial-gradient(circle, rgba(152,162,179,0.35) 1px, transparent 1px),
        #F8F9FC !important;
    background-size: 20px 20px !important;
    border: 1px solid #E4E7EC !important;
    box-shadow:
        0 1px 3px rgba(16,24,40,0.06),
        0 4px 16px rgba(16,24,40,0.04) !important;
    overflow: hidden;
}

.floor-map-detail-panel {
    background: #FFFFFF !important;
    border: 1px solid #E4E7EC !important;
    box-shadow:
        0 1px 3px rgba(16,24,40,0.06),
        0 4px 16px rgba(16,24,40,0.04) !important;
    height: 600px;
    overflow-y: auto;
}

.floor-map-detail-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 60px 0;
}

.fm-empty-icon-wrap {
    width: 64px;
    height: 64px;
    border-radius: 16px;
    background: #F9FAFB;
    border: 1px solid #EAECF0;
    display: flex;
    align-items: center;
    justify-content: center;
}

.fm-status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}

.fm-dot-active   { background: #17B26A; }
.fm-dot-inactive { background: #F04438; }
.fm-dot-planned  { background: #2E90FA; }

.fm-legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    flex-shrink: 0;
}
.fm-swatch-active   { background: #17B26A; border: 1.5px solid #027A48; }
.fm-swatch-inactive { background: #F04438; border: 1.5px solid #B42318; }
.fm-swatch-planned  { background: #2E90FA; border: 1.5px solid #175CD3; }
.fm-swatch-unknown  { background: #98A2B3; border: 1.5px solid #667085; }
```

### 9.12 Rack Unit Diagram

```css
.rack-unit-cabinet {
    display: flex;
    flex-direction: row;
    background: #1C2333;
    border-radius: 8px;
    border: 1.5px solid #2D3748;
    box-shadow:
        0 2px 8px rgba(0,0,0,0.18),
        inset 0 1px 0 rgba(255,255,255,0.05);
    overflow: hidden;
    max-height: 380px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #2D3748 transparent;
}

.rack-unit-cabinet::-webkit-scrollbar { width: 4px; }
.rack-unit-cabinet::-webkit-scrollbar-track { background: transparent; }
.rack-unit-cabinet::-webkit-scrollbar-thumb { background: #2D3748; border-radius: 4px; }

.rack-rail {
    width: 12px;
    flex-shrink: 0;
    background: repeating-linear-gradient(
        180deg,
        #2A3347 0px, #2A3347 20px,
        #232B3E 20px, #232B3E 22px
    );
    border-right: 1px solid #3A4459;
}
.rack-rail-right {
    border-right: none;
    border-left: 1px solid #3A4459;
}
```

---

## 10. API Contracts (Data Shapes) — SADECE FORMAT REFERANSI

> **NOT:** Bu bölüm production API'lerin döndüğü veri formatlarını gösterir.
> Mock dashboard'da yeni mock data oluşturmak için DEĞİL, mock dashboard'un
> mevcut data katmanındaki verilerin hangi alanlara sahip olması gerektiğini
> anlamak için kullanılmalıdır. Mock data'daki alan adları farklı olabilir;
> bu durumda küçük adapter/mapper fonksiyonları yazılabilir.

### 10.1 `GET /api/v1/datacenters/summary` → `list[dict]`

Each item in the returned list:

```json
{
  "id": "DC11",
  "site_name": "ISTANBUL",
  "location": "Istanbul, Turkey",
  "status": "active",
  "host_count": 120,
  "vm_count": 2500,
  "cluster_count": 8,
  "platform_count": 3,
  "stats": {
    "used_cpu_pct": 45.2,
    "used_ram_pct": 62.1,
    "total_energy_kw": 150.5,
    "ibm_kw": 30.2
  }
}
```

### 10.2 `GET /api/v1/datacenters/{dc_id}` → `dict`

```json
{
  "meta": {"name": "DC11 - Istanbul", "location": "Istanbul", "description": "..."},
  "intel": {
    "clusters": 5, "hosts": 80, "vms": 2000,
    "cpu_cap": 1000.0, "cpu_used": 450.0,
    "ram_cap": 8000.0, "ram_used": 5000.0,
    "storage_cap": 100000.0, "storage_used": 60000.0
  },
  "power": {
    "hosts": 10, "vms": 0, "vios": 2, "lpar_count": 50,
    "cpu": 64, "cpu_used": 30.0, "cpu_assigned": 45.0,
    "ram": 256, "memory_total": 256.0, "memory_assigned": 180.0,
    "storage_cap_tb": 50.0, "storage_used_tb": 30.0
  },
  "energy": {
    "total_kw": 150.5, "ibm_kw": 30.2, "vcenter_kw": 120.3,
    "total_kwh": 3612.0, "ibm_kwh": 724.8, "vcenter_kwh": 2887.2
  },
  "platforms": {
    "vmware": {"clusters": 5, "hosts": 80, "vms": 2000},
    "nutanix": {"hosts": 20, "vms": 500},
    "ibm": {"hosts": 10, "vios": 2, "lpars": 50}
  }
}
```

### 10.3 `GET /api/v1/datacenters/{dc_id}/racks` → `dict`

```json
{
  "racks": [
    {
      "id": "rack-uuid",
      "name": "A1",
      "hall_name": "Hall A",
      "u_height": 47,
      "kabin_enerji": "3x16A",
      "status": "active",
      "facility_id": "A1",
      "rack_type": "Standard",
      "serial": "SN123456"
    }
  ],
  "summary": {}
}
```

### 10.4 `GET /api/v1/datacenters/{dc_id}/racks/{rack_name}/devices` → `dict`

```json
{
  "devices": [
    {
      "name": "server-01",
      "device_type": "Server",
      "role": "Compute",
      "position": 1
    }
  ]
}
```

---

## 11. Client-side JS (PDF Export)

File: `assets/export_pdf.js`

Loads html2canvas + jsPDF from CDN and exports the `main-content` element as a multi-page A4 PDF. Triggered by the `global-export-pdf` button via clientside callback.

---

## 12. Stores & Intervals Used

| ID | Type | Purpose |
|----|------|---------|
| `selected-region-store` | `dcc.Store` | Currently selected region from menu |
| `global-export-store` | `dcc.Store` | Export data rows for CSV/Excel |
| `current-view-mode` | `dcc.Store` | `"globe"` / `"building"` / `"floor_map"` |
| `selected-building-dc-store` | `dcc.Store` | `{"dc_id": ..., "dc_name": ...}` for building/floor transitions |
| `last-clicked-dc-id` | `dcc.Store` | Tracks last pin click for double-click detection |
| `global-export-download` | `dcc.Download` | File download trigger |
| `building-reveal-timer` | `dcc.Interval` | 1800ms single-fire timer for building→floor transition |

---

## 13. Dependencies & Packages

### Python

```
dash
dash-mantine-components
dash-iconify
plotly
pandas
httpx
python-dotenv
dash_globe_component  (local package)
```

### npm (DashGlobe component)

```
maplibre-gl ^5.22.0
react ^18.2.0
react-dom ^18.2.0
prop-types ^15.8.1
css-loader ^7.1.4
style-loader ^4.0.0
webpack ^5.89.0
@babel/core ^7.23.0
@babel/preset-env ^7.23.0
@babel/preset-react ^7.22.15
```

### CDN (loaded at runtime)

```
Mantine Core CSS: https://unpkg.com/@mantine/core@7.10.0/styles.css
Mantine Dates CSS: https://unpkg.com/@mantine/dates@7.10.0/styles.css
Google Fonts (DM Sans): https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap
MapLibre Tile Style: https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json
html2canvas (PDF): https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js
jsPDF (PDF): https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js
```

---

> **Mock implementasyon notu:**
>
> 1. `dash_globe_component` paketini olduğu gibi kullan (dizini kopyala).
> 2. Mock dashboard'un **kendi mevcut data katmanını** keşfet ve onu kullan.
>    Production'daki `api_client` çağrılarını mock projenin kendi data fonksiyonlarıyla değiştir.
> 3. **Yeni mock data oluşturma**, production verisini kopyalama. Mock dashboard'un
>    halihazırda sahip olduğu veriler üzerinden yürü.
> 4. Mock data formatı ile §10'daki format arasında fark varsa, küçük adapter
>    fonksiyonları yazabilirsin — ama mock data'nın kendisini değiştirme.
> 5. Eğer mock data'da rack/device gibi veriler hiç yoksa, mock data yapısına
>    **uygun formatta** minimal sahte veri eklenebilir.
