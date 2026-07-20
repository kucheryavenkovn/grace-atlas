export const PLUGIN_NAME = "GRACE Workbench";
export const VIEW_BROWSER = "graceWorkbench.browser";
export const SUPPORTED_SCHEMA_MAJOR = 1;

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
  Evidence: "E",
};
