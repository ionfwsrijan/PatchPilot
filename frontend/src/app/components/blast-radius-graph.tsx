import React, { useEffect, useState, useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useNavigate } from 'react-router';
import { 
  ZoomIn, ZoomOut, Target, X, ShieldAlert, Box, GitBranch, 
  ArrowDownToLine, ArrowUpFromLine, Search, Activity
} from 'lucide-react';
import { getOrgBlastRadius } from '../lib/api';

interface Node {
  id: string;
  type: 'repo' | 'package';
  vulnerable: boolean;
  x?: number;
  y?: number;
  neighbors?: string[];
  links?: any[];
}

interface Link {
  source: string | Node;
  target: string | Node;
}

interface GraphData {
  nodes: Node[];
  links: Link[];
}

interface BlastRadiusGraphProps {
  orgJobId: string;
}

export function BlastRadiusGraph({ orgJobId }: BlastRadiusGraphProps) {
  const navigate = useNavigate();
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const settledRef = useRef(false);

  const [dimensions, setDimensions] = useState({ width: 0, height: 600 });
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [hoverNode, setHoverNode] = useState<Node | null>(null);
  const [highlightNodes, setHighlightNodes] = useState(new Set<string>());
  const [highlightLinks, setHighlightLinks] = useState(new Set<any>());

  const [searchQuery, setSearchQuery] = useState('');
  const [vulnerableOnly, setVulnerableOnly] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const w = el.offsetWidth;
    const h = el.offsetHeight;
    if (w > 0) setDimensions({ width: w, height: h || 600 });

    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect && rect.width > 50 && rect.height > 50) {
        setDimensions({ width: rect.width, height: rect.height });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    settledRef.current = false;
    setData(null);
    setError(null);
    setLoading(true);

    const fetchGraph = async () => {
      try {
        const result = await getOrgBlastRadius(orgJobId);
        
        const clonedNodes = result.nodes.map((n: any) => ({
          ...n,
          x: Math.random() * 1000 - 500,
          y: Math.random() * 1000 - 500,
          neighbors: [],
          links: []
        }));
        const clonedLinks = result.links.map((l: any) => ({ ...l }));

        const nodesById = new Map();
        clonedNodes.forEach((node: any) => nodesById.set(node.id, node));

        clonedLinks.forEach((link: any) => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          const a = nodesById.get(sourceId);
          const b = nodesById.get(targetId);

          if (a && b) {
            a.neighbors.push(b.id);
            b.neighbors.push(a.id);
            a.links.push(link);
            b.links.push(link);
          }
        });

        setData({ nodes: clonedNodes, links: clonedLinks });
      } catch (err) {
        setError('Failed to load dependency graph.');
      } finally {
        setLoading(false);
      }
    };

    if (orgJobId) fetchGraph();
  }, [orgJobId]);

  const handleZoomIn = useCallback(() => {
    if (fgRef.current) fgRef.current.zoom(fgRef.current.zoom() * 1.5, 300);
  }, []);

  const handleZoomOut = useCallback(() => {
    if (fgRef.current) fgRef.current.zoom(fgRef.current.zoom() / 1.5, 300);
  }, []);

  const handleCenter = useCallback(() => {
    if (fgRef.current) fgRef.current.zoomToFit(400, 50);
  }, []);

  const isNodeVisible = useCallback((node: any) => {
    if (!node) return false;
    if (vulnerableOnly && !node.vulnerable) return false;
    if (searchQuery && !node.id.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  }, [vulnerableOnly, searchQuery]);

  const handleNodeClick = useCallback((node: any) => {
    if (!isNodeVisible(node)) return;

    const newHighlightNodes = new Set<string>();
    const newHighlightLinks = new Set<any>();

    newHighlightNodes.add(node.id);
    if (node.neighbors) {
      node.neighbors.forEach((neighborId: string) => newHighlightNodes.add(neighborId));
    }
    if (node.links) {
      node.links.forEach((link: any) => newHighlightLinks.add(link));
    }

    setSelectedNode(node);
    setHighlightNodes(newHighlightNodes);
    setHighlightLinks(newHighlightLinks);

    if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 600);
      fgRef.current.zoom(2.5, 600);
    }
  }, [isNodeVisible]);

  const handleBackgroundClick = useCallback(() => {
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());
    setSelectedNode(null);
    if (fgRef.current) {
      fgRef.current.zoomToFit(400, 50);
    }
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectedNode) {
        handleBackgroundClick();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedNode, handleBackgroundClick]);

  const upstreamCount = selectedNode?.links?.filter(l => (typeof l.source === 'object' ? l.source.id : l.source) === selectedNode.id).length || 0;
  const downstreamCount = selectedNode?.links?.filter(l => (typeof l.target === 'object' ? l.target.id : l.target) === selectedNode.id).length || 0;

  const visibleNodes = data?.nodes.filter(isNodeVisible) || [];
  const visibleVulnCount = visibleNodes.filter(n => n.vulnerable).length;

  return (
    <div
      ref={containerRef}
      className="relative w-full h-[600px] rounded-lg border border-slate-800 overflow-hidden shadow-xl"
      style={{ backgroundColor: '#020617' }}
    >
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px)
          `,
          backgroundSize: '30px 30px',
        }}
      />

      {loading && (
        <div className="absolute inset-0 flex items-center justify-center z-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-500" />
        </div>
      )}

      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-rose-500 z-20">
          {error}
        </div>
      )}

      <div className="absolute top-4 right-4 z-10 flex flex-col gap-2 bg-slate-900/90 p-2 rounded-lg border border-slate-700 shadow-xl backdrop-blur-md">
        <button onClick={handleZoomIn} className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md transition-all" title="Zoom In">
          <ZoomIn className="w-4 h-4" />
        </button>
        <button onClick={handleZoomOut} className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md transition-all" title="Zoom Out">
          <ZoomOut className="w-4 h-4" />
        </button>
        <button onClick={handleCenter} className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md transition-all" title="Recenter (Esc)">
          <Target className="w-4 h-4" />
        </button>
      </div>

      <div className="absolute top-4 left-4 z-10 w-80 flex flex-col gap-3">
        <div className="bg-slate-900/95 p-3 rounded-lg border border-slate-700 shadow-2xl backdrop-blur-md">
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search package or repo..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-md py-2 pl-9 pr-3 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setVulnerableOnly(false)}
              className={`flex-1 flex items-center justify-center gap-2 py-1.5 px-3 rounded text-xs font-medium transition-all ${!vulnerableOnly ? 'bg-slate-800 text-slate-100 border border-slate-600' : 'bg-slate-950 text-slate-500 border border-slate-800 hover:text-slate-300'}`}
            >
              <Activity className="w-3.5 h-3.5" /> All Nodes
            </button>
            <button
              onClick={() => setVulnerableOnly(true)}
              className={`flex-1 flex items-center justify-center gap-2 py-1.5 px-3 rounded text-xs font-medium transition-all ${vulnerableOnly ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-slate-950 text-slate-500 border border-slate-800 hover:text-rose-400/50'}`}
            >
              <ShieldAlert className="w-3.5 h-3.5" /> Vulnerable
            </button>
          </div>
        </div>

        {selectedNode ? (
          <div className="bg-slate-900/95 p-4 rounded-lg border border-slate-700 shadow-2xl backdrop-blur-md animate-in slide-in-from-left-4 fade-in duration-200">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-2">
                {selectedNode.type === 'repo' ? (
                  <GitBranch className="w-5 h-5 text-slate-300" />
                ) : (
                  <Box className="w-5 h-5 text-slate-300" />
                )}
                <h3 className="font-semibold text-slate-100 truncate w-56" title={selectedNode.id}>
                  {selectedNode.id}
                </h3>
              </div>
              <button onClick={handleBackgroundClick} className="text-slate-400 hover:text-slate-100 transition-colors cursor-pointer" title="Close (Esc)">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-400">Type</span>
                <span className="text-slate-200 capitalize bg-slate-800 px-2 py-0.5 rounded text-xs font-medium border border-slate-700">
                  {selectedNode.type}
                </span>
              </div>

              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-400">Status</span>
                {selectedNode.vulnerable ? (
                  <span className="flex items-center gap-1 text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded text-xs font-medium border border-rose-500/20">
                    <ShieldAlert className="w-3 h-3" /> Vulnerable
                  </span>
                ) : (
                  <span className="text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded text-xs font-medium border border-emerald-500/20">
                    Secure
                  </span>
                )}
              </div>

              <div className="w-full h-px bg-slate-800 my-3" />
              
              <div className="space-y-2">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Dependency Tree</p>
                
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <ArrowUpFromLine className="w-3.5 h-3.5 text-slate-500" />
                    Dependencies
                  </span>
                  <span className="text-slate-200 font-mono text-xs bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                    {upstreamCount}
                  </span>
                </div>

                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400 flex items-center gap-1.5">
                    <ArrowDownToLine className="w-3.5 h-3.5 text-slate-500" />
                    Dependents
                  </span>
                  <span className={`font-mono text-xs px-2 py-0.5 rounded border ${downstreamCount > 0 && selectedNode.vulnerable ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-slate-800 text-slate-200 border-slate-700'}`}>
                    {downstreamCount}
                  </span>
                </div>
              </div>

              {selectedNode.vulnerable && (
                <div className="pt-3 mt-2 border-t border-slate-800">
                  <button
                    onClick={() => navigate(`/fix?packageId=${selectedNode.id}`)}
                    className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white py-2 px-4 rounded-md text-sm font-semibold transition-colors shadow-lg shadow-indigo-900/20"
                  >
                    Remediate Vulnerability
                  </button>
                </div>
              )}

            </div>
          </div>
        ) : (
          <div className="bg-slate-900/95 p-4 rounded-lg border border-slate-700 shadow-2xl backdrop-blur-md animate-in slide-in-from-left-4 fade-in duration-200">
            <h3 className="font-semibold text-slate-300 mb-4 flex items-center gap-2">
              <Activity className="w-4 h-4" /> Global Overview
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-950 p-3 rounded-md border border-slate-800">
                <span className="text-slate-500 text-xs block mb-1">Visible Nodes</span>
                <span className="text-2xl font-mono font-semibold text-slate-200">{visibleNodes.length}</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-md border border-slate-800">
                <span className="text-slate-500 text-xs block mb-1">At Risk</span>
                <span className="text-2xl font-mono font-semibold text-rose-400">{visibleVulnCount}</span>
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-4 text-center">
              Click any node to inspect its specific blast radius.
            </p>
          </div>
        )}
      </div>

      {data && dimensions.width > 0 && (
        <div className="absolute inset-0">
          <ForceGraph2D
            ref={fgRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={data}
            nodeLabel="id"
            nodeRelSize={4}
            backgroundColor="rgba(0,0,0,0)"
            warmupTicks={150}
            cooldownTicks={0}
            nodeCanvasObjectMode={() => 'replace'}
            
            onEngineStop={() => {
              if (fgRef.current && !settledRef.current) {
                settledRef.current = true;
                fgRef.current.zoomToFit(0, 50);
              }
            }}
            
            onNodeHover={(node: any) => {
              if (!isNodeVisible(node)) {
                setHoverNode(null);
                if (containerRef.current) containerRef.current.style.cursor = 'default';
                return;
              }
              if (containerRef.current) containerRef.current.style.cursor = node ? 'pointer' : 'default';
              setHoverNode(node || null);
            }}

            onNodeClick={handleNodeClick}
            onBackgroundClick={handleBackgroundClick}

            linkColor={(link: any) => {
              const sourceVisible = isNodeVisible(typeof link.source === 'object' ? link.source : data.nodes.find(n => n.id === link.source));
              const targetVisible = isNodeVisible(typeof link.target === 'object' ? link.target : data.nodes.find(n => n.id === link.target));
              if (!sourceVisible || !targetVisible) return 'rgba(0,0,0,0)';

              if (highlightNodes.size > 0 && !highlightLinks.has(link)) return 'rgba(30, 41, 59, 0.15)';
              const isVuln = typeof link.target === 'object' ? link.target.vulnerable : false;
              return isVuln ? 'rgba(225, 29, 72, 0.6)' : 'rgba(71, 85, 105, 0.4)';
            }}
            
            linkWidth={(link: any) => {
              const sourceVisible = isNodeVisible(typeof link.source === 'object' ? link.source : data.nodes.find(n => n.id === link.source));
              const targetVisible = isNodeVisible(typeof link.target === 'object' ? link.target : data.nodes.find(n => n.id === link.target));
              if (!sourceVisible || !targetVisible) return 0;

              if (highlightNodes.size > 0 && highlightLinks.has(link)) return 1.5;
              const isVuln = typeof link.target === 'object' ? link.target.vulnerable : false;
              return isVuln ? 1 : 0.5;
            }}

            linkDirectionalParticles={(link: any) => {
              const sourceVisible = isNodeVisible(typeof link.source === 'object' ? link.source : data.nodes.find(n => n.id === link.source));
              const targetVisible = isNodeVisible(typeof link.target === 'object' ? link.target : data.nodes.find(n => n.id === link.target));
              if (!sourceVisible || !targetVisible) return 0;

              if (highlightNodes.size > 0 && !highlightLinks.has(link)) return 0;
              if (highlightNodes.size > 0 && highlightLinks.has(link)) return 3;
              const isVuln = typeof link.target === 'object' ? link.target.vulnerable : false;
              return isVuln ? 2 : 0;
            }}
            
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              if (node.x === undefined || node.y === undefined) return;

              const visible = isNodeVisible(node);
              const isDimmed = highlightNodes.size > 0 && !highlightNodes.has(node.id);
              
              ctx.globalAlpha = visible ? (isDimmed ? 0.15 : 1) : 0.02;

              const isRepo = node.type === 'repo';
              const isVuln = node.vulnerable;
              const isHovered = hoverNode?.id === node.id;

              const NODE_R = isRepo ? 4.5 : isVuln ? 3 : 1.5;

              if ((isHovered || selectedNode?.id === node.id) && visible) {
                ctx.beginPath();
                ctx.arc(node.x, node.y, NODE_R + (2 / globalScale), 0, 2 * Math.PI, false);
                ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
                ctx.fill();
              }

              ctx.beginPath();
              ctx.arc(node.x, node.y, NODE_R, 0, 2 * Math.PI, false);

              if (isRepo) {
                ctx.fillStyle = '#ffffff';
                ctx.fill();
                ctx.strokeStyle = '#94a3b8';
                ctx.lineWidth = 1 / globalScale;
                ctx.stroke();
              } else if (isVuln) {
                ctx.fillStyle = isHovered ? '#fb7185' : '#e11d48';
                ctx.fill();
              } else {
                ctx.fillStyle = isHovered ? '#94a3b8' : '#64748b'; 
                ctx.fill();
              }

              const showText = globalScale > 2.5 || (isRepo && globalScale > 1.2) || isVuln || isHovered;

              if (showText && globalScale > 0.5 && visible) {
                const fontSize = Math.max(1, Math.min(20, (isRepo ? 10 : 8) / globalScale));
                ctx.font = `500 ${fontSize}px Inter, system-ui, sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                ctx.lineJoin = 'round';
                ctx.lineWidth = Math.max(0.5, 3 / globalScale);
                ctx.strokeStyle = '#020617';
                ctx.strokeText(node.id, node.x, node.y + NODE_R + 2 / globalScale);
                ctx.fillStyle = isRepo ? '#f8fafc' : isVuln ? '#fecdd3' : '#cbd5e1';
                ctx.fillText(node.id, node.x, node.y + NODE_R + 2 / globalScale);
              }

              ctx.globalAlpha = 1; 
            }}
          />
        </div>
      )}
    </div>
  );
}