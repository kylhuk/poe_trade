import type {
  Service, PriceCheckResponse, StashTab, AppMessage, PoeItem
} from '@/types/api';

const ago = (mins: number) => new Date(Date.now() - mins * 60000).toISOString();

export const mockServices: Service[] = [
  { id: 's1', name: 'Public Stash Crawler', description: 'Crawls GGG public stash API every 5 min', status: 'running', uptime: 86400, lastCrawl: ago(7), rowsInDb: 2_847_392, containerInfo: 'poe-crawler:latest', type: 'crawler' },
  { id: 's2', name: 'Currency Exchange Crawler', description: 'Hourly historical exchange rates', status: 'running', uptime: 72000, lastCrawl: ago(52), rowsInDb: 184_720, containerInfo: 'poe-exchange:latest', type: 'crawler' },
  { id: 's3', name: 'FairValue Engine', description: 'Computes fair values from stash + exchange data', status: 'running', uptime: 43200, lastCrawl: ago(6), rowsInDb: 12_480, containerInfo: null, type: 'analytics' },
  { id: 's4', name: 'Gem Value Model', description: 'ML model for gem pricing anomalies', status: 'stopped', uptime: null, lastCrawl: ago(180), rowsInDb: 8_240, containerInfo: 'gem-model:v2.1', type: 'docker' },
  { id: 's5', name: 'Stale Listing Scanner', description: 'Scans for dormant seller opportunities', status: 'running', uptime: 36000, lastCrawl: ago(3), rowsInDb: 520, containerInfo: null, type: 'worker' },
  { id: 's6', name: 'Shipment Optimizer', description: 'Kingsmarch shipment EV calculator', status: 'error', uptime: null, lastCrawl: ago(420), rowsInDb: 1_200, containerInfo: 'shipment-opt:latest', type: 'docker' },
  { id: 's7', name: 'Heist Loot Router', description: 'Routes heist drops to bins', status: 'running', uptime: 18000, lastCrawl: ago(1), rowsInDb: null, containerInfo: null, type: 'worker' },
  { id: 's8', name: 'Session Controller', description: 'Activity switching recommendations', status: 'running', uptime: 7200, lastCrawl: ago(2), rowsInDb: null, containerInfo: null, type: 'analytics' },
];

export const mockPriceCheck: PriceCheckResponse = {
  predictedValue: 3.5,
  currency: 'divine',
  confidence: 78,
  comparables: [
    { name: 'Similar Rare Helmet (+2 Minion, 90 life)', price: 3.2, currency: 'div' },
    { name: 'Similar Rare Helmet (+2 Minion, 85 life, res)', price: 4.0, currency: 'div' },
    { name: 'Similar Rare Helmet (+2 Minion, 70 life)', price: 2.8, currency: 'div' },
  ],
};

// Helper: PoE frameType → number (0=Normal,1=Magic,2=Rare,3=Unique,4=Gem,5=Currency)
const poeItem = (overrides: Partial<PoeItem> & { id: string; typeLine: string; icon: string; x: number; y: number; w: number; h: number; frameType: number }): PoeItem => ({
  name: '',
  ...overrides,
});

export const mockStashTabs: StashTab[] = [
  {
    id: 'st1', name: 'Trade 1', type: 'normal',
    items: [
      poeItem({ id: 'i1', name: 'Mageblood', typeLine: 'Heavy Belt', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQmVsdHMvTWFnZWJsb29kIiwidyI6MiwiaCI6MSwic2NhbGUiOjF9XQ/24aee6e493/Mageblood.png', x: 0, y: 0, w: 2, h: 1, frameType: 3, estimatedPrice: 185, listedPrice: 180, currency: 'div', priceEvaluation: 'well_priced', estimatedPriceConfidence: 92, priceDeltaChaos: 500, priceDeltaPercent: 2.8 }),
      poeItem({ id: 'i2', name: 'Ashes of the Stars', typeLine: 'Onyx Amulet', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQW11bGV0cy9Bc2hlc09mVGhlU3RhcnMiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/788a738da1/AshesOfTheStars.png', x: 2, y: 0, w: 1, h: 1, frameType: 3, estimatedPrice: 12, listedPrice: 15, currency: 'div', priceEvaluation: 'mispriced', estimatedPriceConfidence: 88, priceDeltaChaos: -450, priceDeltaPercent: -20 }),
      poeItem({ id: 'i3', name: 'Bottled Faith', typeLine: 'Sulphur Flask', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvRmxhc2tzL0JvdHRsZWRGYWl0aCIsInciOjEsImgiOjIsInNjYWxlIjoxfV0/e258a53daf/BottledFaith.png', x: 0, y: 1, w: 1, h: 2, frameType: 3, estimatedPrice: 5.2, listedPrice: 5, currency: 'div', priceEvaluation: 'well_priced', estimatedPriceConfidence: 90, priceDeltaChaos: 30, priceDeltaPercent: 4 }),
      poeItem({ id: 'i4', name: '', typeLine: 'Large Cluster Jewel', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL0NsdXN0ZXJKZXdlbDMiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/df2e61a16e/ClusterJewel3.png', x: 3, y: 0, w: 1, h: 1, frameType: 2, estimatedPrice: 2.5, listedPrice: 1.8, currency: 'div', priceEvaluation: 'could_be_better', estimatedPriceConfidence: 72, priceDeltaChaos: 105, priceDeltaPercent: 38.9, explicitMods: ['Added Small Passive Skills grant: 12% increased Fire Damage', '1 Added Passive Skill is Cremator', '1 Added Passive Skill is Smoking Remains'] }),
      poeItem({ id: 'i5', name: "Watcher's Eye", typeLine: 'Prismatic Jewel', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL0VsZGVyRXllIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/57a138bbfb/ElderEye.png', x: 4, y: 0, w: 1, h: 1, frameType: 3, estimatedPrice: 35, listedPrice: 30, currency: 'div', priceEvaluation: 'could_be_better', estimatedPriceConfidence: 65, priceDeltaChaos: 750, priceDeltaPercent: 16.7 }),
      poeItem({ id: 'i6', name: 'Forbidden Flame', typeLine: 'Cobalt Jewel', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL0ZpcmVTZWVkIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/24e278b4fb/FireSeed.png', x: 1, y: 1, w: 1, h: 1, frameType: 3, estimatedPrice: 8, listedPrice: 8.5, currency: 'div', priceEvaluation: 'well_priced', estimatedPriceConfidence: 85, priceDeltaChaos: -75, priceDeltaPercent: -5.9 }),
      poeItem({ id: 'i7', name: 'Thread of Hope', typeLine: 'Crimson Jewel', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL1RocmVhZE9mSG9wZSIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/6efee3fb78/ThreadOfHope.png', x: 2, y: 1, w: 1, h: 1, frameType: 3, estimatedPrice: 1.0, listedPrice: 0.5, currency: 'div', priceEvaluation: 'mispriced', estimatedPriceConfidence: 82, priceDeltaChaos: 75, priceDeltaPercent: 100 }),
      poeItem({ id: 'i8', name: 'Prism Guardian', typeLine: 'Archon Kite Shield', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQXJtb3Vycy9TaGllbGRzL1ByaXNtR3VhcmRpYW4iLCJ3IjoyLCJoIjozLCJzY2FsZSI6MX1d/48a7d70096/PrismGuardian.png', x: 5, y: 0, w: 2, h: 3, frameType: 3, estimatedPrice: 0.1, listedPrice: 0.08, currency: 'div', priceEvaluation: 'well_priced', estimatedPriceConfidence: 95, priceDeltaChaos: 3, priceDeltaPercent: 25, sockets: [{ group: 0, attr: 'S', sColour: 'R' }, { group: 0, attr: 'S', sColour: 'G' }, { group: 0, attr: 'S', sColour: 'B' }] }),
    ],
  },
  {
    id: 'st2', name: 'Quad Dump', type: 'quad', quadLayout: true,
    items: [
      poeItem({ id: 'q1', name: '', typeLine: 'Divine Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lNb2RWYWx1ZXMiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/e1a54ff97d/CurrencyModValues.png', x: 0, y: 0, w: 1, h: 1, frameType: 5, stackSize: 12, estimatedPrice: 1, listedPrice: 1, currency: 'div', priceEvaluation: 'well_priced', estimatedPriceConfidence: 99 }),
      poeItem({ id: 'q2', name: 'Void Battery', typeLine: 'Prophecy Wand', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvV2VhcG9ucy9PbmVIYW5kV2VhcG9ucy9XYW5kcy9Wb2lkQmF0dGVyeSIsInciOjEsImgiOjMsInNjYWxlIjoxfV0/1a08c0d12d/VoidBattery.png', x: 3, y: 1, w: 1, h: 3, frameType: 3, estimatedPrice: 4.5, listedPrice: 3.8, currency: 'div', priceEvaluation: 'could_be_better', estimatedPriceConfidence: 78, priceDeltaChaos: 105, priceDeltaPercent: 18.4 }),
      poeItem({ id: 'q3', name: 'Inspired Learning', typeLine: 'Crimson Jewel', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvSmV3ZWxzL0luc3BpcmVkTGVhcm5pbmciLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/0c24c3b4cd/InspiredLearning.png', x: 8, y: 0, w: 1, h: 1, frameType: 3, estimatedPrice: 1.2, listedPrice: 2.0, currency: 'div', priceEvaluation: 'mispriced', estimatedPriceConfidence: 80, priceDeltaChaos: -120, priceDeltaPercent: -40 }),
      poeItem({ id: 'q4', name: '', typeLine: 'Chaos Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxSYXJlIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/d119a0d734/CurrencyRerollRare.png', x: 20, y: 0, w: 1, h: 1, frameType: 5, stackSize: 20, estimatedPrice: 0.15, currency: 'div', priceEvaluation: 'could_be_better', estimatedPriceConfidence: 99 }),
      poeItem({ id: 'q5', name: '', typeLine: 'Exalted Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lBZGRNb2RUb1JhcmUiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/da6e194a62/CurrencyAddModToRare.png', x: 21, y: 0, w: 1, h: 1, frameType: 5, stackSize: 5 }),
    ],
  },
  {
    id: 'st3', name: 'Currency', type: 'currency',
    currencyLayout: {
      sections: ['General', 'Influence', 'League'],
      layout: {
        '0': { x: 10, y: 10, w: 47, h: 47, scale: 1, section: 'General' },
        '1': { x: 62, y: 10, w: 47, h: 47, scale: 1, section: 'General' },
        '2': { x: 114, y: 10, w: 47, h: 47, scale: 1, section: 'General' },
        '3': { x: 166, y: 10, w: 47, h: 47, scale: 1, section: 'General' },
        '4': { x: 218, y: 10, w: 47, h: 47, scale: 1, section: 'General' },
        '5': { x: 270, y: 10, w: 47, h: 47, scale: 1, section: 'General' },
        '6': { x: 10, y: 62, w: 47, h: 47, scale: 1, section: 'General' },
        '7': { x: 62, y: 62, w: 47, h: 47, scale: 1, section: 'General' },
        '8': { x: 114, y: 62, w: 47, h: 47, scale: 1, section: 'General' },
        '9': { x: 166, y: 62, w: 47, h: 47, scale: 1, section: 'General' },
        '10': { x: 218, y: 62, w: 47, h: 47, scale: 1, section: 'General' },
        '11': { x: 270, y: 62, w: 47, h: 47, scale: 1, section: 'General' },
        '12': { x: 10, y: 114, w: 47, h: 47, scale: 1, section: 'General' },
        '13': { x: 62, y: 114, w: 47, h: 47, scale: 1, section: 'General' },
        '14': { x: 114, y: 114, w: 47, h: 47, scale: 1, section: 'General' },
        '15': { x: 166, y: 114, w: 47, h: 47, scale: 1, section: 'General' },
      },
    },
    items: [
      poeItem({ id: 'c0', name: '', typeLine: 'Chaos Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxSYXJlIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/d119a0d734/CurrencyRerollRare.png', x: 0, y: 0, w: 1, h: 1, frameType: 5, stackSize: 347 }),
      poeItem({ id: 'c1', name: '', typeLine: 'Divine Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lNb2RWYWx1ZXMiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/e1a54ff97d/CurrencyModValues.png', x: 1, y: 0, w: 1, h: 1, frameType: 5, stackSize: 23 }),
      poeItem({ id: 'c2', name: '', typeLine: 'Exalted Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lBZGRNb2RUb1JhcmUiLCJ3IjoxLCJoIjoxLCJzY2FsZSI6MX1d/da6e194a62/CurrencyAddModToRare.png', x: 2, y: 0, w: 1, h: 1, frameType: 5, stackSize: 14 }),
      poeItem({ id: 'c3', name: '', typeLine: 'Orb of Alchemy', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lVcGdyYWRlVG9SYXJlIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/5a1e8acb5f/CurrencyUpgradeToRare.png', x: 3, y: 0, w: 1, h: 1, frameType: 5, stackSize: 189 }),
      poeItem({ id: 'c4', name: '', typeLine: 'Orb of Alteration', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxNYWdpYyIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/d6e1e43e70/CurrencyRerollMagic.png', x: 4, y: 0, w: 1, h: 1, frameType: 5, stackSize: 523 }),
      poeItem({ id: 'c5', name: '', typeLine: 'Vaal Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lWYWFsIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/e811fecbce/CurrencyVaal.png', x: 5, y: 0, w: 1, h: 1, frameType: 5, stackSize: 42 }),
      poeItem({ id: 'c6', name: '', typeLine: 'Orb of Fusing', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxTb2NrZXRMaW5rcyIsInciOjEsImgiOjEsInNjYWxlIjoxfV0/7b1246d8d1/CurrencyRerollSocketLinks.png', x: 6, y: 0, w: 1, h: 1, frameType: 5, stackSize: 245 }),
      poeItem({ id: 'c7', name: '', typeLine: 'Jeweller\'s Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxTb2NrZXROdW1iZXJzIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/1c3ceb1295/CurrencyRerollSocketNumbers.png', x: 7, y: 0, w: 1, h: 1, frameType: 5, stackSize: 312 }),
      poeItem({ id: 'c8', name: '', typeLine: 'Chromatic Orb', icon: 'https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxTb2NrZXRDb2xvdXJzIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/33ff594afc/CurrencyRerollSocketColours.png', x: 8, y: 0, w: 1, h: 1, frameType: 5, stackSize: 1024 }),
    ],
  },
];

export const mockMessages: AppMessage[] = [
  { id: 'm1', timestamp: ago(1), severity: 'critical', sourceModule: 'StaleListingArb', message: 'Bottled Faith listed at 32.7% below fair value by dormant seller (8hr inactive)', suggestedAction: 'Buy and exchange unwind immediately' },
  { id: 'm2', timestamp: ago(3), severity: 'warning', sourceModule: 'FairValueEngine', message: 'Headhunter spread widening to 7.1% — possible price movement', suggestedAction: 'Monitor, do not trade until spread narrows' },
  { id: 'm3', timestamp: ago(5), severity: 'info', sourceModule: 'SessionController', message: 'Trade stash approaching capacity (18/24 slots). Processing now yields 3.5 div/hr.', suggestedAction: 'Switch to trade batch' },
  { id: 'm4', timestamp: ago(8), severity: 'critical', sourceModule: 'GemValueModel', message: 'Vaal Grace 21/23 anomaly score 85 — underpriced by 31.8% with strong comparable cluster', suggestedAction: 'Buy immediately, relist at 22 div' },
  { id: 'm5', timestamp: ago(15), severity: 'warning', sourceModule: 'GoldShadowPrice', message: 'Gold fee currently at 14.5c — eating 4.2% of typical trade edge', suggestedAction: 'Use divine denomination to reduce fee impact' },
  { id: 'm6', timestamp: ago(22), severity: 'info', sourceModule: 'ShipmentOptimizer', message: 'Ngakanu shipment ready: EV 4.2 div, 1.8 div/hr after risk', suggestedAction: 'Send shipment if no better threshold expected in next 2 hours' },
  { id: 'm7', timestamp: ago(45), severity: 'info', sourceModule: 'HeistRouter', message: 'Replica Farruls Fur blueprint detected — run priority', suggestedAction: 'Queue blueprint for next heist session' },
  { id: 'm8', timestamp: ago(60), severity: 'warning', sourceModule: 'Public Stash Crawler', message: 'Crawl latency increased to 12 min (target: 5 min)', suggestedAction: 'Check API rate limits and connection' },
];
