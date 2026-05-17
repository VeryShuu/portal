import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import a11yPlugin from "eslint-plugin-vuejs-accessibility";
import vuePlugin from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";
import globals from "globals";

const tsRecommended = tseslint.configs["recommended"]?.rules ?? {};
const vueRecommendedConfigs = vuePlugin.configs?.["flat/recommended"] ?? [];

export default [
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "tests/e2e/**",
      "playwright-report/**",
      "coverage/**",
      "**/*.d.ts",
      "scripts/**",
    ],
  },
  js.configs.recommended,
  ...vueRecommendedConfigs,
  {
    files: ["**/*.ts", "**/*.tsx"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
    },
    rules: {
      ...tsRecommended,
      "no-undef": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-empty-object-type": "off",
      "@typescript-eslint/no-unused-expressions": "off",
      "@typescript-eslint/no-this-alias": "off",
      "no-empty": ["warn", { allowEmptyCatch: true }],
      "no-useless-escape": "warn",
      "no-prototype-builtins": "off",
      "no-control-regex": "off",
    },
  },
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsparser,
        ecmaVersion: "latest",
        sourceType: "module",
        extraFileExtensions: [".vue"],
      },
      globals: {
        ...globals.browser,
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "vuejs-accessibility": a11yPlugin,
    },
    rules: {
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "no-undef": "off",
      "no-empty": ["warn", { allowEmptyCatch: true }],

      "vue/multi-word-component-names": "off",
      "vue/no-v-html": "off",

      "vue/html-self-closing": "warn",
      "vue/max-attributes-per-line": "warn",
      "vue/singleline-html-element-content-newline": "warn",
      "vue/multiline-html-element-content-newline": "warn",
      "vue/html-indent": "warn",
      "vue/html-closing-bracket-newline": "warn",
      "vue/html-closing-bracket-spacing": "warn",
      "vue/first-attribute-linebreak": "warn",
      "vue/attributes-order": "warn",
      "vue/attribute-hyphenation": "warn",
      "vue/v-on-event-hyphenation": "warn",
      "vue/component-definition-name-casing": "warn",
      "vue/no-mutating-props": "warn",
      "vue/no-template-shadow": "warn",
      "vue/require-default-prop": "warn",
      "vue/require-explicit-emits": "warn",
      "vue/no-v-text-v-html-on-component": "warn",

      "vuejs-accessibility/alt-text": "warn",
      "vuejs-accessibility/anchor-has-content": "warn",
      "vuejs-accessibility/aria-props": "warn",
      "vuejs-accessibility/aria-role": "warn",
      "vuejs-accessibility/aria-unsupported-elements": "warn",
      "vuejs-accessibility/click-events-have-key-events": "warn",
      "vuejs-accessibility/form-control-has-label": "warn",
      "vuejs-accessibility/heading-has-content": "warn",
      "vuejs-accessibility/iframe-has-title": "warn",
      "vuejs-accessibility/interactive-supports-focus": "warn",
      "vuejs-accessibility/label-has-for": "warn",
      "vuejs-accessibility/media-has-caption": "warn",
      "vuejs-accessibility/mouse-events-have-key-events": "warn",
      "vuejs-accessibility/no-access-key": "warn",
      "vuejs-accessibility/no-aria-hidden-on-focusable": "warn",
      "vuejs-accessibility/no-autofocus": "warn",
      "vuejs-accessibility/no-distracting-elements": "warn",
      "vuejs-accessibility/no-onchange": "warn",
      "vuejs-accessibility/no-redundant-roles": "warn",
      "vuejs-accessibility/no-role-presentation-on-focusable": "warn",
      "vuejs-accessibility/no-static-element-interactions": "warn",
      "vuejs-accessibility/role-has-required-aria-props": "warn",
      "vuejs-accessibility/tabindex-no-positive": "warn",
    },
  },
  {
    files: ["**/*.{js,mjs,cjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  {
    files: ["tests/**/*.{ts,tsx,vue}", "**/*.spec.ts", "**/*.test.ts"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.browser,
        describe: "readonly",
        it: "readonly",
        test: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        beforeAll: "readonly",
        afterAll: "readonly",
        vi: "readonly",
      },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-require-imports": "off",
      "no-empty": "off",
    },
  },
];
