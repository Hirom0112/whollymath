import js from '@eslint/js';
import importPlugin from 'eslint-plugin-import';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// Flat config: @typescript-eslint/recommended + eslint-plugin-import with sorted imports
// (CLAUDE.md §6). ESLint pinned to 9.x for eslint-plugin-import compatibility.
export default tseslint.config(
  {
    // The flat-config file itself is ESM tooling, not app code; don't lint it for
    // app-level import resolution (it resolves fine at runtime via Node ESM).
    ignores: ['dist', 'coverage', 'node_modules', 'eslint.config.js'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  importPlugin.flatConfigs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    settings: {
      'import/resolver': {
        typescript: true,
        node: true,
      },
    },
    rules: {
      // Sorted imports per CLAUDE.md §6 ("Imports: sorted by eslint-plugin-import").
      'import/order': [
        'error',
        {
          alphabetize: { order: 'asc', caseInsensitive: true },
          'newlines-between': 'always',
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
        },
      ],
    },
  },
  {
    // Vitest globals (describe/it/expect) for test files.
    files: ['**/*.test.{ts,tsx}', 'src/test-setup.ts'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
);
