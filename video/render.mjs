// 使い方:
//   node render.mjs stills 1.5,8,13,18,24,29   → out/stills/ に静止画（絵コンテ）
//   node render.mjs video                     → out/inward_lens_30s.mp4（＋10秒版）
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
// 対象のページ・データ・出力名は環境変数で切り替える（既定は円目線とドル目線の動画）
const PAGE = process.env.PAGE || 'inward_lens.html';
const DATA = process.env.DATA || 'data/inward_by_year.json';
const NAME = process.env.NAME || 'inward_lens_30s';
const data = JSON.parse(readFileSync(path.join(here, DATA), 'utf8'));
const FPS = 30;
const [mode = 'stills', arg = '1.5,2.8,8,13,18,24,29'] = process.argv.slice(2);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
await page.goto('file://' + path.join(here, PAGE));
await page.evaluate(d => window.setData(d), data);
const canvas = await page.$('#c');
// ページのキャンバスの大きさに合わせる（縦長・横長どちらにも対応）
const size = await page.evaluate(() => ({ width: document.getElementById('c').width, height: document.getElementById('c').height }));
await page.setViewportSize(size);

async function shot(t, file) {
  await page.evaluate(t => window.renderAt(t), t);
  await canvas.screenshot({ path: file });
}

if (mode === 'stills') {
  const dir = path.join(here, 'out/stills', NAME);
  mkdirSync(dir, { recursive: true });
  for (const t of arg.split(',').map(Number)) {
    const f = path.join(dir, `t${String(t.toFixed(1)).padStart(4, '0')}.png`);
    await shot(t, f);
    console.log(f);
  }
} else {
  const dir = path.join(here, 'out/frames');
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const duration = await page.evaluate(() => window.DURATION);
  const n = Math.round(duration * FPS);
  for (let i = 0; i < n; i++) {
    await shot(i / FPS, path.join(dir, `${String(i).padStart(5, '0')}.png`));
    if (i % 150 === 0) console.log(`frame ${i}/${n}`);
  }
  const out = path.join(here, `out/${NAME}.mp4`);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', path.join(dir, '%05d.png'),
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart', out]);
  console.log(out);
}
await browser.close();
