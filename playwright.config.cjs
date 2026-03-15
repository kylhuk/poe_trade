const path = require('node:path');

const frontendDir = path.join(__dirname, 'frontend');

module.exports = {
  testDir: path.join(frontendDir, 'src/test/playwright'),
  timeout: 30_000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
  },
  webServer: {
    command: 'npm run qa:dev',
    cwd: frontendDir,
    port: 4173,
    reuseExistingServer: true,
    timeout: 120_000,
  },
};
