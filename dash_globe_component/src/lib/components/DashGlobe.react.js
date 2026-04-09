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
        // Use health-based color from Python if available, fall back to status color
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

        // Prefer explicit zoom prop; fall back to altitude conversion for backwards compat
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
