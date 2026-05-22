/**
 * http-utils.mjs — 通用 HTTP 响应辅助函数
 * 依赖: Node.js 内置 fs
 */
import { createReadStream, existsSync, statSync } from "fs";

export function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

export function serveStaticFile(res, filePath, contentType) {
  if (!existsSync(filePath)) { res.writeHead(404); res.end(); return; }
  const stat = statSync(filePath);
  res.writeHead(200, { "Content-Type": contentType, "Content-Length": stat.size, "Accept-Ranges": "bytes" });
  createReadStream(filePath).pipe(res);
}

export function serveMediaFile(req, res, filePath, contentType) {
  if (!existsSync(filePath)) { res.writeHead(404); res.end(); return; }
  const stat = statSync(filePath);
  if (!stat.isFile()) { res.writeHead(404); res.end(); return; }

  const commonHeaders = { "Content-Type": contentType, "Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600" };
  const range = req.headers.range;
  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(String(range).trim());
    if (!match) { res.writeHead(416, { ...commonHeaders, "Content-Range": `bytes */${stat.size}` }); res.end(); return; }
    let start = match[1] ? Number(match[1]) : 0;
    let end = match[2] ? Number(match[2]) : stat.size - 1;
    if (!match[1] && match[2]) { const suffixLength = Number(match[2]); start = Math.max(0, stat.size - suffixLength); end = stat.size - 1; }
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end >= stat.size || start > end) {
      res.writeHead(416, { ...commonHeaders, "Content-Range": `bytes */${stat.size}` }); res.end(); return;
    }
    res.writeHead(206, { ...commonHeaders, "Content-Length": end - start + 1, "Content-Range": `bytes ${start}-${end}/${stat.size}` });
    if (req.method === "HEAD") { res.end(); return; }
    createReadStream(filePath, { start, end }).pipe(res);
    return;
  }

  res.writeHead(200, { ...commonHeaders, "Content-Length": stat.size });
  if (req.method === "HEAD") { res.end(); return; }
  createReadStream(filePath).pipe(res);
}
