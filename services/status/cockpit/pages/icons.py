"""The cockpit's service icons: a JS `ICONS` map of inline SVGs, keyed by
entry name, plus aliases. Joined into pages/main.py's script at {ICONS_JS}."""

ICONS_JS = """// Inline so the page keeps working with no outbound access (xterm.js on the
// terminal page is the one exception in this service).
const ICONS = {
  // A shell: what you get is a prompt, so draw a prompt.
  terminal: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="0.75" y="2.25" width="14.5" height="11.5" rx="2"
      fill="none" stroke="currentColor" stroke-width="1.3"/>
    <path d="M4 6.2 L6.4 8 L4 9.8 M8.4 10.4 H11.6" fill="none" stroke="currentColor"
      stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // The Claude mark: a burst of tapered rays.
  claude: `<svg class="ico claude" viewBox="0 0 16 16" aria-hidden="true">${
    Array.from({ length: 11 }, (_, i) => {
      const a = (i * 360) / 11;
      return `<rect x="7.35" y="0.9" width="1.3" height="7.1" rx="0.65"
        fill="#D97757" transform="rotate(${a} 8 8)"/>`;
    }).join("")}</svg>`,
  // Antigravity: a body breaking upward out of its orbit. Sits next to the
  // Claude mark on the session chips, so it has to read differently at 15px -
  // hence a ring plus an arrow rather than another radial burst.
  antigravity: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <ellipse cx="8" cy="11" rx="5.6" ry="2.4" fill="none" stroke="#4285F4"
      stroke-width="1.3" opacity=".55"/>
    <path d="M8 12.4 V3.2 M5.1 6 L8 3 L10.9 6" fill="none" stroke="#4285F4"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Two sheets: the copy affordance on an address you paste elsewhere.
  copy: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="5.4" y="5.4" width="8.1" height="8.1" rx="1.6" fill="none"
      stroke="currentColor" stroke-width="1.3"/>
    <path d="M10.6 5.4V4a1.6 1.6 0 0 0-1.6-1.6H4a1.6 1.6 0 0 0-1.6 1.6v5a1.6 1.6 0 0 0 1.6 1.6h1.4"
      fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  // The Raspberry Pi berry: also used as the "runs on the Pi" badge.
  raspberry: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><g fill="#C51A4A">
    <path d="M7.6 5.1C6.7 3.6 5.1 2.9 3.6 3.2c0 1.6 1.1 3 2.6 3.4z"/>
    <path d="M8.4 5.1C9.3 3.6 10.9 2.9 12.4 3.2c0 1.6-1.1 3-2.6 3.4z"/>
    <circle cx="8" cy="7.1" r="1.7"/><circle cx="5.9" cy="8.6" r="1.7"/>
    <circle cx="10.1" cy="8.6" r="1.7"/><circle cx="6.9" cy="11" r="1.7"/>
    <circle cx="9.1" cy="11" r="1.7"/></g></svg>`,
  // Home Assistant: the blue house.
  "home-assistant": `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 1.3 15 7.9v6.1c0 .4-.3.7-.7.7H1.7c-.4 0-.7-.3-.7-.7V7.9z" fill="#18BCF2"/>
    <path d="M8 6.4v6.6M5.3 9.1v3.9M10.7 9.1v3.9" stroke="#fff" stroke-width="1.15"
      stroke-linecap="round"/></svg>`,
  // Jellyfin: the two-tone gradient jelly.
  jellyfin: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <defs><linearGradient id="jf" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#AA5CC3"/><stop offset="1" stop-color="#00A4DC"/>
    </linearGradient></defs>
    <path d="M8 1.4c1.5 0 5.9 7.3 5.2 8.7-.8 1.4-9.6 1.4-10.4 0C2.1 8.7 6.5 1.4 8 1.4z"
      fill="url(#jf)" opacity=".45"/>
    <path d="M8 6.3c.8 0 3.4 4.3 3 5-.4.8-5.6.8-6 0-.4-.7 2.2-5 3-5z" fill="url(#jf)"/></svg>`,
  // Docker: containers stacked on the hull of the whale.
  docker: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><g fill="#2496ED">
    <rect x="3" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="5.6" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="8.2" y="6.5" width="2.2" height="2.2" rx=".3"/>
    <rect x="5.6" y="3.9" width="2.2" height="2.2" rx=".3"/>
    <path d="M1 9.4h13.1c0 2.5-2 4.2-5 4.2-3.5 0-6.8-1.2-8.1-4.2z"/></g></svg>`,
  // The *arr suite: same silhouette family, told apart by what they hunt.
  sonarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="3.6" width="13.6" height="9" rx="1.6" fill="none" stroke="#35C5F4"
      stroke-width="1.4"/><path d="M5.4 14.4h5.2M6.6 1.6 8 3.4l1.4-1.8" fill="none"
      stroke="#35C5F4" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  radarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="5.4" width="13.6" height="8.4" rx="1.4" fill="none" stroke="#FFC230"
      stroke-width="1.4"/><path d="M1.6 3.1 13.4 1.6l.3 2.2L1.9 5.3z" fill="#FFC230"/>
    <path d="M5.4 2.6 6.5 4.6M9 2.2l1.1 2" stroke="#0d1117" stroke-width="1"/></svg>`,
  readarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.6 2.4h4.2c1.2 0 2.2.7 2.2 1.6v9.6c0-.9-1-1.6-2.2-1.6H1.6z" fill="#C4392E"/>
    <path d="M14.4 2.4h-4.2c-1.2 0-2.2.7-2.2 1.6v9.6c0-.9 1-1.6 2.2-1.6h4.2z" fill="#E8654F"/>
    </svg>`,
  prowlarr: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="6.9" cy="6.9" r="4.7" fill="none" stroke="#E66000" stroke-width="1.5"/>
    <path d="M10.4 10.4 14.2 14.2" stroke="#E66000" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`,
  // Transmission: a torrent client is a download, so draw the download.
  transmission: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.7" fill="none" stroke="#D33A2C" stroke-width="1.4"/>
    <path d="M8 4.2v6M5.4 7.6 8 10.3l2.6-2.7" fill="none" stroke="#D33A2C"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  // Karakeep: things you kept, so a bookmark.
  karakeep: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.6 1.9h8.8c.5 0 .9.4.9.9v11.3L8 11.2l-5.3 2.9V2.8c0-.5.4-.9.9-.9z"
      fill="#16A394"/></svg>`,
  // Meilisearch: the search box behind Karakeep.
  meilisearch: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <defs><linearGradient id="ms" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#FF5CAA"/><stop offset="1" stop-color="#7700FF"/>
    </linearGradient></defs>
    <circle cx="6.9" cy="6.9" r="4.7" fill="none" stroke="url(#ms)" stroke-width="1.5"/>
    <path d="M10.4 10.4 14.2 14.2" stroke="url(#ms)" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`,
  // Headless Chrome: the four-colour wheel.
  chrome: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="6.8" fill="#4285F4"/>
    <path d="M8 1.2a6.8 6.8 0 0 1 5.9 3.4H8a3.4 3.4 0 0 0-3 1.8L2.2 4.1A6.8 6.8 0 0 1 8 1.2z"
      fill="#EA4335"/>
    <path d="M2.2 4.1 5 6.4a3.4 3.4 0 0 0 .1 3.3l-2.9 5A6.8 6.8 0 0 1 2.2 4.1z" fill="#FBBC05"/>
    <path d="M13.9 4.6A6.8 6.8 0 0 1 8 14.8h-.4l2.9-5A3.4 3.4 0 0 0 8 4.6z" fill="#34A853"/>
    <circle cx="8" cy="8" r="2.9" fill="#fff"/><circle cx="8" cy="8" r="2.2" fill="#4285F4"/>
    </svg>`,
  // Hermes: the messenger, so the thing a message flies as.
  hermes: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M14.6 1.6 1.4 6.9l4.4 1.9z" fill="#D4A017"/>
    <path d="M14.6 1.6 5.8 8.8l.6 5.1 2.4-3.4z" fill="#A87C11"/></svg>`,
  // OpenHands: an agent that drives a computer for you.
  openhands: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 1.4v2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
    <rect x="2.1" y="3.6" width="11.8" height="9.4" rx="2.6" fill="none" stroke="currentColor"
      stroke-width="1.3"/>
    <circle cx="5.8" cy="8.3" r="1.15" fill="currentColor"/>
    <circle cx="10.2" cy="8.3" r="1.15" fill="currentColor"/></svg>`,
  // A protocol bridge (ACP, MCP): two links of a chain.
  bridge: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M6.6 9.4a2.8 2.8 0 0 1 0-3.9l2-2a2.8 2.8 0 0 1 3.9 3.9l-.9.9" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>
    <path d="M9.4 6.6a2.8 2.8 0 0 1 0 3.9l-2 2a2.8 2.8 0 0 1-3.9-3.9l.9-.9" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // A job hunt: the briefcase.
  briefcase: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="1.2" y="4.9" width="13.6" height="8.6" rx="1.4" fill="none" stroke="currentColor"
      stroke-width="1.3"/>
    <path d="M5.7 4.6V3.4c0-.6.5-1 1.1-1h2.4c.6 0 1.1.4 1.1 1v1.2M1.4 8.6h13.2" fill="none"
      stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  // The cockpit itself: a gauge.
  cockpit: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.8 12.4a6.9 6.9 0 1 1 12.4 0" fill="none" stroke="currentColor"
      stroke-width="1.4" stroke-linecap="round"/>
    <path d="M8 11.4 11.2 6.2" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="8" cy="11.9" r="1.2" fill="currentColor"/></svg>`,
  // SSH: the key.
  ssh: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="5.1" cy="10.9" r="3.1" fill="none" stroke="currentColor" stroke-width="1.35"/>
    <path d="M7.3 8.7 13.6 2.4M11.4 4.6l1.6 1.6M9.8 6.2l1.6 1.6" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // Upgrades: what lands on the box.
  upgrade: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M8 10.6V1.9M4.8 5.1 8 1.9l3.2 3.2" fill="none" stroke="currentColor"
      stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M1.9 10.4v2.6c0 .6.5 1.1 1.1 1.1h10c.6 0 1.1-.5 1.1-1.1v-2.6" fill="none"
      stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>`,
  // A log file on disk.
  logfile: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.1 1.6h6L13 5.4v9c0 .6-.5 1-1.1 1H3.1c-.6 0-1.1-.4-1.1-1V2.6c0-.6.5-1 1.1-1z"
      fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
    <path d="M8.9 1.8v3.6h3.7M4.6 8.6h6M4.6 11.1h6M4.6 13h3.6" fill="none"
      stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`,
  // Obsidian: the faceted gem / crystal mark.
  obsidian: `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M5.4 1.5 L10.6 1.5 L14 5.5 L8 14.5 L2 5.5 Z" fill="#7C3AED" opacity=".25"/>
    <path d="M5.4 1.5 L10.6 1.5 L14 5.5 L8 14.5 L2 5.5 Z M5.4 1.5 L8 6 L10.6 1.5 M8 6 L8 14.5 M8 6 L2 5.5 M8 6 L14 5.5"
      fill="none" stroke="#A78BFA" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

// Entries are named after what they are, so the icon usually needs no config:
// the name (or an alias of it) is the lookup key, and `icon = ...` overrides.
Object.assign(ICONS, {
  "jellyfin-web": ICONS.jellyfin,
  "karakeep-meilisearch": ICONS.meilisearch,
  "karakeep-chrome": ICONS.chrome,
  "raspberry-pi": ICONS.raspberry,
  "hermes-ai": ICONS.hermes,
  "openhands-ai": ICONS.openhands,
  "arr-mcp-backend": ICONS.bridge,
  "ai-job-search": ICONS.briefcase,
  "homelab-cockpit": ICONS.cockpit,
  "ai-services-upgrade": ICONS.upgrade,
  "unattended-upgrades": ICONS.upgrade,
  "obsidian-sync": ICONS.obsidian,
});
"""
