/**
 * Flat ESLint config (ESLint 9+ / typescript-eslint 8+ require flat config
 * — there is no `.eslintrc` fallback). Previously shared via a monorepo
 * package (`@platform/eslint-config`); inlined here since this repo no
 * longer has sibling workspaces to share it with.
 */
const js = require("@eslint/js");
const tseslintPlugin = require("@typescript-eslint/eslint-plugin");
const tsParser = require("@typescript-eslint/parser");
const prettierConfig = require("eslint-config-prettier");
const globals = require("globals");

module.exports = [
  js.configs.recommended,
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsParser,
      globals: { ...globals.node, ...globals.es2022 },
    },
    plugins: { "@typescript-eslint": tseslintPlugin },
    rules: {
      ...tseslintPlugin.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/**/*.ts", "test/**/*.ts"],
    languageOptions: {
      parserOptions: {
        project: "./tsconfig.eslint.json",
        tsconfigRootDir: __dirname,
      },
    },
  },
  {
    files: ["test/**/*.ts"],
    languageOptions: {
      globals: globals.jest,
    },
  },
  prettierConfig,
  {
    ignores: ["dist/**"],
  },
];
