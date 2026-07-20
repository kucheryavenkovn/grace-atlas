import { normalizePath, type App } from "obsidian";
import { MODEL_MANIFEST_CANDIDATES, SUPPORTED_SCHEMA_MAJOR } from "../constants";
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

async function pathExists(app: App, path: string): Promise<boolean> {
  try {
    return await app.vault.adapter.exists(normalizePath(path));
  } catch {
    return false;
  }
}

async function readJson<T>(app: App, path: string): Promise<T> {
  const raw = await app.vault.adapter.read(normalizePath(path));
  return JSON.parse(raw) as T;
}

async function readJsonRetry<T>(app: App, path: string, attempts = 3): Promise<T> {
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await readJson<T>(app, path);
    } catch (e) {
      last = e;
      await new Promise((r) => setTimeout(r, 40 * (i + 1)));
    }
  }
  throw last;
}

/**
 * Discover .grace-atlas/model relative to vault (vault may be .grace-atlas/vault).
 */
export async function findModelDir(app: App): Promise<string | null> {
  for (const cand of MODEL_MANIFEST_CANDIDATES) {
    if (await pathExists(app, cand)) {
      const dir = cand.replace(/\/manifest\.json$/, "");
      return dir;
    }
  }
  // absolute project path via common layout: vault is .grace-atlas/vault
  return null;
}

export class ModelLoaderService {
  private lastGood: LoaderResult | null = null;
  private lastHash: string | null = null;

  constructor(private app: App) {}

  getLastGood(): LoaderResult | null {
    return this.lastGood;
  }

  async load(): Promise<LoaderResult> {
    const modelDir = await findModelDir(this.app);
    if (!modelDir) {
      const result: LoaderResult = {
        status: "missing",
        snapshot: null,
        index: this.lastGood?.index ?? null,
        error:
          "Snapshot не найден. Выполните: python -m grace_atlas snapshot build --project-root . " +
          "(ожидается .grace-atlas/model/manifest.json относительно vault)",
      };
      return result;
    }

    try {
      const manifest = await readJsonRetry<SnapshotManifest>(
        this.app,
        `${modelDir}/manifest.json`
      );
      const major = parseMajor(manifest.schemaVersion || "");
      if (major === null || major !== SUPPORTED_SCHEMA_MAJOR) {
        return {
          status: "incompatible",
          snapshot: this.lastGood?.snapshot ?? null,
          index: this.lastGood?.index ?? null,
          error: `Несовместимая schemaVersion ${manifest.schemaVersion} (поддерживается major ${SUPPORTED_SCHEMA_MAJOR})`,
        };
      }

      const files = manifest.files || {};
      const modelPath = `${modelDir}/${files.model || "model.json"}`;
      const diagPath = `${modelDir}/${files.diagnostics || "diagnostics.json"}`;
      const idxPath = `${modelDir}/${files.indexes || "indexes.json"}`;
      const diagGenPath = `${modelDir}/${files.diagramsGenerated || "diagrams.generated.json"}`;

      const model = await readJsonRetry<WorkbenchModel>(this.app, modelPath);
      if (!Array.isArray(model.nodes) || !Array.isArray(model.edges)) {
        throw new Error("model.json: отсутствуют массивы nodes/edges");
      }
      const diagnostics = await readJsonRetry<{
        schemaVersion: string;
        summary: Record<string, unknown>;
        findings: WorkbenchFinding[];
      }>(this.app, diagPath);
      let indexes: SnapshotIndexes | null = null;
      try {
        indexes = await readJsonRetry<SnapshotIndexes>(this.app, idxPath);
      } catch {
        indexes = null;
      }
      let diagramsGenerated: { schemaVersion: string; diagrams: DiagramDefinition[] } = {
        schemaVersion: "1.0.0",
        diagrams: [],
      };
      try {
        diagramsGenerated = await readJsonRetry(this.app, diagGenPath);
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

      let status: ModelStatus = "ready";
      if (this.lastHash && this.lastHash !== manifest.modelHash) {
        // still ready, but could mark stale until UI acknowledges
        status = "ready";
      }
      this.lastHash = manifest.modelHash;
      const result: LoaderResult = {
        status,
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
          error: `Не удалось загрузить snapshot (${msg}); оставлена последняя рабочая модель`,
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
