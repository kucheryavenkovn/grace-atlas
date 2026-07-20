import esbuild from "esbuild";
import process from "process";

const prod = process.argv[2] === "production";

const common = {
  bundle: true,
  sourcemap: !prod,
  minify: prod,
  logLevel: "info",
};

async function build() {
  await esbuild.build({
    ...common,
    entryPoints: ["src/extension.ts"],
    outfile: "dist/extension.js",
    external: ["vscode"],
    format: "cjs",
    platform: "node",
    target: "node18",
  });

  await esbuild.build({
    ...common,
    entryPoints: ["src/webview/workbenchClient.ts"],
    outfile: "dist/webview.js",
    format: "iife",
    platform: "browser",
    target: "es2020",
    // cytoscape + elk bundled into webview
  });
}

if (prod) {
  await build();
} else {
  const ctxExt = await esbuild.context({
    ...common,
    entryPoints: ["src/extension.ts"],
    outfile: "dist/extension.js",
    external: ["vscode"],
    format: "cjs",
    platform: "node",
    target: "node18",
  });
  const ctxWeb = await esbuild.context({
    ...common,
    entryPoints: ["src/webview/workbenchClient.ts"],
    outfile: "dist/webview.js",
    format: "iife",
    platform: "browser",
    target: "es2020",
  });
  await Promise.all([ctxExt.watch(), ctxWeb.watch()]);
  console.log("watching…");
}
