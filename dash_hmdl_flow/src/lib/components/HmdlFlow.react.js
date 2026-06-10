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

function SourceNode({ data }) {
    return (
        <div className="hmdl-node hmdl-node-source">
            <Handle type="source" position={Position.Bottom} />
            <div className="hmdl-node-title">{data.label || 'Loki Inventory'}</div>
            <div className="hmdl-node-sub">NetBox locations</div>
        </div>
    );
}

function DcNode({ data }) {
    const color = statusColor(data.raw || {});
    const isHub = data.isHub;
    return (
        <div className={`hmdl-node hmdl-node-dc${isHub ? ' hmdl-node-hub' : ''}`} style={{ borderColor: color }}>
            <Handle type="target" position={Position.Top} />
            <Handle type="source" position={Position.Bottom} />
            <div className="hmdl-node-title">{data.label}</div>
            <div className="hmdl-badge" style={{ background: `${color}22`, color }}>{badgeLabel(data.raw || {})}</div>
            {data.proxyCount > 0 && (
                <div className="hmdl-node-sub">{data.proxyCount} proxy</div>
            )}
        </div>
    );
}

function ProxyNode({ data }) {
    const synced = data.loki_sync_status === 'loki_synced';
    const color = synced ? SYNC_GREEN : SYNC_RED;
    return (
        <div className="hmdl-node hmdl-node-proxy" style={{ borderColor: color }}>
            <Handle type="target" position={Position.Top} />
            <div className="hmdl-node-title">{data.label}</div>
            <div className="hmdl-badge" style={{ background: `${color}22`, color }}>
                {synced ? 'Synced' : 'Not synced'}
            </div>
        </div>
    );
}

const nodeTypes = {
    source: SourceNode,
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

function layoutTopology(topology, hubDc) {
    const nodes = [];
    const edges = [];
    if (!topology || typeof topology !== 'object') {
        return { nodes, edges };
    }

    const source = topology.source_node || { id: 'LOKI', label: 'Loki Inventory' };
    const dcNodes = topology.nodes || [];
    const cx = 420;
    const sourceY = 20;
    const dcRadius = 240;
    const dcY = 220;

    nodes.push({
        id: source.id || 'LOKI',
        type: 'source',
        position: { x: cx - 90, y: sourceY },
        data: { label: source.label || 'Loki Inventory' },
        draggable: true,
    });

    const count = dcNodes.length || 1;
    dcNodes.forEach((dc, index) => {
        const angle = (2 * Math.PI * index) / count - Math.PI / 2;
        const dcId = dc.dc_code || dc.location_name || `loc-${index}`;
        const x = cx + dcRadius * Math.cos(angle) - 80;
        const y = dcY + dcRadius * Math.sin(angle) * 0.55;
        const isHub = dc.role === 'hub' || (hubDc && dc.dc_code === hubDc);

        nodes.push({
            id: dcId,
            type: 'dc',
            position: { x, y },
            data: {
                label: dc.dc_code || dc.location_name,
                raw: dc,
                isHub,
                proxyCount: (dc.proxies || []).length,
                dcCode: dc.dc_code,
            },
            draggable: true,
        });

        edges.push({
            id: `e-${source.id}-${dcId}`,
            source: source.id || 'LOKI',
            target: dcId,
            type: 'animated',
            data: {
                stroke: dc.proxy_config_status === 'no_configured_proxy' ? NO_PROXY : PRIMARY,
                animated: dc.proxy_config_status === 'configured',
            },
        });

        (dc.proxies || []).forEach((proxy, pIndex) => {
            const pid = proxy.proxy_id;
            const px = x + (pIndex - ((dc.proxies.length - 1) / 2)) * 130;
            const py = y + 110;
            nodes.push({
                id: pid,
                type: 'proxy',
                position: { x: px, y: py },
                data: {
                    label: pid,
                    loki_sync_status: proxy.loki_sync_status,
                },
                draggable: true,
            });
            edges.push({
                id: `e-${dcId}-${pid}`,
                source: dcId,
                target: pid,
                type: 'animated',
                data: {
                    stroke: proxy.loki_sync_status === 'loki_synced' ? SYNC_GREEN : SYNC_RED,
                    animated: true,
                },
            });
        });
    });

    return { nodes, edges };
}

const HmdlFlow = ({ id, setProps, topologyData, hubDc, height, clickedNode }) => {
    const layout = useMemo(
        () => layoutTopology(topologyData, hubDc || topologyData?.hub_dc),
        [topologyData, hubDc],
    );
    const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges);
    const [positionsLoaded, setPositionsLoaded] = useState(false);

    useEffect(() => {
        const storageKey = `hmdl-flow-positions-${id || 'default'}`;
        try {
            const saved = localStorage.getItem(storageKey);
            if (saved) {
                const parsed = JSON.parse(saved);
                setNodes((current) =>
                    current.map((n) => (parsed[n.id] ? { ...n, position: parsed[n.id] } : n)),
                );
            } else {
                setNodes(layout.nodes);
            }
        } catch (_err) {
            setNodes(layout.nodes);
        }
        setEdges(layout.edges);
        setPositionsLoaded(true);
    }, [layout, id, setNodes, setEdges]);

    const persistPositions = useCallback(
        (nextNodes) => {
            const storageKey = `hmdl-flow-positions-${id || 'default'}`;
            const map = {};
            nextNodes.forEach((n) => {
                map[n.id] = n.position;
            });
            try {
                localStorage.setItem(storageKey, JSON.stringify(map));
            } catch (_err) {
                /* ignore quota errors */
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

    const onNodeClick = useCallback(
        (_event, node) => {
            if (!setProps) return;
            const payload = {
                nodeId: node.id,
                nodeType: node.type,
                dcCode: node.data?.dcCode || (node.type === 'dc' ? node.id : null),
            };
            setProps({ clickedNode: payload });
        },
        [setProps],
    );

    if (!positionsLoaded) {
        return <div className="hmdl-flow-shell" style={{ height: height || 560 }} />;
    }

    return (
        <div className="hmdl-flow-shell" style={{ height: height || 560 }}>
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
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.35}
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
                        if (n.type === 'source') return PRIMARY;
                        if (n.type === 'proxy') return n.data?.loki_sync_status === 'loki_synced' ? SYNC_GREEN : SYNC_RED;
                        return statusColor(n.data?.raw || {});
                    }}
                />
            </ReactFlow>
            <div className="hmdl-legend">
                <span className="hmdl-legend-item"><i style={{ background: SYNC_GREEN }} /> Loki synced</span>
                <span className="hmdl-legend-item"><i style={{ background: SYNC_RED }} /> Not synced</span>
                <span className="hmdl-legend-item"><i style={{ background: NO_PROXY }} /> No configured proxy</span>
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
    height: 560,
};

export default HmdlFlow;
