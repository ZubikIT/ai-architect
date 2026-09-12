#!/usr/bin/env node
/**
 * shots.js — снимки страниц для презентаций (локально, puppeteer-core + Chrome).
 *
 *   node scripts/shots.js <out-dir> <spec.json>
 *
 * spec.json — массив: { url, name, wait?, click?, scroll?, full? }
 *   click   — CSS-селектор кнопки, которую надо нажать до снимка (баннер cookie)
 *   scroll  — на сколько пикселей прокрутить перед снимком
 *   full    — снимать всю страницу, а не первый экран
 *
 * Chrome берётся из /opt/puppeteer (Chrome for Testing): snap-сборка не годится,
 * она не читает файлы из скрытых каталогов $HOME.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire('/home/a.zubik/.local/opt/node-v22.23.2-linux-x64/lib/node_modules/@mermaid-js/mermaid-cli/');
const puppeteer = require('puppeteer-core');

const [outDir, specFile] = process.argv.slice(2);
if (!outDir || !specFile) {
  console.error('использование: node scripts/shots.js <out-dir> <spec.json>');
  process.exit(1);
}

const chrome = fs.readdirSync('/opt/puppeteer/chrome')
  .map((d) => `/opt/puppeteer/chrome/${d}/chrome-linux64/chrome`)
  .find((p) => fs.existsSync(p));

const spec = JSON.parse(fs.readFileSync(specFile, 'utf8'));
fs.mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: chrome,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--hide-scrollbars'],
  defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 2 },
});

for (const s of spec) {
  const page = await browser.newPage();
  const file = path.join(outDir, `${s.name}.png`);
  try {
    await page.goto(s.url, { waitUntil: 'networkidle2', timeout: 45000 });
    if (s.click) {
      // Баннеры согласия перекрывают первый экран — жмём и ждём анимацию.
      await page.evaluate((sel) => {
        const el = [...document.querySelectorAll('button, a')]
          .find((b) => b.matches(sel) || b.textContent.trim() === sel);
        if (el) el.click();
      }, s.click);
      await new Promise((r) => setTimeout(r, 800));
    }
    if (s.scroll) {
      await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'instant' }), s.scroll);
      await new Promise((r) => setTimeout(r, 900));
    }
    await new Promise((r) => setTimeout(r, s.wait ?? 600));
    await page.screenshot({ path: file, fullPage: !!s.full });
    const kb = Math.round(fs.statSync(file).size / 1024);
    console.log(`  ${s.name.padEnd(24)} ${kb} КБ`);
  } catch (e) {
    console.log(`  ${s.name.padEnd(24)} НЕ СНЯЛОСЬ: ${e.message.split('\n')[0]}`);
  } finally {
    await page.close();
  }
}

await browser.close();
