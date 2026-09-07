/**
 * SuperLite plugin for OpenCode
 *
 * Registers the bundled skills directory via the config hook so no manual
 * skills.paths entry or symlinks are needed.
 *
 * Deliberately does NOT inject any bootstrap/methodology into conversations:
 * skills are available on demand and triggered by the model based on their
 * descriptions, matching the owner's "dialogue authority" principle.
 */

import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Candidates in priority order (relative to this plugin file only — the
// SuperLite folder must live inside the tool's own plugin directory):
// 1. SuperLite folder living next to this plugin (plugins/SuperLite/skills)
// 2. Skills dir relative to SuperLite's own plugin dir (SuperLite/.opencode/plugin/../../skills)
const CANDIDATES = [
  path.resolve(__dirname, 'SuperLite/skills'),
  path.resolve(__dirname, '../../skills'),
];

const skillsDir =
  CANDIDATES.find((dir) => fs.existsSync(dir)) || CANDIDATES[0];

export const SuperLitePlugin = async () => {
  if (!fs.existsSync(skillsDir)) {
    console.warn('[superlite] skills directory not found:', skillsDir);
  }

  return {
    config: async (config) => {
      config.skills = config.skills || {};
      config.skills.paths = config.skills.paths || [];
      if (!config.skills.paths.includes(skillsDir)) {
        config.skills.paths.push(skillsDir);
      }
    },
  };
};
