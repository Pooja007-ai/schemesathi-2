import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import express from "express";
import dotenv from "dotenv";
import { GoogleGenAI, GenerateContentResponse, type Content } from "@google/genai";

dotenv.config();

const ROOT_DIR = process.cwd();
const VENV_PYTHON = path.join(ROOT_DIR, ".venv", "bin", "python");

const CHAT_SYSTEM_INSTRUCTION = `You are the SchemeSathi Document Submission Assistant for Indian student scholarship verification.
Your job is to answer student doubts clearly and calmly about:
- Uploading documents (income certificate, marks card, community/category certificate in PDF, PNG, or JPG).
- Why scans might fail verification (e.g. blurry photos measured by OpenCV Laplacian variance, an image test—not ML).
- Name consistency across certificates (measured by RapidFuzz string similarity—not ML) and common spelling/initial mismatches.
- Certificate validity dates, missing documents, and what "ELIGIBLE", "ALMOST", and "NOT ELIGIBLE" verdicts mean.
- How SchemeSathi works ("AI reads, rules decide").

Strict boundaries you MUST follow:
1. You NEVER decide scholarship eligibility, approve applications, or override deterministic Python rules in data/schemes.yaml.
2. Placeholder schemes in data/schemes.yaml currently have thresholds marked TODO_VERIFY. NEVER invent, guess, or quote unverified income caps, marks cutoffs, or validity limits as official rules. Always tell the student to confirm exact thresholds on the official portal.
3. Remind students that this prototype uses synthetic documents only and sends uploaded text to an external LLM API for field extraction.
4. Keep answers plain-language, structured, and concise so students know exactly what to check before submitting.`;

function getGeminiClient(): GoogleGenAI {
  const apiKey = (process.env.GEMINI_API_KEY || "").trim();
  if (!apiKey || apiKey === "MY_GEMINI_API_KEY") {
    throw new Error(
      "GEMINI_API_KEY is not configured. Add it in Settings > Secrets or .env to use the Document Submission Assistant."
    );
  }
  return new GoogleGenAI({
    apiKey,
    httpOptions: {
      headers: {
        "User-Agent": "aistudio-build",
      },
    },
  });
}

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

  app.post("/api/chat", async (req, res) => {
    try {
      const { messages, context } = req.body as {
        messages?: Array<{ role: "user" | "model"; text: string }>;
        context?: Record<string, unknown>;
      };

      if (!Array.isArray(messages) || messages.length === 0) {
        res.status(400).json({ error: "Provide at least one chat message." });
        return;
      }

      const lastMsg = messages[messages.length - 1];
      if (!lastMsg || lastMsg.role !== "user" || !lastMsg.text.trim()) {
        res.status(400).json({ error: "Latest message must be a non-empty user question." });
        return;
      }

      const ai = getGeminiClient();

      // Build valid alternating history starting with a 'user' message
      const rawPrior = messages.slice(0, -1).filter((m) => m.text && m.text.trim());
      const firstUserIdx = rawPrior.findIndex((m) => m.role === "user");
      const trimmedPrior = firstUserIdx >= 0 ? rawPrior.slice(firstUserIdx) : [];

      const history: Content[] = [];
      for (const msg of trimmedPrior) {
        const lastHist = history[history.length - 1];
        if (lastHist && lastHist.role === msg.role) {
          lastHist.parts = [{ text: `${lastHist.parts?.[0]?.text ?? ""}\n${msg.text.trim()}` }];
        } else {
          history.push({ role: msg.role, parts: [{ text: msg.text.trim() }] });
        }
      }
      // Ensure history ends with 'model' before sendMessageStream sends the next 'user' turn
      if (history.length > 0 && history[history.length - 1].role === "user") {
        history.pop();
      }

      const contextSuffix = context
        ? `\n\nCurrent non-PII session context from the user's screen:\n${JSON.stringify(context)}`
        : "";

      const envModel = (process.env.GEMINI_MODEL || "").trim();
      const modelName = envModel.startsWith("gemini-") ? envModel : "gemini-4-hydrogen";
      const chat = ai.chats.create({
        model: modelName,
        history,
        config: {
          systemInstruction: `${CHAT_SYSTEM_INSTRUCTION}${contextSuffix}`,
        },
      });

      res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");

      const streamResponse = await chat.sendMessageStream({ message: lastMsg.text.trim() });
      for await (const chunk of streamResponse) {
        const c = chunk as GenerateContentResponse;
        if (c.text) {
          res.write(`data: ${JSON.stringify({ text: c.text })}\n\n`);
        }
      }
      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } catch (err: any) {
      const msg = err?.message || "Gemini chat request failed.";
      if (!res.headersSent) {
        res.status(500).json({ error: msg });
      } else {
        res.write(`data: ${JSON.stringify({ error: msg })}\n\n`);
        res.end();
      }
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
