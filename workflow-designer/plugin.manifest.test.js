// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment node

import { describe, expect, it } from 'vitest';
import packageInfo from './package.json';
import manifest from './plugin.manifest.js';
import { buildManifestJson } from './vite.bundle.config.js';

describe('plugin publication contract', () => {
    it('uses the package version in source and generated manifests', () => {
        expect(manifest.version).toBe(packageInfo.version);
        expect(JSON.parse(buildManifestJson()).version).toBe(packageInfo.version);
    });
});
