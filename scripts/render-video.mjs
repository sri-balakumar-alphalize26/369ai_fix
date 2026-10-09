// Renders video/scene.html to public/media/hero.mp4 (+ a poster still).
// Every CSS animation in the scene is paused and seeked to each frame's time,
// so the output is frame-exact and loops seamlessly.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import puppeteer from 'puppeteer-core';
import ffmpeg from 'ffmpeg-static';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = path.join(root, 'public', 'media');
mkdirSync(out, { recursive: true });

const FPS = 30;
const DURATION = 8;
const POSTER_AT = 4.9; // seconds: repaired screen, ₹0 badge visible

const chrome = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].find((p) => p && existsSync(p));
if (!chrome) throw new Error('No Chrome found. Set CHROME_PATH.');

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: ['--hide-scrollbars'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(path.join(root, 'video', 'scene.html')).href, { waitUntil: 'networkidle0' });
await page.evaluate(() => document.fonts.ready);

const seek = (t) => page.evaluate((ms) => {
  for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; }
}, t * 1000);

// `npm run render:video -- --stills` writes a few frames for a quick check instead.
if (process.argv.includes('--stills')) {
  const dir = path.join(root, 'video', 'frames');
  mkdirSync(dir, { recursive: true });
  for (const t of [0.8, 2.4, 3.4, 4.9, 6.8]) {
    await seek(t);
    await page.screenshot({ type: 'jpeg', quality: 80, path: path.join(dir, `t${t}.jpg`) });
  }
  await browser.close();
  console.log('Stills in video/frames');
  process.exit(0);
}

const enc = spawn(ffmpeg, [
  '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'slow',
  '-movflags', '+faststart', '-an', path.join(out, 'hero.mp4'),
], { stdio: ['pipe', 'inherit', 'inherit'] });

const frames = FPS * DURATION;
for (let i = 0; i < frames; i++) {
  await seek(i / FPS);
  const buf = await page.screenshot({ type: 'png' });
  if (!enc.stdin.write(buf)) await new Promise((r) => enc.stdin.once('drain', r));
  if (i % 30 === 0) process.stdout.write(`frame ${i}/${frames}\n`);
}
enc.stdin.end();
await new Promise((r) => enc.on('close', r));

await seek(POSTER_AT);
await page.screenshot({ type: 'jpeg', quality: 88, path: path.join(out, 'hero.jpg') });

await browser.close();
console.log('Wrote public/media/hero.mp4 and hero.jpg');
