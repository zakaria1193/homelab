#!/usr/bin/env node
/**
 * Renders playwright-mcp.config.json from the service .env plus the generated
 * stealth-launch.json.
 *
 * Only settings the CLI cannot express live here (launch args,
 * ignoreDefaultArgs, channel, context options). Host/port/browser/headless/
 * isolated stay as CLI flags in the unit file, so nothing is specified twice
 * and there is no precedence question between the two.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const here = __dirname;
const svc = path.dirname(here);

const env = (k, d) => {
  const v = process.env[k];
  return v === undefined || v === '' ? d : v;
};

const launch = JSON.parse(fs.readFileSync(path.join(here, 'stealth-launch.json'), 'utf8'));

const stealthOn = env('PLAYWRIGHT_MCP_STEALTH', 'true') === 'true';
const wmClass = env('PLAYWRIGHT_MCP_WM_CLASS', 'PlaywrightHeadful');
const headless = env('PLAYWRIGHT_MCP_HEADLESS', 'true') === 'true';

const args = [];
// The WM_CLASS marker is what i3 assigns on. Chrome and Chromium both honour
// --class; it is independent of the profile directory, so the window rule keeps
// working no matter where the profile lives.
if (!headless) args.push(`--class=${wmClass}`);
if (stealthOn) args.push(...launch.args);

const browser = { launchOptions: {} };
if (args.length) browser.launchOptions.args = args;
if (stealthOn && launch.ignoreDefaultArgs && launch.ignoreDefaultArgs.length) {
  browser.launchOptions.ignoreDefaultArgs = launch.ignoreDefaultArgs;
}

const channel = env('PLAYWRIGHT_MCP_CHANNEL', '');
if (channel) browser.launchOptions.channel = channel;

const contextOptions = {};
const locale = env('PLAYWRIGHT_MCP_LOCALE', '');
if (locale) contextOptions.locale = locale;
const viewport = env('PLAYWRIGHT_MCP_VIEWPORT', '');
if (viewport) {
  const m = /^(\d+)x(\d+)$/.exec(viewport);
  if (!m) throw new Error(`PLAYWRIGHT_MCP_VIEWPORT must look like 1280x800, got "${viewport}"`);
  contextOptions.viewport = { width: Number(m[1]), height: Number(m[2]) };
}
if (Object.keys(contextOptions).length) browser.contextOptions = contextOptions;

const out = path.join(svc, 'playwright-mcp.config.json');
fs.writeFileSync(out, JSON.stringify({ browser }, null, 2) + '\n', 'utf8');

console.log(`[config] wrote ${out}`);
console.log(`[config] stealth=${stealthOn} headless=${headless} class=${headless ? '(n/a)' : wmClass}`);
