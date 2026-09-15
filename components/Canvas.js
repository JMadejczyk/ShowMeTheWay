'use client';
import { useMemo, useCallback } from 'react';
import { ReactFlow, Background, Controls, Handle, Position } from '@xyflow/react';
import { layout } from '@/lib/layout';

const MARK = { known: '✓', done: '✓', doing: '·' };

function RNode({ data, selected }) {
  const n = data.n;
  const cls = ['rnode', n.track, n.status, selected ? 'sel' : ''].join(' ');
  return (
    <div className={cls} title={n.summary}>
      <Handle type="target" position={Position.Top} id="t" />
      <Handle type="target" position={Position.Left} id="l" />
      <Handle type="target" position={Position.Right} id="r" />
      {n.title}
      {MARK[n.status] && <div className={'badge ' + n.status}>{MARK[n.status]}</div>}
      <Handle type="source" position={Position.Bottom} id="b" />
      <Handle type="source" position={Position.Left} id="sl" />
      <Handle type="source" position={Position.Right} id="sr" />
    </div>
  );
}
const types = { r: RNode };

export default function Canvas({ nodes, edges, selected, onSelect, onMove }) {
  const placed = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const pos = useMemo(() => new Map(placed.map(p => [p.id, p.pos])), [placed]);

  const rfNodes = useMemo(() => placed.map(n => ({
    id: n.id, type: 'r', position: n.pos, data: { n }, selected: n.id === selected,
  })), [placed, selected]);

  const rfEdges = useMemo(() => edges.map((e, i) => {
    const a = pos.get(e.src), b = pos.get(e.dst);
    const branch = e.kind === 'branch' || (a && b && Math.abs(a.x - b.x) > 40);
    const leftward = a && b && b.x < a.x;
    return {
      id: 'e' + i, source: e.src, target: e.dst,
      sourceHandle: branch ? (leftward ? 'sl' : 'sr') : 'b',
      targetHandle: branch ? (leftward ? 'r' : 'l') : 't',
      type: branch ? 'default' : 'smoothstep',
      style: {
        stroke: '#2563eb', strokeWidth: 2,
        strokeDasharray: branch ? '5 5' : undefined,
      },
    };
  }), [edges, pos]);

  const onDragStop = useCallback((_, node) => onMove(node.id, node.position), [onMove]);

  return (
    <ReactFlow
      nodes={rfNodes} edges={rfEdges} nodeTypes={types}
      onNodeClick={(_, n) => onSelect(n.id)}
      onNodeDragStop={onDragStop}
      onPaneClick={() => onSelect(null)}
      fitView fitViewOptions={{ padding: 0.18 }}
      minZoom={0.15} maxZoom={1.6}
      proOptions={{ hideAttribution: true }}
      nodesConnectable={false} edgesFocusable={false}
    >
      <Background gap={26} size={1} color="#dcdcd8" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
