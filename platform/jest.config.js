module.exports = {
  rootDir: ".",
  testRegex: ".*\\.spec\\.ts$",
  transform: {
    "^.+\\.ts$": ["ts-jest", { tsconfig: "tsconfig.eslint.json" }],
  },
  testEnvironment: "node",
};
