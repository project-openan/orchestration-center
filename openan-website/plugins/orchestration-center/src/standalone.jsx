// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { createRoot } from 'react-dom/client';
import { MockPortal } from '@openan/portal-sdk/standalone';
import OrchestrationCenter from './index.jsx';

createRoot(document.getElementById('root')).render(
    <MockPortal>
        <OrchestrationCenter />
    </MockPortal>
);
