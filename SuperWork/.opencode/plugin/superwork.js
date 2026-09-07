/**
 * SuperWork plugin for OpenCode
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
// SuperWork folder must live inside the tool's own plugin directory):
// 1. SuperWork folder living next to this plugin (plugins/SuperWork/skills)
// 2. Skills dir relative to SuperWork's own plugin dir (SuperWork/.opencode/plugin/../../skills)
const CANDIDATES = [
  path.resolve(__dirname, 'SuperWork/skills'),
  path.resolve(__dirname, '../../skills'),
];

const skillsDir =
  CANDIDATES.find((dir) => fs.existsSync(dir)) || CANDIDATES[0];

export const SuperWorkPlugin = async () => {
  if (!fs.existsSync(skillsDir)) {
    console.warn('[superwork] skills directory not found:', skillsDir);
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
