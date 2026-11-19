import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import express from "express";
import dotenv from "dotenv";

dotenv.config();

const ROOT_DIR = process.cwd();
const VENV_PYTHON = path.join(ROOT_DIR, ".venv", "bin", "python");

function getPythonExecutable(): string {
  if (fs.existsSync(VENV_PYTHON)) {
    return VENV_PYTHON;
  }
  return "python3";
}

function runPythonBridge(command: string, payload?: unknown): Promise<any> {
  return new Promise((resolve, reject) => {
    const py = getPythonExecutable();
    const child = spawn(py, [path.join(ROOT_DIR, "core", "bridge.py"), command], {
      cwd: ROOT_DIR,
      env: process.env,
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", (err) => {
      reject(new Error(`Failed to spawn Python bridge (${py}): ${err.message}`));
    });

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `Python bridge exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (err: any) {
        reject(new Error(`Invalid JSON from Python bridge: ${err.message}. Output: ${stdout.slice(0, 300)}`));
      }
    });

    if (payload !== undefined) {
      child.stdin.write(JSON.stringify(payload));
    }
    child.stdin.end();
  });
}

function runEvalScript(): Promise<string> {
  return new Promise((resolve, reject) => {
    const py = getPythonExecutable();
    const child = spawn(py, [path.join(ROOT_DIR, "scripts", "evaluate_extraction.py")], {
      cwd: ROOT_DIR,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (c) => {
      stdout += c.toString();
    });
    child.stderr.on("data", (c) => {
      stderr += c.toString();
    });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || stdout.trim() || `Eval exited with code ${code}`));
        return;
      }
      resolve(stdout);
    });
  });
}

async function startServer() {
  const app = express();
  app.use(express.json({ limit: "25mb" }));

  app.get("/api/metadata", async (_req, res) => {
    try {
      const data = await runPythonBridge("metadata");
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  app.get("/api/samples", async (_req, res) => {
    try {
      const data = await runPythonBridge("samples");
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  app.post("/api/extract", async (req, res) => {
    try {
      const data = await runPythonBridge("extract", req.body);
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  app.post("/api/evaluate", async (req, res) => {
    try {
      const data = await runPythonBridge("evaluate", req.body);
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  app.post("/api/run-eval", async (_req, res) => {
    try {
      await runEvalScript();
      const data = await runPythonBridge("metadata");
      res.json(data);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  if (process.env.NODE_ENV !== "production") {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.join(ROOT_DIR, "dist");
    app.use(express.static(distDir));
    app.get("/{*path}", (_req, res) => {
      res.sendFile(path.join(distDir, "index.html"));
    });
  }

  const PORT = 3000;
  app.listen(PORT, "0.0.0.0", () => {
    console.log(`SchemeSathi server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
