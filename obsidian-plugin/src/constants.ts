/** GRACE Workbench constants */

export const PLUGIN_ID = "grace-workbench";
export const PLUGIN_NAME = "GRACE Workbench";

export const VIEW_BROWSER = "grace-model-browser";
export const VIEW_DIAGRAM = "grace-diagram";
export const VIEW_INSPECTOR = "grace-inspector";
export const VIEW_DIAGNOSTICS = "grace-diagnostics";

/** Relative to vault root / project root discovery */
export const MODEL_MANIFEST_CANDIDATES = [
  ".grace-atlas/model/manifest.json",
  "../.grace-atlas/model/manifest.json",
  "../../.grace-atlas/model/manifest.json",
];

export const SUPPORTED_SCHEMA_MAJOR = 1;

export const TYPE_ICONS: Record<string, string> = {
  Requirement: "R",
  UseCase: "UC",
  Module: "M",
  Verification: "V",
  CriticalFlow: "CF",
  DataFlow: "DF",
  Phase: "Ph",
  Step: "St",
  OperationalPacket: "OP",
  SourceFile: "F",
  TestFile: "T",
  Contract: "C",
  SemanticBlock: "B",
  Technology: "Tech",
  Evidence: "E",
  Constraint: "K",
  Risk: "Risk",
  NonGoal: "NG",
  PhaseGate: "G",
  Deployment: "D",
  Actor: "A",
};

export const BROWSER_ROOTS: Array<{
  id: string;
  label: string;
  types?: string[];
  special?: "diagnostics" | "diagrams";
}> = [
  {
    id: "requirements",
    label: "Requirements",
    types: ["Requirement", "Constraint", "Risk", "NonGoal", "UseCase"],
  },
  {
    id: "behavior",
    label: "Behavior",
    types: ["UseCase", "DataFlow", "CriticalFlow"],
  },
  {
    id: "architecture",
    label: "Architecture",
    types: ["Module", "Contract", "SemanticBlock", "SourceFile", "Deployment"],
  },
  {
    id: "verification",
    label: "Verification",
    types: ["Verification", "TestFile", "Evidence", "CriticalFlow"],
  },
  {
    id: "development",
    label: "Development",
    types: ["Phase", "Step", "OperationalPacket"],
  },
  { id: "diagnostics", label: "Diagnostics", special: "diagnostics" },
  { id: "diagrams", label: "Diagrams", special: "diagrams" },
];
