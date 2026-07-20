import * as fs from "fs/promises";
import * as path from "path";
import { SUPPORTED_SCHEMA_MAJOR } from "../constants";
import { buildFrontendIndex, type FrontendIndex } from "../model/indexes";
import type {
  DiagramDefinition,
  LoadedSnapshot,
  ModelStatus,
  SnapshotIndexes,
  SnapshotManifest,
  WorkbenchFinding,
  WorkbenchModel,
} from "../types/snapshot";

export interface LoaderResult {
  status: ModelStatus;
  snapshot: LoadedSnapshot | null;
  index: FrontendIndex | null;
  error: string | null;
}

function parseMajor(version: string): number | null {
  const m = /^(\d+)\./.exec(version);
  return m ? Number(m[1]) : null;
}

async function readJsonFile<T>(filePath: string): Promise<T> {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw) as T;
}

async function exists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolve model dir: workspace/.grace-atlas/model or configured relative path.
 */
export async function resolveModelDir(
  workspaceRoot: string,
  configuredRelative = ".grace-atlas/model"
): Promise<string | null> {
  const candidates = [
    path.join(workspaceRoot, configuredRelative),
    path.join(workspaceRoot, ".grace-atlas", "model"),
    path.join(workspaceRoot, ".grace-atlas", "vault", "..", "model"),
  ];
  for (const c of candidates) {
    const resolved = path.resolve(c);
    if (await exists(path.join(resolved, "manifest.json"))) {
      return resolved;
    }
  }
  return null;
}

export class ModelLoaderService {
  private lastGood: LoaderResult | null = null;

  getLastGood(): LoaderResult | null {
    return this.lastGood;
  }

  async load(workspaceRoot: string, modelRelative = ".grace-atlas/model"): Promise<LoaderResult> {
    const modelDir = await resolveModelDir(workspaceRoot, modelRelative);
    if (!modelDir) {
      return {
        status: "missing",
        snapshot: this.lastGood?.snapshot ?? null,
        index: this.lastGood?.index ?? null,
        error:
          "Snapshot not found. Run: python -m grace_atlas snapshot build --project-root . " +
          `(expected ${modelRelative}/manifest.json under workspace)`,
      };
    }

    try {
      const manifest = await readJsonFile<SnapshotManifest>(path.join(modelDir, "manifest.json"));
      const major = parseMajor(manifest.schemaVersion || "");
      if (major === null || major !== SUPPORTED_SCHEMA_MAJOR) {
        return {
          status: "incompatible",
          snapshot: this.lastGood?.snapshot ?? null,
          index: this.lastGood?.index ?? null,
          error: `Incompatible schemaVersion ${manifest.schemaVersion} (supported major ${SUPPORTED_SCHEMA_MAJOR})`,
        };
      }

      const files = manifest.files || {};
      const model = await readJsonFile<WorkbenchModel>(
        path.join(modelDir, files.model || "model.json")
      );
      if (!Array.isArray(model.nodes) || !Array.isArray(model.edges)) {
        throw new Error("model.json missing nodes/edges arrays");
      }

      const diagnostics = await readJsonFile<{
        schemaVersion: string;
        summary: Record<string, unknown>;
        findings: WorkbenchFinding[];
      }>(path.join(modelDir, files.diagnostics || "diagnostics.json"));

      let indexes: SnapshotIndexes | null = null;
      try {
        indexes = await readJsonFile<SnapshotIndexes>(
          path.join(modelDir, files.indexes || "indexes.json")
        );
      } catch {
        indexes = null;
      }

      let diagramsGenerated: { schemaVersion: string; diagrams: DiagramDefinition[] } = {
        schemaVersion: "1.0.0",
        diagrams: [],
      };
      try {
        diagramsGenerated = await readJsonFile(
          path.join(modelDir, files.diagramsGenerated || "diagrams.generated.json")
        );
      } catch {
        /* optional */
      }

      const snapshot: LoadedSnapshot = {
        manifest,
        model,
        diagnostics: {
          schemaVersion: diagnostics.schemaVersion,
          summary: diagnostics.summary || {},
          findings: diagnostics.findings || [],
        },
        indexes: indexes || {
          nodeById: {},
          incomingByNode: {},
          outgoingByNode: {},
          childrenByNode: {},
          parentByNode: {},
          diagnosticsByNode: {},
          nodesByType: {},
          nodesByStatus: {},
          nodesByPhase: {},
          diagramsByRoot: {},
          sourceFilesByNode: {},
        },
        diagramsGenerated,
        provenance: null,
        modelDir,
      };

      const index = buildFrontendIndex(
        snapshot.model.nodes,
        snapshot.model.edges,
        snapshot.diagnostics.findings,
        snapshot.indexes
      );

      const result: LoaderResult = {
        status: "ready",
        snapshot,
        index,
        error: null,
      };
      this.lastGood = result;
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (this.lastGood?.snapshot) {
        return {
          status: "stale",
          snapshot: this.lastGood.snapshot,
          index: this.lastGood.index,
          error: `Failed to load new snapshot (${msg}); keeping last good model`,
        };
      }
      return {
        status: "invalid",
        snapshot: null,
        index: null,
        error: msg,
      };
    }
  }
}
