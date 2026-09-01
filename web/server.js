// Production server: serve the built SPA and proxy /api -> gateway (REST + WS).
//   npm run build && GATEWAY_URL=http://127.0.0.1:8000 npm start
import express from "express";
import { createProxyMiddleware } from "http-proxy-middleware";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 4173;
const target = process.env.GATEWAY_URL || "http://127.0.0.1:8000";

const app = express();

const apiProxy = createProxyMiddleware({
  target,
  changeOrigin: true,
  ws: true,
  pathRewrite: { "^/api": "" },
});
app.use("/api", apiProxy);

const dist = path.join(__dirname, "dist");
app.use(express.static(dist));
app.get("*", (_req, res) => res.sendFile(path.join(dist, "index.html")));

const server = app.listen(PORT, () => {
  console.log(`web on http://127.0.0.1:${PORT}  ->  gateway ${target}`);
});
// http-proxy-middleware v3 needs the upgrade handler wired explicitly for WS.
server.on("upgrade", apiProxy.upgrade);
