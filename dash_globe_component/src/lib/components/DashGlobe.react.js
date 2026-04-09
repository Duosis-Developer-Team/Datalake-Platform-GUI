import React, { useRef, useEffect, useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import Globe from 'react-globe.gl';
import * as THREE from 'three';

// We removed the 3D buldDCMesh entirely because native DOM elements give us perfect "icons".

const DashGlobe = (props) => {
    const { id, setProps, pointsData, focusRegion, globeImageUrl, height } = props;
    const globeRef = useRef();
    const containerRef = useRef();
    const [dims, setDims] = useState({ width: 800, height: height || 600 });
    const [tooltip, setTooltip] = useState(null);

    // Map dc_id → THREE.Group so we can scale on zoom
    const objectsMap = useRef(new Map());
    // Track current scale so newly created objects get the right size immediately
    const currentScaleRef = useRef(1.0);

    useEffect(() => {
        const update = () => {
            if (containerRef.current) {
                setDims({ width: containerRef.current.offsetWidth, height: height || 600 });
            }
        };
        update();
        const ro = new ResizeObserver(update);
        if (containerRef.current) ro.observe(containerRef.current);
        return () => ro.disconnect();
    }, [height]);

    useEffect(() => {
        if (globeRef.current) {
            const ctrl = globeRef.current.controls();
            ctrl.autoRotate = true;
            ctrl.autoRotateSpeed = 0.4;
            ctrl.enableZoom = true;
            ctrl.minDistance = 115;
            ctrl.maxDistance = 600;
            globeRef.current.pointOfView({ lat: 41.01, lng: 28.96, altitude: 1.8 }, 0);
        }
    }, []);

    useEffect(() => {
        if (focusRegion && globeRef.current) {
            const ctrl = globeRef.current.controls();
            ctrl.autoRotate = false;
            ctrl.minDistance = 115;
            globeRef.current.pointOfView({
                lat: focusRegion.lat,
                lng: focusRegion.lng,
                altitude: focusRegion.altitude || 0.8,
            }, 1200);
        }
    }, [focusRegion]);

    const htmlElementBuilder = useCallback((d) => {
        const outer = document.createElement('div');
        outer.style.pointerEvents = 'auto'; // allow clicking

        const el = document.createElement('div');
        el.className = 'dc-globe-visual-icon';
        
        // Shrunk max size to 32px to allow dense geographically accurate packing without ugly collision
        const sizePx = Math.max(8, Math.min(32, (d.size || 0.04) * 450)); 
        const color = d.color || '#ff4d4f';
        
        // Build the icon styling
        el.style.width = `${sizePx}px`;
        el.style.height = `${sizePx}px`;
        el.style.background = color;
        el.style.borderRadius = '50%';
        el.style.cursor = 'pointer';
        el.style.opacity = '0.9'; // Allows overlapping nodes to form denser visual clusters
        el.style.boxShadow = `0 0 ${sizePx/1.5}px ${sizePx/4}px ${color}88, inset 0 0 ${sizePx/3}px rgba(255,255,255,0.7)`;
        el.style.border = '1.5px solid rgba(255,255,255,0.95)';
        el.style.transition = 'transform 0.1s ease-out';
        
        outer.appendChild(el);

        // Event listeners
        outer.onclick = () => handleObjectClick(d);
        outer.onmouseenter = () => handleObjectHover(d);
        outer.onmouseleave = () => handleObjectHover(null);
        
        return outer;
    }, []);

    const handleZoom = useCallback(({ altitude }) => {
        // Scale isolated icons up dynamically when zoomed far in so they don't look tiny
        let s = 1.0;
        if (altitude < 0.8) {
            s = 1.0 + ((0.8 - altitude) * 2.2); 
        }

        const visualIcons = document.getElementsByClassName('dc-globe-visual-icon');
        for (let i = 0; i < visualIcons.length; i++) {
            visualIcons[i].style.transform = `scale(${s})`;
        }

        // Keeping this for tooltip refresh if needed
        setTooltip(prev => prev ? { ...prev, _tick: Date.now() } : null);
    }, []);

    const handleObjectClick = useCallback((d) => {
        if (setProps) setProps({ clickedPoint: { ...d, _ts: Date.now() } });
        if (globeRef.current) {
            const ctrl = globeRef.current.controls();
            ctrl.autoRotate = false;
            const isTurkey = d.lat >= 35.8 && d.lat <= 42.2 && d.lng >= 25.7 && d.lng <= 44.8;
            ctrl.minDistance = isTurkey ? 20 : 115;
            const alt = isTurkey ? 0.08 : 0.6;
            globeRef.current.pointOfView({ lat: d.lat, lng: d.lng, altitude: alt }, 900);
        }
        setTooltip(null);
    }, [setProps]);

    const handleObjectHover = useCallback((d) => {
        if (d && globeRef.current) {
            const { x, y } = globeRef.current.getScreenCoords(d.lat, d.lng, 0);
            setTooltip({ dc_id: d.dc_id, site_name: d.site_name, color: d.color, x, y });
        } else {
            setTooltip(null);
        }
    }, []);

    // Tooltip position clamped to container bounds
    const tooltipStyle = tooltip ? (() => {
        const W = dims.width;
        const tipW = 180;
        const tipH = 80;
        let left = (tooltip.x || 0) + 14;
        let top  = (tooltip.y || 0) - tipH - 14;
        if (left + tipW > W - 8) left = (tooltip.x || 0) - tipW - 14;
        if (top < 8) top = (tooltip.y || 0) + 14;
        return { left, top };
    })() : null;

    return (
        <div ref={containerRef} id={id} style={{ width: '100%', height: dims.height, overflow: 'hidden', position: 'relative' }}>
            {tooltip && tooltipStyle && (
                <div style={{
                    position: 'absolute',
                    left: tooltipStyle.left,
                    top: tooltipStyle.top,
                    background: '#ffffff',
                    color: '#1a2340',
                    padding: '9px 14px',
                    borderRadius: 8,
                    border: `1.5px solid ${tooltip.color}`,
                    fontSize: 13,
                    zIndex: 1000,
                    pointerEvents: 'none',
                    boxShadow: `0 2px 12px rgba(0,0,0,0.18), 0 0 0 3px ${tooltip.color}22`,
                    lineHeight: 1.5,
                    whiteSpace: 'nowrap',
                }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: tooltip.color, marginBottom: 2 }}>
                        {tooltip.site_name || tooltip.dc_id}
                    </div>
                    <div style={{ color: '#555e7a', fontSize: 12 }}>ID: {tooltip.dc_id}</div>
                    <div style={{ color: '#aab0c2', fontSize: 11, marginTop: 3 }}>Tıkla → Detay</div>
                </div>
            )}
            <Globe
                ref={globeRef}
                globeImageUrl={globeImageUrl || '//unpkg.com/three-globe/example/img/earth-blue-marble.jpg'}
                backgroundColor="rgba(255,255,255,0)"
                atmosphereColor="#c8d8f0"
                atmosphereAltitude={0.18}
                htmlElementsData={pointsData}
                htmlElement={htmlElementBuilder}
                htmlAltitude={0}
                htmlLat="lat"
                htmlLng="lng"
                onZoom={handleZoom}
                width={dims.width}
                height={dims.height}
            />
        </div>
    );
};

DashGlobe.defaultProps = {
    pointsData: [],
    focusRegion: null,
    clickedPoint: null,
    globeImageUrl: '//unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
    height: 600,
};

DashGlobe.propTypes = {
    id: PropTypes.string,
    setProps: PropTypes.func,
    pointsData: PropTypes.array,
    focusRegion: PropTypes.object,
    clickedPoint: PropTypes.object,
    globeImageUrl: PropTypes.string,
    height: PropTypes.number,
};

export default DashGlobe;
