import React, { useCallback, useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    Handle,
    Position,
    BaseEdge,
    getBezierPath,
    useNodesState,
    useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './HmdlFlow.css';

const PRIMARY = '#552cf8';
const SYNC_GREEN = '#17B26A';
const SYNC_RED = '#F04438';
const NO_PROXY = '#98A2B3';
const NODE_W = 152;
const NODE_H = 88;

function statusColor(node) {
    if (node.proxy_config_status === 'no_configured_proxy') return NO_PROXY;
    if (node.loki_sync_status === 'loki_synced') return SYNC_GREEN;
    return SYNC_RED;
}

function badgeLabel(node) {
    if (node.proxy_config_status === 'no_configured_proxy') return 'No configured proxy';
    if (node.loki_sync_status === 'loki_synced') return 'Loki synced';
    return 'Not synced';
}

function nodeId(dc) {
    return String(dc.dc_code || dc.location_name || `loc-${dc.location_id || ''}`);
}

function proxyLabel(proxyId) {
    const name = String(proxyId || '');
    if (name.includes('-NIFI')) {
        return name.replace(/-NIFI/i, ' NiFi');
    }
    return name;
}

function DcNode({ data }) {
    const color = statusColor(data.raw || {});
    const isHub = data.isHub;
    const expanded = data.expanded;
    return (
        <div
            className={`hmdl-node hmdl-node-dc${isHub ? ' hmdl-node-hub' : ''}${expanded ? ' hmdl-node-expanded' : ''}`}
            style={{ borderColor: color }}
        >
            {!isHub && <Handle type="source" position={Position.Bottom} id="out" />}
            {isHub && (
                <>
                    <Handle type="target" position={Position.Top} id="t" />
                    <Handle type="target" position={Position.Right} id="r" />
                    <Handle type="target" position={Position.Bottom} id="b" />
                    <Handle type="target" position={Position.Left} id="l" />
                </>
            )}
            {!isHub && <Handle type="target" position={Position.Top} id="in" />}
            <div className="hmdl-node-title">{data.label}</div>
            {!isHub && (
                <div className="hmdl-badge" style={{ background: `${color}22`, color }}>
                    {badgeLabel(data.raw || {})}
                </div>
            )}
            {isHub && <div className="hmdl-node-sub">Central collector hub</div>}
            {!isHub && data.proxyCount > 0 && (
                <div className="hmdl-node-sub">
                    {expanded ? 'Click to collapse' : `${data.proxyCount} NiFi · click to expand`}
                </div>
            )}
            {data.dcCode && data.onSyncHealth && (
                <button
                    type="button"
                    className="hmdl-sync-health-btn"
                    onClick={(e) => {
                        e.stopPropagation();
                        data.onSyncHealth(data.dcCode);
                    }}
                >
                    Sync Health
                </button>
            )}
        </div>
    );
}

function ProxyNode({ data }) {
    const synced = data.loki_sync_status === 'loki_synced';
    const color = synced ? SYNC_GREEN : SYNC_RED;
    return (
        <div className="hmdl-node hmdl-node-proxy" style={{ borderColor: color }}>
            <Handle type="source" position={Position.Bottom} id="out" />
            <div className="hmdl-node-title">{data.label}</div>
            <div className="hmdl-badge" style={{ background: `${color}22`, color }}>
                {synced ? 'Synced' : 'Not synced'}
            </div>
        </div>
    );
}

const nodeTypes = {
    dc: DcNode,
    proxy: ProxyNode,
};

function AnimatedEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }) {
    const [edgePath] = getBezierPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
    });
    const stroke = data?.stroke || PRIMARY;
    const animated = data?.animated !== false;
    return (
        <BaseEdge
            id={id}
            path={edgePath}
            style={{
                stroke,
                strokeWidth: 2,
                strokeDasharray: animated ? '8 6' : undefined,
                animation: animated ? 'hmdl-flow-dash 1.2s linear infinite' : undefined,
            }}
        />
    );
}

const edgeTypes = {
    animated: AnimatedEdge,
};

function layoutTopology(topology, hubDc, expandedDcs, onSyncHealth) {
    const nodes = [];
    const edges = [];
    if (!topology || typeof topology !== 'object') {
        return { nodes, edges };
    }

    const hub = String(hubDc || topology.hub_dc || 'DC13').toUpperCase();
    const dcNodes = topology.nodes || [];
    const cx = 520;
    const cy = 340;

    const hubData = dcNodes.find(
        (n) => n.role === 'hub' || (n.dc_code && String(n.dc_code).toUpperCase() === hub),
    );
    const spokes = dcNodes.filter((n) => {
        if (hubData && nodeId(n) === nodeId(hubData)) return false;
        return true;
    });

    const spokeCount = Math.max(spokes.length, 1);
    const radius = Math.max(340, ((NODE_W + 48) * spokeCount) / (2 * Math.PI));

    if (hubData) {
        const hid = nodeId(hubData);
        const hubExpanded = expandedDcs.has(hid);
        nodes.push({
            id: hid,
            type: 'dc',
            position: { x: cx - NODE_W / 2, y: cy - 50 },
            data: {
                label: `${hub} ETL Engine`,
                raw: hubData,
                isHub: true,
                expanded: hubExpanded,
                proxyCount: (hubData.proxies || []).length,
                dcCode: hubData.dc_code,
                onSyncHealth,
            },
            draggable: true,
        });

        if (hubExpanded) {
            (hubData.proxies || []).forEach((proxy, pIndex) => {
                const pid = String(proxy.proxy_id);
                const offset = (pIndex - (hubData.proxies.length - 1) / 2) * 145;
                nodes.push({
                    id: pid,
                    type: 'proxy',
                    position: { x: cx + offset - 55, y: cy + 105 },
                    data: {
                        label: proxyLabel(pid),
                        loki_sync_status: proxy.loki_sync_status,
                    },
                    draggable: true,
                });
                edges.push({
                    id: `dist-${pid}-${hid}`,
                    source: pid,
                    target: hid,
                    targetHandle: 'b',
                    type: 'animated',
                    data: {
                        stroke: proxy.loki_sync_status === 'loki_synced' ? SYNC_GREEN : SYNC_RED,
                        animated: true,
                    },
                });
            });
        }
    }

    const hubTargetId = hubData ? nodeId(hubData) : hub;

    spokes.forEach((dc, index) => {
        const angle = (2 * Math.PI * index) / spokeCount - Math.PI / 2;
        const dcId = nodeId(dc);
        const x = cx + radius * Math.cos(angle) - NODE_W / 2;
        const y = cy + radius * Math.sin(angle) - 44;
        const displayName = dc.dc_code || dc.location_name;
        const expanded = expandedDcs.has(dcId);
        const configured = dc.proxy_config_status === 'configured';

        nodes.push({
            id: dcId,
            type: 'dc',
            position: { x, y },
            data: {
                label: `${displayName} Proxy`,
                raw: dc,
                isHub: false,
                expanded,
                proxyCount: (dc.proxies || []).length,
                dcCode: dc.dc_code || null,
                onSyncHealth: dc.dc_code ? onSyncHealth : null,
            },
            draggable: true,
        });

        if (hubData) {
            edges.push({
                id: `ingest-${dcId}-${hubTargetId}`,
                source: dcId,
                sourceHandle: 'out',
                target: hubTargetId,
                type: 'animated',
                data: {
                    stroke: configured ? PRIMARY : NO_PROXY,
                    animated: configured,
                },
            });
        }

        if (expanded) {
            (dc.proxies || []).forEach((proxy, pIndex) => {
                const pid = String(proxy.proxy_id);
                const towardHub = Math.atan2(cy - y, cx - x);
                const spread = (pIndex - (dc.proxies.length - 1) / 2) * 0.35;
                const childAngle = towardHub + spread;
                const childDist = 95;
                const px = x + NODE_W / 2 + childDist * Math.cos(childAngle) - 55;
                const py = y + NODE_H + childDist * Math.sin(childAngle) * 0.4;

                nodes.push({
                    id: `${dcId}::${pid}`,
                    type: 'proxy',
                    position: { x: px, y: py },
                    data: {
                        label: proxyLabel(pid),
                        loki_sync_status: proxy.loki_sync_status,
                    },
                    draggable: true,
                });
                edges.push({
                    id: `dist-${dcId}-${pid}`,
                    source: `${dcId}::${pid}`,
                    target: dcId,
                    targetHandle: 'in',
                    type: 'animated',
                    data: {
                        stroke: proxy.loki_sync_status === 'loki_synced' ? SYNC_GREEN : SYNC_RED,
                        animated: true,
                    },
                });
            });
        }
    });

    return { nodes, edges };
}

const HmdlFlow = ({ id, setProps, topologyData, hubDc, height }) => {
    const [expandedDcs, setExpandedDcs] = useState(() => new Set());

    const onSyncHealth = useCallback(
        (dcCode) => {
            if (!setProps || !dcCode) return;
            setProps({
                clickedNode: {
                    action: 'navigate',
                    nodeType: 'dc',
                    dcCode: String(dcCode).toUpperCase(),
                },
            });
        },
        [setProps],
    );

    const layout = useMemo(
        () => layoutTopology(topologyData, hubDc || topologyData?.hub_dc, expandedDcs, onSyncHealth),
        [topologyData, hubDc, expandedDcs, onSyncHealth],
    );

    const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges);

    useEffect(() => {
        const storageKey = `hmdl-flow-hub-positions-${id || 'default'}`;
        const nextLayout = layoutTopology(
            topologyData,
            hubDc || topologyData?.hub_dc,
            expandedDcs,
            onSyncHealth,
        );
        try {
            const saved = localStorage.getItem(storageKey);
            if (saved) {
                const parsed = JSON.parse(saved);
                nextLayout.nodes = nextLayout.nodes.map((n) =>
                    parsed[n.id] && (n.type === 'dc') ? { ...n, position: parsed[n.id] } : n,
                );
            }
        } catch (_err) {
            /* ignore */
        }
        setNodes(nextLayout.nodes);
        setEdges(nextLayout.edges);
    }, [topologyData, hubDc, expandedDcs, onSyncHealth, id, setNodes, setEdges]);

    const persistPositions = useCallback(
        (nextNodes) => {
            const storageKey = `hmdl-flow-hub-positions-${id || 'default'}`;
            const map = {};
            nextNodes.forEach((n) => {
                if (n.type === 'dc') {
                    map[n.id] = n.position;
                }
            });
            try {
                localStorage.setItem(storageKey, JSON.stringify(map));
            } catch (_err) {
                /* ignore */
            }
        },
        [id],
    );

    const onNodeDragStop = useCallback(() => {
        setNodes((nds) => {
            persistPositions(nds);
            return nds;
        });
    }, [persistPositions, setNodes]);

    const onNodeClick = useCallback((_event, node) => {
        if (node.type !== 'dc') return;
        setExpandedDcs((prev) => {
            const next = new Set(prev);
            if (next.has(node.id)) {
                next.delete(node.id);
            } else {
                next.add(node.id);
            }
            return next;
        });
    }, []);

    return (
        <div className="hmdl-flow-shell" style={{ height: height || 640 }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onNodeDragStop={onNodeDragStop}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                fitView
                fitViewOptions={{ padding: 0.25 }}
                minZoom={0.25}
                maxZoom={1.5}
                proOptions={{ hideAttribution: true }}
            >
                <Background gap={18} size={1} color="#ececf3" />
                <Controls showInteractive={false} />
                <MiniMap
                    nodeStrokeWidth={2}
                    pannable
                    zoomable
                    nodeColor={(n) => {
                        if (n.type === 'proxy') {
                            return n.data?.loki_sync_status === 'loki_synced' ? SYNC_GREEN : SYNC_RED;
                        }
                        if (n.data?.isHub) return PRIMARY;
                        return statusColor(n.data?.raw || {});
                    }}
                />
            </ReactFlow>
            <div className="hmdl-legend">
                <span className="hmdl-legend-item"><i style={{ background: SYNC_GREEN }} /> Loki synced</span>
                <span className="hmdl-legend-item"><i style={{ background: SYNC_RED }} /> Not synced</span>
                <span className="hmdl-legend-item"><i style={{ background: NO_PROXY }} /> No configured proxy</span>
                <span className="hmdl-legend-item hmdl-legend-hint">Click location to expand NiFi nodes</span>
            </div>
        </div>
    );
};

HmdlFlow.propTypes = {
    id: PropTypes.string,
    setProps: PropTypes.func,
    topologyData: PropTypes.object,
    hubDc: PropTypes.string,
    height: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    clickedNode: PropTypes.object,
};

HmdlFlow.defaultProps = {
    topologyData: {},
    hubDc: 'DC13',
    height: 640,
};

export default HmdlFlow;
