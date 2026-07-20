declare module "elkjs/lib/elk.bundled.js" {
  export interface ElkNode {
    id: string;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    children?: ElkNode[];
    edges?: ElkEdge[];
    layoutOptions?: Record<string, string>;
  }
  export interface ElkEdge {
    id: string;
    sources: string[];
    targets: string[];
  }
  export default class ELK {
    layout(graph: ElkNode): Promise<ElkNode>;
  }
}
