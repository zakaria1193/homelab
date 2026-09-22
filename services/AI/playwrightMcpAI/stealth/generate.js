#!/usr/bin/env node
/**
 * Flattens puppeteer-extra-plugin-stealth into artefacts playwright-mcp can eat.
 *
 * playwright-extra's `chromium.use(plugin)` only works when *your* process owns
 * the launch call, and @playwright/mcp owns its own. But every evasion applies
 * itself through exactly two public hooks:
 *
 *   onPageCreated(page) -> page.evaluateOnNewDocument(fn, ...args)
 *   beforeLaunch(options) -> mutates options.args / options.ignoreDefaultArgs
 *
 * So we hand each evasion a fake page and a fake options object, record what it
 * asks for, and emit:
 *
 *   stealth-init.js    - one script for `playwright-mcp --init-script`
 *   stealth-launch.json - args/ignoreDefaultArgs for `browser.launchOptions`
 *
 * Capturing the *wrapper* function means `withUtils`-based evasions serialise
 * themselves for free: their utils and inner function are already strings in the
 * payload by the time it reaches evaluateOnNewDocument.
 */

'use strict';

const fs = require('fs');
const path = require('path');

// Evasions that patch the page. Order matters: utils are re-materialised per
// script, but `navigator.webdriver` should land before anything reads it.
const PAGE_EVASIONS = [
  'navigator.webdriver',
  'chrome.app',
  'chrome.csi',
  'chrome.loadTimes',
  'chrome.runtime',
  'iframe.contentWindow',
  'media.codecs',
  'navigator.hardwareConcurrency',
  'navigator.languages',
  'navigator.permissions',
  'navigator.plugins',
  'navigator.vendor',
  'webgl.vendor',
  'window.outerdimensions',
];

// Evasions that only shape the launch command line.
const LAUNCH_EVASIONS = ['navigator.webdriver', 'defaultArgs'];

// Deliberately excluded, see README:
//   user-agent-override - CDP Network.setUserAgentOverride, not an init script.
//                         Moot for headful real Chrome, which has no "Headless"
//                         to strip; locale/UA are set via the mcp config instead.
//   sourceurl           - rewrites puppeteer's own evaluate call sites.

function load(name) {
  return require(`puppeteer-extra-plugin-stealth/evasions/${name}`)();
}

async function collectPageScripts() {
  const out = [];
  for (const name of PAGE_EVASIONS) {
    const plugin = load(name);
    const captured = [];
    const fakePage = {
      evaluateOnNewDocument: async (fn, ...args) => {
        captured.push({ fn, args });
      },
    };
    // Some evasions reach for these; keep them harmless no-ops.
    fakePage.evaluate = fakePage.evaluateOnNewDocument;
    fakePage.setUserAgent = async () => {};

    await plugin.onPageCreated(fakePage);

    if (!captured.length) {
      throw new Error(`evasion ${name} registered no init script - plugin API changed`);
    }
    for (const { fn, args } of captured) {
      const body = typeof fn === 'string' ? fn : fn.toString();
      out.push(
        `/* ${name} */\n` +
          `try {\n` +
          `  (${body}).apply(null, ${JSON.stringify(args)});\n` +
          `} catch (e) {\n` +
          `  /* an evasion must never break the page */\n` +
          `}`
      );
    }
  }
  return out;
}

async function collectLaunchOptions() {
  const options = { args: [], ignoreDefaultArgs: [] };
  for (const name of LAUNCH_EVASIONS) {
    const plugin = load(name);
    if (typeof plugin.beforeLaunch === 'function') {
      await plugin.beforeLaunch(options);
    }
  }
  return options;
}

async function main() {
  const scripts = await collectPageScripts();
  const launch = await collectLaunchOptions();
  const version = require('puppeteer-extra-plugin-stealth/package.json').version;

  const header =
    `/**\n` +
    ` * GENERATED - do not edit. Run \`make stealth\` in services/AI/playwrightMcpAI.\n` +
    ` * Source: puppeteer-extra-plugin-stealth@${version}\n` +
    ` * Evasions: ${PAGE_EVASIONS.join(', ')}\n` +
    ` */\n`;

  const bundle = `${header}\n${scripts.join('\n\n')}\n`;
  const outDir = __dirname;
  fs.writeFileSync(path.join(outDir, 'stealth-init.js'), bundle, 'utf8');
  fs.writeFileSync(
    path.join(outDir, 'stealth-launch.json'),
    JSON.stringify({ _generatedFrom: `puppeteer-extra-plugin-stealth@${version}`, ...launch }, null, 2) + '\n',
    'utf8'
  );

  console.log(`[stealth] ${PAGE_EVASIONS.length} evasions -> stealth-init.js (${bundle.length} bytes)`);
  console.log(`[stealth] launch args: ${JSON.stringify(launch.args)}`);
  console.log(`[stealth] ignoreDefaultArgs: ${JSON.stringify(launch.ignoreDefaultArgs)}`);
}

main().catch((err) => {
  console.error('[stealth] generation failed:', err);
  process.exit(1);
});
