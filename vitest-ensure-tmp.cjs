const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const tmpDirPath = path.resolve(__dirname, ".vitest/tmp");
fs.mkdirSync(tmpDirPath, { recursive: true });

const setTmpDir = (value) => {
  process.env.TMPDIR = value;
  process.env.TMP = value;
  process.env.TEMP = value;
};

setTmpDir(tmpDirPath);

if (os.tmpdir() !== tmpDirPath) {
  os.tmpdir = () => tmpDirPath;
}
